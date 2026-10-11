"""
novel.character_engine — 角色人格引擎。

管理长篇小说角色的跨章节人格状态，支持：
- 基础人格档案（不变的核心特质）
- 逐章人格变化追踪
- 关系网演变
- LLM 自动分析章节内容并更新角色状态
"""

import json
from typing import Optional
from dataclasses import dataclass, field
from src.utils.llm_client import LLMClient
from src.utils.logger import logger


@dataclass
class PersonalityShift:
    """人格变化记录。"""
    trait: str           # 变化的特质名，如 "谨慎"
    old_value: int       # 旧值 0-10
    new_value: int       # 新值 0-10
    reason: str          # 变化原因


@dataclass
class ChapterEvent:
    """角色在某一章发生的事件。"""
    chapter: int
    mood: str            # 情绪状态
    key_actions: list[str] = field(default_factory=list)
    relationship_changes: list[dict] = field(default_factory=list)  # [{target, old, new, reason}]
    personality_shifts: list[PersonalityShift] = field(default_factory=list)
    skills_gained: list[str] = field(default_factory=list)
    belief_changes: list[str] = field(default_factory=list)  # 信念变化
    summary: str = ""    # 本章角色摘要


@dataclass
class CharacterProfile:
    """角色完整档案。"""
    name: str
    aliases: list[str] = field(default_factory=list)
    role: str = ""       # 主角/反派/配角/路人
    # 核心人格（相对稳定，但可以逐步变化）
    personality: dict = field(default_factory=dict)  # {特质名: 值0-10}
    speaking_style: str = ""
    core_desire: str = ""
    core_fear: str = ""
    moral_compass: dict = field(default_factory=dict)  # {诚实:7, 忠诚:9, ...}
    # 背景
    background: str = ""
    appearance: str = ""
    # 逐章事件记录
    chapter_events: list[ChapterEvent] = field(default_factory=list)
    # 全局关系网
    relationships: dict = field(default_factory=dict)  # {角色名: {状态, 强度0-10, 起始章}}
    # 弧线总结
    arc_summary: str = ""

    @property
    def current_mood(self) -> str:
        if not self.chapter_events:
            return "未知"
        return self.chapter_events[-1].mood

    @property
    def current_chapter(self) -> int:
        if not self.chapter_events:
            return 0
        return self.chapter_events[-1].chapter

    def to_dict(self) -> dict:
        return {
            "name": self.name, "aliases": self.aliases, "role": self.role,
            "personality": self.personality, "speaking_style": self.speaking_style,
            "core_desire": self.core_desire, "core_fear": self.core_fear,
            "moral_compass": self.moral_compass,
            "background": self.background, "appearance": self.appearance,
            "chapter_events": [
                {"chapter": e.chapter, "mood": e.mood, "key_actions": e.key_actions,
                 "personality_shifts": [
                     {"trait": p.trait, "old": p.old_value, "new": p.new_value, "reason": p.reason}
                     for p in e.personality_shifts
                 ],
                 "skills_gained": e.skills_gained, "belief_changes": e.belief_changes,
                 "summary": e.summary}
                for e in self.chapter_events
            ],
            "relationships": self.relationships,
            "arc_summary": self.arc_summary,
        }

    def get_status_for_chapter(self, chapter: int) -> str:
        """生成该章开始时角色状态的 prompt 文本。"""
        if not self.chapter_events:
            return f"【{self.name}】{self.role}。{self.personality_summary()}。{self.speaking_style}"

        parts = [f"【{self.name}】{self.role}"]
        parts.append(f"核心人格: {self.personality_summary()}")
        if self.speaking_style:
            parts.append(f"说话风格: {self.speaking_style}")

        # 最近 3 章事件
        recent = [e for e in self.chapter_events if e.chapter < chapter][-3:]
        if recent:
            parts.append("最近事件:")
            for e in recent:
                acts = "; ".join(e.key_actions) if e.key_actions else "无关键行动"
                mood = e.mood
                parts.append(f"  第{e.chapter}章: {acts}（情绪: {mood}）")
                if e.personality_shifts:
                    for p in e.personality_shifts:
                        parts.append(f"    → 人格变化: {p.trait} {p.old_value}→{p.new_value}（{p.reason}）")

        # 关系网摘要
        if self.relationships:
            rels = []
            for name, info in self.relationships.items():
                if isinstance(info, dict):
                    rels.append(f"{name}({info.get('状态','')} {info.get('强度',5)}/10)")
                else:
                    rels.append(f"{name}({info})")
            parts.append(f"关系: {', '.join(rels)}")

        return "\n".join(parts)

    def personality_summary(self) -> str:
        if not self.personality:
            return "未设定"
        return ", ".join(f"{k}{v}/10" for k, v in sorted(self.personality.items()))


class CharacterEngine:
    """角色人格引擎 — 管理所有角色的跨章节状态。"""

    CHARACTER_ANALYSIS_SYSTEM = """你是一位角色分析师。根据小说的一章内容，分析每个出场角色的状态变化。

对新出场角色，输出其人格设定。对已有角色，输出本章的变化。

请输出 JSON:
{
  "characters": [
    {
      "name": "角色名",
      "is_new": false,
      "personality": {"勇敢": 6, "善良": 8, "冲动": 7},  // 仅新角色需要
      "speaking_style": "寡言/多话/反问多/文绉绉/...",   // 仅新角色需要
      "mood": "当前情绪",
      "key_actions": ["本章做出的关键行动"],
      "personality_shifts": [{"trait": "善良", "old": 8, "new": 6, "reason": "目睹好友欺骗"}],
      "relationship_changes": [{"target": "李四", "old": "友好", "new": "怀疑", "reason": "看到李四与敌人交谈"}],
      "belief_changes": ["开始怀疑正义的意义"],
      "skills_gained": ["习得剑气第四重"],
      "summary": "本章角色摘要（1-2句）"
    }
  ]
}"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self._characters: dict[str, CharacterProfile] = {}

    def add_character(self, profile: CharacterProfile):
        self._characters[profile.name] = profile

    def get_character(self, name: str) -> Optional[CharacterProfile]:
        return self._characters.get(name)

    def all_characters(self) -> list[CharacterProfile]:
        return list(self._characters.values())

    def analyze_chapter(
        self, chapter_num: int, chapter_text: str, existing_names: list[str]
    ) -> list[CharacterProfile]:
        """用 LLM 分析章节内容，提取/更新角色状态。

        Returns:
            更新的角色列表
        """
        prompt = (
            f"章号: {chapter_num}\n"
            f"已有角色: {', '.join(existing_names) or '（无）'}\n\n"
            f"章节内容:\n{chapter_text[:6000]}\n\n"
            f"请分析所有出场角色的状态变化。"
        )
        if not existing_names:
            # 首次写作时角色库为空，必须显式说明——否则模型容易原样返回空数组，
            # 表现为日志里的"角色分析完成: 0 个角色更新"
            # （回归用例见 tests/test_character_engine.py）
            prompt += ("\n当前角色库为空：本章所有出场角色都按新角色输出"
                       "（is_new 置 true，并给出 personality 与 speaking_style）。")

        try:
            response = self.llm.chat(
                [{"role": "system", "content": self.CHARACTER_ANALYSIS_SYSTEM},
                 {"role": "user", "content": prompt}],
                model_tier="flash", temperature=0.3,
            )
            return self._parse_analysis(response, chapter_num)
        except Exception as e:
            logger.warning(f"角色分析失败: {e}")
            return []

    def _parse_analysis(self, response: str, chapter_num: int) -> list[CharacterProfile]:
        from src.utils.json_utils import safe_json_parse
        data = safe_json_parse(response)
        if not data:
            # 不静默：日志里的"0 个角色更新"既可能是模型没提取到角色，
            # 也可能是 JSON 格式不对——两者排查方向完全不同，必须能区分
            logger.warning(
                f"第 {chapter_num} 章角色分析结果无法解析为 JSON，本章角色未更新"
                f"（响应前 200 字: {response[:200]!r}）"
            )
            return []
        if not isinstance(data, dict):
            logger.warning(f"第 {chapter_num} 章角色分析结果不是 JSON 对象: {type(data).__name__}")
            return []

        raw_characters = data.get("characters", [])
        if not isinstance(raw_characters, list):
            logger.warning(f"第 {chapter_num} 章角色分析 characters 字段不是数组，忽略")
            return []
        if not raw_characters:
            logger.info(f"第 {chapter_num} 章角色分析：模型未返回任何角色")
            return []

        updated = []
        for char_data in raw_characters:
            name = char_data.get("name", "")
            if not name:
                continue

            if char_data.get("is_new") or name not in self._characters:
                # 新角色
                profile = CharacterProfile(
                    name=name,
                    personality=char_data.get("personality", {}),
                    speaking_style=char_data.get("speaking_style", ""),
                    role=char_data.get("role", "配角"),
                )
                self._characters[name] = profile

            profile = self._characters[name]

            # 创建本章事件
            shifts = [
                PersonalityShift(
                    trait=s.get("trait", ""),
                    old_value=s.get("old", 5),
                    new_value=s.get("new", 5),
                    reason=s.get("reason", ""),
                )
                for s in char_data.get("personality_shifts", [])
            ]

            event = ChapterEvent(
                chapter=chapter_num,
                mood=char_data.get("mood", ""),
                key_actions=char_data.get("key_actions", []),
                relationship_changes=char_data.get("relationship_changes", []),
                personality_shifts=shifts,
                skills_gained=char_data.get("skills_gained", []),
                belief_changes=char_data.get("belief_changes", []),
                summary=char_data.get("summary", ""),
            )
            profile.chapter_events.append(event)

            # 应用人格变化到当前值
            for shift in shifts:
                if shift.trait in profile.personality:
                    profile.personality[shift.trait] = shift.new_value

            # 更新关系
            for rc in char_data.get("relationship_changes", []):
                target = rc.get("target", "")
                if target:
                    profile.relationships[target] = {
                        "状态": rc.get("new", rc.get("status", "")),
                        "强度": rc.get("intensity", 5),
                        "起始章": chapter_num,
                    }

            updated.append(profile)

        return updated

    def get_context_for_writing(self, chapter_num: int) -> str:
        """生成第 N 章写作时需要的角色上下文 prompt。"""
        if not self._characters:
            return ""

        parts = ["## 角色当前状态（截止上一章）", ""]
        for name, profile in sorted(self._characters.items()):
            status = profile.get_status_for_chapter(chapter_num)
            parts.append(status)
            parts.append("")
        return "\n".join(parts)

    def save(self, path: str):
        data = {name: p.to_dict() for name, p in self._characters.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._characters = {}
        for name, cd in data.items():
            p = CharacterProfile(
                name=cd["name"], aliases=cd.get("aliases", []),
                role=cd.get("role", ""), personality=cd.get("personality", {}),
                speaking_style=cd.get("speaking_style", ""),
                core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
                moral_compass=cd.get("moral_compass", {}),
                background=cd.get("background", ""), appearance=cd.get("appearance", ""),
                relationships=cd.get("relationships", {}),
                arc_summary=cd.get("arc_summary", ""),
            )
            # 恢复逐章事件
            for ed in cd.get("chapter_events", []):
                shifts = [
                    PersonalityShift(trait=s["trait"], old_value=s["old"],
                                     new_value=s["new"], reason=s["reason"])
                    for s in ed.get("personality_shifts", [])
                ]
                event = ChapterEvent(
                    chapter=ed["chapter"], mood=ed["mood"],
                    key_actions=ed.get("key_actions", []),
                    personality_shifts=shifts,
                    skills_gained=ed.get("skills_gained", []),
                    belief_changes=ed.get("belief_changes", []),
                    summary=ed.get("summary", ""),
                )
                p.chapter_events.append(event)
            self._characters[name] = p
