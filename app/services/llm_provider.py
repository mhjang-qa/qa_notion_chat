from __future__ import annotations

from typing import Any

import requests

from app.core import config


class LLMProviderError(RuntimeError):
    pass


class LLMQuotaExceededError(LLMProviderError):
    pass


def _is_quota_error(status_code: int, body: str) -> bool:
    lowered = (body or "").lower()
    return status_code == 429 or any(
        token in lowered
        for token in (
            "quota",
            "resource_exhausted",
            "rate limit",
            "rate_limit",
            "too many requests",
        )
    )


def _gemini_generate(prompt: str) -> str:
    if not config.GEMINI_API_KEY:
        raise LLMProviderError("GEMINI_API_KEY가 설정되지 않았습니다.")

    model = config.GEMINI_MODEL or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": 900,
        },
    }

    try:
        response = requests.post(url, params={"key": config.GEMINI_API_KEY}, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise LLMProviderError(f"Gemini API 호출 실패: {exc}") from exc
    if response.status_code >= 400:
        if _is_quota_error(response.status_code, response.text):
            raise LLMQuotaExceededError(f"Gemini API 쿼터 초과 ({response.status_code}): {response.text}")
        raise LLMProviderError(f"Gemini API 오류 ({response.status_code}): {response.text}")

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMProviderError("Gemini API 응답에 후보 답변이 없습니다.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    answer = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
    if not answer:
        raise LLMProviderError("Gemini API 빈 응답")
    return answer


def generate_text(prompt: str) -> str:
    provider = (config.LLM_PROVIDER or "gemini").lower()
    if provider != "gemini":
        raise LLMProviderError(f"지원하지 않는 LLM_PROVIDER입니다: {provider}")
    return _gemini_generate(prompt)
