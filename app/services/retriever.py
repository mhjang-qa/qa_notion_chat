from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.core import config


@dataclass
class Chunk:
    chunk_id: str
    page_id: str
    title: str
    url: str
    path: list[str]
    text: str


@dataclass
class SearchHit:
    chunk: Chunk
    score: float


_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_./-]+")
_STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "및", "또는", "그리고", "관련", "대한", "대해",
    "무엇", "뭐", "어떻게", "왜", "언제", "어디", "알려줘", "설명", "정리", "기준",
    "있는", "없는", "합니다", "해주세요", "인가요", "인가", "은", "는", "이", "가", "을", "를",
}

_HIGH_VALUE_PATH_KEYWORDS = (
    "qa 업무 진행 현황",
    "업무 공간",
    "기타 자료",
    "업무 진행 현황",
    "테스트 진행 현황",
    "current testing status",
    "출시 테스트 보고서",
    "테스트 결과서",
    "장애 리포트",
    "장애보고서",
    "결함",
    "issue",
    "critical issues",
    "regression test",
    "운영 배포 테스트 결과",
)

_LOW_VALUE_PATH_KEYWORDS = (
    "it quality management",
    "raw data",
    "test design",
    "테스트 정보",
    "한패스 용어 사전",
    "기타",
    "sample page",
)

_INTENT_KEYWORDS = {
    "current": ("현재", "진행", "진행중", "진행 중", "current", "status", "현황"),
    "result": ("결과", "결과서", "보고서", "리포트", "검증", "summary"),
    "defect": ("결함", "장애", "이슈", "오류", "버그", "제보", "등록", "issue", "bug", "critical", "major", "minor"),
    "regression": ("회귀", "regression", "운영 배포", "운영배포"),
    "process": ("프로세스", "절차", "가이드", "업무 공간", "업무공간", "process", "guide"),
    "definition": ("뭐야", "무엇", "란", "정의", "뜻", "의미", "설명", "what is", "what's"),
}


def _norm_id(raw: str) -> str:
    return (raw or "").strip().replace("-", "").lower()


def _version_tuple(raw: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)", raw or "")
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _version_label(version: tuple[int, int, int] | None) -> str:
    if version is None:
        return ""
    return f"{version[0]}.{version[1]}.{version[2]}"


def _contains_version(text: str, version: tuple[int, int, int] | None) -> bool:
    if version is None:
        return False
    for match in re.finditer(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)", text or ""):
        major, minor, patch = match.groups()
        if (int(major), int(minor), int(patch or 0)) == version:
            return True
    return False


def _issue_target_version(text: str) -> tuple[int, int, int] | None:
    for line in (text or "").splitlines():
        if any(key in line for key in ("타겟 정보", "타겟정보", "목표버전", "목표 버전")):
            version = _version_tuple(line)
            if version is not None:
                return version
    return _version_tuple(text)


def _is_issue_chunk(chunk: Chunk) -> bool:
    return "QA_ISSUES" in " > ".join(chunk.path)


_PRIORITY_IDS = {
    "result": _norm_id(config.QA_PRIORITY_RESULT_PAGE_ID),
    "plan": _norm_id(config.QA_PRIORITY_PLAN_PAGE_ID),
    "defect": _norm_id(config.QA_PRIORITY_DEFECT_PAGE_ID),
    "workspace": _norm_id(config.QA_PRIORITY_WORKSPACE_DB_ID),
    "misc": _norm_id(config.QA_PRIORITY_MISC_DB_ID),
}
_MIN_ISSUE_VERSION = _version_tuple(config.QA_ISSUE_MIN_TARGET_VERSION)
_GENERIC_DEFECT_TOKENS = {"결함", "검색", "이슈", "버그", "장애", "오류", "issue", "bug"}


def _tokenize(text: str) -> list[str]:
    raw = [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]
    tokens: list[str] = []
    for token in raw:
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.append(token)
        tokens.extend(part.lower() for part in re.findall(r"[A-Za-z]{2,}|\d+(?:\.\d+){1,2}|[가-힣]{2,}", token))
    return [t for t in dict.fromkeys(tokens) if len(t) >= 2 and t not in _STOPWORDS]


def _chunk_text(text: str, max_chars: int = 1000, overlap: int = 140) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paras:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}".strip()
            continue
        if current:
            chunks.append(current)
        if len(para) <= max_chars:
            current = para
            continue
        start = 0
        while start < len(para):
            end = min(len(para), start + max_chars)
            chunks.append(para[start:end].strip())
            if end >= len(para):
                break
            start = max(0, end - overlap)
        current = ""
    if current:
        chunks.append(current)
    return chunks


def load_index() -> dict[str, Any]:
    if not config.QA_INDEX_PATH.exists():
        return {"pages": [], "synced_at": None}
    try:
        return json.loads(config.QA_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"pages": [], "synced_at": None}


def load_chunks() -> list[Chunk]:
    payload = load_index()
    chunks: list[Chunk] = []
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "제목 없음")
        path = [str(x) for x in page.get("path") or [title]]
        page_text = str(page.get("text") or "").strip()
        if not page_text:
            continue
        prefix = f"페이지: {title}\n경로: {' > '.join(path)}"
        for idx, text in enumerate(_chunk_text(page_text)):
            full_text = f"{prefix}\n\n{text}".strip()
            chunks.append(
                Chunk(
                    chunk_id=f"{page.get('page_id')}:{idx}",
                    page_id=str(page.get("page_id") or ""),
                    title=title,
                    url=str(page.get("url") or ""),
                    path=path,
                    text=full_text,
                )
            )
    return chunks


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _priority_score(question: str, chunk: Chunk, matched: int) -> float:
    q = (question or "").lower()
    title = chunk.title.lower()
    path = " > ".join(chunk.path).lower()
    text = chunk.text.lower()
    scope = f"{title}\n{path}"
    full = f"{scope}\n{text}"
    page_id = _norm_id(chunk.page_id)
    url = _norm_id(chunk.url)

    score = 0.0

    if _contains_any(scope, _HIGH_VALUE_PATH_KEYWORDS):
        score += 6.0
    if _contains_any(scope, _LOW_VALUE_PATH_KEYWORDS):
        score -= 2.5

    # 허브/목차 페이지는 질문어가 조금만 맞아도 과하게 뜨므로 낮춘다.
    child_refs = text.count("하위 페이지:") + text.count("하위 데이터베이스:")
    if child_refs >= 5 and matched <= 2:
        score -= 5.0

    current_intent = _contains_any(q, _INTENT_KEYWORDS["current"])
    result_intent = _contains_any(q, _INTENT_KEYWORDS["result"])
    defect_intent = _contains_any(q, _INTENT_KEYWORDS["defect"])
    regression_intent = _contains_any(q, _INTENT_KEYWORDS["regression"])
    process_intent = _contains_any(q, _INTENT_KEYWORDS["process"])
    definition_intent = _contains_any(q, _INTENT_KEYWORDS["definition"])
    plan_intent = _contains_any(q, ("계획", "계획서", "범위", "테스트 계획", "test plan"))

    if process_intent:
        if _PRIORITY_IDS["workspace"] and (_PRIORITY_IDS["workspace"] == page_id or _PRIORITY_IDS["workspace"] in url):
            score += 34.0
        if _contains_any(scope, ("업무 공간", "qa 프로세스", "프로세스", "가이드")):
            score += 22.0
        if _contains_any(scope, ("테스트 결과서", "오류 리포트", "장애 리포트", "qa_issues")):
            score -= 14.0

    if definition_intent:
        if _PRIORITY_IDS["misc"] and (_PRIORITY_IDS["misc"] == page_id or _PRIORITY_IDS["misc"] in url):
            score += 34.0
        if _contains_any(scope, ("기타 자료", "knowledge db", "qa란", "hqi", "hanpass quality index")):
            score += 22.0
        if _contains_any(scope, ("테스트 결과서", "오류 리포트", "장애 리포트", "qa_issues")):
            score -= 12.0

    if current_intent:
        if _contains_any(scope, ("qa 업무 진행 현황", "업무 진행 현황", "테스트 진행 현황", "current testing status")):
            score += 18.0
        if _contains_any(scope, ("진행 현황", "진행현황", "테스트 결과서", "출시 테스트 보고서")):
            score += 8.0
        if _contains_any(full, ("진행중", "진행 중", "in progress", "current", "status", "updated")):
            score += 4.0
        if _contains_any(scope, ("test design", "테스트 계획서", "한패스 용어 사전", "테스트 정보")):
            score -= 8.0

    if result_intent:
        if _PRIORITY_IDS["result"] and (_PRIORITY_IDS["result"] == page_id or _PRIORITY_IDS["result"] in url):
            score += 26.0
        if _contains_any(scope, ("테스트 결과서", "출시 테스트 보고서", "결과서", "보고서", "리포트")):
            score += 18.0
        if _contains_any(full, ("테스트 결과", "summary", "critical", "major", "minor")):
            score += 3.0

    if plan_intent:
        if _PRIORITY_IDS["plan"] and (_PRIORITY_IDS["plan"] == page_id or _PRIORITY_IDS["plan"] in url):
            score += 26.0
        if _contains_any(scope, ("테스트 계획서", "계획서", "test plan")):
            score += 18.0

    if defect_intent:
        if _PRIORITY_IDS["defect"] and (_PRIORITY_IDS["defect"] == page_id or _PRIORITY_IDS["defect"] in url):
            score += 30.0
        if _contains_any(scope, ("결함", "장애 리포트", "장애보고서", "오류 리포트", "issue", "bug")):
            score += 18.0
        if _contains_any(full, ("결함", "이슈", "critical", "major", "minor", "opened", "closed", "fatal exception", "crash", "anr")):
            score += 4.0

    if regression_intent and _contains_any(scope, ("regression test", "회귀", "운영 배포 테스트 결과", "운영배포")):
        score += 10.0

    # 제목/경로 직접 일치는 본문 반복보다 더 강하게 본다.
    for keyword_group in _INTENT_KEYWORDS.values():
        for keyword in keyword_group:
            if keyword in q and keyword.lower() in scope:
                score += 2.0

    return score


def search(question: str, top_k: int | None = None) -> list[SearchHit]:
    chunks = load_chunks()
    if not chunks:
        return []

    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    explicit_query_version = _version_tuple(question)
    is_defect_query = _contains_any((question or "").lower(), _INTENT_KEYWORDS["defect"])
    is_result_query = _contains_any((question or "").lower(), _INTENT_KEYWORDS["result"])
    is_plan_query = _contains_any((question or "").lower(), ("계획", "계획서", "test plan"))
    is_process_query = _contains_any((question or "").lower(), _INTENT_KEYWORDS["process"])
    is_definition_query = _contains_any((question or "").lower(), _INTENT_KEYWORDS["definition"])
    version_scoped_query = bool(
        explicit_query_version
        and _contains_any(
            (question or "").lower(),
            _INTENT_KEYWORDS["result"]
            + _INTENT_KEYWORDS["regression"]
            + ("테스트", "test", "계획", "계획서", "출시"),
        )
    )
    if is_defect_query and explicit_query_version and _MIN_ISSUE_VERSION and explicit_query_version < _MIN_ISSUE_VERSION:
        return []
    specific_defect_tokens = [
        token for token in query_tokens if token not in _GENERIC_DEFECT_TOKENS and _version_tuple(token) is None
    ]

    doc_tokens = [_tokenize(f"{chunk.title} {' '.join(chunk.path)} {chunk.text}") for chunk in chunks]
    doc_freq: dict[str, int] = {}
    for tokens in doc_tokens:
        for token in set(tokens):
            doc_freq[token] = doc_freq.get(token, 0) + 1

    total_docs = len(chunks)
    hits: list[SearchHit] = []
    query_set = set(query_tokens)
    phrase = (question or "").strip().lower()

    for chunk, tokens in zip(chunks, doc_tokens):
        if not tokens:
            continue
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        score = 0.0
        for token in query_set:
            count = tf.get(token, 0)
            if not count:
                continue
            idf = math.log((total_docs + 1) / (doc_freq.get(token, 0) + 0.5)) + 1
            score += (1 + math.log(count)) * idf

        title_lower = chunk.title.lower()
        text_lower = chunk.text.lower()
        if phrase and len(phrase) >= 3:
            if phrase in text_lower:
                score += 8.0
            if phrase in title_lower:
                score += 12.0

        matched = sum(1 for token in query_set if token in tf)
        score += matched * 0.4
        if matched == 0:
            continue
        full_text_for_version = f"{chunk.title}\n{' > '.join(chunk.path)}\n{chunk.text}"
        child_refs = chunk.text.count("하위 페이지:") + chunk.text.count("하위 데이터베이스:") + chunk.text.count("하위  ")
        if version_scoped_query and not _contains_version(full_text_for_version, explicit_query_version):
            continue
        if version_scoped_query and child_refs >= 3:
            continue
        if (is_result_query or is_plan_query) and not is_defect_query and _is_issue_chunk(chunk):
            continue
        scope_for_intent = f"{chunk.title}\n{' > '.join(chunk.path)}".lower()
        if is_process_query and not _contains_any(scope_for_intent, ("업무 공간", "qa 프로세스")):
            continue
        if is_process_query and "프로세스" in (question or "").lower() and "프로세스" not in scope_for_intent:
            continue
        if is_definition_query and _contains_any(scope_for_intent, ("오류 리포트", "테스트 결과서", "qa_issues")):
            continue
        if is_result_query and not is_plan_query and _contains_any(scope_for_intent, ("테스트 계획서", "test plan")):
            continue
        if is_plan_query and not is_result_query and _contains_any(scope_for_intent, ("테스트 결과서", "결과서")):
            continue
        if is_defect_query and not _is_issue_chunk(chunk):
            continue
        if is_defect_query and _is_issue_chunk(chunk):
            target_version = _issue_target_version(chunk.text)
            if _MIN_ISSUE_VERSION and (target_version is None or target_version < _MIN_ISSUE_VERSION):
                continue
            if explicit_query_version:
                if target_version == explicit_query_version:
                    score += 10.0
                else:
                    continue
            if specific_defect_tokens and not any(token in tf for token in specific_defect_tokens):
                continue
        score += _priority_score(question, chunk, matched)
        hits.append(SearchHit(chunk=chunk, score=score))

    hits.sort(key=lambda hit: hit.score, reverse=True)
    filtered = [hit for hit in hits if hit.score >= 1.2]
    if is_definition_query and len(filtered) >= 2 and filtered[0].score - filtered[1].score >= 15.0:
        top_page_id = filtered[0].chunk.page_id
        return [hit for hit in filtered if hit.chunk.page_id == top_page_id][: top_k or config.QA_TOP_K]
    return filtered[: top_k or config.QA_TOP_K]


def source_payload(hits: list[SearchHit]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        key = hit.chunk.page_id
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": hit.chunk.title,
                "url": hit.chunk.url,
                "path": " > ".join(hit.chunk.path),
                "score": round(hit.score, 3),
                "preview": hit.chunk.text[:300],
            }
        )
    return out
