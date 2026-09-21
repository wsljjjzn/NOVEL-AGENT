"""
novel.chapter_writer — 逐章写作管线。

流程：
1. 组装角色上下文（来自 CharacterEngine）
2. 组装前情提要（来自 NovelProject）
3. 组装大纲引用
4. 构建完整 prompt → LLM 写作
5. 写入章节 → 分析角色变化 → 更新引擎
"""

from typing import Optional
from pathlib import Path

from src.utils.llm_client import LLMClient
from src.utils.logger import logger
from .character_engine import CharacterEngine, CharacterProfile
from .project_manager import NovelProject


CHAPTER_WRITER_SYSTEM = """你是一位长篇小说作家。请根据提供的角色档案、前情提要和写作要求，写出本章内容。

写作原则：
1. 角色对话和行为必须符合其人格设定（见角色状态）
2. 充分利用已有的伏笔和关系线
3. 本章要有独立的情节完整性（有起因-发展-高潮/转折-收尾）
4. 为后续章节埋下新的伏笔
5. 字数控制在要求范围内

输出格式：
只输出本章正文，不要加"本章标题"等额外标记。"""


OUTLINE_GENERATOR_SYSTEM = """你是一位长篇小说策划师。请根据小说的基本信息，生成分章大纲。

输出 JSON 格式：
{
  "outline": [
    {
      "chapter": 1,
      "title": "章节标题",
      "expected_content": "本章预期发生的主要事件",
      "key_foreshadowing": ["伏笔描述1", "伏笔描述2"]
    }
  ]
}"""


class ChapterWriter:
    """逐章写作器。"""

    def __init__(self, project: NovelProject, engine: CharacterEngine,
                 llm_client: Optional[LLMClient] = None):
        self.project = project
        self.engine = engine
        self.llm = llm_client or LLMClient()

    def write_chapter(self, chapter_num: int, instructions: str = "",
                      target_words: int = 2500, model_tier: str = "pro") -> str:
        """写一章小说。

        Args:
            chapter_num: 章号
            instructions: 本章写作要求
            target_words: 目标字数
            model_tier: 使用的模型层级

        Returns:
            章节正文
        """
        logger.info(f"写作第 {chapter_num} 章")

        prompt = self._build_prompt(chapter_num, instructions, target_words)

        response = self.llm.chat(
            [{"role": "system", "content": CHAPTER_WRITER_SYSTEM},
             {"role": "user", "content": prompt}],
            model_tier=model_tier, temperature=0.8,
        )

        # 清理输出（去掉可能的标题行）
        chapter_text = response.strip()

        # 存入项目
        title = self._extract_title(chapter_text, chapter_num)
        self.project.add_chapter(chapter_num, title, chapter_text)

        # 自动分析角色变化
        try:
            existing_names = [c.name for c in self.engine.all_characters()]
            updated = self.engine.analyze_chapter(
                chapter_num, chapter_text, existing_names
            )
            logger.info(f"角色分析完成: {len(updated)} 个角色更新")
        except Exception as e:
            logger.warning(f"角色分析跳过: {e}")

        # 保存项目
        self.project.save()
        self.engine.save(str(self.project.base_dir / "characters.json"))

        return chapter_text

    def _build_prompt(self, chapter_num: int, instructions: str,
                      target_words: int) -> str:
        parts = []

        # 角色上下文
        char_context = self.engine.get_context_for_writing(chapter_num)
        if char_context:
            parts.append(char_context)

        # 前情提要
        recap = self.project.get_recap(chapter_num)
        if recap:
            parts.append(f"## 前情提要\n{recap}")

        # 大纲引用
        for item in self.project.outline:
            if item.chapter == chapter_num:
                parts.append(f"## 本章大纲\n- 标题: {item.title}\n- 预期内容: {item.expected_content}")
                if item.key_foreshadowing:
                    parts.append(f"- 关键伏笔: {'; '.join(item.key_foreshadowing)}")
                break

        # 写作要求
        parts.append(f"## 本章写作要求")
        parts.append(f"写第{chapter_num}章，约{target_words}字。")
        if instructions:
            parts.append(f"具体要求: {instructions}")
        parts.append(f"\n请写出本章正文。")

        return "\n\n".join(parts)

    def _extract_title(self, text: str, chapter_num: int) -> str:
        """从章节文本中提取或生成标题。

        优先级：大纲标题 > 文本 Markdown 标题 > 默认标题
        """
        # 优先从大纲获取
        for item in self.project.outline:
            if item.chapter == chapter_num and item.title:
                return item.title
        # 尝试从文本第一行提取
        lines = text.strip().split("\n")
        if lines and lines[0].startswith("#"):
            return lines[0].lstrip("#").strip()[:50]
        return f"第{chapter_num}章"

    def generate_outline(self, total_chapters: int, instructions: str = "",
                         model_tier: str = "flash") -> list:
        """生成分章大纲。

        Args:
            total_chapters: 总章节数
            instructions: 故事简介
            model_tier: 模型层级

        Returns:
            OutlineItem 列表
        """
        prompt = (
            f"小说标题: {self.project.title}\n"
            f"类型: {self.project.genre}\n"
            f"简介: {instructions}\n"
            f"请生成 {total_chapters} 章的分章大纲。"
        )

        response = self.llm.chat(
            [{"role": "system", "content": OUTLINE_GENERATOR_SYSTEM},
             {"role": "user", "content": prompt}],
            model_tier=model_tier, temperature=0.5,
        )

        from src.utils.json_utils import safe_json_parse
        data = safe_json_parse(response)

        if not data:
            return []

        from .project_manager import OutlineItem
        items = [
            OutlineItem(
                chapter=item.get("chapter", i + 1),
                title=item.get("title", ""),
                expected_content=item.get("expected_content", ""),
                key_foreshadowing=item.get("key_foreshadowing", []),
            )
            for i, item in enumerate(data.get("outline", []))
        ]
        self.project.set_outline(items)
        self.project.save()
        return items
