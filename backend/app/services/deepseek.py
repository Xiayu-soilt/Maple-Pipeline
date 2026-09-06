import json
from typing import AsyncGenerator

import httpx

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class DeepSeekError(Exception):
    pass


def _headers() -> dict:
    if not DEEPSEEK_API_KEY:
        raise DeepSeekError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写")
    return {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}


async def chat(messages: list[dict], temperature: float = 0.3, json_mode: bool = False) -> str:
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{DEEPSEEK_BASE_URL}/chat/completions", headers=_headers(), json=payload)
        if resp.status_code != 200:
            raise DeepSeekError(f"DeepSeek 接口返回 {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]


async def chat_stream(messages: list[dict], temperature: float = 0.3) -> AsyncGenerator[str, None]:
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{DEEPSEEK_BASE_URL}/chat/completions",
                                 headers=_headers(), json=payload) as resp:
            if resp.status_code != 200:
                text = await resp.aread()
                raise DeepSeekError(f"DeepSeek 接口返回 {resp.status_code}: {text.decode()[:300]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise
