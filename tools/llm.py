"""Shared LLM client wrapping Sumopod (OpenAI-compatible)."""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(
    api_key=os.getenv("SUMOPOD_API_KEY"),
    base_url=os.getenv("SUMOPOD_BASE_URL"),
)
MODEL = os.getenv("SUMOPOD_MODEL", "claude-sonnet-4-6")


def chat(system: str, user: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
    """Simple chat completion."""
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


def chat_with_history(messages: list[dict], max_tokens: int = 800, temperature: float = 0.7) -> str:
    """Chat with full message history."""
    completion = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return completion.choices[0].message.content
