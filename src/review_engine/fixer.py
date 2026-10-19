"""
review_engine.fixer — 审稿修改应用器。

将审稿发现的问题按级别落回正文，并生成报告。

正确性要点（历史缺陷见 docs/modules/review_engine.md §5）：
- **归一化匹配必须映射回原文下标**：早期实现用「空白归一化后的下标」去切原文，
  会把修复插到文章开头、吃掉换行。这里显式记录归一化字符→原文区间的映射。
- **最小锚点**：`before_text` 去空白后至少 2 字符；单字符仅在全文唯一时替换，
  防止 `before_text="的"` 误伤全文第一处。
- **命中计数**：返回 `FixOutcome`，调用方据此区分「改了 N 处」与「一个都没改到」。
"""

import re
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import logger
from src.models import ReviewIssue, AggregatedReview


# 自动替换的最小锚点长度（去空白后）。单字符仅允许在全文唯一时替换。
MIN_ANCHOR_CHARS = 2


@dataclass
class FixOutcome:
    """一次批量修改的结果。"""
    text: str
    applied: int = 0
    missed: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)


class ArticleFixer:
    """将审稿 issue 实际应用到正文。"""

    # ---- 匹配 ----

    @staticmethod
    def _normalized_index_map(text: str) -> tuple[str, list[int], list[int]]:
        """构建空白归一化文本，并记录每个归一化字符对应的原文区间。

        Returns:
            (normalized_text, starts, lengths)
            - `normalized_text[i]` 取自原文 `text[starts[i]:starts[i]+lengths[i]]`
            - 连续空白折叠为单个空格；一个空格对应整段空白。
        """
        chars: list[str] = []
        starts: list[int] = []
        lengths: list[int] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch.isspace():
                j = i
                while j < n and text[j].isspace():
                    j += 1
                chars.append(' ')
                starts.append(i)
                lengths.append(j - i)
                i = j
            else:
                chars.append(ch)
                starts.append(i)
                lengths.append(1)
                i += 1
        return ''.join(chars), starts, lengths

    @staticmethod
    def _anchor_ok(before: str, text: str) -> bool:
        """锚点是否足够具体，可以安全替换。"""
        anchor = before.strip()
        if not anchor:
            return False
        if len(anchor) >= MIN_ANCHOR_CHARS:
            return True
        # 单字符：只有全文唯一时才允许（避免"的"命中第一处）
        return len(anchor) == 1 and text.count(anchor) == 1

    @staticmethod
    def _find_and_replace(text: str, before: str, after: str,
                          label: str) -> tuple[str, str]:
        """替换 text 中 before 的**第一处**。

        Returns:
            (new_text, status)，status ∈ {"applied", "missed", "skipped"}
        """
        if not before:
            return text, "skipped"
        if not ArticleFixer._anchor_ok(before, text):
            logger.warning(f"锚点过短/退化，已跳过 [{label}]: {before[:30]!r}")
            return text, "skipped"

        # 策略 1: 精确匹配（按下标切片，不用 str.replace，避免命中别处）
        idx = text.find(before)
        if idx != -1:
            new_text = text[:idx] + after + text[idx + len(before):]
            logger.debug(f"精确修复 [{label}]: {before[:30]} -> {after[:30]}")
            return new_text, "applied"

        # 策略 2: 空白归一化后匹配，再把归一化区间映射回原文区间
        norm, starts, lengths = ArticleFixer._normalized_index_map(text)
        before_norm = re.sub(r'\s+', ' ', before).strip()
        if before_norm:
            pos = norm.find(before_norm)
            if pos != -1:
                end = pos + len(before_norm) - 1
                orig_start = starts[pos]
                orig_end = starts[end] + lengths[end]
                new_text = text[:orig_start] + after + text[orig_end:]
                logger.debug(f"模糊修复(空白归一化) [{label}]: {before[:30]} -> {after[:30]}")
                return new_text, "applied"

        # 策略 3: 前 30 字符前缀定位后向前扩展匹配
        prefix = before.strip()[:30]
        if len(prefix) > 10:
            idx = text.find(prefix)
            if idx != -1:
                limit = min(len(before), len(text) - idx)
                matched = len(prefix)
                j = len(prefix)
                while j < limit and text[idx + j] == before[j]:
                    j += 1
                matched = j
                new_text = text[:idx] + after + text[idx + matched:]
                logger.debug(f"模糊修复(前缀匹配) [{label}]: {before[:30]} -> {after[:30]}")
                return new_text, "applied"

        logger.warning(f"修复失败: 未找到匹配文本 [{label}]: {before[:50]}")
        return text, "missed"

    # ---- 批量应用 ----

    @staticmethod
    def _apply_issues(text: str, issues: list[Any]) -> FixOutcome:
        outcome = FixOutcome(text=text)
        for issue in issues:
            if isinstance(issue, dict):
                desc = issue.get("description") or ""
                before = issue.get("before_text") or ""
                after = issue.get("after_text") or ""
            else:
                desc = getattr(issue, "description", "") or ""
                before = getattr(issue, "before_text", "") or ""
                after = getattr(issue, "after_text", "") or ""

            label = (desc or "未命名修改")[:40]
            if not (before and after):
                outcome.skipped += 1
                outcome.details.append(f"跳过（缺 before/after）: {label}")
                continue
            new_text, status = ArticleFixer._find_and_replace(
                outcome.text, before, after, label,
            )
            outcome.text = new_text
            if status == "applied":
                outcome.applied += 1
            elif status == "skipped":
                outcome.skipped += 1
                outcome.details.append(f"跳过（锚点退化）: {label}")
            else:
                outcome.missed += 1
                outcome.details.append(f"未命中: {label}")
        return outcome

    @staticmethod
    def apply_auto_fixes_detailed(text: str, level1_issues: list[Any]) -> FixOutcome:
        """应用 Level 1 自动修改，返回命中统计。"""
        return ArticleFixer._apply_issues(text, level1_issues)

    @staticmethod
    def apply_confirmed_fixes_detailed(text: str, issues: list[Any]) -> FixOutcome:
        """应用用户确认后的 Level 2 修改，返回命中统计。"""
        return ArticleFixer._apply_issues(text, issues)

    @staticmethod
    def apply_auto_fixes(text: str, level1_issues: list[Any]) -> str:
        """应用 Level 1 自动修改（兼容旧签名，仅返回文本）。"""
        return ArticleFixer.apply_auto_fixes_detailed(text, level1_issues).text

    @staticmethod
    def apply_confirmed_fixes(text: str, issues: list[Any]) -> str:
        """应用用户确认后的 Level 2 修改（兼容旧签名，仅返回文本）。"""
        return ArticleFixer.apply_confirmed_fixes_detailed(text, issues).text

    # ---- 报告 ----

    @staticmethod
    def format_review_report(aggregated: AggregatedReview) -> str:
        """生成 Markdown 格式的审稿报告。"""
        lines = ["# 📋 审稿报告", ""]

        failed = aggregated.failed_reports
        if aggregated.reports:
            lines.append(
                f"**综合评分**: {aggregated.overall_score:.1f}/10"
                f" · **有效维度**: {aggregated.coverage}"
            )
            lines.append("")
            lines.append("## 各维度评分")
            lines.append("| Agent | 评分 | 问题数 | 总体评价 |")
            lines.append("|-------|------|--------|----------|")
            for r in aggregated.reports:
                if r.status == "failed":
                    lines.append(f"| {r.agent} | ❌ 审稿失败 | — | {(r.error or r.overall_assessment)[:60]} |")
                else:
                    lines.append(
                        f"| {r.agent} | {r.score:.1f}/10 | {len(r.issues)} | "
                        f"{(r.overall_assessment or '')[:60]} |"
                    )
            lines.append("")

        if failed:
            lines.append(
                f"> ⚠️ {len(failed)}/{len(aggregated.reports)} 个维度调用/解析失败，"
                f"下列结论**不代表全文已合格**。"
            )
            lines.append("")

        for warning in aggregated.warnings:
            lines.append(f"> ⚠️ {warning}")
        if aggregated.warnings:
            lines.append("")

        # Level 1 自动修改
        lines.append(f"## Level 1 · 自动修改 ({len(aggregated.level1_changes)} 项)")
        lines.append(
            f"_实际命中 {aggregated.applied_fixes} 处 · 未命中 {aggregated.missed_fixes} 处 · "
            f"跳过 {aggregated.skipped_fixes} 处_"
        )
        if aggregated.level1_changes:
            for i in aggregated.level1_changes:
                suffix = f"（{('、'.join(i.duplicated_by))} 也报出）" if i.duplicated_by else ""
                lines.append(f"- ✅ [{i.agent}] {i.description}{suffix}")
                if i.before_text and i.after_text:
                    lines.append(f"  - `{i.before_text[:40]}` → `{i.after_text[:40]}`")
        else:
            lines.append("_无_")
        lines.append("")

        # Level 2 待确认
        lines.append(f"## Level 2 · 待用户确认 ({len(aggregated.level2_changes)} 项)")
        if aggregated.level2_changes:
            for i in aggregated.level2_changes:
                suffix = f"（{('、'.join(i.duplicated_by))} 也报出）" if i.duplicated_by else ""
                lines.append(f"- 📝 [{i.agent}] **{i.description}**{suffix}")
                if i.suggestion:
                    lines.append(f"  - 建议: {i.suggestion}")
                if i.before_text and i.after_text:
                    lines.append(f"  - `{i.before_text[:40]}` → `{i.after_text[:40]}`")
        else:
            lines.append("_无_")
        lines.append("")

        # Level 3 手动指引
        lines.append(f"## Level 3 · 手动修改指引 ({len(aggregated.level3_guidance)} 项)")
        if aggregated.level3_guidance:
            for i in aggregated.level3_guidance:
                sev = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(i.severity, "")
                suffix = f"（{('、'.join(i.duplicated_by))} 也报出）" if i.duplicated_by else ""
                lines.append(f"- {sev} [{i.agent}] **{i.description}**{suffix}")
                if i.location:
                    lines.append(f"  - 位置: {i.location}")
                if i.suggestion:
                    lines.append(f"  - 指引: {i.suggestion}")
        else:
            lines.append("_无_")

        return "\n".join(lines)
