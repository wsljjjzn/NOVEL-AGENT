"""
review_engine.context — 小说审稿用的「作品状态」摘要。

审稿 Agent 只看得到给它的正文，无法知道第 3 章埋了什么伏笔、林雪当前人格值是多少。
本模块把确定性的领域状态（角色档案 / 开放伏笔 / 世界观 / 前情 / 本章大纲）压成一段
文本，注入审稿 user 消息，供一致性维度核对。

设计约束：
- **不做业务判断**，只做格式化；不依赖 LLM（可安全用于离线）。
- 对传入对象做鸭子类型 + 容错调用，缺字段/类型异常一律降级为空，绝不因状态不全而让审稿崩。
- 主动限长，避免状态撑爆审稿 prompt。
"""

import json
from typing import Any, Optional

_MAX_CHARACTERS = 20
_MAX_FORESHADOWS = 15
_MAX_FIELD_CHARS = 200
_MAX_CONTEXT_CHARS = 8000


def _plain(value: Any, limit: int = _MAX_FIELD_CHARS) -> str:
    """把任意字段压成单行短文本。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            value = str(value)
    value = value.strip().replace("\n", " ").replace("\r", " ")
    value = " ".join(value.split())
    return value[:limit] + ("…" if len(value) > limit else "")


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """安全取属性；属性是方法则调用（用于 personality_summary 这类）。"""
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    if callable(value):
        try:
            return value()
        except Exception:
            return default
    return value


def _join_list(values: Any, limit: int = _MAX_FORESHADOWS) -> str:
    if not values:
        return ""
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    items = [_plain(v, 60) for v in values if _plain(v, 60)]
    return "；".join(items[:limit])


def _format_relationships(relationships: Any) -> str:
    if not isinstance(relationships, dict) or not relationships:
        return ""
    parts = []
    for target, info in list(relationships.items())[:12]:
        target = _plain(target, 30)
        if not target:
            continue
        if isinstance(info, dict):
            strength = info.get("强度") or info.get("strength")
            state = info.get("状态") or info.get("state") or info.get("描述")
            bits = []
            if strength not in (None, ""):
                bits.append(f"强度{strength}")
            if state:
                bits.append(_plain(state, 40))
            parts.append(f"{target}({'，'.join(bits)})" if bits else target)
        else:
            parts.append(f"{target}({_plain(info, 40)})")
    return "；".join(parts)


def _format_characters(engine: Any, chapter_num: Optional[int]) -> str:
    if engine is None:
        return ""
    try:
        characters = list(engine.all_characters())
    except Exception:
        return ""
    if not characters:
        return ""

    # 主角/反派优先，确保关键角色不被截断
    role_rank = {"主角": 0, "反派": 1}
    characters.sort(key=lambda c: role_rank.get(_attr(c, "role", "") or "", 2))
    characters = characters[:_MAX_CHARACTERS]

    blocks = ["## 角色档案"]
    for c in characters:
        name = _plain(_attr(c, "name", ""), 40)
        if not name:
            continue
        role = _plain(_attr(c, "role", ""), 20)
        lines = [f"### {name}" + (f"（{role}）" if role else "")]
        personality = _plain(_attr(c, "personality_summary", ""), 120)
        if personality:
            lines.append(f"- 人格：{personality}")
        for label, attr in (("核心欲望", "core_desire"), ("核心恐惧", "core_fear"),
                            ("说话风格", "speaking_style")):
            value = _plain(_attr(c, attr, ""), 80)
            if value:
                lines.append(f"- {label}：{value}")
        rels = _format_relationships(_attr(c, "relationships", {}))
        if rels:
            lines.append(f"- 关系：{rels}")
        # 最近事件（写作/审稿前的情报）
        try:
            events = c.sorted_events()
            if chapter_num:
                events = [e for e in events if getattr(e, "chapter", 0) < int(chapter_num)]
            events = events[-2:]
            for e in events:
                mood = _plain(_attr(e, "mood", ""), 20)
                summary = _plain(_attr(e, "summary", ""), 60)
                if mood or summary:
                    lines.append(f"- 第{getattr(e, 'chapter', '?')}章：{mood} {summary}".rstrip())
        except Exception:
            pass
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _format_world(plot: Any) -> str:
    world = _attr(plot, "world", None) if plot is not None else None
    if world is None:
        return ""
    lines = []
    for label, attr in (("时间线", "timeline"), ("地理", "geography"), ("力量体系", "power_system")):
        value = _plain(_attr(world, attr, ""), 200)
        if value:
            lines.append(f"- {label}：{value}")
    for label, attr in (("势力", "factions"), ("特殊规则", "custom_rules")):
        joined = _join_list(_attr(world, attr, []), limit=10)
        if joined:
            lines.append(f"- {label}：{joined}")
    return "## 世界观\n" + "\n".join(lines) if lines else ""


def build_novel_context(project: Any = None, engine: Any = None,
                        plot: Any = None, chapter_num: Optional[int] = None) -> str:
    """把领域状态压成一段审稿上下文。任何一项缺失都只跳过，不报错。"""
    parts: list[str] = []

    # 1. 作品信息
    if project is not None:
        lines = []
        title = _plain(_attr(project, "title", "") or _attr(project, "name", ""), 80)
        genre = _plain(_attr(project, "genre", ""), 40)
        description = _plain(_attr(project, "description", ""), 300)
        if title:
            lines.append(f"- 书名：《{title}》")
        if genre:
            lines.append(f"- 类型：{genre}")
        if description:
            lines.append(f"- 简介：{description}")
        if lines:
            parts.append("## 作品\n" + "\n".join(lines))

    # 2. 本章大纲 + 前情提要
    if project is not None:
        chapter_lines = []
        if chapter_num is not None:
            try:
                for item in _attr(project, "outline", []) or []:
                    if getattr(item, "chapter", None) == int(chapter_num):
                        expected = _plain(getattr(item, "expected_content", ""), 300)
                        if expected:
                            chapter_lines.append(f"- 本章大纲：{expected}")
                        key_fs = _join_list(getattr(item, "key_foreshadowing", None), limit=10)
                        if key_fs:
                            chapter_lines.append(f"- 大纲要求伏笔：{key_fs}")
                        break
            except Exception:
                pass
            try:
                recap = _plain(project.get_recap(int(chapter_num)), 600)
                if recap:
                    chapter_lines.append(f"- 前情提要：{recap}")
            except Exception:
                pass
        if chapter_lines:
            parts.append(f"## 第{chapter_num}章上下文\n" + "\n".join(chapter_lines))

    # 3. 开放伏笔
    if project is not None:
        open_fs = _join_list(_attr(project, "foreshadowing", []))
        if open_fs:
            parts.append("## 开放伏笔（尚未回收）\n- " + open_fs)

    # 4. 角色档案
    characters = _format_characters(engine, chapter_num)
    if characters:
        parts.append(characters)

    # 5. 世界观
    world = _format_world(plot)
    if world:
        parts.append(world)

    context = "\n\n".join(parts)
    if len(context) > _MAX_CONTEXT_CHARS:
        context = context[:_MAX_CONTEXT_CHARS] + "\n…（作品状态过长已截断）"
    return context
