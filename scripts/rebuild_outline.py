#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild_outline — 从既有素材机械重建小说项目的 outline / chapter_titles / 开放伏笔。

背景
----
长篇小说项目 `data/projects/<名>/project.json` 里的 `outline` 是**写作前**的计划。
若项目在写作过程中丢过大纲（例如 50 章项目：正文 50 章齐备，`outline` 却是空数组、
`chapter_titles` 全是「第N章」、`foreshadowing` 为空），TUI 与后续章节写作都会失去上下文。
本脚本把大纲**反推**回来。

数据来源（按可靠性排序）
------------------------
1. `characters.json` 的 `chapter_events`：当年逐章写作时，模型自己产出的逐章
   `summary` / `key_actions`。这是"作者本人"的逐章纪要，质量最高，且零成本、零 API。
2. 章节正文：对没有任何事件记录的章（事件覆盖不全时），用纯规则兜底：
   抽取式摘要（句子 TF-IDF 打分）+ 显著名词短语标题。

产出
----
- `outline`：每章 {chapter, title, expected_content, key_foreshadowing}
- `chapter_titles`：把「第N章」换成重建出的真标题（TUI `novel show` / 导出都受益）
- `foreshadowing`：开放伏笔 = 故事前沿（最后 N 章）的章尾钩子句，带章号出处

安全
----
- 默认 dry-run，只预览不落盘；`--apply` 才写入，且先备份 `project.json.bak-<时间戳>`
- 只改上面三个字段，其余字段（chapters/metadata/description…）原样保留，
  写回格式与 `NovelProject.save()` 一致（ensure_ascii=False, indent=2）
- 已有 outline 的项目默认跳过（`--force` 覆盖）

依赖
----
仅标准库。不 import 项目内模块 —— 因此本机缺 yaml/loguru/openai 时也能跑。

用法
----
    python3 scripts/rebuild_outline.py                          # 列出可重建的项目
    python3 scripts/rebuild_outline.py --project "项目名"        # 预览
    python3 scripts/rebuild_outline.py --project "项目名" --apply
    python3 scripts/rebuild_outline.py --project "项目名" --apply --rebuild-export
    python3 scripts/rebuild_outline.py --project "项目名" --open-chapters 8 --max-open 10
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "data" / "projects"

# ========== 中文文本工具（无 jieba 依赖的轻量实现） ==========

CJK_RUN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
SENT_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")
QUOTES = "“”\"'‘’《》「」『』"
# 标题收尾宜为名词性字，用来滤掉「克没有立刻调」这类断句碎片
NOUN_END = set(
    "包袋卡舱站门器件机系统信号数据技术声音眼睛纹路空间时间世界计划编号名字记录样本"
    "记忆意识心跳孩子胎儿男人女人父亲妹妹博士医生教授士长员者体面线层板墙室厅港船"
    "舰壁灯锁钥匙针种痕迹象答案问题秘密真相代价选择规则秩序生命氧气星球银河星集团"
    "联邦协会基地废墟通道竖井穹顶摇篮皿网格托盘屏幕面板终端带刻弧度密码电码间隔间"
    "隙镜像备份警报权限流结构装置矩阵处理器接口神经力量资格命令誓约契约烙印残骸"
)
FUNC_EDGE = set("的了是在和与他她它我你都很就也这那不有上下里中个之与及或但而且所以被把给对从到向为以将于着过吗呢吧啊哦些某")
VERBISH = ("没有", "不是", "已经", "正在", "开始", "继续", "然后", "于是", "但是", "因为",
           "所以", "如果", "虽然", "可是", "而且", "并且", "似乎", "仿佛", "一个", "一种",
           "一些", "某种", "什么", "怎么", "自己", "他们", "我们", "你们")
# 角色未出场的 summary（这类不能当作本章内容）
ABSENT_MARKERS = ("未出场", "未出现", "未直接出场", "本章未", "未登场", "没有出场", "无变化", "未直接登场")
# 标题截断点：在语义边界切短，避免生硬截字（取字符串中**位置最靠前**的切点）
TITLE_CUTS = ("并且", "并", "，", ",", "；", ";", "：", ":", "、", "之后", "后", "关于",
              "中的", "以", "让", "使", "导致", "从而", "同时", "与", "和", "为")
# 章尾钩子里的"面向未来"标记（用于挑出未解伏笔）
FORWARD_MARKERS = ("等待", "还在", "仍然", "尚未", "还没", "更深处", "下一个", "下一位",
                   "即将", "将会", "会不会", "吗？", "吗?", "呢？", "呢?", "没有回答",
                   "还不知道", "直到", "迟早", "未来", "还没有")
# 纯动作叙述（走位句不是伏笔线头，直接排除）
MOVEMENT_VERBS = ("走去", "走进", "走出", "转身", "踏上", "迈步", "前行", "继续走",
                  "坠入", "倒下", "爬", "退回", "离开这里")
# 贯穿全书的线索实体：句子里同时出现它 + 未来标记，才更像"未回收的线头"
THREAD_TOKENS = ("林雪", "妹妹", "父亲", "七十七", "七十三", "七十四", "零号", "信号",
                 "心跳", "规则", "试验场", "名字", "竖井", "间隙", "容器", "卡尔",
                 "安德森", "苏辰", "苏晴", "艾莉亚", "刻痕", "针")


def cjk_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def split_sentences(text: str) -> list[str]:
    out = []
    for chunk in SENT_SPLIT.split(text):
        s = chunk.strip()
        if s:
            out.append(s)
    return out


def strip_marks(text: str) -> str:
    return text.strip().strip(QUOTES).strip("*_`# ").strip()


# ========== 来源一：characters.json 的 chapter_events ==========

def load_chapter_events(chars_path: Path) -> dict[int, list[tuple[str, dict]]]:
    """{章号: [(角色名, 事件 dict), ...]}"""
    if not chars_path.exists():
        return {}
    data = json.loads(chars_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "characters" in data and isinstance(data["characters"], dict):
        data = data["characters"]  # 兼容嵌套格式
    by_chapter: dict[int, list[tuple[str, dict]]] = defaultdict(list)
    for name, profile in (data or {}).items():
        if not isinstance(profile, dict):
            continue
        for ev in profile.get("chapter_events") or []:
            if not isinstance(ev, dict):
                continue
            num = ev.get("chapter")
            if isinstance(num, int):
                by_chapter[num].append((name, ev))
    return dict(by_chapter)


def pick_primary(events: list[tuple[str, dict]], protagonist: str) -> tuple[str, dict] | None:
    """挑出最能代表本章的事件记录：优先主角，其次关键行动最多的角色。"""
    best, best_score = None, None
    for name, ev in events:
        actions = [a for a in (ev.get("key_actions") or []) if isinstance(a, str) and a.strip()]
        summary = (ev.get("summary") or "").strip()
        useful = bool(actions) or (bool(summary) and not is_absent(summary))
        if not useful:
            continue
        score = (
            1 if name == protagonist else 0,
            len(actions),
            1 if summary and not is_absent(summary) else 0,
        )
        if best_score is None or score > best_score:
            best, best_score = (name, ev), score
    return best


def is_absent(summary: str) -> bool:
    return any(m in summary for m in ABSENT_MARKERS)


# ========== 标题生成 ==========

def title_from_actions(actions: list[str], used: set[str], chapter: int) -> str | None:
    """从模型产出的关键行动里取一个干净的短事件名，如「潜入服务器机房」。"""
    for action in actions:
        cand = strip_marks(action)
        # 取位置最靠前的语义切点（TITLE_CUTS 的顺序不代表优先级）
        hits = [(cand.index(cut), -len(cut), cut) for cut in TITLE_CUTS if cut in cand]
        if hits:
            pos, _, cut = min(hits)
            head = cand[:pos].strip()
            if cjk_len(head) >= 4:
                cand = head
        cand = strip_marks(cand)
        # 标题里不带引号（"'值得'" 这类装饰性引号单独留下会显得残缺）
        cand = "".join(ch for ch in cand if ch not in QUOTES)
        cand = re.sub(r"[，。！？；、,.!?;:：…—\-\s]+$", "", cand).strip()
        n = cjk_len(cand)
        if not (4 <= n <= 12):
            continue
        if any(m in cand for m in ABSENT_MARKERS):
            continue
        if cand in used:
            continue
        return cand
    return None


def title_from_text(text: str, used: set[str]) -> str | None:
    """兜底：章内 TF-IDF 最高的"名词性"短语（严格过滤断句碎片）。"""
    segs = CJK_RUN.findall(text)
    counter: Counter[str] = Counter()
    for seg in segs:
        seg = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", seg)
        for n in range(3, 8):
            for i in range(len(seg) - n + 1):
                counter[seg[i:i + n]] += 1
    cands = []
    for phrase, count in counter.items():
        if count < 2 or phrase in used:
            continue
        if phrase[0] in FUNC_EDGE or phrase[-1] not in NOUN_END:
            continue
        if any(v in phrase for v in VERBISH):
            continue
        # 长短语优先，同时奖励 4-6 字的紧凑名词
        score = count * math.log(2 + len(phrase))
        cands.append((score, phrase))
    cands.sort(key=lambda x: -x[0])
    return cands[0][1] if cands else None


# ========== 摘要生成（兜底） ==========

def _cut_clean(text: str, limit: int) -> str:
    """在语义边界内截断，避免出现「关键行动：使」这种半截尾巴。"""
    if len(text) <= limit:
        return text
    head = text[:limit]
    for sep in ("。", "；", "，", "、", " "):
        pos = head.rfind(sep)
        if pos >= limit * 0.6:
            return head[:pos].rstrip("，,、； ") + "…"
    return head.rstrip() + "…"


def extractive_summary(text: str, max_sentences: int = 2, max_chars: int = 90) -> str:
    """句子级 TF-IDF 抽取式摘要，供没有事件记录的章使用。"""
    sents = [s for s in split_sentences(text) if 8 <= cjk_len(s) <= 120]
    if not sents:
        return _cut_clean(strip_marks(text), max_chars)
    df: Counter[str] = Counter()
    per = []
    for s in sents:
        grams = {s[i:i + 3] for i in range(max(0, len(s) - 2))}
        per.append(grams)
        df.update(grams)
    n = len(sents)
    scored = []
    for idx, (s, grams) in enumerate(zip(sents, per)):
        if not grams:
            continue
        weight = sum(math.log((n + 1) / (df[g] + 0.5)) for g in grams) / math.sqrt(len(grams))
        # 章首/章尾略加权（钩子通常在这些位置）
        pos = 1.15 if idx < 3 or idx >= n - 3 else 1.0
        scored.append((weight * pos, idx, s))
    scored.sort(key=lambda x: -x[0])
    chosen = sorted(scored[:max_sentences], key=lambda x: x[1])
    out = ""
    for _, _, s in chosen:
        if out and cjk_len(out) + cjk_len(s) > max_chars:
            break
        out += s
    return _cut_clean(strip_marks(out), max_chars)


# ========== 开放伏笔：故事前沿的章尾钩子 ==========

def open_foreshadowing(chapters: dict[int, str], last_n: int, max_items: int) -> list[str]:
    """开放伏笔 = 最近 last_n 章里**面向未来且尚未回收**的句子（带着章号出处）。

    只保留含 FORWARD_MARKERS 的句子，并排除纯动作叙述 —— 宁可少而准，
    也不把「然后转身朝来时路走去」这种动作句当成伏笔。
    """
    items: list[str] = []
    for num in sorted(chapters)[-last_n:]:
        sents = [strip_marks(s) for s in split_sentences(chapters[num])]
        best, best_score = None, 0
        for idx, s in enumerate(sents):
            if not (6 <= cjk_len(s) <= 70):
                continue
            if any(v in s for v in MOVEMENT_VERBS):
                continue  # 走位句，不是线头
            markers = sum(1 for m in FORWARD_MARKERS if m in s)
            if markers == 0:
                continue
            score = markers
            if any(t in s for t in THREAD_TOKENS):
                score += 1
            if idx >= len(sents) - 10:
                score += 1  # 章尾附近更像钩子
            if cjk_len(s) <= 22:
                score += 1  # 短句更像钩子，长句多是描写
            if score > best_score:
                best, best_score = s, score
        # 宁少勿滥：只收「未来标记 + 线索实体/章尾/短句」级别的句子
        if best and best_score >= 2:
            line = f"（第{num}章）{_cut_clean(best, 60)}"
            if line not in items:
                items.append(line)
    return items[-max_items:]


# ========== 导出文本（与 NovelProject.export_novel 完全一致） ==========

def build_export(project: dict) -> str:
    title = project.get("title") or project.get("name", "")
    genre = project.get("genre", "")
    desc = project.get("description", "")
    chapters = {int(k): v for k, v in (project.get("chapters") or {}).items()}
    titles = {int(k): v for k, v in (project.get("chapter_titles") or {}).items()}
    lines = [f"# {title}", "", f"*{genre}* — {desc}", "", "---", ""]
    for num in sorted(chapters):
        lines.append(f"## 第{num}章 {titles.get(num, f'第{num}章')}")
        lines.append("")
        lines.append(chapters[num])
        lines.append("")
    return "\n".join(lines)


# ========== 主流程 ==========

def rebuild(name: str, args) -> int:
    base = PROJECTS_DIR / name
    proj_path = base / "project.json"
    if not proj_path.exists():
        print(f"[x] 项目不存在: {proj_path}")
        return 1

    raw = proj_path.read_text(encoding="utf-8")
    project = json.loads(raw)
    chapters = {int(k): v for k, v in (project.get("chapters") or {}).items()}
    if not chapters:
        print("[x] 项目没有正文，无法反推大纲")
        return 1

    outline_existing = project.get("outline") or []
    if outline_existing and not args.force:
        print(f"[!] 已有 {len(outline_existing)} 章大纲，未加 --force，跳过")
        return 0

    events = load_chapter_events(base / "characters.json")
    # 主角 = 事件记录最多的角色（通常是贯穿全书的视角人物）
    counter = Counter()
    for evs in events.values():
        for nm, _ in evs:
            counter[nm] += 1
    protagonist = counter.most_common(1)[0][0] if counter else ""
    print(f"项目: {name}")
    print(f"  正文: {len(chapters)} 章 / {sum(len(v) for v in chapters.values()):,} 字")
    print(f"  chapter_events 覆盖: {len(events)} 章，主角推断为「{protagonist}」")

    used_titles: set[str] = set()
    outline, from_event, from_text = [], 0, 0
    for num in sorted(chapters):
        text = chapters[num]
        evs = events.get(num, [])
        primary = pick_primary(evs, protagonist)

        # --- title ---
        title = None
        if primary:
            actions = [a for a in (primary[1].get("key_actions") or []) if isinstance(a, str)]
            title = title_from_actions(actions, used_titles, num)
        if not title:  # 主角行动名不合适时，试其他角色的行动
            for nm, ev in evs:
                actions = [a for a in (ev.get("key_actions") or []) if isinstance(a, str)]
                title = title_from_actions(actions, used_titles, num)
                if title:
                    break
        source = "事件"
        if not title:
            title = title_from_text(text, used_titles)
            source = "抽取"
        if not title:
            title = f"第{num}章"
            source = "缺省"
        used_titles.add(title)
        if source == "事件":
            from_event += 1
        elif source == "抽取":
            from_text += 1

        # --- expected_content ---
        summary = ""
        if primary:
            summary = (primary[1].get("summary") or "").strip()
            if is_absent(summary):
                summary = ""
        if summary:
            content = summary
            actions = [strip_marks(a) for a in (primary[1].get("key_actions") or [])
                       if isinstance(a, str) and a.strip()]
            actions = [a for a in actions if a and a != title and not is_absent(a)]
            if actions:
                with_actions = f"{summary} 关键行动：{'；'.join(actions[:2])}"
                # 超长时先丢「关键行动」尾巴，而不是把摘要切半
                content = with_actions if len(with_actions) <= args.max_content \
                    else _cut_clean(summary, args.max_content)
            else:
                content = _cut_clean(summary, args.max_content)
        else:
            content = extractive_summary(text)

        outline.append({
            "chapter": num,
            "title": title,
            "expected_content": content,
            "key_foreshadowing": [],
        })

    foreshadowing = open_foreshadowing(chapters, args.open_chapters, args.max_open)

    # --- 报告 ---
    print(f"  标题来源: 事件行动 {from_event} 章 / 正文抽取 {len(chapters) - from_event} 章")
    print(f"  开放伏笔: {len(foreshadowing)} 条（取材最近 {args.open_chapters} 章）")
    print()
    for item in outline:
        print(f"  第{item['chapter']}章「{item['title']}」")
        print(f"      {item['expected_content']}")
    print()
    for line in foreshadowing:
        print(f"  伏笔 {line}")

    # --- 导出文本自检：用当前(旧)标题重算，应与磁盘上的 export.txt 逐字节一致 ---
    export_path = base / "export.txt"
    if export_path.exists():
        rebuilt = build_export(project)
        same = rebuilt == export_path.read_text(encoding="utf-8")
        print(f"\n  export.txt 复现自检: {'一致 ✓' if same else '不一致 ✗（导出实现与 export_novel 有差异，请勿用 --rebuild-export）'}")
        if not same and args.rebuild_export:
            print("  → 已忽略 --rebuild-export（自检未通过）")
            args.rebuild_export = False

    if not args.apply:
        print("\n[dry-run] 未写入。加 --apply 落盘。")
        return 0

    # --- 落盘 ---
    backup = proj_path.with_name(f"project.json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(proj_path, backup)
    project["outline"] = outline
    project["chapter_titles"] = {str(i["chapter"]): i["title"] for i in outline}
    project["foreshadowing"] = foreshadowing
    proj_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] 已写入 {proj_path}")
    print(f"     备份 {backup.name}")

    if args.rebuild_export:
        export_path.write_text(build_export(project), encoding="utf-8")
        print(f"[ok] 已按新标题重写 {export_path.name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从已有素材反推小说项目大纲（标准库实现，无需 API）",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("用法\n----")[-1])
    ap.add_argument("--project", default="", help="项目名（省略则列出所有项目）")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    ap.add_argument("--force", action="store_true", help="已有 outline 也覆盖")
    ap.add_argument("--open-chapters", type=int, default=8, help="开放伏笔取材的最近章数（默认 8）")
    ap.add_argument("--max-open", type=int, default=8, help="开放伏笔条数上限（默认 8）")
    ap.add_argument("--max-content", type=int, default=200, help="单章 expected_content 字数上限")
    ap.add_argument("--rebuild-export", action="store_true", help="顺带按新标题重写 export.txt")
    args = ap.parse_args(argv)

    if not args.project:
        names = sorted(d.name for d in PROJECTS_DIR.iterdir()
                       if d.is_dir() and (d / "project.json").exists()) if PROJECTS_DIR.exists() else []
        if not names:
            print("没有找到任何项目")
            return 1
        print("可重建的项目：")
        for n in names:
            p = json.loads((PROJECTS_DIR / n / "project.json").read_text(encoding="utf-8"))
            print(f"  - {n}｜正文 {len(p.get('chapters') or {})} 章｜"
                  f"outline {len(p.get('outline') or [])} 章｜伏笔 {len(p.get('foreshadowing') or [])} 条")
        print("\n用法: python3 scripts/rebuild_outline.py --project \"项目名\" [--apply]")
        return 0

    return rebuild(args.project, args)


if __name__ == "__main__":
    raise SystemExit(main())
