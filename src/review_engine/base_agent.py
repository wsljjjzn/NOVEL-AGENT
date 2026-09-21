"""
review_engine.base_agent — 审稿 Agent 基类。
"""

from typing import Optional

from src.utils.llm_client import LLMClient, LLMUnavailableError
from src.utils.logger import logger
from src.utils.cost_tracker import BudgetExceeded
from src.models import ReviewIssue, ReviewReport
from src.utils.json_utils import safe_json_parse, find_json_in_text


def _safe_int_level(value, default=2):
    """将 LLM 返回的 level 值安全转为 int 1/2/3。"""
    if isinstance(value, int):
        return max(1, min(3, value))
    if isinstance(value, str):
        try:
            return max(1, min(3, int(value)))
        except ValueError:
            pass
        level_map = {
            '严重': 1, 'critical': 1, '错误': 1, 'error': 1,
            '警告': 2, 'warning': 2,
            '建议': 3, 'info': 3, '提示': 3,
        }
        return level_map.get(value.strip().lower() if value.isascii() else value.strip(), default)
    return default


def _try_fix_truncated_json(text: str) -> Optional[dict]:
    """尝试修复被 max_tokens 截断的 JSON。

    LLM 返回的 JSON 可能因 max_tokens 限制被截断，
    导致缺少闭合括号。此函数尝试补全括号后解析。
    """
    import json
    # 计算缺少的闭合括号数
    depth = 0
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\':
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

    # 尝试补全：去掉末尾可能的截断残余，然后补全括号
    fixed = text.rstrip().rstrip(',').rstrip()
    # 补全未闭合的字符串和 JSON 结构
    if in_string:
        fixed += '"'
    # 补全数组
    arr_open = text.count('[') - text.count(']')
    if arr_open > 0:
        fixed += ']' * arr_open
    # 补全对象
    fixed += '}' * depth

    try:
        result = json.loads(fixed)
        if isinstance(result, dict):
            logger.info(f"截断 JSON 修复成功: 补全了 {depth} 个括号")
            return result
    except json.JSONDecodeError:
        pass
    return None


class BaseReviewAgent:
    """审稿 Agent 基类。"""

    def __init__(self, name: str, system_prompt: str, llm_client: Optional[LLMClient] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm_client or LLMClient()

    def review(self, article_text: str, article_id: str = "",
               model_tier: str = "pro") -> ReviewReport:
        """审稿一篇完整的文章。

        Args:
            article_text: 文章全文
            article_id: 文章 ID
            model_tier: 使用的模型层级

        Returns:
            审稿报告
        """
        logger.info(f"{self.name} 开始审稿...")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"请审阅以下文章：\n\n{article_text}"},
        ]

        try:
            response = self.llm.chat(messages, model_tier=model_tier, temperature=0.3)
            report = self._parse_response(response, article_id)
        except BudgetExceeded:
            # 成本护栏：预算耗尽必须向上中断，不允许逐 Agent 降级吞掉
            raise
        except LLMUnavailableError as e:
            # 基础设施故障（重试后仍失败）：记录错误级别，返回带说明的降级报告
            logger.error(f"{self.name} 审稿 API 不可用: {e}")
            report = ReviewReport(
                agent=self.name,
                article_id=article_id,
                overall_assessment=f"审稿失败（API 不可用）: {e}",
                issues=[],
                score=0.0,
            )
        except Exception as e:
            logger.warning(f"{self.name} 审稿 API 调用失败: {e}")
            report = ReviewReport(
                agent=self.name,
                article_id=article_id,
                overall_assessment=f"审稿失败: {e}",
                issues=[],
                score=0.0,
            )
        return report

    def _parse_response(self, response: str, article_id: str) -> ReviewReport:
        """解析 LLM 审稿结果。"""
        import json
        data = safe_json_parse(response)
        if data is None:
            data = find_json_in_text(response)

        if data is None:
            data = _try_fix_truncated_json(response)

        if data is None:
            # 从 response 中提取评分
            import re as _re
            score = 5.0
            score_match = _re.search(r'(?:评分|分数|得分|score)[：:\s]*(\d+(?:\.\d+)?)', response, _re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
            # JSON 解析完全失败，返回空 issues（不展示原始文本）
            return ReviewReport(
                agent=self.name,
                article_id=article_id,
                overall_assessment=f"审稿完成（JSON 解析失败，无法展示结构化结果）",
                strengths=[],
                issues=[],
                score=max(0, min(10, score)),
            )

        try:
            raw_issues = data.get("issues", [])
            if not isinstance(raw_issues, list):
                raw_issues = []
            # 过滤掉非 dict 的 issue（LLM 可能返回 string 类型 issue）
            issues = [
                ReviewIssue(
                    agent=self.name,
                    level=_safe_int_level(issue.get("level", 2)),
                    location=issue.get("location", ""),
                    severity=issue.get("severity", "warning"),
                    description=issue.get("description", ""),
                    suggestion=issue.get("suggestion", ""),
                    before_text=issue.get("before_text", ""),
                    after_text=issue.get("after_text", ""),
                    auto_fixable=_safe_int_level(issue.get("level", 2)) == 1,
                )
                for issue in raw_issues if isinstance(issue, dict)
            ]
            # 从 JSON data 或 response 中提取评分（大小写不敏感）
            score = data.get("score") or data.get("评分") or data.get("分数")
            if score is None:
                # 遍历 data keys 找任何类似 score 的字段
                for k, v in data.items():
                    if k.lower() in ("score", "评分", "分数", "得分", "grade", "rating"):
                        try:
                            score = float(v)
                            break
                        except (ValueError, TypeError):
                            continue
            if score is None:
                import re as _re
                score_match = _re.search(r'(?:评分|分数|得分|score)[：:\s]*(\d+(?:\.\d+)?)', response, _re.IGNORECASE)
                score = float(score_match.group(1)) if score_match else 5.0
            else:
                try:
                    score = float(score)
                except (ValueError, TypeError):
                    score = 5.0
            return ReviewReport(
                agent=self.name,
                article_id=article_id,
                overall_assessment=data.get("overall_assessment", ""),
                strengths=data.get("strengths", []),
                issues=issues,
                score=score,
            )
        except (json.JSONDecodeError, KeyError):
            return ReviewReport(
                agent=self.name,
                article_id=article_id,
                overall_assessment=response[:500],
                issues=[],
                score=5.0,
            )
