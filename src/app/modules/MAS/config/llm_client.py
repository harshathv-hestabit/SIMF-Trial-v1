import asyncio
import json
import random
from dataclasses import dataclass
from typing import Any, List

from aiolimiter import AsyncLimiter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from .settings import settings

_PROVIDER_CLIENTS = {
    "openai": ChatOpenAI,
    "nvidia": ChatOpenAI,
    "gemini": ChatGoogleGenerativeAI,
}


@dataclass(slots=True)
class LLMBackend:
    name: str
    model: str
    provider: str
    llm: Any
    limiter: AsyncLimiter
    semaphore: asyncio.Semaphore

    async def invoke(self, messages: List[Any]):
        async with self.limiter:
            async with self.semaphore:
                return await self.llm.ainvoke(messages)


@dataclass(slots=True)
class LLMCallResult:
    text: str
    backend_name: str
    backend_provider: str
    backend_model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    raw_usage: dict[str, Any]


class LLMClient:
    def __init__(self, backends: list[LLMBackend], max_retries: int = 3):
        if not backends:
            raise ValueError("LLM backend pool cannot be empty")

        self.backends = backends
        self.max_retries = max_retries
        self._rr_index = 0
        self._rr_lock = asyncio.Lock()

    @classmethod
    def from_config(
        cls,
        pool_config: str | None = None,
        max_retries: int | None = None,
    ) -> "LLMClient":
        backends = cls._build_backends(pool_config=pool_config)
        return cls(
            backends=backends,
            max_retries=max_retries if max_retries is not None else settings.LLM_MAX_RETRIES,
        )

    @classmethod
    def _build_backends(cls, pool_config: str | None = None) -> list[LLMBackend]:
        raw_pool = (pool_config if pool_config is not None else settings.LLM_POOL_CONFIG).strip()
        if not raw_pool:
            raw_entries = [
                {
                    "name": "primary",
                    "model": "meta/llama-3.1-70b-instruct",
                    "provider": "nvidia",
                    "api_key": settings.LLM_API_KEY,
                    "base_url": settings.LLM_BASE_URL,
                    "rpm": 30,
                    "concurrency": 2,
                    "temperature": settings.LLM_TEMPERATURE,
                }
            ]
        else:
            try:
                raw_entries = json.loads(raw_pool)
            except json.JSONDecodeError as exc:
                raise ValueError("LLM_POOL_CONFIG must be valid JSON") from exc

        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError("LLM_POOL_CONFIG must be a non-empty JSON array")

        return [cls._build_backend(entry, index) for index, entry in enumerate(raw_entries)]

    @staticmethod
    def _default_provider_kwargs(provider: str) -> dict[str, Any]:
        if provider in {"openai", "nvidia"}:
            return {
                "api_key": settings.LLM_API_KEY,
                "base_url": settings.LLM_BASE_URL,
                "temperature": settings.LLM_TEMPERATURE,
            }

        if provider == "gemini":
            return {
                "api_key": settings.GOOGLE_API_KEY,
                "temperature": settings.LLM_TEMPERATURE,
            }

        return {}

    @staticmethod
    def _build_backend(entry: Any, index: int) -> LLMBackend:
        if not isinstance(entry, dict):
            raise ValueError(f"LLM pool entry at index {index} must be an object")

        provider = str(entry.get("provider", "nvidia")).lower()
        client_cls = _PROVIDER_CLIENTS.get(provider)
        if client_cls is None:
            supported = ", ".join(sorted(_PROVIDER_CLIENTS))
            raise ValueError(
                f"Unsupported LLM provider '{provider}' for entry {index}. "
                f"Supported providers: {supported}"
            )

        name = str(entry.get("name") or f"backend-{index + 1}")
        model = entry.get("model")
        provider_defaults = LLMClient._default_provider_kwargs(provider)
        api_key = entry.get("api_key") or provider_defaults.get("api_key")
        if not model or not api_key:
            raise ValueError(
                f"LLM pool entry '{name}' must define both 'model' and 'api_key'"
            )

        rpm = int(entry.get("rpm", 60))
        concurrency = int(entry.get("concurrency", 1))

        llm_kwargs = dict(provider_defaults)
        llm_kwargs.update(
            {
                key: value
                for key, value in entry.items()
                if key
                not in {
                    "name",
                    "model",
                    "provider",
                    "api_key",
                    "rpm",
                    "concurrency",
                }
            }
        )
        llm_kwargs.pop("api_key", None)

        llm = client_cls(
            model=model,
            api_key=api_key,
            **llm_kwargs,
        )
        return LLMBackend(
            name=name,
            model=str(model),
            provider=provider,
            llm=llm,
            limiter=AsyncLimiter(rpm, 60),
            semaphore=asyncio.Semaphore(concurrency),
        )

    async def _next_start_index(self) -> int:
        async with self._rr_lock:
            start_index = self._rr_index
            self._rr_index = (self._rr_index + 1) % len(self.backends)
            return start_index

    def _ordered_backends(self, start_index: int) -> list[LLMBackend]:
        total = len(self.backends)
        return [self.backends[(start_index + offset) % total] for offset in range(total)]

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        error_text = str(exc).lower()
        return "rate_limit" in error_text or "429" in error_text or "too many requests" in error_text

    @staticmethod
    def extract_text(response: Any) -> str:
        content = getattr(response, "content", response)

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str):
                        parts.append(text)

            return "\n".join(part for part in parts if part).strip()

        return str(content).strip()

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def extract_usage(cls, response: Any) -> dict[str, Any]:
        usage: dict[str, Any] = {}

        usage_metadata = getattr(response, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            usage.update(usage_metadata)

        response_metadata = getattr(response, "response_metadata", None)
        if isinstance(response_metadata, dict):
            token_usage = response_metadata.get("token_usage")
            if isinstance(token_usage, dict):
                usage.update(token_usage)
            usage_section = response_metadata.get("usage")
            if isinstance(usage_section, dict):
                usage.update(usage_section)

        if not usage and isinstance(response, dict):
            for key in ("usage", "usage_metadata", "token_usage"):
                value = response.get(key)
                if isinstance(value, dict):
                    usage.update(value)

        prompt_tokens = cls._as_int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("prompt_token_count")
        )
        completion_tokens = cls._as_int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("candidates_token_count")
        )
        total_tokens = cls._as_int(
            usage.get("total_tokens")
            or usage.get("total_token_count")
            or usage.get("totalTokens")
        )
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "raw_usage": usage,
        }

    async def call(self, messages: List[Any]):
        response, _ = await self.call_with_backend(messages)
        return response

    async def call_with_backend(self, messages: List[Any]) -> tuple[Any, LLMBackend]:
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            start_index = await self._next_start_index()
            saw_rate_limit = False

            for backend in self._ordered_backends(start_index):
                try:
                    response = await backend.invoke(messages)
                    return response, backend
                except Exception as exc:
                    last_error = exc
                    if self._is_rate_limit_error(exc):
                        saw_rate_limit = True
                        print(
                            f"[LLM] Backend '{backend.name}' rate limited. "
                            "Trying next backend."
                        )
                        continue

                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(1)
                    break
            else:
                if saw_rate_limit and attempt < self.max_retries - 1:
                    sleep_time = (2**attempt) + random.uniform(0, 1)
                    print(
                        f"[LLM] All backends rate limited. Retrying in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                    continue

        if last_error is not None:
            raise last_error

        raise RuntimeError("LLM call failed after retries")

    async def call_text(self, messages: List[Any]) -> str:
        result = await self.call_text_with_usage(messages)
        return result.text

    async def call_text_with_usage(self, messages: List[Any]) -> LLMCallResult:
        response, backend = await self.call_with_backend(messages)
        usage = self.extract_usage(response)
        return LLMCallResult(
            text=self.extract_text(response),
            backend_name=backend.name,
            backend_provider=backend.provider,
            backend_model=backend.model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            raw_usage=usage["raw_usage"],
        )


_llm_client = None


def get_llm():
    global _llm_client

    if _llm_client is None:
        _llm_client = LLMClient.from_config()

    return _llm_client
