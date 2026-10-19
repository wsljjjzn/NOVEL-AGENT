"""
utils.cost_tracker — LLM 调用开销追踪器。

追踪每次调用的 token 数、模型层级、估算费用。
支持：
- 会话硬预算（超支抛 BudgetExceeded，由 LLM 客户端在发起调用前检查）
- 用量持久化到独立 SQLite 小库（llm_usage），便于事后对账
- 输出到终端日志，并支持查询累计统计
"""

import time
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.logger import logger


# DeepSeek V4 参考定价（$ / 百万 tokens），可通过 configure(pricing=...) 覆盖
PRICING = {
    "flash": {"input": 0.14, "output": 0.28},
    "pro": {"input": 0.435, "output": 0.87},
}

# 人民币汇率
USD_TO_CNY = 7.25

_DEFAULT_USAGE_DB = "data/knowledge/llm_usage.db"


class BudgetExceeded(RuntimeError):
    """单会话成本预算已耗尽——应中断后续 LLM 调用，而不是降级继续。"""


class UsageRecord:
    """单次调用的用量记录。"""
    def __init__(self, model_tier: str, prompt_tokens: int = 0,
                 completion_tokens: int = 0, duration: float = 0.0,
                 model: str = "", pricing: Optional[dict] = None):
        self.model_tier = model_tier
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.duration = duration
        self.timestamp = datetime.now()
        self._pricing = pricing

    def use_pricing(self, pricing: dict) -> None:
        if self._pricing is None:
            self._pricing = pricing

    @property
    def _price(self) -> dict:
        # _pricing 若为完整 tier 映射，则取当前 tier；否则回退模块默认价
        if self._pricing is not None:
            p = self._pricing
            if isinstance(p, dict) and "input" in p and self.model_tier not in p:
                return p
            if self.model_tier in p:
                return p[self.model_tier]
        return PRICING.get(self.model_tier, PRICING["flash"])

    @property
    def cost_usd(self) -> float:
        p = self._price
        return (self.prompt_tokens * p["input"] + self.completion_tokens * p["output"]) / 1_000_000

    @property
    def cost_cny(self) -> float:
        return self.cost_usd * USD_TO_CNY

    def __str__(self):
        return (f"[{self.model_tier.upper()}] {self.prompt_tokens}in + "
                f"{self.completion_tokens}out tokens | "
                f"¥{self.cost_cny:.5f} | {self.duration:.1f}s")


class CostTracker:
    """全局开销追踪器（线程安全）。"""

    def __init__(self, pricing: Optional[dict] = None,
                 budget_cny: float = 0.0,
                 usage_db_path: str = ""):
        self._records: list[UsageRecord] = []
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._pricing = pricing or dict(PRICING)
        self._budget_cny = budget_cny
        self._usage_db_path = usage_db_path or ""
        self._usage_conn: Optional[sqlite3.Connection] = None
        # 并行审稿会有多个 worker 线程同时落库，写操作必须串行化
        self._db_lock = threading.Lock()

    # ========== 配置 ==========

    def configure(self, pricing: Optional[dict] = None,
                  budget_cny: Optional[float] = None,
                  usage_db_path: Optional[str] = None) -> None:
        """幂等地应用运行时配置（不影响已累计的记录）。"""
        if pricing:
            self._pricing = dict(pricing)
        if budget_cny is not None:
            self._budget_cny = float(budget_cny)
        if usage_db_path:
            self._usage_db_path = usage_db_path

    @property
    def budget_cny(self) -> float:
        return self._budget_cny

    def assert_budget(self) -> None:
        """预算硬闸：超支则抛 BudgetExceeded（发起新调用前调用）。"""
        if self._budget_cny > 0 and self.total_cost_cny >= self._budget_cny:
            raise BudgetExceeded(
                f"会话预算已用完：已花费 ¥{self.total_cost_cny:.4f} / 上限 ¥{self._budget_cny:.2f}。"
                "可调大 config.yaml budget.max_cny_per_session 或换更省模型。"
            )

    # ========== 记录 ==========

    def add_record(self, record: UsageRecord):
        record.use_pricing(self._pricing)
        with self._lock:
            self._records.append(record)
        # 终端日志
        logger.info(f"LLM 调用: {record}")
        self._persist(record)

    def _persist(self, record: UsageRecord) -> None:
        """把单条记录写入 llm_usage 小库（尽力而为，失败不影响主流程）。

        并行审稿会从多个 worker 线程同时落库：连接必须
        `check_same_thread=False`，且建连与写入都要在同一把锁里串行化，
        否则 SQLite 直接拒绝跨线程使用，记录被静默吞掉
        （REVIEW-2026-10-12.md F3.3；实测 6 个维度只落 0-1 行）。
        失败用 WARNING 而不是 DEBUG：这条库是对账依据，丢了必须看得见。
        """
        if not self._usage_db_path:
            return
        try:
            with self._db_lock:
                if self._usage_conn is None:
                    path = Path(self._usage_db_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self._usage_conn = sqlite3.connect(
                        str(path), check_same_thread=False,
                    )
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
            logger.warning(f"用量持久化失败（对账库会少行）: {e}")

    @property
    def total_calls(self) -> int:
        return len(self._records)

    @property
    def total_cost_cny(self) -> float:
        with self._lock:
            return sum(r.cost_cny for r in self._records)

    @property
    def total_tokens(self) -> tuple[int, int]:
        prompt = sum(r.prompt_tokens for r in self._records)
        completion = sum(r.completion_tokens for r in self._records)
        return prompt, completion

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time

    def summary(self) -> str:
        prompt, completion = self.total_tokens
        total_tok = prompt + completion
        budget_note = ""
        if self._budget_cny > 0:
            budget_note = f"\n- 预算上限: ¥{self._budget_cny:.2f}"
        return (
            f"**LLM 调用统计**\n"
            f"- 调用次数: {self.total_calls}\n"
            f"- 输入 tokens: {prompt:,}\n"
            f"- 输出 tokens: {completion:,}\n"
            f"- 总 tokens: {total_tok:,}\n"
            f"- 总费用: ¥{self.total_cost_cny:.4f}{budget_note}\n"
            f"- 运行时间: {self.elapsed/60:.1f} 分钟"
        )

    def markdown_summary(self) -> str:
        """返回 Markdown 格式的统计。"""
        prompt, completion = self.total_tokens
        total_tok = prompt + completion
        budget_note = ""
        if self._budget_cny > 0:
            budget_note = f"（上限 ¥{self._budget_cny:.2f}）"
        lines = [
            "### LLM 调用统计",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 调用次数 | {self.total_calls} |",
            f"| 输入 tokens | {prompt:,} |",
            f"| 输出 tokens | {completion:,} |",
            f"| 总 tokens | {total_tok:,} |",
            f"| 总费用 | ¥{self.total_cost_cny:.4f}{budget_note} |",
            f"| 运行时间 | {self.elapsed/60:.1f} 分钟 |",
        ]
        return "\n".join(lines)

    def snapshot(self):
        """保存当前快照，供 delta_summary 使用。"""
        self._snapshot_calls = self.total_calls
        p, c = self.total_tokens
        self._snapshot_tokens = p + c
        self._snapshot_cost = self.total_cost_cny
        self._snapshot_time = self.elapsed

    def delta_summary(self) -> str:
        """自上次 snapshot 以来的增量开销。"""
        if not hasattr(self, '_snapshot_calls'):
            self.snapshot()
            return ""
        d_calls = self.total_calls - self._snapshot_calls
        if d_calls == 0:
            return ""
        p, c = self.total_tokens
        d_tokens = (p + c) - self._snapshot_tokens
        d_cost = self.total_cost_cny - self._snapshot_cost
        d_time = self.elapsed - self._snapshot_time
        return f"本次调用: {d_calls} 次 | {d_tokens} tokens | ¥{d_cost:.5f} | {d_time:.1f}s"


# 全局单例
_tracker: Optional[CostTracker] = None
_tracker_lock = threading.Lock()


def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = CostTracker()
    return _tracker
