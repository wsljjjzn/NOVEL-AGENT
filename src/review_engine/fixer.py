"""
review_engine.fixer — 审稿修改应用器。
将审稿发现的三级问题应用到文章文本并生成报告。
"""

from src.utils.logger import logger
from src.models import ReviewIssue, AggregatedReview


class ArticleFixer:
    """将审稿 issue 实际应用到文章文本。"""

    @staticmethod
    def _find_and_replace(text: str, before: str, after: str, label: str) -> str:
        """在 text 中查找 before 并替换为 after，支持精确和模糊匹配。

        策略：
        1. 精确匹配 before
        2. 按空白归一化后匹配
        3. 取 before 的前 30 个字符作子串搜索
        """
        # 策略 1: 精确匹配
        if before in text:
            result = text.replace(before, after, 1)
            logger.debug(f"精确修复 [{label}]: {before[:30]} -> {after[:30]}")
            return result

        # 策略 2: 按空白归一化（连续空格/换行归一化为单个空格）后匹配
        import re as _re
        text_norm = _re.sub(r'\s+', ' ', text)
        before_norm = _re.sub(r'\s+', ' ', before)
        if before_norm in text_norm:
            # 找到归一化后的位置，在原文中做替换
            idx = text_norm.index(before_norm)
            # 将原始 text 中对应范围的字符替换
            orig_before = text[idx:idx + len(before)]
            result = text.replace(orig_before, after, 1)
            logger.debug(f"模糊修复(空白归一化) [{label}]: {before[:30]} -> {after[:30]}")
            return result

        # 策略 3: 取 before 前 30 字符作子串搜索
        prefix = before[:30].strip()
        if len(prefix) > 10 and prefix in text:
            # 找到匹配位置后，尝试从该位置开始匹配尽可能长的 before 前缀
            idx = text.index(prefix)
            # 从 idx 往后找最长的匹配后缀
            matched_len = len(prefix)
            for j in range(len(prefix), min(len(before), len(text) - idx)):
                if text[idx:idx + j] == before[:j]:
                    matched_len = j
                else:
                    break
            orig_before = text[idx:idx + matched_len]
            result = text.replace(orig_before, after, 1)
            logger.debug(f"模糊修复(前缀匹配) [{label}]: {before[:30]} -> {after[:30]}")
            return result

        logger.warning(f"修复失败: 未找到匹配文本 [{label}]: {before[:50]}")
        return text

    @staticmethod
    def apply_auto_fixes(text: str, level1_issues: list[ReviewIssue]) -> str:
        """应用 Level 1 自动修改（支持模糊匹配）。"""
        result = text
        for issue in level1_issues:
            if issue.before_text and issue.after_text:
                result = ArticleFixer._find_and_replace(
                    result, issue.before_text, issue.after_text,
                    issue.description[:40],
                )
        return result

    @staticmethod
    def apply_confirmed_fixes(text: str, issues: list[ReviewIssue]) -> str:
        """应用用户确认后的 Level 2 修改（支持模糊匹配）。"""
        result = text
        for issue in issues:
            if issue.before_text and issue.after_text:
                result = ArticleFixer._find_and_replace(
                    result, issue.before_text, issue.after_text,
                    issue.description[:40],
                )
        return result

    @staticmethod
    def format_review_report(aggregated: AggregatedReview) -> str:
        """生成 Markdown 格式的审稿报告。"""
        lines = ["# 📋 审稿报告", ""]

        # 各 Agent 评分汇总
        if aggregated.reports:
            lines.append("## 各维度评分")
            lines.append("| Agent | 评分 | 问题数 | 总体评价 |")
            lines.append("|-------|------|--------|----------|")
            for r in aggregated.reports:
                lines.append(
                    f"| {r.agent} | {r.score:.1f}/10 | {len(r.issues)} | "
                    f"{r.overall_assessment[:60]} |"
                )
            lines.append("")

        # Level 1 自动修改
        lines.append(f"## Level 1 · 自动修改 ({len(aggregated.level1_changes)} 项)")
        if aggregated.level1_changes:
            for i in aggregated.level1_changes:
                lines.append(f"- ✅ [{i.agent}] {i.description}")
                if i.before_text and i.after_text:
                    lines.append(f"  - `{i.before_text[:40]}` → `{i.after_text[:40]}`")
        else:
            lines.append("_无_")
        lines.append("")

        # Level 2 待确认
        lines.append(f"## Level 2 · 待用户确认 ({len(aggregated.level2_changes)} 项)")
        if aggregated.level2_changes:
            for i in aggregated.level2_changes:
                lines.append(f"- 📝 [{i.agent}] **{i.description}**")
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
                lines.append(f"- {sev} [{i.agent}] **{i.description}**")
                if i.location:
                    lines.append(f"  - 位置: {i.location}")
                if i.suggestion:
                    lines.append(f"  - 指引: {i.suggestion}")
        else:
            lines.append("_无_")

        return "\n".join(lines)
