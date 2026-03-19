import asyncio
import random
from typing import Any, List
from aiolimiter import AsyncLimiter
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from .settings import settings

_PROVIDER_CLIENTS = {
    "openai": ChatOpenAI,
    "gemini": ChatGoogleGenerativeAI,
}

class LLMClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        provider: str = "openai",
        rpm: int = 60,
        concurrency: int = 2,
        max_retries: int = 3,
        **kwargs: Any,
    ):
        provider_key = provider.lower()
        client_cls = _PROVIDER_CLIENTS.get(provider_key)
        if client_cls is None:
            supported = ", ".join(sorted(_PROVIDER_CLIENTS))
            raise ValueError(
                f"Unsupported LLM provider '{provider}'. Supported providers: {supported}"
            )

        llm_kwargs = dict(kwargs)

        self.llm = client_cls(
            model=model,
            api_key=api_key,
            **llm_kwargs,
        )
        self.limiter = AsyncLimiter(rpm, 60)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.max_retries = max_retries

    async def _call(self, messages: List[Any]):
        async with self.limiter:
            async with self.semaphore:
                return await self.llm.ainvoke(messages)

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

    async def call(self, messages: List[Any]):
        for attempt in range(self.max_retries):
            try:
                return await self._call(messages)

            except Exception as e:
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"[LLM] Rate limited. Retrying in {sleep_time:.2f}s...")
                    await asyncio.sleep(sleep_time)
                else:
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(1)

        raise RuntimeError("LLM call failed after retries")

    async def call_text(self, messages: List[Any]) -> str:
        response = await self.call(messages)
        return self.extract_text(response)
    
_llm_client = None

def get_llm():
    global _llm_client

    if _llm_client is None:
        _llm_client = LLMClient(
            model="openai/gpt-oss-120b",
            api_key=settings.GROQ_API_KEY,
            provider="openai",
            rpm=30,
            concurrency=1,
            base_url=settings.GROQ_BASE_URL,
            temperature=0.3,
        )

    return _llm_client

# def get_llm():
#     global _llm_client

#     if _llm_client is None:
#         _llm_client = LLMClient(
#             model="gemini-3.1-flash-lite-preview",
#             api_key=settings.GOOGLE_API_KEY,
#             provider="gemini",
#             rpm=3,
#             concurrency=1,
#             temperature=1,
#         )

#     return _llm_client
