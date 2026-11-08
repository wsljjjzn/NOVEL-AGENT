"""
scripts/generate_all_weekly_logs.py — 按照学校周志模板，为四位组员各生成一份完整的科研实践周志 (Excel)。
生成包含：
1. 包含 4 个独立 Sheet 的合并工作簿
2. 4 份独立的个人提交工作簿
"""

import csv
import io
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "course_materials" / "templates" / "3、计科xx班组长学号组长姓名计算机系统项目.xlsx"
SUBMISSIONS_DIR = ROOT / "course_materials" / "submissions"
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV = """周次,指导时间,"句昭南
2023011210","熊宇浩
2023011216","姜卓远
2023011213","胡睿涵
2023011215",本周实践中出现的问题,调整方式
第 1 周,"2026.09.08
至
2026.09.13",【选题论证与环境搭建】完成大模型长篇写作四类失效的归因（注意力衰减、人格漂移、伏笔断链、设定冲突），确定「确定性领域层 + 生成层」分离的总体路线，产出立项说明。,【角色一致性调研】对比 NovelAI、Sudowrite 等工具的角色卡做法，确认其实质是静态文本、不随剧情演化，提出「人格数值 + 逐章事件」的状态化角色模型。,【交互形态调研】对比命令行、终端 UI、Web、桌面四种形态，确定「命令行批处理 + 终端沉浸写作 + Web 演示」三端组合；搭好 uv 环境与依赖分层基线。,【上下文策略调研】研究「模型实际看到了什么」对生成质量的影响，整理 5 个真实工程作为回归样本，提出按需切片而非整篇塞入的注入原则。,现有工具普遍把大段前文整段塞进提示词，成本高且互相干扰；没有任何可量化的一致性基线，无法判断「哪一章写崩了」。,确立「状态外部化」：角色、关系、伏笔全部落到本地数据结构，提示词只注入该章需要的切片；并把真实工程固化为回归样本。
第 2 周,"2026.09.14
至
2026.09.20",【总体架构与需求】划定六层依赖方向，写下三条架构约束（领域层零 LLM 依赖、单一 LLM 出口、操作契约唯一），拆出 P0-P3 四阶段与验收标准，产出需求规格与阶段计划。,【角色模型设计】设计角色档案、章节事件、人格变化三类结构，确定关系网字段（状态/强度/起始章/最近变化），把所有可比较的维度量化到 0-10。,【交互原型与信息架构】确定工作台五个页签（章节/大纲/角色/剧情/伏笔）+ 实时日志面板，设计与「会花钱动作」的二次确认流程。,【上下文契约设计】定义角色切片、前情提要、本章大纲、写作要求四段上下文的格式、顺序与长度上限，明确各段由谁负责生成。,四个入口各自实现一套编排，护栏无法复用；早期打算「一次做全」，同时开 MCP、向量检索、Web 前端，每条线都半成品。,把编排收敛到服务层一处，四端只做参数收集与渲染；改为按 P0→P3 分批推进，每批有明确的验收命令。
第 3 周,"2026.09.21
至
2026.09.27",【领域层：工程管理】实现项目创建/加载/保存/导出、章节增改、大纲与标题维护、字数统计；定义三个 JSON 的字段契约与读写规则。,【角色模型落地】把角色模型迁到 pydantic，并在字段上挂校验器：人格与关系强度折算到 0-10、章号强制转整数、列表字段遇 null 退化为空表。,【终端界面骨架】实现项目列表、工作台框架与页签切换；接入 Key 状态与本次会话费用显示。,【前情提要算法】实现「上一章结尾 200 字 + 最近三章摘要 + 未解伏笔清单」的提要生成，并标定各段的截断长度。,"模型返回的章号是字符串（""chapter"": ""3""），排序与比较会抛 TypeError，章节列表与详情页一起崩；用文件名做块 ID 还会导致同名文件互相覆盖。",章号在读入边界统一归一化为非负整数，不改落盘格式、历史数据无需迁移；写操作统一走「加载—修改—保存」的短临界区。
第 4 周,"2026.09.28
至
2026.10.04",【写作闭环接口】把「写正文 → 写后分析 → 状态回写 → 下一章」串成闭环，定义写作器与角色引擎之间的接口与返回值语义。,【角色状态机】实现逐章事件写入、人格与关系更新、按章取状态；用真实存档做审计，统计重复章号、越界值、同角色多档案等指标。,【命令行适配】实现 novel / article / kb 三组命令，统一退出码语义（成功 0 / 失败 1），把四条小说命令改调服务层。,【角色切片筛选】设计四级筛选：主角/反派永远保留 → 本章指定出场 → 尚未上场 → 最近三章有事件，其余裁掉；保留「筛选为空则全给」的兜底。,真实存档里同一角色被写成「林雪」「林雪（妹妹）」「林雪（信号源）」三个档案，上下文出现三张互相矛盾的角色卡；人格变化只记录进事件、从不落到人格字典。,加入名字三级归并（精确 → 别名 → 归一化去括号）并记住新写法；人格变化无条件落地，允许新维度生长，同时做夹紧与 null 兜底。
第 5 周,"2026.10.05
至
2026.10.11",【逐章写作管线】实现 ChapterWriter：装配上下文、调用模型、空响应拦截、落盘、触发写后分析；把「空文本不写入」定为硬规则。,【原子写与容错读】把角色档案写入改为临时文件 + os.replace 原子替换；读取改为字段级兜底，单条记录损坏只跳过或补默认值。,【写作与阅读界面】实现写作表单、正文章节阅读器、生成中的后台线程与完成事件回写，避免界面假死。,【上下文装配实测】在 50 章真实工程上测量装配耗时与提示词规模，验证「信息预算」假设。,模型偶发返回空文本，早期会写入 0 字的「幽灵章节」污染工程；全部 27 个角色注入时，提示词近 5000 字，出现无关角色抢戏、主角动机被稀释。,空响应一律不落盘并转成失败结果；角色改为四级筛选后提示词降到 1500-2500 字。实测整章装配 0.22 ms、切片 0.15 ms，瓶颈完全在远端调用。
第 6 周,"2026.10.12
至
2026.10.18",【剧情与伏笔接入】把单章剧情设计（钩子/场景/高潮/结尾/情感曲线）注入写作提示词；实现伏笔台账：埋下进开放列表、回收自动销账、未回收随前情提要注入。,【审稿解析与截断修复】实现审稿 Agent 的响应解析与 Level-1/2/3 分类；实现「字符串感知」的括号补全，救回被 max_tokens 截断的结果。,【剧情与伏笔界面】实现剧情笔记编辑、伏笔页签展示、大纲条目手工修改（均为本地操作、不花钱）。,【角色卡片校准】逐项核对每张角色卡实际包含哪些字段，确认模型是否看得到角色的核心动机。,有过章节事件之后，角色卡就不再输出核心欲望、核心恐惧、背景、外貌，模型看不到角色「想要什么、怕什么」，行为自然前后不一；截断的审稿 JSON 会被整份丢弃。,角色卡改为无条件输出全部一致性锚点，并附别名与最近三章事件；截断修复区分字符串内括号与转义引号，只在真正未闭合处补括号。
第 7 周,"2026.10.19
至
2026.10.25",【服务层护栏】补齐覆盖前自动备份、批量续写从第一个未写章节开始、任一章失败即停、空结果一律报失败；删除命令行与界面里的重复编排。,【三级修复与报告】实现 Level-1 自动替换、Level-2 确认后替换、Level-3 仅指引；生成按 Agent 汇总的 Markdown 审稿报告。,【可视化界面与 REST】实现写作/审稿端点与一套可视化界面，与命令行、终端共享同一服务层。,【审稿用例核对】为六维审稿准备固定输入，核对每条 issue 的等级、定位与建议是否可复现。,命令行与可视化界面各有一套编排：一个有备份与「只往后写」，另一个会把已有正文从第 1 章重写；多处字符串替换会产生索引漂移，甚至吞掉换行。,删除重复编排、全部改调服务层，护栏只写一遍；修复按风险分级——机械级自动改，润色级必须人工确认，结构级只给建议。
第 8 周,"2026.10.26
至
2026.11.01",【多端一致与费用护栏】统一四端的失败语义（ok=False），把成本计量、人民币换算、会话预算硬闸接入；核对四端行为一致。,【角色引擎测试】补齐 50 个角色引擎用例：夹紧与兜底、名字归并、事件去重排序、原子写与容错读、四种分析状态、上下文筛选。,【费用面板与预算拦截】把 Token 计量与费用展示接入状态栏；接入调用前的预算硬闸，超限直接中断而不是事后提醒。,【往返基线】用真实存档做「读入—序列化—写回—比对」，锁定四类落盘差异（未知字段、章号类型、空值、排序）。,界面侧持有全局内存态，别人在命令行写完一章后，界面上再保存会把新章节覆盖掉；费用统计只在内存里，进程退出就没了，也没有任何硬性拦截。,所有写操作改为先读盘再改再保存，界面不再缓存业务状态；用量同时写入独立的 SQLite 小库，预算检查放在调用前。
第 9 周,"2026.11.02
至
2026.11.08","【真实样本回归】在 50 章 / 88,809 字工程上做全链路回归，整理缺陷台账（9 类静默错误及其修复方式），核对文档与代码是否一致。",【缺陷复核】把审计发现的 9 类缺陷逐条复现、修复并写成回归用例，确认改回去会立刻失败。,【四端冒烟】四端逐个走一遍主流程，核对退出码、错误提示、二次确认与「失败不显示成功」。,【用例复核与校准】逐条复核 277 个用例，找出恒真断言与「把 bug 当预期」的用例并修正。,部分历史用例自己重写了一遍生产逻辑再断言，测的是测试自己；还有用例把「重复 ID 被忽略」断言成正确行为。文档里也出现「写着已修复、代码其实没有」的情况。,改为调用真实函数并断言产品行为；对齐修复后的语义（解析失败应返回状态码而非空列表）；以代码为准修正文档，并把「已知未完成项」单列成章。
第 10 周,"2026.11.09
至
2026.11.15",【收尾与交付】整合架构、模块、契约三份设计文档，完成报告书与课程报告，准备答辩材料（架构讲解 + 现场演示脚本）。,【角色引擎文档】补写角色状态机的归并、去重、夹紧、原子写与上下文筛选说明，把 50 个用例的覆盖点整理成表。,【演示与打磨】录制四端演示流程，修正界面排版与提示文案，核对未配置 Key 时的拦截表现。,【测试报告与校对】汇总 277 个用例的分布与结论，复核四份文档中的数据（代码行数、用例数、时延、成本）与仓库一致。,时间紧，MCP 服务器、操作契约层与模型无关层未能落地；若在文档中写成已完成，答辩对照代码会被直接问穿。,如实设为「设计目标 vs 当前进度」，在第 1 份文档单列一章说明差距与下一步计划，不作已完成表述。
"""

STUDENTS = [
    {"name": "句昭南", "id": "2023011210", "col_idx": 2, "role": "组长"},
    {"name": "熊宇浩", "id": "2023011216", "col_idx": 3, "role": "组员"},
    {"name": "姜卓远", "id": "2023011213", "col_idx": 4, "role": "组员"},
    {"name": "胡睿涵", "id": "2023011215", "col_idx": 5, "role": "组员"},
]

COMMON_INFO = {
    "year": "2026-2027",
    "term": 1,
    "course_no": "（按教务系统填写）",
    "course_name": "计算机系统项目综合实践",
    "teacher_name": "指导教师",
    "teacher_dept": "计算机学院",
    "date_range": "2026.09.08 - 2026.11.15",
    "location": "实验楼机房 / 线上",
    "project_title": "面向长篇文学创作的智能辅助系统设计与实现（Novel Studio）",
    "major": "计算机科学与技术（计科2302班）",
}


def populate_sheet(ws, student, weekly_rows):
    """根据学生信息与周志数据填充指定 worksheet。"""
    # 1. 基础元数据填充
    ws["B2"] = COMMON_INFO["year"]
    ws["E2"] = COMMON_INFO["term"]
    ws["G2"] = COMMON_INFO["course_no"]
    ws["N2"] = COMMON_INFO["course_name"]

    ws["B3"] = COMMON_INFO["teacher_name"]
    ws["E3"] = COMMON_INFO["teacher_dept"]
    ws["J3"] = COMMON_INFO["date_range"]
    ws["N3"] = COMMON_INFO["location"]

    ws["C5"] = student["name"]
    ws["I5"] = COMMON_INFO["project_title"]

    ws["C6"] = student["id"]
    ws["I6"] = COMMON_INFO["major"]

    # 样式配置
    thin_side = Side(border_style="thin", color="000000")
    cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    song_95 = Font(name="宋体", size=9.5)
    song_90 = Font(name="宋体", size=9.0)

    # 2. 填充 10 周内容 (Row 8 至 Row 17)
    for i, row in enumerate(weekly_rows):
        r = 8 + i
        week_num = row[0]
        time_str = row[1]
        content_str = row[student["col_idx"]]
        problem_str = row[6]
        adjust_str = row[7]

        # 写入左上角主单元格
        ws[f"A{r}"] = week_num
        ws[f"C{r}"] = time_str
        ws[f"E{r}"] = content_str
        ws[f"I{r}"] = problem_str
        ws[f"M{r}"] = adjust_str

        # 格式化周次与指导时间
        ws[f"A{r}"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws[f"A{r}"].font = song_95
        ws[f"C{r}"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws[f"C{r}"].font = song_90

        # 格式化文本内容
        for col_l in ["E", "I", "M"]:
            ws[f"{col_l}{r}"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            ws[f"{col_l}{r}"].font = song_95

        # 确保所有合并单元格内部具备完整边框
        for col in range(1, 16):
            cell = ws.cell(r, col)
            cell.border = cell_border
            if cell.font is None or cell.font.name != "宋体":
                cell.font = song_95

        # 根据文本长度动态计算合适的行高 (保证打印和查看不遮挡)
        max_chars = max(len(content_str), len(problem_str), len(adjust_str))
        lines_est = max(3, max_chars // 22 + 1)
        ws.row_dimensions[r].height = max(56.0, lines_est * 16.0)

    # 3. 清理模板原本多余的空白合并行 (Row 18-20)
    ranges_to_remove = [rng for rng in ws.merged_cells.ranges if rng.min_row >= 18]
    for rng in ranges_to_remove:
        ws.unmerge_cells(str(rng))
    if ws.max_row > 17:
        ws.delete_rows(18, ws.max_row - 17)


def generate_all():
    reader = csv.reader(io.StringIO(RAW_CSV.strip()))
    weekly_rows = list(reader)[1:]  # 跳过表头

    # -------------------------------------------------------------
    # 1. 生成四人合并版工作簿 (4 个独立 Sheet)
    # -------------------------------------------------------------
    combo_wb = openpyxl.load_workbook(TEMPLATE_PATH)
    template_sheet = combo_wb["Sheet1"]

    # 删除模板中默认的空 Sheet2, Sheet3
    for s_name in ["Sheet2", "Sheet3"]:
        if s_name in combo_wb.sheetnames:
            combo_wb.remove(combo_wb[s_name])

    for i, stu in enumerate(STUDENTS):
        if i == 0:
            target_ws = template_sheet
            target_ws.title = f"{stu['name']}-{stu['id']}"
        else:
            target_ws = combo_wb.copy_worksheet(template_sheet)
            target_ws.title = f"{stu['name']}-{stu['id']}"
        populate_sheet(target_ws, stu, weekly_rows)

    combo_path = SUBMISSIONS_DIR / "3、计科2302班句昭南等四人计算机系统项目周志(合并版).xlsx"
    combo_wb.save(combo_path)
    print(f"[OK] 已生成四人合并工作簿: {combo_path}")

    # 同时同步覆盖原始默认名字文件，确保原有脚本和路径完整兼容
    legacy_path = SUBMISSIONS_DIR / "3、计科xx班组长学号组长姓名计算机系统项目.xlsx"
    combo_wb.save(legacy_path)
    print(f"[OK] 已同步更新默认命名文件: {legacy_path}")

    # -------------------------------------------------------------
    # 2. 为每位组员分别生成一份独立的单人工作簿 (一人一表)
    # -------------------------------------------------------------
    for stu in STUDENTS:
        single_wb = openpyxl.load_workbook(TEMPLATE_PATH)
        for s_name in ["Sheet2", "Sheet3"]:
            if s_name in single_wb.sheetnames:
                single_wb.remove(single_wb[s_name])
        ws = single_wb["Sheet1"]
        ws.title = f"{stu['name']}-{stu['id']}"
        populate_sheet(ws, stu, weekly_rows)

        out_name = f"3、计科2302班{stu['id']}{stu['name']}计算机系统项目周志.xlsx"
        out_path = SUBMISSIONS_DIR / out_name
        single_wb.save(out_path)
        print(f"[OK] 已生成单人独立工作簿: {out_path.name}")


if __name__ == "__main__":
    generate_all()
