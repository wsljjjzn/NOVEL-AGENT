"""
scripts/integration_test.py — 自动集成测试。

模拟完整的创作流程：
创建项目 → 生成大纲 → 生成角色 → 设计剧情 → 写第1章 → 写第2章 → 查看文章
"""

import sys, json, os, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.novel import CharacterEngine, NovelProject, ChapterWriter
from src.novel.plot_engine import PlotEngine

PASS = 0
FAIL = 0

def check(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [OK] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")

def main():
    global PASS, FAIL
    print("=" * 60)
    print("集成测试：长篇小说创作全流程")
    print("=" * 60)

    # === 清理测试项目 ===
    test_dir = Path("data/projects/__integration_test__")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)

    # === 1. 创建项目 ===
    print("\n【1/6】创建项目")
    proj = NovelProject("__integration_test__")
    proj.genre = "都市/校园"
    proj.description = "集成测试"
    check(os.path.exists(proj.base_dir), "项目目录已创建")
    check(proj.title == "__integration_test__", "项目标题正确")

    # === 2. 生成大纲 ===
    print("\n【2/6】大纲生成")
    engine = CharacterEngine()
    writer = ChapterWriter(proj, engine)
    items = writer.generate_outline(3, "一个大学生发现校花是黑帮千金的故事。", model_tier="flash")
    check(len(items) == 3, f"生成了 {len(items)} 章大纲")
    check(items[0].title != "", "第1章大纲标题非空")
    check(items[1].expected_content != "", "第2章大纲内容非空")

    # === 3. 生成角色系统 ===
    print("\n【3/6】角色系统")
    plot_engine = PlotEngine()
    chars_data, world = plot_engine.design_characters(
        proj.title, proj.genre, proj.description, proj.get_outline_context()
    )
    check(len(chars_data) > 0, f"生成了 {len(chars_data)} 个角色")

    # 填充到引擎
    char_count_before = len(engine.all_characters())
    for cd in chars_data:
        if not isinstance(cd, dict):
            continue
        from src.novel.character_engine import CharacterProfile
        profile = CharacterProfile(
            name=cd["name"], role=cd.get("role", ""),
            personality=cd.get("personality", {}),
            speaking_style=cd.get("speaking_style", ""),
            core_desire=cd.get("core_desire", ""), core_fear=cd.get("core_fear", ""),
            background=cd.get("background", ""), appearance=cd.get("appearance", ""),
            relationships=cd.get("relationships", {}),
            arc_summary=cd.get("arc_summary", ""),
        )
        engine.add_character(profile)
    check(len(engine.all_characters()) > char_count_before, "角色已填充到引擎")

    # === 4. 剧情设计 ===
    print("\n【4/6】剧情设计")
    plot = plot_engine.design_chapter_plot(
        1,
        {"title": items[0].title, "expected_content": items[0].expected_content},
    )
    check(plot.opening_hook != "", "开篇钩子非空")
    check(len(plot.scenes) > 0, "至少有1个场景")
    check(plot.chapter_num == 1, "章节号正确")
    plot_text = plot.to_prompt_text()
    check(len(plot_text) > 100, "剧情设计文本长度 > 100")

    # === 5. 写第1章 ===
    print("\n【5/6】写作第1章")
    try:
        text1 = writer.write_chapter(1, plot_text, 500, model_tier="flash")
        check(len(text1) > 100, f"第1章正文长度 {len(text1)} > 100")
        ch1 = proj.get_chapter(1)
        check(len(ch1) > 0, "第1章已存入项目")

        # 检查标题是否从大纲获取
        title1 = proj.chapter_titles.get(1, "")
        check(title1 != "" and title1 != "第1章", f"第1章标题为「{title1}」（非默认标题）")
    except Exception as e:
        check(False, f"第1章写作失败: {e}")

    # === 6. 写第2章 ===
    print("\n【6/6】写作第2章")
    old_chars_count = len(engine.all_characters())
    try:
        plot2 = plot_engine.design_chapter_plot(
            2,
            {"title": items[1].title, "expected_content": items[1].expected_content},
            proj.get_recap(2),
        )
        text2 = writer.write_chapter(2, plot2.to_prompt_text(), 500, model_tier="flash")
        check(len(text2) > 100, f"第2章正文长度 {len(text2)} > 100")
        ch2 = proj.get_chapter(2)
        check(len(ch2) > 0, "第2章已存入项目")

        # 检查角色引擎已更新
        check(len(engine.all_characters()) >= old_chars_count, "角色引擎未丢失角色")
        check(proj.metadata.get("chapter_count", 0) >= 2, "项目计数 >= 2")

        # 全文导出
        full = proj.export_novel()
        check("第1章" in full and "第2章" in full, "全文导出包含所有章节")
    except Exception as e:
        check(False, f"第2章写作失败: {e}")

    # === 结果 ===
    print(f"测试结果: {PASS} 通过 / {FAIL} 失败")
    print(f"{'='*60}")

    # 清理
    import shutil
    shutil.rmtree(test_dir)

    return FAIL == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
