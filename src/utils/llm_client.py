"""
utils.llm_client — LLM API 客户端（支持动态双模型路由）。

P0-1 硬化：
- 按 tier 的 RPM 令牌桶限流（读取 rpm_limit）
- 429 / 5xx / 网络错误 指数退避重试（max_retries / retry_base_delay / timeout_seconds）
- 重试耗尽后抛 LLMUnavailableError（上层不再静默吞掉基础设施故障）
- 每次调用前检查会话预算（cost_tracker.assert_budget，超支抛 BudgetExceeded）
"""

import threading
import time
from pathlib import Path
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from config.settings import get_config
from src.utils.cost_tracker import UsageRecord, get_tracker
from src.utils.logger import logger


class LLMUnavailableError(RuntimeError):
    """LLM API 在重试后仍不可用（网络/429/5xx/超时）。"""

    def __init__(self, message: str, cause: BaseException | None = None):
        super().__init__(message)
        self.cause = cause


def _mask_api_key(key: str) -> str:
    """对 API Key 脱敏，只显示前4字符。"""
    if len(key) <= 8:
        return key[:4] + "..."
    return key[:4] + "..." + key[-4:]


class _RateLimiter:
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
            # 锁外等待，避免长时间占锁；每 50ms 醒来看一次
            time.sleep(min(wait, 0.05))


class _DynamicLLMConfig:
    """运行时动态 LLM 配置（替代静态 LLMConfig）。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        rpm_limit: int = 50,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        thinking: bool = True,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.rpm_limit = rpm_limit
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.thinking = thinking


def _num(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fnum(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _thinking_payload(thinking: bool) -> dict:
    """DeepSeek 的 thinking 开关是**对象**，不是布尔。

    传 `thinking: false` 会被服务端 422 拒绝（expected struct）；
    正确形状是 `{"thinking": {"type": "disabled"}}`。抽成纯函数便于测试锁定。

    本项目**默认保持思考开启**（`config.yaml` 里 `llm.<tier>.thinking: true`）：
    思考质量优先，靠"把 max_tokens 加够"来容纳它。这个开关只留给运维按档位关停。
    """
    return {"thinking": {"type": "enabled" if thinking else "disabled"}}


def _request_payload(*, model: str, messages: list, temperature: float,
                     max_tokens: int, timeout: float, thinking: bool,
                     json_mode: bool) -> dict:
    """构造 `chat.completions.create` 的形参（纯函数，便于测试锁定 wire 形状）。

    `json_mode=True` 时补上 `response_format={"type": "json_object"}`：
    思考开着时模型偶尔会用散文回答（实测同一提示词 content 无法解析），
    这个约束是"结构化输出可用"的保证，且**不影响思考**。
    """
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "extra_body": _thinking_payload(thinking),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


class LLMClient:
    """LLM API 客户端，支持 Flash/Pro 双模型路由及运行时动态配置。"""

    def __init__(self):
        cfg = get_config()
        self.flash_cfg = cfg.llm.get("deepseek_v4_flash")
        self.pro_cfg = cfg.llm.get("deepseek_v4_pro")
        # 运行时动态覆盖配置（优先级高于静态配置）
        self._overrides: dict[str, _DynamicLLMConfig] = {}
        self._flash_client: OpenAI | None = None
        self._pro_client: OpenAI | None = None
        self._rl: dict[str, _RateLimiter] = {}
        self._rl_lock = threading.Lock()
        self._apply_session_guards(cfg)

    def _apply_session_guards(self, cfg) -> None:
        """把 config.yaml 的预算/用量落库配置应用到全局 tracker。"""
        budget = getattr(cfg, "budget", None)
        if budget is None:
            return
        try:
            tracker = get_tracker()
            if budget.max_cny_per_session and budget.max_cny_per_session > 0:
                tracker.configure(budget_cny=budget.max_cny_per_session)
            usage_db = budget.usage_db or ""
            if usage_db:
                if not Path(usage_db).is_absolute():
                    usage_db = str(Path(cfg.project_root) / usage_db)
                tracker.configure(usage_db_path=usage_db)
        except Exception as e:
            if getattr(budget, "max_cny_per_session", 0) > 0:
                raise RuntimeError("无法启用会话预算保护，已阻止发起模型调用") from e
            logger.warning(f"会话预算/用量配置失败: {e}")

    def _get_effective_cfg(self, tier: str):
        """获取 tier 的有效配置：动态覆盖优先，其次静态配置。"""
        if tier in self._overrides:
            return self._overrides[tier]
        if tier == "flash":
            return self.flash_cfg
        elif tier == "pro":
            return self.pro_cfg
        return None

    def _get_client(self, tier: str) -> OpenAI | None:
        """获取 tier 对应的 OpenAI 客户端（考虑动态覆盖）。

        未配置 api_key 时返回 None（而不是拿空 Key 去构造客户端）—— 这样
        `chat()` 会抛出明确的"模型层未配置"，而不是一个语焉不详的
        OpenAIError / 401 "Your api key: ****KEY is invalid"。
        """
        cfg = self._get_effective_cfg(tier)
        if cfg is None or not self._has_key(cfg):
            return None
        if tier == "flash":
            if self._flash_client is None:
                self._flash_client = OpenAI(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                )
            return self._flash_client
        elif tier == "pro":
            if self._pro_client is None:
                self._pro_client = OpenAI(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                )
            return self._pro_client
        return None

    @staticmethod
    def _has_key(cfg) -> bool:
        """Key 是否真的配好了（空串或未解析的 ${VAR} 都算没配）。"""
        key = (getattr(cfg, "api_key", "") or "").strip()
        return bool(key) and "${" not in key

    def _rate_limiter(self, tier: str, rpm: int) -> _RateLimiter:
        with self._rl_lock:
            rl = self._rl.get(tier)
            if rl is None or rl.interval != (60.0 / rpm if rpm and rpm > 0 else 0.0):
                rl = _RateLimiter(rpm)
                self._rl[tier] = rl
            return rl

    @property
    def flash(self) -> OpenAI | None:
        return self._get_client("flash")

    @property
    def pro(self) -> OpenAI | None:
        return self._get_client("pro")

    def chat(
        self,
        messages: list[dict],
        model_tier: str = "flash",
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        thinking: bool | None = None,
        json_mode: bool = False,
    ) -> str:
        """调用 LLM chat 补全（带限流 + 重试 + 预算检查）。

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model_tier: "flash" 或 "pro"
            temperature: 温度（默认使用配置值）
            max_tokens: 最大 token 数（默认使用配置值）
            timeout: 单次请求超时秒数（默认使用配置值）
            thinking: 是否开启思考（None = 用该档配置值，**缺省开启**）。
                思考会先消耗 max_tokens，所以该档的 max_tokens 必须足够大。
            json_mode: 需要结构化 JSON 输出时置 True，会补上
                `response_format={"type": "json_object"}`（与思考可共存，
                是"折腾半天拿到散文"的解法）。

        Returns:
            模型回复文本

        Raises:
            RuntimeError: 模型层未配置
            BudgetExceeded: 会话预算已耗尽
            LLMUnavailableError: 重试后仍网络/服务端失败
        """
        client = self._get_client(model_tier)
        if client is None:
            raise RuntimeError(f"模型层 '{model_tier}' 未配置，请先在设置中配置 API")
        cfg = self._get_effective_cfg(model_tier)

        # 预算硬闸：调用前检查
        get_tracker().assert_budget()

        # RPM 限流
        rpm = _num(getattr(cfg, "rpm_limit", None), 50)
        self._rate_limiter(model_tier, rpm).acquire()

        if temperature is None:
            temperature = cfg.temperature
        if max_tokens is None:
            max_tokens = cfg.max_tokens
        if timeout is None:
            timeout = _fnum(getattr(cfg, "timeout_seconds", None), 60)
        if thinking is None:
            thinking = bool(getattr(cfg, "thinking", True))

        max_retries = max(0, _num(getattr(cfg, "max_retries", None), 3))
        base_delay = _fnum(getattr(cfg, "retry_base_delay", None), 1.0)
        model = getattr(cfg, "model", "deepseek-chat")

        last_exc: BaseException | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._request(
                    client,
                    cfg,
                    model,
                    model_tier,
                    messages,
                    temperature,
                    max_tokens,
                    timeout,
                    thinking,
                    json_mode,
                )
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                last_exc = e
                if attempt >= max_retries:
                    break
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"{model_tier} 调用失败（{type(e).__name__}），"
                    f"{delay:.1f}s 后重试 ({attempt + 1}/{max_retries}): {str(e)[:120]}"
                )
                time.sleep(delay)
            except APIStatusError as e:
                last_exc = e
                code = getattr(e, "status_code", 0) or 0
                if code >= 500 and attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"{model_tier} 服务端错误 {code}，"
                        f"{delay:.1f}s 后重试 ({attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                raise LLMUnavailableError(
                    f"{model_tier} API 错误 {code}: {str(e)[:200]}",
                    e,
                ) from e

        raise LLMUnavailableError(
            f"{model_tier} 调用在 {max_retries + 1} 次尝试后仍失败: {str(last_exc)[:200]}",
            last_exc,
        )

    def _request(
        self,
        client,
        cfg,
        model,
        model_tier,
        messages,
        temperature,
        max_tokens,
        timeout,
        thinking: bool = True,
        json_mode: bool = False,
    ) -> str:
        logger.debug(
            f"LLM 调用: model_tier={model_tier}, model={model}, "
            f"messages={len(messages)}条, temperature={temperature}, "
            f"thinking={thinking}, json_mode={json_mode}"
        )

        # 思考**先于**正文消耗 max_tokens：预算不够时会出现
        # 「completion 打满、content 为空串」（2026-10-13 审稿 6 维里 4 维翻车）。
        # 对策是把 max_tokens 加到能容纳思考（见 config.yaml），而不是关掉思考。
        payload = _request_payload(
            model=model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, timeout=timeout,
            thinking=thinking, json_mode=json_mode,
        )
        t0 = time.time()
        response = client.chat.completions.create(**payload)
        elapsed = time.time() - t0

        result = response.choices[0].message.content or ""

        # 记录用量
        usage = response.usage
        if usage:
            record = UsageRecord(
                model_tier=model_tier,
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
                duration=elapsed,
                model=model,
            )
            get_tracker().add_record(record)
            if not result and (usage.completion_tokens or 0) > 0:
                # 空内容 + 有输出 token = 钱花了但什么都没拿到，必须留下痕迹
                logger.warning(
                    f"模型返回空内容，却消耗了 {usage.completion_tokens} 输出 tokens"
                    f"（思考吃满输出预算？tier={model_tier}, thinking={thinking}）"
                )

        logger.debug(f"LLM 返回: {len(result)} chars ({elapsed:.1f}s)")
        return result

    # ========== 运行时动态配置 ==========

    def update_tier_config(
        self,
        tier: str,
        api_key: str,
        base_url: str,
        model: str,
        **kwargs,
    ) -> bool:
        """运行时更新指定 tier 的 LLM 配置。

        Args:
            tier: "flash" 或 "pro"
            api_key: API Key
            base_url: API 基础 URL
            model: 模型名称
            **kwargs: 可选覆盖 temperature, max_tokens, rpm_limit,
                      timeout_seconds, max_retries, retry_base_delay

        Returns:
            是否成功
        """
        if tier not in ("flash", "pro"):
            logger.warning(f"update_tier_config: 无效 tier '{tier}'")
            return False

        self._overrides[tier] = _DynamicLLMConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.7),
            rpm_limit=kwargs.get("rpm_limit", 50),
            timeout_seconds=kwargs.get("timeout_seconds", 60),
            max_retries=kwargs.get("max_retries", 3),
            retry_base_delay=kwargs.get("retry_base_delay", 1.0),
            thinking=kwargs.get("thinking", True),
        )

        # 清除客户端缓存，下次访问时用新配置重建
        if tier == "flash":
            self._flash_client = None
        elif tier == "pro":
            self._pro_client = None

        logger.info(f"运行时更新模型配置: {tier}={model} @ {base_url}")
        return True

    def get_tier_info(self, tier: str) -> dict[str, Any] | None:
        """获取指定 tier 的当前配置信息（API Key 脱敏）。"""
        cfg = self._get_effective_cfg(tier)
        if cfg is None:
            return None
        return {
            "api_key": _mask_api_key(cfg.api_key),
            "base_url": cfg.base_url,
            "model": cfg.model,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "rpm_limit": cfg.rpm_limit,
            "timeout_seconds": getattr(cfg, "timeout_seconds", None),
            "max_retries": getattr(cfg, "max_retries", None),
            "retry_base_delay": getattr(cfg, "retry_base_delay", None),
            "thinking": getattr(cfg, "thinking", True),
        }

    def get_available_tiers(self) -> list[str]:
        """获取所有**可用**（即 Key 已配置）的 tier 名称。"""
        tiers = []
        for tier in ("flash", "pro"):
            cfg = self._get_effective_cfg(tier)
            if cfg is not None and self._has_key(cfg):
                tiers.append(tier)
        return tiers
