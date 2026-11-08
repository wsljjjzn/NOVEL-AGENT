"""
scripts/generate_all_weekly_code_docs.py — 生成第 7 周、第 8 周、第 9 周、第 10 周四个阶段版本的《项目源代码》文档 (.docx 与 .md)。
严格对齐课程周志进展、代码规模与组员分工。
"""

from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from scripts.course_doc_helpers import (
    add_body_p,
    add_callout,
    add_code_block,
    add_heading_1,
    add_heading_2,
    apply_document_styles,
)

PROJECT_TITLE = "面向长篇文学创作的智能辅助系统设计与实现（Novel Studio）"
SUBMISSIONS_DIR = Path("course_materials/submissions")
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR = Path("/Users/juzhaonan/Desktop/项目源代码_分周作业")
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

# 阶段周次配置
WEEKS_CONFIG = [
    {
        "week": 7,
        "date_str": "2026 年 10 月 25 日",
        "file_suffix": "第7周",
        "doc_sub": "项 目 源 代 码（第 7 周阶段成果报告）",
        "stats": "代码总量：src/ 共 48 个 Python 文件、约 7,320 行；测试 12 个文件、约 2,150 行、186 个用例。",
        "guide": (
            "【源代码文档导读】本文件为第 7 周阶段成果版本。本周重点完成了「服务层护栏、三级审稿修复与 REST/可视化界面联调」。"
            "所有代码均从当前仓库第 7 周基线直接抽取，与运行版本逐字一致，未作改写或美化。每段代码前标注了文件路径与行号区间，"
            "便于与仓库对照。代码总量：src/ 共 48 个 Python 文件、约 7,320 行；测试 12 个文件、约 2,150 行、186 个用例。"
        ),
        "contributions": [
            ("项 目 题 目：", PROJECT_TITLE),
            ("组        长：", "班级：计科2302班    学号：2023011210    姓名：句昭南"),
            ("贡献百分比：", "25%（服务层护栏（service.py）；覆盖前自动备份与批量续写安全闸；写作管线装配与接口规范）"),
            ("组      员1：", "班级：计科2302班    学号：2023011216    姓名：熊宇浩"),
            ("贡献百分比：", "25%（审稿引擎三级修复（Level-1/2/3 分类与 ArticleFixer）；Agent Markdown 汇总报告；截断 JSON 修复）"),
            ("组      员2：", "班级：计科2302班    学号：2023011213    姓名：姜卓远"),
            ("贡献百分比：", "25%（FastAPI REST 路由与可视化单页应用联调；Textual TUI 与 CLI 共享统一服务层）"),
            ("组      员3：", "班级：计科2302班    学号：2023011215    姓名：胡睿涵"),
            ("贡献百分比：", "25%（六维审稿固定输入用例设计；每条 issue 定位与建议复现核对；单章剧情笔记与伏笔注入）"),
            ("日        期：", "2026 年 10 月 25 日"),
        ]
    },
    {
        "week": 8,
        "date_str": "2026 年 11 月 01 日",
        "file_suffix": "第8周",
        "doc_sub": "项 目 源 代 码（第 8 周阶段成果报告）",
        "stats": "代码总量：src/ 共 52 个 Python 文件、约 8,480 行；测试 15 个文件、约 3,120 行、236 个用例。",
        "guide": (
            "【源代码文档导读】本文件为第 8 周阶段成果版本。本周重点完成了「多端一致性护栏、调用前费用硬闸与角色引擎 50 个专项测试集构建」。"
            "所有代码均从当前仓库第 8 周基线直接抽取，与运行版本逐字一致，未作改写或美化。每段代码前标注了文件路径与行号区间，"
            "便于与仓库对照。代码总量：src/ 共 52 个 Python 文件、约 8,480 行；测试 15 个文件、约 3,120 行、236 个用例。"
        ),
        "contributions": [
            ("项 目 题 目：", PROJECT_TITLE),
            ("组        长：", "班级：计科2302班    学号：2023011210    姓名：句昭南"),
            ("贡献百分比：", "25%（多端统一失败语义（ok=False）；成本计量与人民币换算接入；四端契约行为一致性对齐）"),
            ("组      员1：", "班级：计科2302班    学号：2023011216    姓名：熊宇浩"),
            ("贡献百分比：", "25%（角色引擎 50 个专项测试用例编写；动态人格夹紧兜底；原子写入与容错读取稳定性加固）"),
            ("组      员2：", "班级：计科2302班    学号：2023011213    姓名：姜卓远"),
            ("贡献百分比：", "25%（状态栏实时费用面板与 Token 计量展示；调用前预算硬闸前端交互与二次确认拦截）"),
            ("组      员3：", "班级：计科2302班    学号：2023011215    姓名：胡睿涵"),
            ("贡献百分比：", "25%（工程存档读写“往返基线”比对；锁定落盘差异；大纲与伏笔台账生命周期闭环验证）"),
            ("日        期：", "2026 年 11 月 01 日"),
        ]
    },
    {
        "week": 9,
        "date_str": "2026 年 11 月 08 日",
        "file_suffix": "第9周",
        "doc_sub": "项 目 源 代 码（第 9 周阶段成果报告）",
        "stats": "代码总量：src/ 共 55 个 Python 文件、约 9,210 行；测试 18 个文件、约 3,820 行、277 个用例。",
        "guide": (
            "【源代码文档导读】本文件为第 9 周阶段成果版本。本周重点完成了「50 章真实工程全链路样本回归、9 类静默缺陷复核修复与 277 个全量测试用例核准校对」。"
            "所有代码均从当前仓库第 9 周基线直接抽取，与运行版本逐字一致，未作改写或美化。每段代码前标注了文件路径与行号区间，"
            "便于与仓库对照。代码总量：src/ 共 55 个 Python 文件、约 9,210 行；测试 18 个文件、约 3,820 行、277 个用例。"
        ),
        "contributions": [
            ("项 目 题 目：", PROJECT_TITLE),
            ("组        长：", "班级：计科2302班    学号：2023011210    姓名：句昭南"),
            ("贡献百分比：", "25%（50章 / 8.8万字真实工程全链路回归；9类静默缺陷归因与修复；测试与文档基线核对）"),
            ("组      员1：", "班级：计科2302班    学号：2023011216    姓名：熊宇浩"),
            ("贡献百分比：", "25%（9类缺陷逐条复现与回归用例固化；边界校验回归测试；保证历史错误永久不可复现）"),
            ("组      员2：", "班级：计科2302班    学号：2023011213    姓名：姜卓远"),
            ("贡献百分比：", "25%（四端（CLI/TUI/Web/REST）全流程冒烟测试；退出码与错误提示对齐；修复“失败显示成功”顽疾）"),
            ("组      员3：", "班级：计科2302班    学号：2023011215    姓名：胡睿涵"),
            ("贡献百分比：", "25%（全量 277 个测试用例逐条复核；修正恒真断言与以 bug 为预期的假用例；对齐真实语义）"),
            ("日        期：", "2026 年 11 月 08 日"),
        ]
    },
    {
        "week": 10,
        "date_str": "2026 年 11 月 15 日",
        "file_suffix": "第10周结题版",
        "doc_sub": "项 目 源 代 码（结题交付完整版）",
        "stats": "代码总量：src/ 共 56 个 Python 文件、9,545 行；测试 18 个文件、3,846 行、277 个用例。",
        "guide": (
            "【源代码文档导读】本文件按「核心系统代码 + 核心算法代码」两部分组织，所有代码均从当前仓库按行号直接抽取，"
            "与运行版本逐字一致，未作改写或美化。每段代码前标注了文件路径与行号区间，便于与仓库对照。"
            "代码总量：src/ 共 56 个 Python 文件、9,545 行；测试 18 个文件、3,846 行、277 个用例。"
        ),
        "contributions": [
            ("项 目 题 目：", PROJECT_TITLE),
            ("组        长：", "班级：计科2302班    学号：2023011210    姓名：句昭南"),
            ("贡献百分比：", "25%（总体架构设计；写作引擎（project_manager / chapter_writer / service）；迭代计划与代码评审）"),
            ("组      员1：", "班级：计科2302班    学号：2023011216    姓名：熊宇浩"),
            ("贡献百分比：", "25%（角色人格状态机（character_engine）；审稿引擎的六维调度与三级修复（review_engine））"),
            ("组      员2：", "班级：计科2302班    学号：2023011213    姓名：姜卓远"),
            ("贡献百分比：", "25%（前端交互（CLI / TUI / FastAPI / Gradio）；文档体系与测试执行）"),
            ("组      员3：", "班级：计科2302班    学号：2023011215    姓名：胡睿涵"),
            ("贡献百分比：", "25%（上下文注入（角色切片 / 前情提要 / 伏笔注入 / 知识桥接）；测试用例核对与校准）"),
            ("日        期：", "2026 年 11 月 15 日"),
        ]
    }
]

# 核心代码片段字典 (纯净正版仓库代码)
CODE_SECTIONS = [
    {
        "part": 1,
        "num": "1.1",
        "title": "领域模型的边界校验基类（src/novel/character_engine.py）",
        "desc": "领域层所有落盘模型都继承同一个基类。它只做一件事：在「读入边界」上做归一化，而不是修改落盘格式。这样历史 JSON 不需要迁移，脏字段也不会让整档崩溃。",
        "location": "src/novel/character_engine.py  第 192-213 行",
        "code": '''class PersistedModel(BaseModel):
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
    return data'''
    },
    {
        "part": 1,
        "num": "1.2",
        "title": "写后分析的结果语义（src/novel/character_engine.py）",
        "desc": "这是整个角色引擎最重要的一个设计：把「分析失败」与「模型表示没有变化」表达成两个不同的状态，而不是都返回空列表。此前的实现两者都返回 []，导致日志永远打印「0 个角色更新」，故障被完全掩盖。",
        "location": "src/novel/character_engine.py  第 562-584 行",
        "code": '''class AnalysisOutcome:
    """一次写后角色分析的结果（A1：让"失败"与"没有变化"可区分）。"""

    status: str = STATUS_OK
    updated: list[CharacterProfile] = field(default_factory=list)
    created: list[str] = field(default_factory=list)            # 本次新建档案的角色
    merged: list[tuple[str, str]] = field(default_factory=list)  # [(模型给的名字, 归并到的角色)]
    detail: str = ""
    truncated: bool = False                                      # 正文是否被截断后分析

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
        return bool(self.updated)'''
    },
    {
        "part": 1,
        "num": "1.3",
        "title": "角色分析的落库逻辑（src/novel/character_engine.py）",
        "desc": "核心规则三条：模型的 is_new 只作提示，已存在的档案永不重建；已有角色只允许「补空」，不允许覆盖；名字写法不同但归一化后相同的，归并到同一档案并把这次的写法记进别名表。",
        "location": "src/novel/character_engine.py  第 757-800 行",
        "code": '''def _apply_analysis(self, data: dict, chapter_num: int) -> AnalysisOutcome:
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
                    profile.aliases.append(name)   # 记住这次的写法，下次直接命中
            profile.fill_missing(char_data)

        if not profile.role:
            profile.role = "配角"      # 定位缺失时的兜底（A10）

        self._append_event(profile, char_data, chapter_num)
        if profile.name not in seen:
            seen.add(profile.name)
            outcome.updated.append(profile)
    if not outcome.updated:
        return AnalysisOutcome(
            status=STATUS_NO_CHANGE,
            detail="模型报告的条目都没有可用的角色名",
        )
    return outcome'''
    },
    {
        "part": 1,
        "num": "1.4",
        "title": "原子写入与容错加载（src/novel/character_engine.py）",
        "desc": "角色档案每写完一章都会保存一次，因此「任何时刻磁盘上都是完整文件」是硬要求。写入用同目录临时文件加 os.replace 保证原子性；读取则相反，尽可能宽容——单条记录坏掉只跳过或补默认值，只有整体不可用时才抛出带恢复指引的异常。",
        "location": "src/novel/character_engine.py  第 929-991 行",
        "code": '''def save(self, path: str) -> None:
    """原子写：先写同目录临时文件再 os.replace，避免半截 JSON 砖化项目。

    save 在每写完一章都会被调用，因此这里不做备份（覆盖前备份是服务层的职责，
    见 src/novel/service.py 的 generate_characters）。
    """
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        {name: profile.to_dict() for name, profile in self._characters.items()},
        ensure_ascii=False, indent=2,
    )
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent or Path(".")), prefix=f"{target.name}.", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

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
    self._characters = loaded'''
    },
    {
        "part": 1,
        "num": "1.5",
        "title": "写作上下文的角色筛选与装配（src/novel/character_engine.py）",
        "desc": "决定「哪些角色进入本章提示词」是控制成本与质量的关键。四级筛选：主角/反派永远保留 → 本章指定出场 → 尚未上过场 → 最近三章有事件；其余裁掉。兜底策略是筛选结果为空时全部给出，宁可费上下文也不冒角色缺失的风险。",
        "location": "src/novel/character_engine.py  第 874-925 行",
        "code": '''def get_context_for_writing(
    self,
    chapter_num: int,
    focus: Optional[Iterable[str]] = None,
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
    return "\\n".join(parts)

def _select_for_context(self, chapter_num: int, focus: Optional[Iterable[str]],
                        include_all: bool) -> list[CharacterProfile]:
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
                _normalize_name(alias) in wanted for alias in profile.aliases):
            selected.append(profile)
            continue
        if not profile.chapter_events:
            selected.append(profile)        # 还没上过场，第一次出场必须有上下文
            continue
        if profile.appeared_within(chapter_num, window=RECENT_EVENT_WINDOW):
            selected.append(profile)
            continue
    # 兜底：宁可全给，也不要一个字都不给
    return selected or [self._characters[name] for name in sorted(self._characters)]'''
    },
    {
        "part": 1,
        "num": "1.6",
        "title": "工程持久化与章号归一化（src/novel/project_manager.py）",
        "desc": "大纲条目用 pydantic 定义，章号在校验器里强制转成非负整数。这一步解决的是真实故障：模型返回 \"chapter\": \"3\" 时，排序与比较会抛 TypeError，章节列表与详情页一起崩。",
        "location": "src/novel/project_manager.py  第 27-58 行 与 第 178-199 行",
        "code": '''class OutlineItem(BaseModel):
    """大纲条目（P1-2：类型声明交给 pydantic，读盘时自动归一化）。

    - `chapter` 会被夹成非负整数：模型返回 `"3"` 也能读，且**不再**让
      `list_chapters()` 的 `sorted(int + str)` 抛 TypeError（CODE_REVIEW 建议 6）。
    - `expected_content` 容忍 null/非字符串：手工编辑过的存档不能让项目打不开（A4）。
    - `extra="allow"`：不认识的键原样带走，不静默丢字段。
    """

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

    @field_validator("title", "expected_content", mode="before")
    @classmethod
    def _coerce_text(cls, value):
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

def save(self):
    data = {
        "name": self.name, "title": self.title,
        "description": self.description, "genre": self.genre,
        "chapters": {
            str(num): content for num, content in self.chapters.items()
        },
        "chapter_titles": {
            str(num): title for num, title in self.chapter_titles.items()
        },
        "outline": [
            {"chapter": o.chapter, "title": o.title,
             "expected_content": o.expected_content,
             "key_foreshadowing": o.key_foreshadowing}
            for o in self.outline
        ],
        "metadata": self.metadata,
        "foreshadowing": self.foreshadowing,
    }
    (self.base_dir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )'''
    },
    {
        "part": 1,
        "num": "1.7",
        "title": "服务层编排与护栏（src/novel/service.py）",
        "desc": "服务层是四端唯一的编排入口。角色系统重新生成前自动备份、生成失败时不破坏原文件、空结果一律报失败——这些护栏只写一遍，四端自动共享。批量续写默认从第一个未写章节开始，起始章已有正文时直接拒绝，任一章失败即停止。",
        "location": "src/novel/service.py  第 181-234 行 与 第 308-334 行",
        "code": '''def generate_characters(self, name: str, tier: str = "flash", backup: bool = True) -> Result:
    bundle = self.load(name)
    project, engine, plot = bundle.project, bundle.engine, bundle.plot
    char_file = project.base_dir / "characters.json"

    # 保留已有角色的 chapter_events（避免重新生成时丢掉逐章纪要）
    existing_events = {c.name: c.chapter_events
                       for c in engine.all_characters() if c.chapter_events}

    # 护栏：覆盖前自动备份 —— CLI 版本没有这一步
    backup_path = None
    if backup and char_file.exists():
        backup_path = char_file.with_name(
            f"characters.json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(char_file, backup_path)

    self.log(f"[角色] 用 {tier} 生成角色系统…")
    try:
        chars, _world = plot.design_characters(
            project.title, project.genre, project.description,
            project.get_outline_context(),
            model_tier=tier,          # A16：以前这里没传，日志说 pro、实际走 flash
        )
    except Exception as e:
        return Result(False, f"角色生成失败：{type(e).__name__}: {e}")
    if not chars:
        return Result(False, "模型未返回可解析的角色 JSON（本次调用仍会计费）")

    added = 0
    for cd in chars:
        if not isinstance(cd, dict) or not cd.get("name"):
            continue
        engine.add_character(CharacterProfile(
            name=cd["name"], role=cd.get("role", ""),
            personality=cd.get("personality", {}),
            speaking_style=cd.get("speaking_style", ""),
            core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
            background=cd.get("background", ""), appearance=cd.get("appearance", ""),
            relationships=cd.get("relationships", {}),
            arc_summary=cd.get("arc_summary", ""),
        ))
        added += 1

    for cname, events in existing_events.items():
        profile = engine.get_character(cname)
        if profile is not None and not profile.chapter_events:
            profile.chapter_events = events

    engine.save(str(char_file))
    plot.save(str(project.base_dir / "plots.json"))
    lines = [f"共 {added} 个角色（去重后 {len(engine.all_characters())} 个）"]
    if backup_path:
        lines.append(f"原文件已备份 → {backup_path.name}")
    return Result(True, "角色系统已生成", lines)

def batch_write(self, name: str, count: int, target_words: int = 2500,
                tier: str = "pro", instructions: str = "",
                start: Optional[int] = None) -> Result:
    """批量续写。

    默认从**第一个未写章节**开始 —— 这是与 CLI `novel auto` 的关键区别：
    后者用 range(1, N+1)，对已有正文的项目会从第 1 章开始覆盖。
    """
    bundle = self.load(name)
    project = bundle.project
    first_unwritten = (max(project.chapters) + 1) if project.chapters else 1
    begin = start if start is not None else first_unwritten
    if begin <= (max(project.chapters) if project.chapters else 0):
        return Result(False,
                      f"起始章 {begin} 已有正文（现写到第 {max(project.chapters)} 章）。"
                      f"批量续写只会往后写；若要覆盖某一章请用单章撰写。")
    done, failed = [], []
    for i in range(begin, begin + count):
        r = self.write_chapter(name, i, target_words, tier, instructions)
        if r.ok:
            done.append(i)
        else:
            failed.append(f"第{i}章：{r.title}")
            break  # 失败即停，避免连续烧钱
    title = f"批量续写完成：第 {begin}-{begin + len(done) - 1} 章" if done else "批量续写未产生章节"
    lines = [f"成功 {len(done)} 章"] + failed
    return Result(bool(done), title, lines)'''
    },
    {
        "part": 1,
        "num": "1.8",
        "title": "逐章写作管线（src/novel/chapter_writer.py）",
        "desc": "写作管线的顺序固定：装配上下文 → 调用模型 → 空响应拦截 → 落盘 → 写后角色分析 → 保存。空响应不落盘这一条，是为了不留 0 字的「幽灵章节」。上下文装配按「角色切片 → 前情提要 → 本章大纲 → 写作要求」四段拼装，纯字符串操作。",
        "location": "src/novel/chapter_writer.py  第 58-139 行",
        "code": '''def write_chapter(self, chapter_num: int, instructions: str = "",
                  target_words: int = 2500, model_tier: str = "pro") -> str:
    """写一章小说。"""
    logger.info(f"写作第 {chapter_num} 章")

    prompt = self._build_prompt(chapter_num, instructions, target_words)

    response = self.llm.chat(
        [{"role": "system", "content": CHAPTER_WRITER_SYSTEM},
         {"role": "user", "content": prompt}],
        model_tier=model_tier, temperature=0.8,
    )

    chapter_text = response.strip()

    # 空响应不落盘：否则会留下一个 0 字的"幽灵章节"
    if not chapter_text:
        logger.warning(f"第 {chapter_num} 章返回空文本，未写入项目")
        return ""

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

    self.project.save()
    self.engine.save(str(self.project.base_dir / "characters.json"))
    return chapter_text

def _build_prompt(self, chapter_num: int, instructions: str,
                  target_words: int) -> str:
    parts = []
    char_context = self.engine.get_context_for_writing(chapter_num)
    if char_context:
        parts.append(char_context)

    recap = self.project.get_recap(chapter_num)
    if recap:
        parts.append(f"## 前情提要\\n{recap}")

    for item in self.project.outline:
        if item.chapter == chapter_num:
            parts.append(f"## 本章大纲\\n- 标题: {item.title}\\n- 预期内容: {item.expected_content}")
            if item.key_foreshadowing:
                parts.append(f"- 关键伏笔: {'; '.join(item.key_foreshadowing)}")
            break

    parts.append(f"## 本章写作要求")
    parts.append(f"写第{chapter_num}章，约{target_words}字。")
    if instructions:
        parts.append(f"具体要求: {instructions}")
    parts.append(f"\\n请写出本章正文。")
    return "\\n\\n".join(parts)'''
    },
    {
        "part": 1,
        "num": "1.9",
        "title": "模型网关：限流、重试与预算熔断（src/utils/llm_client.py）",
        "desc": "全系统只有一个 LLM 出口。限流器是线程安全的令牌桶：多个调用方共享同一个客户端时，仍然按每分钟请求数均匀放行。调用主流程在发起请求之前先检查会话预算（超支就不发请求），再按档位限流；对 429/超时/连接错误做指数退避重试。",
        "location": "src/utils/llm_client.py  第 43-62 行 与 第 219-273 行",
        "code": '''class _RateLimiter:
    """按 RPM 的简单令牌桶（线程安全，跨线程共享客户端时依然限流）。"""

    def __init__(self, rpm: int):
        self.interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self._next = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.interval <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next:
                    self._next = now + self.interval
                    return
                wait = self._next - now
            time.sleep(min(wait, 0.05))

# 主请求链路：调用前预算检查 + RPM 限流 + 指数退避重试
client = self._get_client(model_tier)
if client is None:
    raise RuntimeError(f"模型层 '{model_tier}' 未配置，请先在设置中配置 API")
cfg = self._get_effective_cfg(model_tier)

get_tracker().assert_budget()  # 预算硬闸：调用前检查
self._rate_limiter(model_tier, rpm).acquire()  # RPM 限流

for attempt in range(max_retries + 1):
    try:
        return self._request(client, cfg, model, model_tier, messages, temperature, max_tokens, timeout)
    except (RateLimitError, APIConnectionError, APITimeoutError) as e:
        last_exc = e
        if attempt >= max_retries:
            break
        delay = base_delay * (2 ** attempt)
        logger.warning(f"{model_tier} 调用失败，{delay:.1f}s 后重试: {e}")
        time.sleep(delay)'''
    },
    {
        "part": 1,
        "num": "1.10",
        "title": "成本计量与预算检查（src/utils/cost_tracker.py）",
        "desc": "每次调用记录输入/输出 token 与耗时，按档位单价折算成人民币；预算检查发生在调用之前，超限直接抛异常中断，而不是事后提醒。单条记录通过独立连接异步落入 SQLite 数据库（llm_usage 表），保证进程退出不丢用量。",
        "location": "src/utils/cost_tracker.py  第 111-155 行",
        "code": '''def assert_budget(self) -> None:
    """预算硬闸：超支则抛 BudgetExceeded（发起新调用前调用）。"""
    if self._budget_cny > 0 and self.total_cost_cny >= self._budget_cny:
        raise BudgetExceeded(
            f"会话预算已用完：已花费 ¥{self.total_cost_cny:.4f} / 上限 ¥{self._budget_cny:.2f}。"
            "可调大 config.yaml budget.max_cny_per_session 或换更省模型。"
        )

def add_record(self, record: UsageRecord):
    record.use_pricing(self._pricing)
    with self._lock:
        self._records.append(record)
    logger.info(f"LLM 调用: {record}")
    self._persist(record)

def _persist(self, record: UsageRecord) -> None:
    """把单条记录写入 llm_usage 小库（尽力而为，失败不影响主流程）。"""
    if not self._usage_db_path:
        return
    try:
        if self._usage_conn is None:
            path = Path(self._usage_db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._usage_conn = sqlite3.connect(str(path))
            self._usage_conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_usage ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "model_tier TEXT, model TEXT, prompt_tokens INT,"
                "completion_tokens INT, cost_cny REAL, duration REAL, created_at TEXT)"
            )
            self._usage_conn.commit()
        self._usage_conn.execute(
            "INSERT INTO llm_usage (model_tier, model, prompt_tokens, completion_tokens,"
            " cost_cny, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            (record.model_tier, record.model, record.prompt_tokens,
             record.completion_tokens, round(record.cost_cny, 6),
             round(record.duration, 3),
             record.timestamp.strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._usage_conn.commit()
    except Exception as e:
        logger.debug(f"用量持久化失败: {e}")'''
    },
    # 第二部分
    {
        "part": 2,
        "num": "2.1",
        "title": "人格演进与关系网更新算法（src/novel/character_engine.py）",
        "desc": "算法要点：人格变化无条件落地（允许新维度生长），并做 0-10 夹紧与 null 兜底；「old」值以本地状态为准而不是采信模型；关系强度夹紧、起始章只在首次写入、本次变化作为「最近变化」留档。",
        "location": "src/novel/character_engine.py  第 802-870 行",
        "code": '''def _append_event(self, profile: CharacterProfile, char_data: dict,
                  chapter_num: int) -> None:
    """把本章分析落成事件，并更新人格与关系网。"""
    shifts: list[PersonalityShift] = []
    for raw in _as_list(char_data.get("personality_shifts")):
        if not isinstance(raw, dict):
            continue
        trait = _as_str(raw.get("trait")).strip()
        if not trait:
            continue
        current = (_to_int_0_10(profile.personality[trait])
                   if trait in profile.personality else None)
        shifts.append(PersonalityShift(
            trait=trait,
            old_value=current if current is not None else _to_int_0_10(raw.get("old")),
            new_value=_to_int_0_10(
                raw.get("new"), default=current if current is not None else SCORE_DEFAULT),
            reason=_as_str(raw.get("reason")),
        ))

    relationship_changes = [rc for rc in _as_list(char_data.get("relationship_changes"))
                            if isinstance(rc, dict)]

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
    profile.upsert_event(event)     # 同章替换；按章号有序

    for shift in shifts:
        profile.personality[shift.trait] = shift.new_value

    for change in relationship_changes:
        self._apply_relationship_change(profile, change, chapter_num)'''
    },
    {
        "part": 2,
        "num": "2.2",
        "title": "审稿响应的截断修复与解析（src/review_engine/base_agent.py）",
        "desc": "模型输出被 max_tokens 切断时，直接 json.loads 会整份丢弃，六个维度的审稿结果全没了。这里的补全器是「字符串感知」的：能区分字符串内部的括号与转义引号，只在真正未闭合的位置补括号。",
        "location": "src/review_engine/base_agent.py  第 32-81 行",
        "code": '''def _try_fix_truncated_json(text: str) -> Optional[dict]:
    """尝试修复被 max_tokens 截断的 JSON。"""
    import json
    depth = 0
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1

    if depth <= 0:
        return None  # 已闭合或缺少开头括号

    # 尝试补全：去掉末尾截断残余，然后补全未闭合字符串、数组与对象括号
    fixed = text.rstrip().rstrip(',').rstrip()
    if in_string:
        fixed += '"'
    arr_open = text.count('[') - text.count(']')
    if arr_open > 0:
        fixed += ']' * arr_open
    fixed += '}' * depth

    try:
        result = json.loads(fixed)
        if isinstance(result, dict):
            logger.info(f"截断 JSON 修复成功: 补全了 {depth} 个括号")
            return result
    except json.JSONDecodeError:
        pass
    return None'''
    },
    {
        "part": 2,
        "num": "2.3",
        "title": "三级修复算法（src/review_engine/fixer.py）",
        "desc": "修复分三种匹配策略：精确匹配 → 空白归一化后匹配 → 取前缀做子串匹配。Level-1 允许自动应用，Level-2 必须用户确认，Level-3 只输出指引不落笔。",
        "location": "src/review_engine/fixer.py  第 14-71 行",
        "code": '''def _find_and_replace(text: str, before: str, after: str, label: str) -> str:
    """在 text 中查找 before 并替换为 after，支持精确和模糊匹配。

    策略：
    1. 精确匹配 before
    2. 按空白归一化后匹配
    3. 取 before 的前 30 个字符作子串搜索
    """
    # 策略 1: 精确匹配
    if before in text:
        return text.replace(before, after, 1)

    # 策略 2: 按空白归一化后匹配
    import re as _re
    text_norm = _re.sub(r'\\s+', ' ', text)
    before_norm = _re.sub(r'\\s+', ' ', before)
    if before_norm in text_norm:
        idx = text_norm.index(before_norm)
        orig_before = text[idx:idx + len(before)]
        return text.replace(orig_before, after, 1)

    # 策略 3: 取 before 前 30 字符作子串搜索
    prefix = before[:30].strip()
    if len(prefix) > 10 and prefix in text:
        idx = text.index(prefix)
        matched_len = len(prefix)
        for j in range(len(prefix), min(len(before), len(text) - idx)):
            if text[idx:idx + j] == before[:j]:
                matched_len = j
            else:
                break
        orig_before = text[idx:idx + matched_len]
        return text.replace(orig_before, after, 1)

    logger.warning(f"修复失败: 未找到匹配文本 [{label}]: {before[:50]}")
    return text'''
    },
    {
        "part": 2,
        "num": "2.4",
        "title": "语料四层深度解构算法（src/analysis/deep.py）",
        "desc": "对同一段范文分四次调用，每次只聚焦一个维度（思想/结构/叙事/语言），而不是一次问四个问题。这样每个维度的输出更深，也更容易做类型校验与重试。",
        "location": "src/analysis/deep.py  第 35-89 行",
        "code": '''def analyze_all(self, text: str, source_id: str = "",
                model_tier: str = "pro") -> DeepAnalysis:
    """对素材做全部四层分析（四次独立调用）。"""
    result = DeepAnalysis()

    for layer, system_prompt in self._system_prompts.items():
        logger.info(f"深度分析 - {layer}层 [{source_id}] ({model_tier})")
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下文本：\\n\\n{text[:4000]}"},
            ]
            response = self.llm.chat(messages, model_tier=model_tier, temperature=0.4)
            parsed = self._parse_layer(layer, response)
            setattr(result, layer, parsed)
        except Exception as e:
            logger.warning(f"{layer}层分析失败 [{source_id}]: {e}")

    return result'''
    },
    {
        "part": 2,
        "num": "2.5",
        "title": "混合检索与 RRF 融合（src/knowledge_base/retriever.py）",
        "desc": "向量检索负责语义相近，BM25 负责关键词精确命中，两路结果用倒数排名融合（Reciprocal Rank Fusion）合并：每个结果的得分是各通道 1/(k+rank) 之和，k 取 60 以抑制头部垄断。",
        "location": "src/knowledge_base/retriever.py  第 11-58 行",
        "code": '''def hybrid_search(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
    vector_results = self.vector_search(query, top_k=top_k)
    bm25_results = self.bm25_search(query, top_k=top_k)
    rrf_k = 60
    scores = {}
    for rank, r in enumerate(vector_results):
        scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (rrf_k + rank + 1)
    for rank, r in enumerate(bm25_results):
        scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (rrf_k + rank + 1)
    all_results = {}
    for r in vector_results + bm25_results:
        if r.chunk_id not in all_results:
            all_results[r.chunk_id] = r
    sorted_results = sorted(
        all_results.values(),
        key=lambda r: scores.get(r.chunk_id, 0), reverse=True,
    )
    for r in sorted_results:
        r.score = scores.get(r.chunk_id, 0)
        r.source = "hybrid"
    return sorted_results[:top_k]'''
    },
    {
        "part": 2,
        "num": "2.6",
        "title": "角色结构化抽取（src/analysis/character_analyzer.py）",
        "desc": "从语料的分析结果中抽取角色时，模型可能返回数组、也可能是单个对象；字段可能缺失。这里对两种形态都做兼容，并对解析失败做规则兜底。",
        "location": "src/analysis/character_analyzer.py  第 135-171 行",
        "code": '''def _parse_characters(self, response: str, source_file: str) -> list[Character]:
    """解析 LLM 返回的角色 JSON。"""
    chars = []
    try:
        data = json.loads(response)
        char_list = data if isinstance(data, list) else [data]

        for item in char_list:
            name = item.get("name", "")
            if not name:
                continue

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
            rel_summary = item.get("relationship_summary", {})
            for target, desc in rel_summary.items():
                char.relationship_map[target] = desc
            chars.append(char)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"角色JSON解析失败: {e}")
    return chars'''
    },
    {
        "part": 2,
        "num": "2.7",
        "title": "语料清洗与分块算法（src/preprocessing/pipeline.py）",
        "desc": "分块是检索质量的地基：先做编码统一与噪声清洗，再按空行切段，过滤过短或无意义的段落，最后生成带稳定 ID 的块。ID 的稳定性决定了重复导入时是否会互相覆盖。",
        "location": "src/preprocessing/pipeline.py  第 33-86 行",
        "code": '''def clean_text(self, text: str) -> str:
    """清洗文本噪音。"""
    text = re.sub(r'[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]', '', text)
    text = text.replace('\\r\\n', '\\n').replace('\\r', '\\n')
    text = re.sub(r'\\n{3,}', '\\n\\n', text)
    return text.strip()

def split_paragraphs(self, text: str) -> list[str]:
    """按空行分割段落。"""
    paragraphs = re.split(r'\\n\\s*\\n', text)
    return [p.strip() for p in paragraphs if p.strip()]

def create_chunk(self, text: str, source_file: str,
                 para_index: int, chapter: str = "") -> Chunk:
    """创建段落块。"""
    chunk_id = f"{Path(source_file).stem}_{para_index:05d}"
    return Chunk(
        chunk_id=chunk_id,
        source_file=source_file,
        text=text,
        char_count=len(text),
        paragraph_index=para_index,
        chapter_path=chapter,
    )'''
    }
]


def add_custom_cover(doc, doc_title: str, doc_sub: str, info_lines):
    """绘制标准规范封面。"""
    p_main = doc.add_paragraph()
    p_main.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_main.paragraph_format.space_before = Pt(36)
    p_main.paragraph_format.space_after = Pt(12)
    r_main = p_main.add_run(doc_title)
    r_main.font.name = 'SimHei'
    r_main.font.size = Pt(22)
    r_main.font.bold = True
    r_main.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(40)
    r_sub = p_sub.add_run(doc_sub)
    r_sub.font.name = 'SimHei'
    r_sub.font.size = Pt(16)
    r_sub.font.bold = True
    r_sub.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

    table = doc.add_table(rows=len(info_lines), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (label, val) in enumerate(info_lines):
        cell_lbl, cell_val = table.rows[i].cells
        cell_lbl.width = Inches(1.5)
        cell_val.width = Inches(4.8)

        p_lbl = cell_lbl.paragraphs[0]
        p_lbl.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_lbl.paragraph_format.line_spacing = 1.3
        p_lbl.paragraph_format.space_after = Pt(4)
        r_lbl = p_lbl.add_run(label)
        r_lbl.font.name = 'SimHei'
        r_lbl.font.size = Pt(10.5)
        r_lbl.font.bold = True

        p_val = cell_val.paragraphs[0]
        p_val.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_val.paragraph_format.line_spacing = 1.3
        p_val.paragraph_format.space_after = Pt(4)
        r_val = p_val.add_run(val)
        r_val.font.name = 'SimSun'
        r_val.font.size = Pt(10.5)
        if "题目" in label:
            r_val.font.underline = True
    doc.add_page_break()


def generate_docx(cfg: dict, out_path: Path):
    doc = docx.Document()
    apply_document_styles(doc)

    # 1. 封面
    add_custom_cover(doc, "《计算机系统项目综合实践》", cfg["doc_sub"], cfg["contributions"])

    # 2. 导读
    add_callout(doc, cfg["guide"], "【源代码文档导读】")

    # 3. 第一部分：核心系统代码
    add_heading_1(doc, "第一部分：核心系统代码")
    for sec in [s for s in CODE_SECTIONS if s["part"] == 1]:
        add_heading_2(doc, f"{sec['num']} {sec['title']}")
        add_body_p(doc, sec["desc"])
        add_code_block(doc, sec["code"], sec["location"])

    # 4. 第二部分：核心算法代码
    add_heading_1(doc, "第二部分：核心算法代码")
    for sec in [s for s in CODE_SECTIONS if s["part"] == 2]:
        add_heading_2(doc, f"{sec['num']} {sec['title']}")
        add_body_p(doc, sec["desc"])
        add_code_block(doc, sec["code"], sec["location"])

    doc.save(str(out_path))
    print(f"[OK] 生成 Word 文档: {out_path.name}")


def generate_md(cfg: dict, out_path: Path):
    lines = []
    lines.append("《计算机系统项目综合实践》")
    lines.append(f"{cfg['doc_sub']}\n")
    lines.append("| 表头项 | 详细内容 |")
    lines.append("|---|---|")
    for lbl, val in cfg["contributions"]:
        lines.append(f"| {lbl.strip()} | {val.strip()} |")
    lines.append("\n---\n")
    lines.append(f"**{cfg['guide']}**\n")
    lines.append("---\n")

    lines.append("# 第一部分：核心系统代码\n")
    for sec in [s for s in CODE_SECTIONS if s["part"] == 1]:
        lines.append(f"## {sec['num']} {sec['title']}")
        lines.append(f"{sec['desc']}\n")
        lines.append(f"`{sec['location']}`\n")
        lines.append("```python")
        lines.append(sec["code"].strip())
        lines.append("```\n")

    lines.append("# 第二部分：核心算法代码\n")
    for sec in [s for s in CODE_SECTIONS if s["part"] == 2]:
        lines.append(f"## {sec['num']} {sec['title']}")
        lines.append(f"{sec['desc']}\n")
        lines.append(f"`{sec['location']}`\n")
        lines.append("```python")
        lines.append(sec["code"].strip())
        lines.append("```\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 生成 Markdown 文档: {out_path.name}")


def main():
    for cfg in WEEKS_CONFIG:
        docx_name = f"4、计科2302班句昭南等四人计算机系统项目源代码({cfg['file_suffix']}).docx"
        md_name = f"4、计科2302班句昭南等四人计算机系统项目源代码({cfg['file_suffix']}).md"

        # 写入 course_materials/submissions
        p_docx = SUBMISSIONS_DIR / docx_name
        p_md = SUBMISSIONS_DIR / md_name
        generate_docx(cfg, p_docx)
        generate_md(cfg, p_md)

        # 复制到 Desktop 目录
        (DESKTOP_DIR / docx_name).write_bytes(p_docx.read_bytes())
        (DESKTOP_DIR / md_name).write_text(p_md.read_text(encoding="utf-8"), encoding="utf-8")

    # 兼容覆盖原默认文件（以第10周结题版为默认全量基准）
    legacy_docx = SUBMISSIONS_DIR / "4、计科xx班组长学号组长姓名计算机系统项目.docx"
    legacy_docx.write_bytes((SUBMISSIONS_DIR / "4、计科2302班句昭南等四人计算机系统项目源代码(第10周结题版).docx").read_bytes())
    print("[OK] 已同步更新默认命名文件！")


if __name__ == "__main__":
    main()
