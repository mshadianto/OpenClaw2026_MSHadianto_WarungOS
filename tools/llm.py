"""Shared LLM client wrapping Sumopod (OpenAI-compatible) with retry."""
import os
import time
import logging
from openai import OpenAI, RateLimitError, APIError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client = OpenAI(
    api_key=os.getenv("SUMOPOD_API_KEY"),
    base_url=os.getenv("SUMOPOD_BASE_URL"),
)
MODEL = os.getenv("SUMOPOD_MODEL", "claude-sonnet-4-6")


def _with_retry(call_fn, max_retries: int = 4):
    """Retry wrapper with exponential backoff for rate limits & transient errors."""
    for attempt in range(max_retries):
        try:
            return call_fn()
        except RateLimitError as e:
            wait = 2 ** attempt * 3  # 3, 6, 12, 24 seconds
            logger.warning(f"Rate limit hit (attempt {attempt+1}/{max_retries}). Waiting {wait}s...")
            time.sleep(wait)
        except APIError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning(f"API error {e}, retrying in {wait}s...")
            time.sleep(wait)
    raise RateLimitError("Max retries exceeded for rate limit") from None


def chat(system: str, user: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
    def _call():
        completion = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return completion.choices[0].message.content
    return _with_retry(_call)


def chat_with_history(messages: list[dict], max_tokens: int = 800, temperature: float = 0.7) -> str:
    def _call():
        completion = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return completion.choices[0].message.content
    return _with_retry(_call)
