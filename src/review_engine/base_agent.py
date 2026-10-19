"""
review_engine.base_agent — 审稿 Agent 基类。

失败语义（对齐 docs/specs/contracts.md §4 三态）：
- 解析/调用彻底失败 → `ReviewReport(status="failed", error=...)`，`score=0.0`，不再伪装成
  「审稿完成，5.0 分」。
- 成功但确实没问题 → `status="ok"`、`issues=[]`，这是正常结论。
"""

import re
from typing import Optional

from src.utils.llm_client import LLMClient, LLMUnavailableError
from src.utils.logger import logger
from src.utils.cost_tracker import BudgetExceeded
from src.models import ReviewIssue, ReviewReport
from src.utils.json_utils import safe_json_parse, find_json_in_text


_LEVEL_CHARS = {"1": 1, "2": 2, "3": 3, "一": 1, "二": 2, "三": 3}
_LEVEL_WORDS = {
    "严重": 1, "critical": 1, "错误": 1, "error": 1,
    "警告": 2, "warning": 2,
    "建议": 3, "info": 3, "提示": 3,
}
# 审稿要的是"能解析的 JSON"，而不是"不要思考"。思考保持开启（质量优先），
# 靠两件事保证结构化输出可用：
#   1) json_object 输出模式 —— 思考开着时模型偶尔改写成散文，实测同一提示词
#      不加约束会拿到无法解析的 content；
#   2) 该档 max_tokens 必须能容纳思考 —— 实测单维「思考 + 正文」需要 6k~13k
#      tokens，config.yaml 已把 flash / pro 两档都提到 16384。
# 2026-10-13 的现场：flash 的 4096 被思考吃满 → content 空串 → 报「JSON 解析失败」。
REVIEW_JSON_MODE = True

_SEVERITY_WORDS = {
    "critical": "critical", "严重": "critical", "error": "critical", "错误": "critical",
    "warning": "warning", "警告": "warning", "warn": "warning",
    "info": "info", "建议": "info", "提示": "info", "suggestion": "info",
}


def _safe_int_level(value, default=2):
    """将 LLM 返回的 level 值安全转为 int 1/2/3。

    支持纯数字、"Level 1"、"L2"、"级别3"、"第1级"、"严重/警告/建议" 等写法。
    识别不了才退回 default，绝不因措辞差异静默降级 Level 1。
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        try:
            return max(1, min(3, int(value)))
        except (TypeError, ValueError):
            return default
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text:
        return default
    try:
        return max(1, min(3, int(text)))
    except ValueError:
        pass
    match = re.search(
        r'(?:level|lvl|l|级别|等级|优先级|第)\s*([123一二三])\s*(?:级|档)?',
        text, re.IGNORECASE,
    )
    if match:
        return _LEVEL_CHARS[match.group(1)]
    match = re.search(r'([123一二三])\s*(?:级|档)', text)
    if match:
        return _LEVEL_CHARS[match.group(1)]
    return _LEVEL_WORDS.get(text if not text.isascii() else text.lower(), default)


def _safe_severity(value, default="warning") -> str:
    """把严重程度写法归一到 critical / warning / info。"""
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text:
        return default
    return _SEVERITY_WORDS.get(text if not text.isascii() else text.lower(), default)


def _try_fix_truncated_json(text: str) -> Optional[dict]:
    """尝试修复被 max_tokens 截断的 JSON（补全未闭合的容器）。

    早期实现用 `text.count('[') - text.count(']')` 数括号，会把**字符串内部**
    的方括号也算进去，补出非法 JSON。这里改为逐字符扫描并跳过字符串。
    """
    import json
    stack: list[str] = []   # 未闭合的容器，'{' 或 '['
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            stack.append('{')
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == '[':
            stack.append('[')
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()

    if not stack and not in_string:
        return None

    fixed = text.rstrip()
    if in_string:
        fixed += '"'
    fixed = fixed.rstrip().rstrip(',')
    # 逆序补全：最后打开的容器最先闭合
    for opener in reversed(stack):
        fixed += ']' if opener == '[' else '}'

    try:
        result = json.loads(fixed)
        if isinstance(result, dict):
            logger.info(f"截断 JSON 修复成功: 补全了 {len(stack)} 个容器")
            return result
    except json.JSONDecodeError:
        pass
    return None


class BaseReviewAgent:
    """审稿 Agent 基类。"""

    def __init__(self, name: str, system_prompt: str,
                 llm_client: Optional[LLMClient] = None, key: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self.key = key or name
        self.llm = llm_client or LLMClient()

    @staticmethod
    def _build_user_content(article_text: str, context: str = "") -> str:
        """拼装 user 消息；有作品状态时先给参照，再给正文。"""
        context = (context or "").strip()
        if context:
            return (
                "【作品状态（供一致性核对，勿照抄）】\n"
                f"{context}\n\n"
                "请审阅以下正文：\n\n"
                f"{article_text}"
            )
        return f"请审阅以下文章：\n\n{article_text}"

    def _failed_report(self, article_id: str, error: str) -> ReviewReport:
        """构造一个显式失败的报告（不是「没问题」）。"""
        return ReviewReport(
            agent=self.name,
            dimension=self.key,
            article_id=article_id,
            status="failed",
            error=error,
            overall_assessment=f"审稿失败：{error}（本次调用仍会计费）",
            strengths=[],
            issues=[],
            score=0.0,
        )

    def review(self, article_text: str, article_id: str = "",
               model_tier: str = "pro", context: str = "") -> ReviewReport:
        """审稿一段完整文本。

        Args:
            article_text: 正文
            article_id: 文章/章节 ID
            model_tier: 模型层级（flash/pro）
            context: 可选的作品状态（角色/伏笔/世界观/前情），用于一致性核对

        Returns:
            审稿报告；失败时 `status="failed"`，不抛出业务异常。
        """
        logger.info(f"{self.name} 开始审稿...")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self._build_user_content(article_text, context)},
        ]

        try:
            response = self.llm.chat(
                messages, model_tier=model_tier, temperature=0.3,
                json_mode=REVIEW_JSON_MODE,
            )
            return self._parse_response(response, article_id)
        except BudgetExceeded:
            # 成本护栏：预算耗尽必须向上中断，不允许逐 Agent 降级吞掉
            raise
        except LLMUnavailableError as e:
            logger.error(f"{self.name} 审稿 API 不可用: {e}")
            return self._failed_report(article_id, f"API 不可用：{e}")
        except Exception as e:
            logger.warning(f"{self.name} 审稿调用失败: {e}")
            return self._failed_report(article_id, f"{type(e).__name__}: {e}")

    def _parse_response(self, response: str, article_id: str) -> ReviewReport:
        """解析 LLM 审稿结果；解析失败显式标记为 failed。"""
        data = safe_json_parse(response)
        if data is None:
            data = find_json_in_text(response)
        if data is None:
            data = _try_fix_truncated_json(response)

        if not isinstance(data, dict):
            raw = (response or "").strip()
            if not raw:
                # 空串是「思考吃满输出预算」的典型形状，与「返回了散文」区分开，
                # 否则只会看到一个和模型行为无关的「JSON 解析失败」。
                return self._failed_report(
                    article_id,
                    "模型未返回任何内容（输出预算可能被思考吃满；请调大该档 max_tokens）",
                )
            logger.warning(
                f"{self.name} 审稿输出无法解析为 JSON（{len(raw)} 字符）: "
                f"头部 {raw[:200]!r} … 尾部 {raw[-200:]!r}"
            )
            return self._failed_report(
                article_id, "模型未返回可解析的 JSON（JSON 解析失败）",
            )

        try:
            raw_issues = data.get("issues", [])
            if not isinstance(raw_issues, list):
                raw_issues = []
            issues = []
            for item in raw_issues:
                if not isinstance(item, dict):
                    continue
                level = _safe_int_level(item.get("level", 2))
                issues.append(ReviewIssue(
                    agent=self.name,
                    dimension=self.key,
                    level=level,
                    location=str(item.get("location", "") or ""),
                    severity=_safe_severity(item.get("severity", "warning")),
                    description=str(item.get("description", "") or ""),
                    suggestion=str(item.get("suggestion", "") or ""),
                    before_text=str(item.get("before_text", "") or ""),
                    after_text=str(item.get("after_text", "") or ""),
                    auto_fixable=(level == 1),
                ))

            strengths = data.get("strengths", [])
            if not isinstance(strengths, list):
                strengths = [str(strengths)] if strengths else []
            strengths = [str(s) for s in strengths if s]

            return ReviewReport(
                agent=self.name,
                dimension=self.key,
                article_id=article_id,
                status="ok",
                overall_assessment=str(data.get("overall_assessment", "") or ""),
                strengths=strengths,
                issues=issues,
                score=self._extract_score(data, response),
            )
        except Exception as e:
            logger.warning(f"{self.name} 审稿结果解析异常: {e}")
            return self._failed_report(article_id, f"结果解析异常：{type(e).__name__}: {e}")

    @staticmethod
    def _extract_score(data: dict, response: str) -> float:
        """从结构化数据取分；显式 0 分合法，不因 `or` 被当成缺失。"""
        for key in ("score", "评分", "分数", "得分"):
            if key in data and data[key] is not None:
                return data[key]
        for key, value in data.items():
            if str(key).lower() in ("score", "评分", "分数", "得分", "grade", "rating"):
                if value is not None:
                    return value
        match = re.search(r'(?:评分|分数|得分|score)[：:\s]*(\d+(?:\.\d+)?)',
                          response, re.IGNORECASE)
        return float(match.group(1)) if match else 5.0
