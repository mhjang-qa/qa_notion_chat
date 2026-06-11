from __future__ import annotations

import logging
from typing import Any

import requests

from app.core import config

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    pass


class LLMQuotaExceededError(LLMProviderError):
    pass


class LLMIncompleteResponseError(LLMProviderError):
    pass


class LLMBlockedResponseError(LLMProviderError):
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


def _gemini_payload(prompt: str, *, max_output_tokens: int) -> dict[str, Any]:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": max_output_tokens,
        },
    }


def _gemini_generate_once(prompt: str, *, max_output_tokens: int) -> str:
    if not config.GEMINI_API_KEY:
        raise LLMProviderError("GEMINI_API_KEY가 설정되지 않았습니다.")

    model = config.GEMINI_MODEL or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = _gemini_payload(prompt, max_output_tokens=max_output_tokens)

    try:
        response = requests.post(url, params={"key": config.GEMINI_API_KEY}, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise LLMProviderError(f"Gemini API 호출 실패: {exc}") from exc
    if response.status_code >= 400:
        if _is_quota_error(response.status_code, response.text):
            raise LLMQuotaExceededError(f"Gemini API 쿼터 초과 ({response.status_code}): {response.text}")
        logger.warning("[LLM] Gemini API error status=%s body=%s", response.status_code, response.text[:1000])
        raise LLMProviderError(f"Gemini API 오류 ({response.status_code}): {response.text}")

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        logger.warning("[LLM] Gemini response has no candidates: %s", str(data)[:1000])
        raise LLMProviderError("Gemini API 응답에 후보 답변이 없습니다.")
    candidate = candidates[0]
    finish_reason = str(candidate.get("finishReason") or "").upper()
    if finish_reason and finish_reason not in {"STOP", "FINISH_REASON_UNSPECIFIED"}:
        if finish_reason == "MAX_TOKENS":
            raise LLMIncompleteResponseError("Gemini API 응답이 토큰 제한으로 중단되었습니다.")
        if finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
            logger.warning("[LLM] Gemini response blocked finish_reason=%s data=%s", finish_reason, str(data)[:1000])
            raise LLMBlockedResponseError(f"Gemini API 응답이 정책에 의해 제한되었습니다: {finish_reason}")
        logger.warning("[LLM] Gemini response stopped finish_reason=%s data=%s", finish_reason, str(data)[:1000])
        raise LLMProviderError(f"Gemini API 응답이 중단되었습니다: {finish_reason}")
    parts = ((candidate.get("content") or {}).get("parts") or [])
    answer = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
    if not answer:
        raise LLMProviderError("Gemini API 빈 응답")
    return answer


def _gemini_generate(prompt: str) -> str:
    try:
        return _gemini_generate_once(prompt, max_output_tokens=2048)
    except LLMIncompleteResponseError:
        return _gemini_generate_once(prompt, max_output_tokens=4096)


def generate_text(prompt: str) -> str:
    provider = (config.LLM_PROVIDER or "gemini").lower()
    if provider != "gemini":
        raise LLMProviderError(f"지원하지 않는 LLM_PROVIDER입니다: {provider}")
    return _gemini_generate(prompt)
