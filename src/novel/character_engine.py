"""
novel.character_engine — 角色人格引擎。

管理长篇小说角色的跨章节人格状态，支持：
- 基础人格档案（不变的核心特质）
- 逐章人格变化追踪
- 关系网演变
- LLM 自动分析章节内容并更新角色状态

本轮修复（对应 CODE_REVIEW.md 的 A1-A13；A14 的回归测试见 tests/test_character_engine.py）：
- A1  分析失败不再与"没有变化"混为一谈：analyze_chapter_ex() 返回 AnalysisOutcome，
      状态区分 ok / no_change / parse_failed / llm_failed；分析调用单独放大输出预算
- A2  is_new 只当提示：是否新建以"归一化后的名字是否已存在"为准，已有档案只补空字段，
      不再整份重建（此前会清空人格、关系与全部逐章事件）
- A3  人格变化一律落地：未登记过的特质按模型给的新值写入，不再静默丢弃
- A4  relationship_changes 进 to_dict/load；load 改防御式读取（单条缺字段不再 KeyError），
      仅当整个文件损坏时抛可读的 CharacterDataError；save 改原子写，避免半截文件砖化项目
- A5  名字归一化（全角括号、括号注释、空白）后归并到已有档案，并把该写法记进 aliases
- A6  关系强度走 0-10 夹紧，起始章只在首次写入，最近一次变化的 old/reason 落盘
- A7  写作卡片无条件输出核心欲望/恐惧/道德准则/背景/外貌/别名
- A8  同章重写替换而非追加（upsert_event）
- A9  人格与强度统一走 _to_int_0_10，null/字符串/越界不再污染 prompt
- A10 role 进分析模板；已有角色只补空，不覆盖
- A11 逐章视图按章号显式排序，乱序写章不再取错
- A12 正文超限时告警并记录截断比例
- A13 角色上下文支持 focus 筛选，默认裁剪"最近未出场且非主角/反派"的角色
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from src.utils.file_utils import atomic_write_json
from src.utils.llm_client import LLMClient
from src.utils.logger import logger

# ========== 常量 ==========

# 分析调用的输出预算。历史：flash 档默认 4096 时角色一多 JSON 就被硬截断，
# 解析失败后表现为"0 个角色更新"（生产事故见 CODE_REVIEW.md A1）。
# 现在 V4 的思考也吃这份预算，16384 才够同时容纳「思考 + 角色 JSON」。
ANALYSIS_MAX_TOKENS = 16384

# 进入分析 prompt 的正文字数上限；超出会截断并告警（A12）
ANALYSIS_TEXT_LIMIT = 6000

# 计算"最近 N 章"时的窗口（A11）
RECENT_EVENT_WINDOW = 3

# 卡片里背景/外貌/说话风格这类长文本的截断长度，避免每章 prompt 被少数角色撑爆
CARD_TEXT_LIMIT = 200

# 值域（人格特质、关系强度）
SCORE_MIN, SCORE_MAX = 0, 10
SCORE_DEFAULT = 5

# get_context_for_writing 默认裁剪时始终保留的定位（A13）
ALWAYS_KEEP_ROLES = ("主角", "反派")

# AnalysisOutcome.status 的取值
STATUS_OK = "ok"
STATUS_NO_CHANGE = "no_change"
STATUS_PARSE_FAILED = "parse_failed"
STATUS_LLM_FAILED = "llm_failed"


class CharacterDataError(ValueError):
    """角色档案损坏到无法部分恢复时抛出（消息里带路径，便于定位）。"""


# ========== 值归一化（LLM 输出与手工编辑的存档都可能不规范，统一在这里兜底）==========


def _to_int_0_10(value: Any, default: int = SCORE_DEFAULT) -> int:
    """把任意值夹到 0-10 的整数。None/空串/非法值/越界一律兜底（A9）。"""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(SCORE_MIN, min(SCORE_MAX, number))


def _to_chapter(value: Any, default: int = 0) -> int:
    """把章号夹成非负整数（LLM 可能返回 "3" 或 null）。"""
    if value is None or isinstance(value, bool):
        return default
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _as_str(value: Any, default: str = "") -> str:
    """把任意值变成字符串；dict/list 走 JSON，避免 prompt 里出现裸对象。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _as_dict(value: Any) -> dict:
    """把 dict 或"JSON 字符串形式的 dict"统一成 dict，其余返回空字典。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list:
    """把 None/标量/list 统一成 list。"""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_str_list(value: Any) -> list[str]:
    """把任意值变成"去掉空项"的字符串列表。"""
    texts = []
    for item in _as_list(value):
        text = _as_str(item).strip()
        if text:
            texts.append(text)
    return texts


def _clip(text: str, limit: int = CARD_TEXT_LIMIT) -> str:
    """单行化并截断长文本（进 prompt 用）。"""
    flat = re.sub(r"\s+", " ", _as_str(text)).strip()
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _normalize_name(name: str) -> str:
    """归一化角色名，用于把同一角色的不同写法归并到一起（A5）。

    "父亲(神秘人)" / "父亲（神秘人）" → "父亲"
    "林雪（林辰妹妹）" → "林雪"；括号注释被去掉后不足 2 字则保留原名。
    """
    text = _as_str(name).strip()
    if not text:
        return ""
    for src, dst in (("（", "("), ("）", ")"), ("【", "("), ("】", ")")):
        text = text.replace(src, dst)
    text = re.sub(r"\s+", "", text)
    stripped = re.sub(r"\([^()]*\)$", "", text).strip()
    return stripped if len(stripped) >= 2 else text


def _normalize_relationship(info: Any) -> dict:
    """把关系表项统一成 {状态, 强度, 起始章[, 最近变化]}，并**原样保留未知键**。

    未知键必须带走：真实存档里的遗留键 `描述` 以前会在 load→save 时被静默丢掉
    （50 章项目里 8 条，见 tests/test_roundtrip_baseline.py 的往返基线）。
    """
    if isinstance(info, str):
        return {"状态": info, "强度": SCORE_DEFAULT, "起始章": 0}
    if not isinstance(info, dict):
        return {"状态": "", "强度": SCORE_DEFAULT, "起始章": 0}
    entry = dict(info)  # 先原样收下，再覆盖需要规范化的已知键
    entry["状态"] = _as_str(info.get("状态", info.get("status")))
    entry["强度"] = _to_int_0_10(info.get("强度", info.get("intensity")))
    entry["起始章"] = _to_chapter(info.get("起始章", info.get("start_chapter")))
    latest = info.get("最近变化")
    if isinstance(latest, dict):
        entry["最近变化"] = dict(latest)
    return entry


# ========== 数据模型 ==========


class PersistedModel(BaseModel):
    """落盘模型的共同配置（P1-2：类型声明的校验交给 pydantic）。

    两条刻意的选择：

    - ``extra="allow"``，而不是 pydantic 默认的 ``"ignore"``。默认值会把档案里
      我们不认识的键**静默丢掉** —— 那正是 `_normalize_relationship` 刚修掉的
      "描述 消失" 同一类问题。允许额外键后，`to_dict` 再把它们并回去，
      手工编辑过或更新版本写出的字段就不会丢。
    - **不开** ``validate_assignment``。引擎会在原地改字段和容器
      （`profile.personality[t] = v`、`upsert_event` 里下标赋值 + sort），
      开了赋值校验会让这些既有路径直接报错。
    """

    model_config = ConfigDict(extra="allow", validate_assignment=False)


def _with_extras(model: BaseModel, data: dict) -> dict:
    """把 pydantic 收下的「额外键」并回序列化结果，保证落盘不丢字段。"""
    for key, value in (getattr(model, "__pydantic_extra__", None) or {}).items():
        data.setdefault(key, value)
    return data


class PersonalityShift(PersistedModel):
    """人格变化记录。"""

    trait: str = ""  # 变化的特质名，如 "谨慎"
    old_value: int = 0  # 旧值 0-10
    new_value: int = 0  # 新值 0-10
    reason: str = ""  # 变化原因

    # 直接构造（LLM 输出路径）与 from_dict 走同一套兜底：null/字符串/越界都夹到 0-10（A9）
    @field_validator("trait", "reason", mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _as_str(value)

    @field_validator("old_value", "new_value", mode="before")
    @classmethod
    def _coerce_score(cls, value: Any) -> int:
        return _to_int_0_10(value)

    def to_dict(self) -> dict:
        return _with_extras(
            self,
            {
                "trait": self.trait,
                "old": self.old_value,
                "new": self.new_value,
                "reason": self.reason,
            },
        )

    @classmethod
    def from_dict(cls, data: Any) -> "PersonalityShift":
        """防御式读取：缺字段/null/越界一律兜底（A4/A9）；未知键原样带走。"""
        raw = data if isinstance(data, dict) else {}
        extra = {key: value for key, value in raw.items() if key not in cls.model_fields}
        return cls(
            trait=_as_str(raw.get("trait")).strip(),
            old_value=_to_int_0_10(raw.get("old")),
            new_value=_to_int_0_10(raw.get("new")),
            reason=_as_str(raw.get("reason")),
            **extra,
        )


class ChapterEvent(PersistedModel):
    """角色在某一章发生的事件。"""

    chapter: int = 0
    mood: str = ""  # 情绪状态
    key_actions: list[str] = []
    # ⚠️ 保持「纯 dict 列表」：to_dict 与写作卡片都用 isinstance(rc, dict) 判定，
    # 换成嵌套模型会让关系变化在落盘时被静默丢掉（A4 事故的翻版）
    relationship_changes: list[dict] = []
    personality_shifts: list["PersonalityShift"] = []
    skills_gained: list[str] = []
    belief_changes: list[str] = []  # 信念变化
    summary: str = ""  # 本章角色摘要

    @field_validator("chapter", mode="before")
    @classmethod
    def _coerce_chapter(cls, value: Any) -> int:
        return _to_chapter(value)

    @field_validator("mood", "summary", mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _as_str(value)

    @field_validator("key_actions", "skills_gained", "belief_changes", mode="before")
    @classmethod
    def _coerce_str_list(cls, value: Any) -> list[str]:
        return _as_str_list(value)

    @field_validator("relationship_changes", mode="before")
    @classmethod
    def _keep_only_dict_changes(cls, value: Any) -> list[dict]:
        return [rc for rc in _as_list(value) if isinstance(rc, dict)]

    def to_dict(self) -> dict:
        """序列化。A4：relationship_changes 此前被漏掉，导致落盘即丢。"""
        return _with_extras(
            self,
            {
                "chapter": self.chapter,
                "mood": self.mood,
                "key_actions": list(self.key_actions),
                "relationship_changes": [
                    dict(rc) for rc in self.relationship_changes if isinstance(rc, dict)
                ],
                "personality_shifts": [shift.to_dict() for shift in self.personality_shifts],
                "skills_gained": list(self.skills_gained),
                "belief_changes": list(self.belief_changes),
                "summary": self.summary,
            },
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ChapterEvent":
        """防御式读取：手工编辑过的存档缺 mood/chapter 也不再让项目打不开（A4）。"""
        raw = data if isinstance(data, dict) else {}
        extra = {key: value for key, value in raw.items() if key not in cls.model_fields}
        return cls(
            chapter=_to_chapter(raw.get("chapter")),
            mood=_as_str(raw.get("mood")),
            key_actions=_as_str_list(raw.get("key_actions")),
            relationship_changes=[
                rc for rc in _as_list(raw.get("relationship_changes")) if isinstance(rc, dict)
            ],
            personality_shifts=[
                PersonalityShift.from_dict(s) for s in _as_list(raw.get("personality_shifts"))
            ],
            skills_gained=_as_str_list(raw.get("skills_gained")),
            belief_changes=_as_str_list(raw.get("belief_changes")),
            summary=_as_str(raw.get("summary")),
            **extra,
        )


class CharacterProfile(PersistedModel):
    """角色完整档案。"""

    name: str = ""
    aliases: list[str] = []
    role: str = ""  # 主角/反派/配角/路人
    # 核心人格（相对稳定，但可以逐步变化）
    # ⚠️ 保持无参 dict：存量档案里有 {"善良": None} 这类值，读取时由
    # personality_summary()/_to_int_0_10 兜底；收紧成 dict[str, int] 会让老存档直接打不开
    personality: dict = {}  # {特质名: 值0-10}
    speaking_style: str = ""
    core_desire: str = ""
    core_fear: str = ""
    moral_compass: dict = {}  # {诚实:7, 忠诚:9, ...}
    # 背景
    background: str = ""
    appearance: str = ""
    # 逐章事件记录
    chapter_events: list[ChapterEvent] = []
    # 全局关系网（值可能是 dict，也可能是历史遗留的字符串描述）
    relationships: dict = {}  # {角色名: {状态, 强度0-10, 起始章}}
    # 弧线总结
    arc_summary: str = ""

    @field_validator(
        "name",
        "role",
        "speaking_style",
        "core_desire",
        "core_fear",
        "background",
        "appearance",
        "arc_summary",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _as_str(value).strip() if value is not None else ""

    @field_validator("aliases", mode="before")
    @classmethod
    def _coerce_aliases(cls, value: Any) -> list[str]:
        return _as_str_list(value)

    @field_validator("personality", "moral_compass", mode="before")
    @classmethod
    def _coerce_mapping(cls, value: Any) -> dict:
        return _as_dict(value)

    @field_validator("relationships", mode="before")
    @classmethod
    def _normalize_relationships(cls, value: Any) -> dict:
        """关系表统一走 _normalize_relationship（字符串→dict、未知键原样带走）。"""
        out: dict = {}
        for target, info in _as_dict(value).items():
            target = _as_str(target).strip()
            if target:
                out[target] = _normalize_relationship(info)
        return out

    # ---- 逐章视图（一律按章号排序，A11）----

    def sorted_events(self) -> list[ChapterEvent]:
        """按章号升序返回逐章事件。乱序写章时不再依赖数组顺序。"""
        return sorted(self.chapter_events, key=lambda event: event.chapter)

    def upsert_event(self, event: ChapterEvent) -> None:
        """写入一章事件：同章替换、异章追加，并保持按章号有序（A8 + A11）。"""
        for index, existing in enumerate(self.chapter_events):
            if existing.chapter == event.chapter:
                self.chapter_events[index] = event
                break
        else:
            self.chapter_events.append(event)
        self.chapter_events.sort(key=lambda item: item.chapter)

    def recent_events(
        self, before_chapter: int, window: int = RECENT_EVENT_WINDOW
    ) -> list[ChapterEvent]:
        """第 before_chapter 章之前、最近 window 章的事件（A11）。"""
        events = [e for e in self.sorted_events() if e.chapter < before_chapter]
        return events[-window:] if window > 0 else events

    def appeared_within(self, chapter_num: int, window: int = RECENT_EVENT_WINDOW) -> bool:
        """是否在"即将写作的这一章之前 window 章内"出场过（A13 筛选用）。

        与 recent_events 的区别：recent_events 取"最后 N 条事件"（展示用），
        这里按章号区间判断"最近是否出场"——第 1 章出场过一次的角色，写到第 20 章
        时应当视为长期未出场。
        """
        if window <= 0:
            return bool(self.chapter_events)
        lower = chapter_num - window
        return any(lower <= event.chapter < chapter_num for event in self.chapter_events)

    @property
    def current_mood(self) -> str:
        events = self.sorted_events()
        return events[-1].mood if events else "未知"

    @property
    def current_chapter(self) -> int:
        events = self.sorted_events()
        return events[-1].chapter if events else 0

    def personality_summary(self) -> str:
        if not self.personality:
            return "未设定"
        return ", ".join(
            f"{trait}{_to_int_0_10(value)}/10" for trait, value in sorted(self.personality.items())
        )

    # ---- 序列化（A4）----

    def to_dict(self) -> dict:
        return _with_extras(
            self,
            {
                "name": self.name,
                "aliases": list(self.aliases),
                "role": self.role,
                "personality": dict(self.personality),
                "speaking_style": self.speaking_style,
                "core_desire": self.core_desire,
                "core_fear": self.core_fear,
                "moral_compass": dict(self.moral_compass),
                "background": self.background,
                "appearance": self.appearance,
                # 落盘时按章号排序，顺带把旧档案里乱序的事件规范化
                "chapter_events": [event.to_dict() for event in self.sorted_events()],
                "relationships": dict(self.relationships),
                "arc_summary": self.arc_summary,
            },
        )

    @classmethod
    def from_dict(cls, data: Any, fallback_name: str = "") -> "CharacterProfile":
        """防御式反序列化：任何缺字段/类型异常都用默认值兜底（A4）；未知键原样带走。"""
        raw = data if isinstance(data, dict) else {}
        extra = {key: value for key, value in raw.items() if key not in cls.model_fields}
        profile = cls(
            name=_as_str(raw.get("name"), fallback_name).strip() or fallback_name,
            aliases=_as_str_list(raw.get("aliases")),
            role=_as_str(raw.get("role")),
            speaking_style=_as_str(raw.get("speaking_style")),
            core_desire=_as_str(raw.get("core_desire")),
            core_fear=_as_str(raw.get("core_fear")),
            background=_as_str(raw.get("background")),
            appearance=_as_str(raw.get("appearance")),
            arc_summary=_as_str(raw.get("arc_summary")),
            **extra,
        )
        for trait, value in _as_dict(raw.get("personality")).items():
            trait = _as_str(trait).strip()
            if trait:
                profile.personality[trait] = _to_int_0_10(value)
        for trait, value in _as_dict(raw.get("moral_compass")).items():
            trait = _as_str(trait).strip()
            if trait:
                profile.moral_compass[trait] = _to_int_0_10(value)
        for target, info in _as_dict(raw.get("relationships")).items():
            target = _as_str(target).strip()
            if target:
                profile.relationships[target] = _normalize_relationship(info)
        profile.chapter_events = []
        for event in (ChapterEvent.from_dict(item) for item in _as_list(raw.get("chapter_events"))):
            # 用 upsert 而不是直接赋值：既按章号排序，又顺手修掉旧档案里
            # 已经存在的重复章号（A8 的修复只覆盖新写入，存量数据靠这里规范化）
            profile.upsert_event(event)
        return profile

    def fill_missing(self, data: dict) -> list[str]:
        """只补充空字段，绝不覆盖已有内容（A2/A10：演进不重建）。

        分析模型给出的东西是"本章观察"，不能用来推翻档案里已有的长期设定；
        但它可以补上此前没有的记录。

        Returns:
            实际被补充的字段名列表（日志/测试用）
        """
        filled: list[str] = []
        for key in (
            "role",
            "speaking_style",
            "core_desire",
            "core_fear",
            "background",
            "appearance",
            "arc_summary",
        ):
            value = _as_str(data.get(key)).strip()
            if value and not getattr(self, key):
                setattr(self, key, value)
                filled.append(key)

        for trait, value in _as_dict(data.get("personality")).items():
            trait = _as_str(trait).strip()
            if trait and trait not in self.personality:
                self.personality[trait] = _to_int_0_10(value)
                filled.append(f"personality.{trait}")

        for alias in _as_str_list(data.get("aliases")):
            if alias != self.name and alias not in self.aliases:
                self.aliases.append(alias)
                filled.append(f"aliases.{alias}")
        return filled

    # ---- 写作用角色卡片（A7）----

    def get_status_for_chapter(self, chapter: int) -> str:
        """生成该章开始时角色状态的 prompt 文本。

        A7：核心欲望/恐惧/道德准则/背景/外貌/别名这些一致性锚点此前只要角色
        有过章节事件就全部不输出，这里改为无条件输出。
        """
        parts = [f"【{self.name}】{self.role or '未定位'}"]
        if self.aliases:
            parts.append(f"别名: {', '.join(self.aliases)}")
        parts.append(f"核心人格: {self.personality_summary()}")
        if self.speaking_style:
            parts.append(f"说话风格: {_clip(self.speaking_style, 120)}")
        if self.core_desire:
            parts.append(f"核心欲望: {_clip(self.core_desire, 120)}")
        if self.core_fear:
            parts.append(f"核心恐惧: {_clip(self.core_fear, 120)}")
        if self.moral_compass:
            parts.append(
                "道德准则: "
                + ", ".join(
                    f"{trait}{_to_int_0_10(value)}/10"
                    for trait, value in sorted(self.moral_compass.items())
                )
            )
        if self.background:
            parts.append(f"背景: {_clip(self.background)}")
        if self.appearance:
            parts.append(f"外貌: {_clip(self.appearance)}")

        recent = self.recent_events(chapter)
        if recent:
            parts.append(f"最近{len(recent)}章事件:")
            for event in recent:
                actions = "; ".join(event.key_actions) if event.key_actions else "无关键行动"
                parts.append(f"  第{event.chapter}章: {actions}（情绪: {event.mood or '未记录'}）")
                for shift in event.personality_shifts:
                    parts.append(
                        f"    → 人格变化: {shift.trait} "
                        f"{shift.old_value}→{shift.new_value}（{shift.reason}）"
                    )
                for change in event.relationship_changes:
                    target = _as_str(change.get("target")).strip()
                    if target:
                        parts.append(
                            f"    → 关系变化: {target} "
                            f"{_as_str(change.get('old')) or '?'}→"
                            f"{_as_str(change.get('new')) or '?'}"
                        )

        if self.relationships:
            relations = []
            for target, info in self.relationships.items():
                if isinstance(info, dict):
                    relations.append(
                        f"{target}({info.get('状态', '')} {_to_int_0_10(info.get('强度'))}/10)"
                    )
                else:
                    relations.append(f"{target}({info})")
            parts.append(f"关系: {', '.join(relations)}")

        return "\n".join(parts)


@dataclass
class AnalysisOutcome:
    """一次写后角色分析的结果（A1：让"失败"与"没有变化"可区分）。"""

    status: str = STATUS_OK
    updated: list[CharacterProfile] = field(default_factory=list)
    created: list[str] = field(default_factory=list)  # 本次新建档案的角色
    merged: list[tuple[str, str]] = field(default_factory=list)  # [(模型给的名字, 归并到的角色)]
    detail: str = ""
    truncated: bool = False  # 正文是否被截断后分析

    @property
    def ok(self) -> bool:
        """分析成功且模型确实报告了角色。"""
        return self.status == STATUS_OK

    @property
    def failed(self) -> bool:
        """基础设施或解析失败——此时项目里的角色状态没有被更新。"""
        return self.status in (STATUS_PARSE_FAILED, STATUS_LLM_FAILED)

    @property
    def has_change(self) -> bool:
        return bool(self.updated)


class CharacterEngine:
    """角色人格引擎 — 管理所有角色的跨章节状态。"""

    CHARACTER_ANALYSIS_SYSTEM = """你是一位角色分析师。根据小说的一章内容，分析每个出场角色的状态变化。

对新出场角色，输出其人格设定。对已有角色，只输出本章**确实发生了变化**的部分。

请输出 JSON:
{
  "characters": [
    {
      "name": "角色名（用正文里的原始写法）",
      "is_new": false,
      "role": "主角/反派/配角/路人（仅新角色需要）",
      "personality": {"勇敢": 6, "善良": 8},
      "speaking_style": "寡言/多话/反问多/文绉绉/...",
      "mood": "当前情绪",
      "key_actions": ["本章做出的关键行动"],
      "personality_shifts": [{"trait": "善良", "old": 8, "new": 6, "reason": "目睹好友欺骗"}],
      "relationship_changes": [{"target": "李四", "old": "友好", "new": "怀疑", "reason": "看到李四与敌人交谈", "intensity": 7}],
      "belief_changes": ["开始怀疑正义的意义"],
      "skills_gained": ["习得剑气第四重"],
      "summary": "本章角色摘要（1-2句）"
    }
  ]
}

要求：
- personality 的值、intensity 一律用 0-10 的整数，不要用文字描述。
- personality_shifts 只写本章真正改变的特质；没有变化就不要编造。
- relationship_changes 必须给出 intensity（这段关系的亲疏/信任强度，0-10）。
- 只分析本章正文里确实出场的角色。"""

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()
        self._characters: dict[str, CharacterProfile] = {}

    # ---- 基本操作 ----

    def add_character(self, profile: CharacterProfile):
        self._characters[profile.name] = profile

    def get_character(self, name: str) -> CharacterProfile | None:
        """按名字取角色；名字写法不同但归并到同一角色时同样能取到（A5）。"""
        resolved = self._resolve_existing_name(name)
        return self._characters.get(resolved) if resolved else None

    def all_characters(self) -> list[CharacterProfile]:
        return list(self._characters.values())

    def _resolve_existing_name(self, name: str) -> str | None:
        """把一个名字解析到引擎里已有的角色键（A5 归并）。

        依次尝试：精确匹配 → 别名表 → 归一化名字（去括号注释/全角括号/空白）。
        """
        raw = _as_str(name).strip()
        if not raw or not self._characters:
            return None
        if raw in self._characters:
            return raw
        normalized = _normalize_name(raw)
        for canonical, profile in self._characters.items():
            if raw in profile.aliases:
                return canonical
            if any(_normalize_name(alias) == normalized for alias in profile.aliases):
                return canonical
        for canonical in self._characters:
            if _normalize_name(canonical) == normalized:
                return canonical
        return None

    # ---- 写后分析 ----

    def analyze_chapter(
        self,
        chapter_num: int,
        chapter_text: str,
        existing_names: Iterable[str] | None = None,
        model_tier: str = "flash",
        max_tokens: int = ANALYSIS_MAX_TOKENS,
    ) -> list[CharacterProfile]:
        """用 LLM 分析章节内容，提取/更新角色状态。

        兼容旧接口：失败与"没有变化"都返回空列表。需要区分失败原因请用
        analyze_chapter_ex()。

        Returns:
            本章被更新的角色列表
        """
        return self.analyze_chapter_ex(
            chapter_num,
            chapter_text,
            existing_names,
            model_tier=model_tier,
            max_tokens=max_tokens,
        ).updated

    def analyze_chapter_ex(
        self,
        chapter_num: int,
        chapter_text: str,
        existing_names: Iterable[str] | None = None,
        model_tier: str = "flash",
        max_tokens: int = ANALYSIS_MAX_TOKENS,
    ) -> AnalysisOutcome:
        """分析一章并更新角色状态；失败原因可区分，不再"静默 0 个更新"（A1）。

        Args:
            chapter_num: 章号
            chapter_text: 本章正文
            existing_names: 已知角色名（与引擎内部状态取并集后提示模型）
            model_tier: 模型档位，默认 flash
            max_tokens: 输出预算，默认 ANALYSIS_MAX_TOKENS
        """
        text = _as_str(chapter_text)
        truncated = len(text) > ANALYSIS_TEXT_LIMIT
        if truncated:
            logger.warning(
                f"第{chapter_num}章正文 {len(text)} 字，超过角色分析上限 "
                f"{ANALYSIS_TEXT_LIMIT} 字，仅前 {ANALYSIS_TEXT_LIMIT} 字参与分析"
                f"（截断 {1 - ANALYSIS_TEXT_LIMIT / max(len(text), 1):.0%}）"
            )

        known = set(self._characters)
        known.update(_as_str_list(list(existing_names or [])))
        prompt = (
            f"章号: {chapter_num}\n"
            f"已有角色: {', '.join(sorted(known)) or '（无）'}\n\n"
            f"章节内容:\n{text[:ANALYSIS_TEXT_LIMIT]}\n\n"
            f"请分析所有出场角色的状态变化。"
        )
        if not known:
            # 首次写作时角色库为空：system prompt 要求"已有角色只输出确实变化的部分"，
            # 不显式引导时模型容易返回空数组（表现为写第一章"0 个角色更新"）
            prompt += (
                "\n当前角色库为空：本章所有出场角色都按新角色输出"
                "（is_new 置 true，并给出 personality 与 speaking_style）。"
            )

        try:
            response = self.llm.chat(
                [
                    {"role": "system", "content": self.CHARACTER_ANALYSIS_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                model_tier=model_tier,
                temperature=0.3,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            logger.error(f"第{chapter_num}章角色分析调用失败，角色状态未更新: {detail}")
            return AnalysisOutcome(status=STATUS_LLM_FAILED, detail=detail, truncated=truncated)

        outcome = self._parse_analysis(response, chapter_num)
        outcome.truncated = truncated

        if outcome.status == STATUS_PARSE_FAILED:
            logger.error(
                f"第{chapter_num}章角色分析返回无法解析，角色状态未更新: {outcome.detail}"
                f"（模型返回 {len(_as_str(response))} 字）"
            )
        elif outcome.created:
            logger.info(f"第{chapter_num}章角色分析新建档案: {', '.join(outcome.created)}")
        if outcome.merged:
            logger.info(
                f"第{chapter_num}章角色分析归并了同一角色的不同写法: "
                + ", ".join(f"{alias}→{canonical}" for alias, canonical in outcome.merged)
            )
        return outcome

    def _parse_analysis(self, response: str, chapter_num: int) -> AnalysisOutcome:
        from src.utils.json_utils import safe_json_parse

        data = safe_json_parse(_as_str(response))
        if not isinstance(data, dict):
            return AnalysisOutcome(
                status=STATUS_PARSE_FAILED,
                detail="模型返回不是可解析的 JSON 对象（常见原因：输出被 max_tokens 截断）",
            )
        return self._apply_analysis(data, chapter_num)

    def _apply_analysis(self, data: dict, chapter_num: int) -> AnalysisOutcome:
        """把模型返回的 JSON 落成状态更新（A2/A3/A5/A6/A8/A9/A10/A11）。"""
        raw_characters = _as_list(data.get("characters"))
        if not raw_characters:
            return AnalysisOutcome(status=STATUS_NO_CHANGE, detail="模型未报告任何角色")

        outcome = AnalysisOutcome(status=STATUS_OK)
        seen: set[str] = set()
        for char_data in raw_characters:
            if not isinstance(char_data, dict):
                continue
            name = _as_str(char_data.get("name")).strip()
            if not name:
                continue

            existing = self._resolve_existing_name(name)
            if existing is None:
                # 未登记的名字才建档；模型的 is_new 只当提示（A2）
                profile = CharacterProfile(name=name)
                profile.fill_missing(char_data)
                self._characters[profile.name] = profile
                outcome.created.append(profile.name)
            else:
                # 已有档案只补空字段，绝不重建（此前 is_new=true 会清空全部历史）
                profile = self._characters[existing]
                if existing != name:
                    outcome.merged.append((name, existing))
                    if name not in profile.aliases:
                        profile.aliases.append(name)  # 记住这次的写法，下次直接命中
                profile.fill_missing(char_data)

            if not profile.role:
                profile.role = "配角"  # 定位缺失时的兜底（A10）

            self._append_event(profile, char_data, chapter_num)
            if profile.name not in seen:
                seen.add(profile.name)
                outcome.updated.append(profile)
        if not outcome.updated:
            return AnalysisOutcome(
                status=STATUS_NO_CHANGE,
                detail="模型报告的条目都没有可用的角色名",
            )
        return outcome

    def _append_event(self, profile: CharacterProfile, char_data: dict, chapter_num: int) -> None:
        """把本章分析落成事件，并更新人格与关系网。"""
        shifts: list[PersonalityShift] = []
        for raw in _as_list(char_data.get("personality_shifts")):
            if not isinstance(raw, dict):
                continue
            trait = _as_str(raw.get("trait")).strip()
            if not trait:
                continue
            current = (
                _to_int_0_10(profile.personality[trait]) if trait in profile.personality else None
            )
            shifts.append(
                PersonalityShift(
                    trait=trait,
                    # 模型给的 old 没有可信来源（分析 prompt 不含角色当前数值），
                    # 本地有这个特质时以本地状态为准
                    old_value=current if current is not None else _to_int_0_10(raw.get("old")),
                    new_value=_to_int_0_10(
                        raw.get("new"), default=current if current is not None else SCORE_DEFAULT
                    ),
                    reason=_as_str(raw.get("reason")),
                )
            )

        relationship_changes = [
            rc for rc in _as_list(char_data.get("relationship_changes")) if isinstance(rc, dict)
        ]

        event = ChapterEvent(
            chapter=chapter_num,
            mood=_as_str(char_data.get("mood")),
            key_actions=_as_str_list(char_data.get("key_actions")),
            relationship_changes=relationship_changes,
            personality_shifts=shifts,
            skills_gained=_as_str_list(char_data.get("skills_gained")),
            belief_changes=_as_str_list(char_data.get("belief_changes")),
            summary=_as_str(char_data.get("summary")),
        )
        profile.upsert_event(event)  # A8：同章替换；A11：按章号有序

        for shift in shifts:
            # A3：未登记过的特质也要落地，否则"人格演变"只存在于事件日志里
            profile.personality[shift.trait] = shift.new_value

        for change in relationship_changes:
            self._apply_relationship_change(profile, change, chapter_num)

    @staticmethod
    def _apply_relationship_change(
        profile: CharacterProfile, change: dict, chapter_num: int
    ) -> None:
        """更新关系网（A6：强度夹紧、起始章只在首次写入、最近变化落盘）。"""
        target = _as_str(change.get("target")).strip()
        if not target:
            return
        entry = profile.relationships.get(target)
        entry = dict(entry) if isinstance(entry, dict) else {}

        new_status = _as_str(change.get("new")).strip() or _as_str(change.get("status")).strip()
        if new_status or not entry.get("状态"):
            entry["状态"] = new_status or entry.get("状态", "")
        entry["强度"] = _to_int_0_10(
            change.get("intensity", change.get("强度")),
            default=_to_int_0_10(entry.get("强度")),
        )
        entry.setdefault("起始章", chapter_num)  # A6：不再每章被覆盖
        entry["最近变化"] = {
            "chapter": chapter_num,
            "from": _as_str(change.get("old")),
            "to": new_status,
            "reason": _as_str(change.get("reason")),
        }
        profile.relationships[target] = entry

    # ---- 写作上下文 ----

    def get_context_for_writing(
        self,
        chapter_num: int,
        focus: Iterable[str] | None = None,
        include_all: bool = False,
    ) -> str:
        """生成第 N 章写作时需要的角色上下文 prompt。

        Args:
            chapter_num: 即将写作的章号
            focus: 本章确定出场的角色名（可传剧情设计里的 character_appearances）
            include_all: True 时输出全部角色（修复前的行为，用于对照/回退）
        """
        if not self._characters:
            return ""

        parts = ["## 角色当前状态（截止上一章）", ""]
        for profile in self._select_for_context(chapter_num, focus, include_all):
            parts.append(profile.get_status_for_chapter(chapter_num))
            parts.append("")
        return "\n".join(parts)

    def _select_for_context(
        self, chapter_num: int, focus: Iterable[str] | None, include_all: bool
    ) -> list[CharacterProfile]:
        """挑选要进写作 prompt 的角色（A13）。

        保留：focus 中指定的、主角/反派、最近几章有事件的、以及还没有任何事件的
        新角色；被裁掉的是"有历史但最近没戏、也不是主角/反派"的角色。
        """
        if include_all:
            return [self._characters[name] for name in sorted(self._characters)]

        wanted = {_normalize_name(name) for name in _as_str_list(list(focus or []))}
        selected: list[CharacterProfile] = []
        for name in sorted(self._characters):
            profile = self._characters[name]
            role = profile.role or ""
            if any(key in role for key in ALWAYS_KEEP_ROLES):
                selected.append(profile)
                continue
            if _normalize_name(name) in wanted or any(
                _normalize_name(alias) in wanted for alias in profile.aliases
            ):
                selected.append(profile)
                continue
            if not profile.chapter_events:
                selected.append(profile)  # 还没上过场，第一次出场必须有上下文
                continue
            if profile.appeared_within(chapter_num, window=RECENT_EVENT_WINDOW):
                selected.append(profile)
                continue
        # 兜底：宁可全给，也不要一个字都不给
        return selected or [self._characters[name] for name in sorted(self._characters)]

    # ---- 持久化（A4）----

    def save(self, path: str) -> None:
        """原子写：先写同目录临时文件再 os.replace，避免半截 JSON 砖化项目。

        save 在每写完一章都会被调用，因此这里不做备份（覆盖前备份是服务层的职责，
        见 src/novel/service.py 的 generate_characters）。
        """
        atomic_write_json(
            path, {name: profile.to_dict() for name, profile in self._characters.items()}
        )

    def load(self, path: str) -> None:
        """读取角色档案（A4）。

        单条记录缺字段会用默认值兜底，不再让整个项目打不开；只有整个文件读不了或
        顶层结构不对时才抛带路径的 CharacterDataError。
        """
        target = Path(path)
        try:
            raw_text = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise CharacterDataError(f"角色档案读取失败：{target}（{exc}）") from exc

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise CharacterDataError(
                f"角色档案不是合法 JSON：{target}（第 {exc.lineno} 行）。"
                f"若为半截文件，可尝试用同目录的 characters.json.bak-* 恢复。"
            ) from exc
        if not isinstance(data, dict):
            raise CharacterDataError(f"角色档案顶层应为「角色名 → 档案」的对象：{target}")

        loaded: dict[str, CharacterProfile] = {}
        for key, char_data in data.items():
            if not isinstance(char_data, dict):
                logger.warning(f"角色档案跳过非法记录 [{key}]（应为对象）: {target}")
                continue
            profile = CharacterProfile.from_dict(char_data, fallback_name=_as_str(key))
            if not profile.name:
                logger.warning(f"角色档案跳过无名记录: {target}")
                continue
            loaded[profile.name] = profile
        self._characters = loaded
