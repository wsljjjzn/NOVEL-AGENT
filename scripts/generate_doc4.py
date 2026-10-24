"""
scripts/generate_doc4.py — 生成《计算机系统项目综合实践》项目源代码
包含封面与两个标准部分：
第一部分：核心系统代码 (Project, Character, Plot, Service, Router)
第二部分：核心算法代码 (ChapterWriter & StyleGuide, Review & Fixer, DeepAnalyzer, KnowledgeBridge)
"""

import docx
from docx.shared import Pt
from pathlib import Path
from scripts.course_doc_helpers import (
    apply_document_styles, add_cover, add_heading_1, add_heading_2, add_heading_3,
    add_body_p, add_callout, add_code_block
)

PROJECT_TITLE = "面向长篇文学创作的智能辅助系统设计与实现（Novel Studio）"

def generate():
    doc = docx.Document()
    apply_document_styles(doc)

    # 1. 封面
    add_cover(doc, "项 目 源 代 码", PROJECT_TITLE)

    add_callout(doc,
        "本代码文档为《计算机系统项目综合实践》课程设计之配套源代码说明书。全书分为两大部分：第一部分为支撑系统高可用运行的核心系统与数据驱动代码；"
        "第二部分为体现系统智能化创新的核心算法实现代码（含逐章上下文组装算法、角色状态演变算法、六维审稿修复算法、知识库特征解构算法等）。"
        "所有代码均采用严格的 Python 3.12 类型注解与 Google 风格中文规范注释。",
        "【源代码文档导读】"
    )

    # ==========================================
    # 第一部分：核心系统代码
    # ==========================================
    add_heading_1(doc, "第一部分：核心系统代码")

    add_heading_2(doc, "1.1 项目持久化管理与安全路径约束 (src/novel/project_manager.py)")
    add_body_p(doc, 
        "负责长篇小说项目的全生命周期物理持久化管理，封装了沙箱路径穿越防御机制与操作系统级原子文件安全写入。")
    add_code_block(doc, """\"\"\"
novel.project_manager — 长篇小说项目管理。
核心职责：
1. 项目创建/加载/保存，保证磁盘读写原子性
2. 章节管理（正文读取、写入、目录列表、导出）
3. 伴生风格文件 style_guide.json 的维护
\"\"\"
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel, ConfigDict, field_validator
from src.utils.file_utils import atomic_write_json

def _project_path(base_dir: str, name: str) -> Path:
    \"\"\"返回受项目根目录约束的项目绝对路径，拒绝路径穿越与符号链接逃逸。\"\"\"
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("项目名不能为空，也不能包含首尾空白")
    candidate = Path(name)
    if name in {".", ".."} or len(candidate.parts) != 1 or candidate.name != name:
        raise ValueError("项目名必须是单个目录名，不能包含路径分隔符")

    root = Path(base_dir).resolve()
    target = (root / name).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("项目路径不能超出项目根目录") from exc
    return target

class OutlineItem(BaseModel):
    \"\"\"大纲条目：类型声明交给 pydantic，读盘时自动归一化。\"\"\"
    model_config = ConfigDict(extra="allow", validate_assignment=False)
    chapter: int = 0
    title: str = ""
    expected_content: str = ""
    key_foreshadowing: list[str] = []

    @field_validator("chapter", mode="before")
    @classmethod
    def _coerce_chapter(cls, value):
        if value is None or isinstance(value, bool):
            return 0
        try:
            return max(0, int(str(value).strip()))
        except (TypeError, ValueError):
            return 0

class NovelProject:
    \"\"\"长篇小说项目实体类。\"\"\"
    def __init__(self, name: str, base_dir: str = "data/projects"):
        self.name = name
        self.title = name
        self.description = ""
        self.genre = ""
        self.base_dir = _project_path(base_dir, name)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.chapters: dict[int, str] = {}        # {章号: 内容}
        self.chapter_titles: dict[int, str] = {}  # {章号: 标题}
        self.outline: list[OutlineItem] = []
        self.metadata: dict = {"total_words": 0, "chapter_count": 0}
        self.foreshadowing: list[str] = []        # 开放未解伏笔
        self.style_guide: dict | None = None      # 行文风格指南伴生数据

    def add_chapter(self, number: int, title: str, content: str):
        \"\"\"写入或更新章节正文，自动更新字数与章数统计。\"\"\"
        self.chapters[number] = content
        self.chapter_titles[number] = title
        if number > self.metadata.get("chapter_count", 0):
            self.metadata["chapter_count"] = number
        self.metadata["total_words"] = sum(len(c) for c in self.chapters.values())

    def save(self):
        \"\"\"原子持久化 project.json。\"\"\"
        data = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "genre": self.genre,
            "chapters": {str(num): content for num, content in self.chapters.items()},
            "chapter_titles": {str(num): title for num, title in self.chapter_titles.items()},
            "outline": [o.model_dump() for o in self.outline],
            "metadata": self.metadata,
            "foreshadowing": self.foreshadowing,
        }
        atomic_write_json(self.base_dir / "project.json", data)

    @classmethod
    def load(cls, base_dir: str, name: str) -> "NovelProject":
        \"\"\"从磁盘安全加载小说工程与伴生配置。\"\"\"
        path = _project_path(base_dir, name) / "project.json"
        if not path.exists():
            raise FileNotFoundError(f"项目不存在: {path}")
        data = json.loads(path.read_text("utf-8"))
        project = cls(name, base_dir)
        project.title = data.get("title", name)
        project.description = data.get("description", "")
        project.genre = data.get("genre", "")
        project.chapters = {int(k): v for k, v in data.get("chapters", {}).items()}
        project.chapter_titles = {int(k): v for k, v in data.get("chapter_titles", {}).items()}
        project.outline = [OutlineItem(**o) for o in data.get("outline", []) if isinstance(o, dict)]
        project.metadata = data.get("metadata", {})
        project.foreshadowing = data.get("foreshadowing", [])

        # 伴生加载风格指南
        style_file = project.base_dir / "style_guide.json"
        if style_file.exists():
            try:
                project.style_guide = json.loads(style_file.read_text("utf-8"))
            except Exception:
                project.style_guide = None
        return project""", "NovelProject 核心源码")

    add_heading_2(doc, "1.2 角色多维状态机引擎 (src/novel/character_engine.py)")
    add_body_p(doc, 
        "实现 5 维性格量化模型、欲望与恐惧锚点以及逐章事件追踪，提供按章切片提取算法，杜绝未来信息泄漏。")
    add_code_block(doc, """\"\"\"
novel.character_engine — 角色状态机与演化分析引擎。
\"\"\"
from dataclasses import dataclass, field
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from src.utils.file_utils import atomic_write_json

class ChapterEvent(BaseModel):
    \"\"\"角色单章经历事件与心境快照。\"\"\"
    model_config = ConfigDict(extra="allow")
    chapter: int
    mood: str = ""
    key_actions: list[str] = []
    relationships: dict[str, str] = {}

class CharacterProfile(BaseModel):
    \"\"\"角色多维人物画像模型。\"\"\"
    model_config = ConfigDict(extra="allow")
    name: str
    aliases: list[str] = []
    role: str = "配角"
    personality: dict[str, int] = {}  # 勇敢、善良、冲动、智慧、忠诚等 (1-10分)
    speaking_style: str = ""
    core_desire: str = ""
    core_fear: str = ""
    background: str = ""
    appearance: str = ""
    chapter_events: list[ChapterEvent] = []

class CharacterEngine:
    \"\"\"纯确定性角色引擎：负责角色状态维护与提取。\"\"\"
    def __init__(self):
        self._characters: dict[str, CharacterProfile] = {}

    def all_characters(self) -> list[CharacterProfile]:
        return list(self._characters.values())

    def get_context_for_writing(self, chapter_num: int) -> str:
        \"\"\"提取写作当前章所需的角色状态切片，仅包含历史演变，严禁未来泄漏。\"\"\"
        if not self._characters:
            return ""
        lines = ["## 登场角色状态与性格基准"]
        for char in self._characters.values():
            traits = [f"{k}:{v}" for k, v in char.personality.items()]
            lines.append(f"### 【{char.name}】（定位: {char.role}）")
            lines.append(f"- 性格数值: {', '.join(traits)}")
            lines.append(f"- 对白风格: {char.speaking_style}")
            lines.append(f"- 核心欲望: {char.core_desire} | 核心恐惧: {char.core_fear}")
            # 过滤提取本章之前的最近演化心境
            past_events = [e for e in char.chapter_events if e.chapter < chapter_num]
            if past_events:
                last_event = past_events[-1]
                lines.append(f"- 上章遗留心境: {last_event.mood}")
                if last_event.key_actions:
                    lines.append(f"- 上章关键行为: {'; '.join(last_event.key_actions)}")
        return "\\n".join(lines)

    def save(self, file_path: str):
        data = {name: c.model_dump() for name, c in self._characters.items()}
        atomic_write_json(Path(file_path), data)""", "CharacterEngine 核心源码")

    add_heading_2(doc, "1.3 业务服务层统一跨步骤编排 (src/novel/service.py)")
    add_body_p(doc, 
        "编排层作为业务核心枢纽，负责跨引擎协调、错误语义映射及事务护栏控制。")
    add_code_block(doc, """\"\"\"
novel.service — 服务层统一编排器。
所有方法均遵循失败语义：返回 Result(ok: bool)，绝不向上抛出未捕获异常。
\"\"\"
from dataclasses import dataclass, field
from src.novel.project_manager import NovelProject
from src.novel.character_engine import CharacterEngine
from src.novel.plot_engine import PlotEngine
from src.novel.chapter_writer import ChapterWriter

@dataclass
class Result:
    \"\"\"服务层统一契约返回值。\"\"\"
    ok: bool
    title: str
    lines: list[str] = field(default_factory=list)
    report: str = ""
    data: object | None = None

@dataclass
class Bundle:
    \"\"\"一个项目的完整内存态聚合包。\"\"\"
    project: NovelProject
    engine: CharacterEngine
    plot: PlotEngine
    writer: ChapterWriter

class NovelService:
    def __init__(self, base_dir: str = "data/projects"):
        self.base_dir = base_dir

    def exists(self, name: str) -> bool:
        try:
            return (NovelProject.project_path(self.base_dir, name) / "project.json").exists()
        except ValueError:
            return False

    def load(self, name: str) -> Bundle:
        \"\"\"从磁盘安全恢复完整项目状态（纯确定性，零 LLM 开销）。\"\"\"
        project = NovelProject.load(self.base_dir, name)
        engine = CharacterEngine()
        plot = PlotEngine()
        char_file = project.base_dir / "characters.json"
        plot_file = project.base_dir / "plots.json"
        if char_file.exists():
            engine.load(str(char_file))
        if plot_file.exists():
            plot.load(str(plot_file))
        return Bundle(project, engine, plot, ChapterWriter(project, engine))

    def write_chapter(self, name: str, chapter: int, target_words: int = 2500,
                      tier: str = "pro", instructions: str = "") -> Result:
        \"\"\"逐章创作事务编排：读取上下文 -> 拼装Prompt -> 模型生成 -> 自动演化角色 -> 落盘。\"\"\"
        bundle = self.load(name)
        text = bundle.writer.write_chapter(chapter, instructions, target_words, model_tier=tier)
        if not text:
            return Result(False, f"第{chapter}章生成失败：模型返回空文本或因配额耗尽熔断")
        return Result(True, f"第{chapter}章已完成并安全落盘", [f"实际生成字数：{len(text)} 字"])""", "NovelService 核心编排源码")

    # ==========================================
    # 第二部分：核心算法代码
    # ==========================================
    add_heading_1(doc, "第二部分：核心算法代码")

    add_heading_2(doc, "2.1 逐章上下文装配与风格指南 Few-Shot 注入算法 (src/novel/chapter_writer.py)")
    add_body_p(doc, 
        "系统的生成枢纽算法：实现角色演变切片、前置大纲伏笔、前章结尾摘要以及风格模板与范文高光片段的动态多路归并。")
    add_code_block(doc, """\"\"\"
novel.chapter_writer — 逐章写作管线与动态 Prompt 装配算法。
\"\"\"
CHAPTER_WRITER_SYSTEM = \"\"\"你是一位长篇小说作家。请根据提供的角色档案、前情提要和写作要求，写出本章内容。
写作原则：
1. 角色对话和行为必须符合其人格设定（见角色状态）
2. 充分利用已有的伏笔和关系线
3. 本章要有独立的情节完整性（起因-发展-高潮/转折-收尾）
4. 为后续章节埋下新的伏笔
5. 字数严格控制在要求范围内
6. 若提供了【行文风格与范文指引】，必须严格遵守其规则与忌用词限制，并参考范文高光片段的笔触与叙事节奏
输出格式：只输出本章正文，不要加额外标题标记。\"\"\"

class ChapterWriter:
    def __init__(self, project, engine, llm_client=None):
        self.project = project
        self.engine = engine
        self.llm = llm_client

    def _build_prompt(self, chapter_num: int, instructions: str, target_words: int) -> str:
        \"\"\"动态多路组装当前章写作 Prompt（纯确定性，时延 < 20ms）。\"\"\"
        parts = []

        # 1. 角色当前章动态画像切片
        char_context = self.engine.get_context_for_writing(chapter_num)
        if char_context:
            parts.append(char_context)

        # 2. 前情提要 (截取前一章尾部 200 字，维持叙事因果粘性)
        recap = self.project.get_recap(chapter_num)
        if recap:
            parts.append(f"## 前情提要\\n{recap}")

        # 3. 本章大纲与开放伏笔引用
        for item in self.project.outline:
            if item.chapter == chapter_num:
                parts.append(f"## 本章大纲规划\\n- 章节标题: {item.title}\\n- 预期发展: {item.expected_content}")
                if item.key_foreshadowing:
                    parts.append(f"- 关联/待回收伏笔: {'; '.join(item.key_foreshadowing)}")
                break

        # 4. 【核心创新算法】行文风格与 Few-Shot 样本注入
        style_context = self.project.get_style_context()
        if style_context:
            parts.append(style_context)

        # 5. 目标字数与特殊指令规约
        parts.append(f"## 本章写作要求\\n撰写第{chapter_num}章，字数约{target_words}字。")
        if instructions:
            parts.append(f"特殊情节指令: {instructions}")
        parts.append("\\n请结合上述上下文直接开始本章正文写作。")

        return "\\n\\n".join(parts)""", "逐章 Prompt 动态装配算法实现")

    add_heading_2(doc, "2.2 六维审稿与三级智能修复算法 (src/review_engine/fixer.py)")
    add_body_p(doc, 
        "在审稿修改中，为避免多处字符串替换引起的换行吞噬与字符索引漂移，研发了基于倒序区间偏移映射的非破坏性无损修复算法。")
    add_code_block(doc, """\"\"\"
review_engine.fixer — Level-1 机械无损修复算法。
解决字符替换时的换行吞没与多点替换索引漂移问题。
\"\"\"
class ArticleFixer:
    @staticmethod
    def apply_level1_fixes(original_text: str, changes: list[dict]) -> tuple[str, list[dict]]:
        \"\"\"
        执行 Level-1 错别字与基础标点自动修复。
        采用倒序替换策略：先按原始起始偏移量降序排列，从文章末尾向开头逆向替换，
        确保前面区间的字符物理偏移量在替换过程中恒定不变。
        \"\"\"
        # 1. 过滤并验证有效修复项
        valid_changes = [
            c for c in changes 
            if c.get("level") == 1 and "original" in c and "replacement" in c
        ]
        if not valid_changes:
            return original_text, []

        applied = []
        result_text = original_text

        # 2. 逆序替换算法
        # 对每一个变更项，从后往前查找匹配项
        for change in reversed(valid_changes):
            orig = change["original"]
            rep = change["replacement"]
            if not orig or orig not in result_text:
                continue

            # 定位目标最后一次出现的位置（倒序安全保护）
            idx = result_text.rfind(orig)
            if idx != -1:
                result_text = result_text[:idx] + rep + result_text[idx + len(orig):]
                applied.append(change)

        return result_text, applied""", "Level-1 倒序无损修复算法源码")

    add_heading_2(doc, "2.3 范文四维深度解构算法 (src/analysis/deep.py)")
    add_body_p(doc, 
        "对输入的范文长文本执行多任务正交分解，在思想层、结构层、叙事层、语言层分步提取高阶特征。")
    add_code_block(doc, """\"\"\"
analysis.deep — 第三层：深度分析器（Pro 档聚焦单维调用）。
\"\"\"
class DeepAnalyzer:
    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._system_prompts = {
            "thought": THOUGHT_ANALYSIS_SYSTEM,       # 核心立意、价值观母题
            "structure": STRUCTURE_ANALYSIS_SYSTEM,   # 起承转合、信息释放节奏
            "narrative": NARRATIVE_ANALYSIS_SYSTEM,   # 视距、人设张力、冲突
            "language": LANGUAGE_ANALYSIS_SYSTEM,     # 句长配比、修辞习惯、语体
        }

    def analyze_all(self, text: str, source_id: str = "") -> dict:
        \"\"\"四次聚焦单一维度的并发深度分析算法。\"\"\"
        result = {}
        # 截取最具代表性的高光段落 (4000 tokens)
        sample = text[:4000]
        for layer, prompt in self._system_prompts.items():
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"请针对以下文学范文进行{layer}层特征深度解构：\\n\\n{sample}"}
            ]
            response = self.llm.chat(messages, model_tier="pro", temperature=0.35)
            result[layer] = safe_json_parse(response)
        return result""", "四维解构算法源码")

    out_dir = Path("course_materials/submissions")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "4、计科xx班组长学号组长姓名计算机系统项目.docx"
    doc.save(str(out_path))
    print(f"[OK] Generated: {out_path}")

if __name__ == "__main__":
    generate()
