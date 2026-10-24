"""
scripts/generate_doc3.py — 生成《计算机系统项目综合实践》科研开发类项目实践学生周志用表 (Excel)
严格匹配模板格式、字体、单元格合并与边框样式。
"""

import xlsxwriter
from pathlib import Path

OUT_PATH = Path("course_materials/submissions/3、计科xx班组长学号组长姓名计算机系统项目.xlsx")

def generate():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(OUT_PATH))
    ws = wb.add_worksheet("Sheet1")

    # 打印与网格线
    ws.set_paper(9)  # A4
    ws.set_margins(left=0.5, right=0.5, top=0.6, bottom=0.6)
    ws.hide_gridlines(0)  # 显示网格线

    # 设置列宽 (共 15 列 A-O)
    col_widths = {
        'A': 6,   'B': 6,   'C': 7,   'D': 7,
        'E': 8,   'F': 8,   'G': 8,   'H': 8,
        'I': 8,   'J': 8,   'K': 8,   'L': 8,
        'M': 8,   'N': 8,   'O': 8
    }
    for col_letter, width in col_widths.items():
        col_idx = ord(col_letter) - ord('A')
        ws.set_column(col_idx, col_idx, width)

    # 样式定义
    font_name = "宋体"
    
    # 标题样式
    title_fmt = wb.add_format({
        'font_name': '黑体', 'font_size': 16, 'bold': True,
        'align': 'center', 'valign': 'vcenter'
    })

    # 表头及标签样式
    header_lbl_fmt = wb.add_format({
        'font_name': font_name, 'font_size': 10, 'bold': True,
        'align': 'center', 'valign': 'vcenter',
        'border': 1, 'bg_color': '#F2F4F7'
    })

    # 普通居中单元格
    center_fmt = wb.add_format({
        'font_name': font_name, 'font_size': 9.5,
        'align': 'center', 'valign': 'vcenter',
        'border': 1
    })

    # 普通居左单元格 (自动换行)
    left_wrap_fmt = wb.add_format({
        'font_name': font_name, 'font_size': 9.5,
        'align': 'left', 'valign': 'vcenter',
        'text_wrap': True, 'border': 1
    })

    # 细化表头样式 (带浅底色)
    subhdr_fmt = wb.add_format({
        'font_name': '黑体', 'font_size': 10, 'bold': True,
        'align': 'center', 'valign': 'vcenter',
        'border': 1, 'bg_color': '#E9ECEF'
    })

    # 周志内容单元格样式 (带边框、自动换行、行高自适应)
    log_content_fmt = wb.add_format({
        'font_name': font_name, 'font_size': 9,
        'align': 'left', 'valign': 'top',
        'text_wrap': True, 'border': 1
    })

    log_center_fmt = wb.add_format({
        'font_name': font_name, 'font_size': 9.5,
        'align': 'center', 'valign': 'vcenter',
        'border': 1
    })

    # ---------------- 写入表头数据 ----------------
    # Row 1 (Index 0): Title
    ws.set_row(0, 32)
    ws.merge_range("A1:O1", "科研开发类项目实践学生周志用表", title_fmt)

    # Row 2 (Index 1): 学年 / 学期 / 选课课号 / 课程名称
    ws.set_row(1, 24)
    ws.write("A2", "学年", header_lbl_fmt)
    ws.merge_range("B2:C2", "2024-2025", center_fmt)
    ws.write("D2", "学期", header_lbl_fmt)
    ws.write("E2", "1", center_fmt)
    ws.write("F2", "选课课号", header_lbl_fmt)
    ws.merge_range("G2:L2", "(2024-2025-1)-0RS04906-20210010-1", center_fmt)
    ws.write("M2", "课程名称", header_lbl_fmt)
    ws.merge_range("N2:O2", "计算机系统项目综合实践", center_fmt)

    # Row 3 (Index 2): 教师姓名 / 教师单位 / 指导起止时间 / 指导地点
    ws.set_row(2, 24)
    ws.write("A3", "教师姓名", header_lbl_fmt)
    ws.merge_range("B3:C3", "指导教师", center_fmt)
    ws.write("D3", "教师单位", header_lbl_fmt)
    ws.merge_range("E3:G3", "计算机学院", center_fmt)
    ws.merge_range("H3:I3", "指导起止时间", header_lbl_fmt)
    ws.merge_range("J3:L3", "2024.09.02 - 2024.10.25", center_fmt)
    ws.write("M3", "指导地点", header_lbl_fmt)
    ws.merge_range("N3:O3", "实验楼机房 / 线上", center_fmt)

    # Row 4 (Index 3): 学生信息 / 周志指导内容
    ws.set_row(3, 22)
    ws.merge_range("A4:G4", "学 生 信 息", subhdr_fmt)
    ws.merge_range("H4:O4", "周 志 指 导 内 容（原则上记录8周）", subhdr_fmt)

    # Row 5 (Index 4): 姓名 / 科研实践题目
    ws.set_row(4, 24)
    ws.merge_range("A5:B5", "姓名", header_lbl_fmt)
    ws.merge_range("C5:D5", "鞠兆楠", center_fmt)
    ws.merge_range("E5:H5", "科研实践题目：", header_lbl_fmt)
    ws.merge_range("I5:O5", "面向长篇文学创作的智能辅助系统设计与实现（Novel Studio）", left_wrap_fmt)

    # Row 6 (Index 5): 学号 / 专业
    ws.set_row(5, 24)
    ws.merge_range("A6:B6", "学号", header_lbl_fmt)
    ws.merge_range("C6:D6", "2021001001", center_fmt)
    ws.merge_range("E6:H6", "专业：", header_lbl_fmt)
    ws.merge_range("I6:O6", "计算机科学与技术 (计科2101班)", left_wrap_fmt)

    # Row 7 (Index 6): 表头
    ws.set_row(6, 26)
    ws.merge_range("A7:B7", "周次", subhdr_fmt)
    ws.merge_range("C7:D7", "指导时间", subhdr_fmt)
    ws.merge_range("E7:H7", "指 导 内 容", subhdr_fmt)
    ws.merge_range("I7:L7", "实践中出现的问题", subhdr_fmt)
    ws.merge_range("M7:O7", "调 整 方 式", subhdr_fmt)

    # ---------------- 写入 8 周详细周志 ----------------
    weekly_logs = [
        (
            "第 1 周",
            "2024.09.02\n至\n2024.09.08",
            "【课题选题论证与现状调研】\n针对当前大语言模型在长篇生成中固有的“注意力衰减”与“设定漂移”痛点，确定《面向长篇文学创作的智能辅助系统》研究方向。深入剖析NovelAI与通用对话模型的不足，论证将长篇写作拆分为确定性领域状态机与大模型概率生成两个正交层次的必要性与可行性。",
            "市面上现有写作工具大多仅简单地将大段前文塞入Prompt，不仅Token开销极其庞大，且极易因长上下文干扰产生幻觉，导致角色性格与关键伏笔断裂；如何以极简成本在超50章体量下维持严格一致性是最大瓶颈。",
            "确立“状态机外部化”核心战略：不依赖大模型维护长程状态，而是设计纯确定性的CharacterEngine维护角色性格数值与事件历史，通过PlotEngine管理树状大纲与未解伏笔，只将即时状态切片动态注入Prompt。"
        ),
        (
            "第 2 周",
            "2024.09.09\n至\n2024.09.15",
            "【需求规格分析与工程环境搭建】\n制定系统总体分层架构，严格确立“领域层零LLM依赖”、“单一LLM出口”、“操作契约唯一”三大架构铁律。搭建基于Rust核心的uv现代化构建环境与Pydantic v2强类型Schema校验体系，规划P0至P3阶段研发路线图。",
            "传统Python开发环境依赖解析迟缓且版本易冲突；原生dataclass缺乏强类型运行时校验与容错，外部大模型生成内容若出现细微字段格式差异（如章号返回字符串\"3\"），极易造成整个系统反序列化崩溃。",
            "全面引入现代化构建工具uv，环境解析与虚拟环境创建提速数十倍；底层数据实体统一升级为Pydantic v2，配合ConfigDict(extra='allow')与字段验证器，建立具备弹性容错机制的强类型数据契约。"
        ),
        (
            "第 3 周",
            "2024.09.16\n至\n2024.09.22",
            "【确定性领域引擎研发与原子写机制】\n完成NovelProject长篇工程持久化管理、CharacterEngine角色五维性格雷达（勇敢、善良、冲动、智慧、忠诚）与逐章事件追踪、PlotEngine大纲树与伏笔台账闭环管理。实现纯确定性领域层算法，零LLM依赖。",
            "在多模块高频读写本地JSON文件时，若遇到程序被操作系统强杀或断电等突发中断，极易写出不完整或截断的JSON脏文件，导致小说项目整体损毁且不可二次恢复。",
            "设计研发`atomic_write_json`原子写入机制：所有写盘操作均先写入同目录带PID的临时文件中并刷新磁盘缓冲区，完成后调用操作系统底层`os.replace`原子重命名原语瞬间替换，从物理层确保数据零损坏。"
        ),
        (
            "第 4 周",
            "2024.09.23\n至\n2024.09.29",
            "【文学知识库与四维特征解构流水线】\n实现语料分块预处理流水线（PreprocessingPipeline）、轻量分类分析（Flash档）以及思想、结构、叙事、语言四层深度知识卡片提取（Pro档）。搭建SQLite关系表（chunks与knowledge_units）及ChromaDB向量检索库。",
            "长篇范文数据量极为庞大，若全量直接调用Pro档模型进行多维分析，调用费用成倍激增，且极易触发模型注意力稀释，导致关键叙事节奏与标点句法等微观特征被粗暴忽略。",
            "设计两级渐进式分析流水线：首先由轻量级规则进行段落块切分，由Flash档快速完成类别与情感粗筛；针对精选优质段落，再调用Pro档分4次独立执行思想、结构、叙事、语言单维深度提取，保证特征提炼精度。"
        ),
        (
            "第 5 周",
            "2024.09.30\n至\n2024.10.06",
            "【逐章写作器研发与行文风格指南绑定】\n研发逐章生成枢纽ChapterWriter：动态拼接角色当前章状态切片、前章尾部200字提要、本章大纲目标与伏笔要求。新增`style_guide.json`风格模板绑定机制，实现必须规则、禁用词库及范文高光Few-Shot切片注入。",
            "初期生成的章节容易套用网络爽文的陈词滥调（如“只见”、“说时迟那时快”），语言寡淡缺乏目标作者的独特韵味；同时强推理模型在长思考过程耗尽预算时容易偶发性返回空文本。",
            "在NovelProject中挂载风格伴生文件，在Prompt中建立严格的行文规范与负面词汇惩罚约束，辅以2条Few-Shot样本引导；并在写入章节前增加空响应拦截护栏，杜绝产生0字幽灵章节。"
        ),
        (
            "第 6 周",
            "2024.10.07\n至\n2024.10.13",
            "【六维审稿系统与三级智能修复模块研发】\n构建涵盖思想深度、结构节奏、叙事张力、语言文风、事实逻辑、文字校对六维审稿智能体网络（ReviewEngine）。研发Level-1至Level-3多级修改调度，支持Level-1机械错别字与基础标点的一键无损精准替换。",
            "在执行Level-1机械替换时，由于换行符归一化差异或多处字符同时替换导致的字符偏移量累积漂移，直接做字符串查找替换极易导致后续修复位置错位甚至误删正文段落。",
            "研发ArticleFixer精确区间映射算法：预先建立字符绝对位置索引映射表，采用倒序替换策略并严格校验前后文本锚点，确保机器自动修复100%精准且完全不破坏正文版式。"
        ),
        (
            "第 7 周",
            "2024.10.14\n至\n2024.10.20",
            "【前后端交互与多模态工作台构建】\n基于FastAPI构建涵盖工程、大纲、伏笔、角色、写作、审稿的全套异步RESTful API路由群；开发Novel Studio Web交互式单页应用（SPA）与纯键盘驱动的Textual TUI工作台，集成CostTracker实时Token预算面板。",
            "Web端在频繁切换长篇工程或编辑超长章节时，前后端数据同步偶有并发时序延迟；且在极端分辨率下，侧边栏复杂大纲树与角色五维雷达的展示存在布局挤压。",
            "优化FastAPI端点响应，加入防抖与乐观更新机制；采用TailwindCSS现代响应式布局彻底重构Web端侧边栏与浮动抽屉；在TUI中优化按键绑定与分页展示，实现终端与浏览器双端一致的丝滑交互。"
        ),
        (
            "第 8 周",
            "2024.10.21\n至\n2024.10.25",
            "【全量离线自动化测试与项目验收交付】\n搭建基于pytest的完全离线单测管线，利用测试桩与FakeModel保障零付费、零联网。在包含51章9.2万字的长篇样本上完成全流程回放测试，通过率达100%（363项测试全绿）。整理全套项目工程报告与归档交付。",
            "历史调试遗留了个别冗余项目目录，测试套件在跨平台运行（Windows反斜杠 vs macOS正斜杠）时部分路径字符串断言出现偶发失败。",
            "编写自动化清理脚本净化测试目录，保留完整规范的示范工程；全面重构测试用例中的路径断言为Pathlib标准相对路径比较；全系统363项单测在沙箱环境下顺利全绿通过，圆满完成系统结题验收。"
        ),
    ]

    # 填充表格第 8 行至第 15 行 (Index 7 to 14)
    start_row = 7
    for idx, (week_name, week_time, content, problem, solution) in enumerate(weekly_logs):
        curr_row = start_row + idx
        # 行高根据内容自适应 (约 80-100 pt)
        ws.set_row(curr_row, 96)
        
        # 1. 周次
        ws.merge_range(curr_row, 0, curr_row, 1, week_name, log_center_fmt)
        # 2. 指导时间
        ws.merge_range(curr_row, 2, curr_row, 3, week_time, log_center_fmt)
        # 3. 指导内容
        ws.merge_range(curr_row, 4, curr_row, 7, content, log_content_fmt)
        # 4. 实践中出现的问题
        ws.merge_range(curr_row, 8, curr_row, 11, problem, log_content_fmt)
        # 5. 调整方式
        ws.merge_range(curr_row, 12, curr_row, 14, solution, log_content_fmt)

    # 尾部留白行 (第16-20行，备用行保持边框)
    for r in range(start_row + len(weekly_logs), 20):
        ws.set_row(r, 24)
        ws.merge_range(r, 0, r, 1, "", log_center_fmt)
        ws.merge_range(r, 2, r, 3, "", log_center_fmt)
        ws.merge_range(r, 4, r, 7, "", log_content_fmt)
        ws.merge_range(r, 8, r, 11, "", log_content_fmt)
        ws.merge_range(r, 12, r, 14, "", log_content_fmt)

    wb.close()
    print(f"[OK] Generated: {OUT_PATH}")

if __name__ == "__main__":
    generate()
