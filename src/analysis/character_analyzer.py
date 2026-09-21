"""
analysis.character_analyzer — 角色分析器。

从原文和现有分析结果中提取角色信息，逐章构建 Character 对象。

核心功能：
1. 从 analysis_results.json 的叙事层中解析角色
2. 逐章调用 LLM 分析角色状态变化
3. 将角色写入 SQLite 持久化
"""

import json
import re
from pathlib import Path
from typing import Optional

from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from src.models import Character, ChapterState, RelationshipState, DialogueStyle


# LLM 提示词：逐章提取角色状态
CHAPTER_CHARACTER_ANALYSIS_SYSTEM = """你是一位角色分析师。给定小说的一章原文，请提取该章中每个出场角色的状态。

对每个角色输出 JSON：
{
  "character_name": "",
  "mood": "当前情绪（如：愤怒/恐惧/喜悦/悲伤/平静）",
  "motivation": "本章驱动目标",
  "key_action": "本章做出的关键行动/决定",
  "behavior_shift": "相比上一章的行为变化",
  "trigger": "触发变化的事件",
  "inner_conflict": "内心矛盾",
  "new_info": "本章获得的新信息",
  "relationship_changes": [
    {"target": "对方角色", "change": "变化描述", "new_status": "新关系"}
  ]
}

如果没有足够信息判断某个字段，设为空字符串。"""


# LLM 提示词：从整篇分析中提取角色 base_profile
CHARACTER_BASE_EXTRACTION_SYSTEM = """你是一位角色建模师。给定一篇小说的四维分析（思想/结构/叙事/语言），请提取出所有主要角色的基础信息。

对每个角色输出 JSON：
{
  "name": "",
  "aliases": ["别名1"],
  "base_profile": {
    "年龄": "",
    "身份": "",
    "外貌": "",
    "核心欲望": "",
    "核心恐惧": ""
  },
  "personality": {
    "性格概述": "",
    "说话方式": "",
    "习惯动作": "",
    "优点": "",
    "缺点": ""
  },
  "dialogue_style": {
    "句式特征": "",
    "口头禅": [],
    "语气倾向": ""
  },
  "relationship_summary": {
    "对方角色名": "关系描述"
  },
  "arc_summary": "从开头到结局的角色变化"
}"""


class CharacterAnalyzer:
    """角色分析器 — 从分析结果和原文中提取角色信息。"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def extract_from_analysis_json(self, json_path: str) -> list[Character]:
        """从 analysis_results.json 的叙事层人物塑造中提取角色列表。

        Args:
            json_path: analysis_results.json 路径

        Returns:
            Character 列表（有 base_profile，无 chapter_states）
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        characters = []
        for sample in data.get("samples", []):
            narrative = sample.get("analysis", {}).get("叙事层", {})
            character_text = narrative.get("人物塑造", "")

            if not character_text:
                continue

            # 用 LLM 从人物塑造文本中提取结构化角色
            chars = self._extract_from_text(
                character_text,
                sample.get("title", ""),
                sample.get("file", ""),
            )
            characters.extend(chars)

        return characters

    def _extract_from_text(self, character_text: str,
                           title: str, source_file: str) -> list[Character]:
        """用 LLM 从人物塑造描述中提取角色。"""
        prompt = (
            f"素材标题：{title}\n"
            f"素材文件：{source_file}\n\n"
            f"以下是对该素材中人物的描述，请提取每个角色的结构化信息：\n\n"
            f"{character_text[:3000]}"
        )

        try:
            response = self.llm.chat(
                [{"role": "system", "content": CHARACTER_BASE_EXTRACTION_SYSTEM},
                 {"role": "user", "content": prompt}],
                model_tier="flash",
                temperature=0.3,
            )
            return self._parse_characters(response, source_file)
        except Exception as e:
            logger.warning(f"角色提取失败 [{title}]: {e}")
            # 有 API key 失败时，用规则解析兜底
            return self._rule_based_extract(character_text, title, source_file)

    def _parse_characters(self, response: str, source_file: str) -> list[Character]:
        """解析 LLM 返回的角色 JSON。"""
        chars = []
        try:
            data = json.loads(response)
            # 可能是数组或单个对象
            char_list = data if isinstance(data, list) else [data]

            for item in char_list:
                name = item.get("name", "")
                if not name:
                    continue

                # 构建角色
                char = Character(
                    character_id=f"{Path(source_file).stem}_{name}",
                    name=name,
                    aliases=item.get("aliases", []),
                    source_file=source_file,
                    base_profile=item.get("base_profile", {}),
                    personality=item.get("personality", {}),
                    dialogue_style=DialogueStyle(**item.get("dialogue_style", {}))
                        if item.get("dialogue_style") else DialogueStyle(),
                    arc_summary=item.get("arc_summary", ""),
                )

                # 关系
                rel_summary = item.get("relationship_summary", {})
                for target, desc in rel_summary.items():
                    char.relationship_map[target] = desc

                chars.append(char)

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"角色JSON解析失败: {e}")

        return chars

    def _rule_based_extract(self, text: str, title: str,
                            source_file: str) -> list[Character]:
        """无 API 时的规则兜底提取。"""
        chars = []
        # 按句号/分号分割
        segments = re.split(r'[。；]', text)
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            # 尝试提取角色名（冒号或——前的文本）
            match = re.match(r'^([^：:—]+)[：:]', seg)
            if match:
                name = match.group(1).strip()
                if name and len(name) <= 20:
                    char = Character(
                        character_id=f"{Path(source_file).stem}_{name}",
                        name=name,
                        source_file=source_file,
                        base_profile={"初步描述": seg[:200]},
                    )
                    chars.append(char)
        return chars

    def analyze_chapter_from_text(self, chapter_text: str,
                                   chapter_index: int,
                                   characters: list[Character]) -> list[ChapterState]:
        """分析一章原文，提取所有出场角色的状态变化。

        Args:
            chapter_text: 该章原文
            chapter_index: 章号
            characters: 已有角色列表（用于识别角色名）

        Returns:
            该章各角色的 ChapterState 列表
        """
        char_names = [c.name for c in characters]
        prompt = (
            f"章号：{chapter_index}\n"
            f"出场角色：{', '.join(char_names[:10])}\n\n"
            f"原文：\n{chapter_text[:4000]}\n\n"
            f"请分析每个出场角色的状态。"
        )

        try:
            response = self.llm.chat(
                [{"role": "system", "content": CHAPTER_CHARACTER_ANALYSIS_SYSTEM},
                 {"role": "user", "content": prompt}],
                model_tier="flash",
                temperature=0.3,
            )
            return self._parse_chapter_states(response, chapter_index)
        except Exception as e:
            logger.warning(f"第{chapter_index}章角色分析失败: {e}")
            return []

    def _parse_chapter_states(self, response: str,
                               chapter_index: int) -> list[ChapterState]:
        """解析逐章角色状态 JSON。"""
        states = []
        try:
            data = json.loads(response)
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                state = ChapterState(
                    chapter_index=chapter_index,
                    mood=entry.get("mood", ""),
                    motivation=entry.get("motivation", ""),
                    key_action=entry.get("key_action", ""),
                    behavior_shift=entry.get("behavior_shift", ""),
                    trigger=entry.get("trigger", ""),
                    inner_conflict=entry.get("inner_conflict", ""),
                    new_info_learned=entry.get("new_info", ""),
                    relationship_changes=entry.get("relationship_changes", []),
                )
                states.append(state)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"章节状态解析失败: {e}")
        return states

    def save_characters_to_db(self, characters: list[Character], db_path: str):
        """将角色写入 SQLite。"""
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                character_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                aliases TEXT DEFAULT '[]',
                source_file TEXT DEFAULT '',
                base_profile TEXT DEFAULT '{}',
                personality TEXT DEFAULT '{}',
                dialogue_style TEXT DEFAULT '{}',
                arc_summary TEXT DEFAULT '',
                chapter_states TEXT DEFAULT '[]',
                relationship_map TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        for char in characters:
            conn.execute(
                """INSERT OR REPLACE INTO characters
                   (character_id, name, aliases, source_file,
                    base_profile, personality, dialogue_style, arc_summary,
                    chapter_states, relationship_map)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    char.character_id,
                    char.name,
                    json.dumps(char.aliases, ensure_ascii=False),
                    char.source_file,
                    json.dumps(char.base_profile, ensure_ascii=False),
                    json.dumps(char.personality, ensure_ascii=False),
                    char.dialogue_style.model_dump_json() if hasattr(char.dialogue_style, 'model_dump_json') else "{}",
                    char.arc_summary,
                    json.dumps([s.model_dump() for s in char.chapter_states], ensure_ascii=False),
                    json.dumps(char.relationship_map, ensure_ascii=False),
                ),
            )
        conn.commit()
        conn.close()
        logger.info(f"已保存 {len(characters)} 个角色到数据库")
