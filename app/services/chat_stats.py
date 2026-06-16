from __future__ import annotations

import logging
import re
import threading
from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core import config
from app.services.notion_tree import NotionSyncError, _request, normalize_notion_id

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
DAILY_DB_TITLE = "BUNI Chat Daily Stats"
LOG_DB_TITLE = "BUNI Chat Question Logs"
DAILY_BODY_MARKER = "[BUNI_STATS_BODY]"

_database_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


def _rich_text(text: str, limit: int = 1900) -> list[dict[str, Any]]:
    clean = (text or "").strip()[:limit]
    return [{"type": "text", "text": {"content": clean}}] if clean else []


def _title(text: str, limit: int = 1900) -> list[dict[str, Any]]:
    clean = (text or "").strip()[:limit] or "Untitled"
    return [{"type": "text", "text": {"content": clean}}]


def _select(name: str) -> dict[str, Any]:
    return {"name": (name or "기타")[:100]}


def _now() -> datetime:
    return datetime.now(KST)


def _date_key(dt: datetime) -> str:
    return dt.astimezone(KST).date().isoformat()


def _plain_text(rich_text: Any) -> str:
    if not isinstance(rich_text, list):
        return ""
    return "".join(str(item.get("plain_text") or "") for item in rich_text if isinstance(item, dict)).strip()


def _truncate(text: str, limit: int) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[: max(limit - 3, 0)]}..."


def _database_title(database: dict[str, Any]) -> str:
    return _plain_text(database.get("title"))


def _iter_child_databases(page_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = None
    while True:
        query = "?page_size=100"
        if cursor:
            query += f"&start_cursor={cursor}"
        data = _request("GET", f"/blocks/{normalize_notion_id(page_id)}/children{query}")
        for block in data.get("results") or []:
            if isinstance(block, dict) and block.get("type") == "child_database":
                out.append(block)
        if not data.get("has_more"):
            return out
        cursor = data.get("next_cursor")
        if not cursor:
            return out


def _find_child_database(page_id: str, title: str) -> str:
    for block in _iter_child_databases(page_id):
        body = block.get("child_database") or {}
        if isinstance(body, dict) and (body.get("title") or "").strip() == title:
            return normalize_notion_id(block.get("id") or "")
    return ""


def _create_daily_database(page_id: str) -> str:
    payload = {
        "parent": {"type": "page_id", "page_id": normalize_notion_id(page_id)},
        "title": _title(DAILY_DB_TITLE),
        "properties": {
            "일자": {"title": {}},
            "날짜": {"date": {}},
            "총 인입": {"number": {"format": "number"}},
            "고유 질문": {"number": {"format": "number"}},
            "LLM 요청": {"number": {"format": "number"}},
            "Notion 답변": {"number": {"format": "number"}},
            "고정 응답": {"number": {"format": "number"}},
            "결함 제보": {"number": {"format": "number"}},
            "범위 밖 질문": {"number": {"format": "number"}},
            "고유 IP": {"number": {"format": "number"}},
            "IP 목록": {"rich_text": {}},
            "주요 주제": {"rich_text": {}},
            "최근 질문": {"rich_text": {}},
            "마지막 업데이트": {"date": {}},
        },
    }
    return normalize_notion_id(_request("POST", "/databases", payload=payload).get("id") or "")


def _create_log_database(page_id: str) -> str:
    payload = {
        "parent": {"type": "page_id", "page_id": normalize_notion_id(page_id)},
        "title": _title(LOG_DB_TITLE),
        "properties": {
            "질문": {"title": {}},
            "일자": {"date": {}},
            "시각": {"date": {}},
            "모드": {"select": {}},
            "출처": {"select": {}},
            "주제": {"select": {}},
            "LLM 여부": {"checkbox": {}},
            "응답 요약": {"rich_text": {}},
            "질문 키": {"rich_text": {}},
            "IP 주소": {"rich_text": {}},
            "User Agent": {"rich_text": {}},
            "Referer": {"rich_text": {}},
        },
    }
    return normalize_notion_id(_request("POST", "/databases", payload=payload).get("id") or "")


def _ensure_database_properties(database_id: str, required: dict[str, Any]) -> None:
    database = _request("GET", f"/databases/{normalize_notion_id(database_id)}")
    existing = database.get("properties") or {}
    if not isinstance(existing, dict):
        existing = {}
    missing = {name: schema for name, schema in required.items() if name not in existing}
    if missing:
        _request("PATCH", f"/databases/{normalize_notion_id(database_id)}", payload={"properties": missing})


def _ensure_databases() -> tuple[str, str]:
    if not config.CHAT_STATS_PAGE_ID:
        raise NotionSyncError("CHAT_STATS_PAGE_ID가 설정되지 않았습니다.")
    with _cache_lock:
        daily_id = _database_cache.get("daily") or _find_child_database(config.CHAT_STATS_PAGE_ID, DAILY_DB_TITLE)
        if not daily_id:
            daily_id = _create_daily_database(config.CHAT_STATS_PAGE_ID)
        log_id = _database_cache.get("log") or _find_child_database(config.CHAT_STATS_PAGE_ID, LOG_DB_TITLE)
        if not log_id:
            log_id = _create_log_database(config.CHAT_STATS_PAGE_ID)
        if _database_cache.get("schema_checked") != f"{daily_id}:{log_id}":
            _ensure_database_properties(
                daily_id,
                {
                    "고유 IP": {"number": {"format": "number"}},
                    "IP 목록": {"rich_text": {}},
                },
            )
            _ensure_database_properties(
                log_id,
                {
                    "IP 주소": {"rich_text": {}},
                    "User Agent": {"rich_text": {}},
                    "Referer": {"rich_text": {}},
                },
            )
            _database_cache["schema_checked"] = f"{daily_id}:{log_id}"
        _database_cache["daily"] = daily_id
        _database_cache["log"] = log_id
        return daily_id, log_id


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().lower())


def _classify_topic(question: str, answer: dict[str, Any]) -> str:
    text = f"{question or ''} {answer.get('mode') or ''}".lower()
    compact = re.sub(r"\s+", "", text)
    if "bug_report" in text or any(token in compact for token in ("결함제보", "버그제보", "이슈제보")):
        return "결함 제보"
    if any(token in compact for token in ("결함현황", "결함개수", "결함검색", "이슈현황", "버그현황", "결함카운트")):
        return "결함 현황"
    if any(token in compact for token in ("진행중", "현재진행", "업무현황", "테스트항목")):
        return "업무/테스트 현황"
    if any(token in compact for token in ("테스트결과", "결과서", "리포트", "보고서")):
        return "테스트 결과"
    if any(token in compact for token in ("테스트계획", "계획서", "테스트범위")):
        return "테스트 계획"
    if any(token in compact for token in ("사용법", "가이드", "도움말")):
        return "사용법/가이드"
    if answer.get("origin") == "LLM" or str(answer.get("mode") or "").startswith("llm_"):
        return "LLM 보조답변"
    if answer.get("mode") in {"out_of_scope", "casual_guardrail", "buni_meta", "greeting"}:
        return "일반/고정 응답"
    return "기타"


def _create_log_page(
    log_db_id: str,
    *,
    question: str,
    answer: dict[str, Any],
    now: datetime,
    request_meta: dict[str, str] | None = None,
) -> None:
    date = _date_key(now)
    mode = str(answer.get("mode") or "unknown")
    origin = str(answer.get("origin") or "UNKNOWN")
    topic = _classify_topic(question, answer)
    answer_preview = str(answer.get("answer") or "").strip().replace("\n", " ")[:500]
    request_meta = request_meta or {}
    ip_address = str(request_meta.get("ip") or "").strip()
    user_agent = str(request_meta.get("user_agent") or "").strip()
    referer = str(request_meta.get("referer") or "").strip()
    payload = {
        "parent": {"database_id": normalize_notion_id(log_db_id)},
        "properties": {
            "질문": {"title": _title(question, limit=250)},
            "일자": {"date": {"start": date}},
            "시각": {"date": {"start": now.isoformat()}},
            "모드": {"select": _select(mode)},
            "출처": {"select": _select(origin)},
            "주제": {"select": _select(topic)},
            "LLM 여부": {"checkbox": origin == "LLM" or mode.startswith("llm_")},
            "응답 요약": {"rich_text": _rich_text(answer_preview, limit=500)},
            "질문 키": {"rich_text": _rich_text(_normalize_question(question), limit=500)},
            "IP 주소": {"rich_text": _rich_text(ip_address, limit=200)},
            "User Agent": {"rich_text": _rich_text(user_agent, limit=500)},
            "Referer": {"rich_text": _rich_text(referer, limit=500)},
        },
    }
    _request("POST", "/pages", payload=payload)


def _block_rich_text(text: str, limit: int = 1900) -> list[dict[str, Any]]:
    return _rich_text(_truncate(text, limit), limit=limit)


def _paragraph(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _block_rich_text(text)}}


def _heading(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _block_rich_text(text, limit=200)}}


def _bulleted(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _block_rich_text(text)}}


def _block_plain_text(block: dict[str, Any]) -> str:
    btype = block.get("type")
    body = block.get(btype) if btype else None
    if not isinstance(body, dict):
        return ""
    return _plain_text(body.get("rich_text"))


def _iter_block_children(block_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = None
    while True:
        query = "?page_size=100"
        if cursor:
            query += f"&start_cursor={cursor}"
        data = _request("GET", f"/blocks/{normalize_notion_id(block_id)}/children{query}")
        out.extend([block for block in data.get("results") or [] if isinstance(block, dict)])
        if not data.get("has_more"):
            return out
        cursor = data.get("next_cursor")
        if not cursor:
            return out


def _delete_existing_daily_body(page_id: str) -> None:
    deleting = False
    for block in _iter_block_children(page_id):
        if DAILY_BODY_MARKER in _block_plain_text(block):
            deleting = True
        if deleting:
            _request("DELETE", f"/blocks/{normalize_notion_id(block.get('id') or '')}")


def _property_date(page: dict[str, Any], name: str) -> str:
    prop = (page.get("properties") or {}).get(name) or {}
    value = prop.get("date") or {}
    if not isinstance(value, dict):
        return ""
    return str(value.get("start") or "")


def _append_daily_body(page_id: str, *, date: str, logs: list[dict[str, Any]], now: datetime) -> None:
    _delete_existing_daily_body(page_id)
    ordered_logs = sorted(logs, key=lambda page: _property_date(page, "시각"), reverse=True)
    children: list[dict[str, Any]] = [
        _paragraph(f"{DAILY_BODY_MARKER} {now.strftime('%Y-%m-%d %H:%M:%S')} KST 기준 자동 갱신"),
        _heading("질문/답변 품질 확인 목록"),
    ]
    if not ordered_logs:
        children.append(_paragraph("아직 기록된 질문이 없습니다."))
    for index, page in enumerate(ordered_logs[:50], start=1):
        question = _property_title(page, "질문") or "질문 없음"
        answer = _property_rich_text(page, "응답 요약") or "응답 없음"
        mode = _property_select_name(page, "모드") or "-"
        origin = _property_select_name(page, "출처") or "-"
        topic = _property_select_name(page, "주제") or "-"
        asked_at = _property_date(page, "시각")
        ip_address = _property_ip(page) or "-"
        children.extend(
            [
                _heading(f"{index}. {question}"),
                _bulleted(f"질문: {question}"),
                _bulleted(f"답변: {answer}"),
                _bulleted(f"분류: {topic} / 모드: {mode} / 출처: {origin}"),
                _bulleted(f"시각: {asked_at} / IP: {ip_address}"),
            ]
        )
    for start in range(0, len(children), 90):
        _request(
            "PATCH",
            f"/blocks/{normalize_notion_id(page_id)}/children",
            payload={"children": children[start : start + 90]},
        )


def _query_logs_for_date(log_db_id: str, date: str) -> list[dict[str, Any]]:
    payload = {
        "page_size": 100,
        "filter": {"property": "일자", "date": {"equals": date}},
        "sorts": [{"property": "시각", "direction": "descending"}],
    }
    out: list[dict[str, Any]] = []
    cursor = None
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        data = _request("POST", f"/databases/{normalize_notion_id(log_db_id)}/query", payload=payload)
        out.extend([page for page in data.get("results") or [] if isinstance(page, dict)])
        if not data.get("has_more"):
            return out
        cursor = data.get("next_cursor")
        if not cursor:
            return out


def _property_select_name(page: dict[str, Any], name: str) -> str:
    prop = (page.get("properties") or {}).get(name) or {}
    selected = prop.get("select") or {}
    return str(selected.get("name") or "") if isinstance(selected, dict) else ""


def _property_rich_text(page: dict[str, Any], name: str) -> str:
    prop = (page.get("properties") or {}).get(name) or {}
    return _plain_text(prop.get("rich_text"))


def _property_title(page: dict[str, Any], name: str) -> str:
    prop = (page.get("properties") or {}).get(name) or {}
    return _plain_text(prop.get("title"))


def _property_ip(page: dict[str, Any]) -> str:
    return _property_rich_text(page, "IP 주소")


def _find_daily_page(daily_db_id: str, date: str) -> str:
    payload = {"page_size": 1, "filter": {"property": "날짜", "date": {"equals": date}}}
    data = _request("POST", f"/databases/{normalize_notion_id(daily_db_id)}/query", payload=payload)
    results = data.get("results") or []
    if results and isinstance(results[0], dict):
        return normalize_notion_id(results[0].get("id") or "")
    return ""


def _upsert_daily_page(daily_db_id: str, *, date: str, logs: list[dict[str, Any]], now: datetime) -> None:
    total = len(logs)
    question_keys = [_property_rich_text(page, "질문 키") for page in logs]
    unique_questions = len({key for key in question_keys if key})
    mode_counter = Counter(_property_select_name(page, "모드") for page in logs)
    origin_counter = Counter(_property_select_name(page, "출처") for page in logs)
    topic_counter = Counter(_property_select_name(page, "주제") for page in logs)
    ip_values = sorted({ip for ip in (_property_ip(page) for page in logs) if ip})
    llm_count = sum(
        1
        for page in logs
        if _property_select_name(page, "출처") == "LLM" or _property_select_name(page, "모드").startswith("llm_")
    )
    recent_questions = [_property_title(page, "질문") for page in logs[:5]]
    topic_summary = ", ".join(f"{topic} {count}건" for topic, count in topic_counter.most_common(5) if topic)

    properties = {
        "일자": {"title": _title(date)},
        "날짜": {"date": {"start": date}},
        "총 인입": {"number": total},
        "고유 질문": {"number": unique_questions},
        "LLM 요청": {"number": llm_count},
        "Notion 답변": {"number": origin_counter["NOTION"]},
        "고정 응답": {"number": origin_counter["SYSTEM"]},
        "결함 제보": {"number": topic_counter["결함 제보"]},
        "범위 밖 질문": {"number": mode_counter["out_of_scope"]},
        "고유 IP": {"number": len(ip_values)},
        "IP 목록": {"rich_text": _rich_text(", ".join(ip_values), limit=1000)},
        "주요 주제": {"rich_text": _rich_text(topic_summary or "질문 없음")},
        "최근 질문": {"rich_text": _rich_text(" / ".join(q for q in recent_questions if q)[:1000])},
        "마지막 업데이트": {"date": {"start": now.isoformat()}},
    }

    page_id = _find_daily_page(daily_db_id, date)
    if page_id:
        _request("PATCH", f"/pages/{page_id}", payload={"properties": properties})
        _append_daily_body(page_id, date=date, logs=logs, now=now)
        return
    page = _request("POST", "/pages", payload={"parent": {"database_id": normalize_notion_id(daily_db_id)}, "properties": properties})
    new_page_id = normalize_notion_id(page.get("id") or "")
    if new_page_id:
        _append_daily_body(new_page_id, date=date, logs=logs, now=now)


def record_chat_interaction(
    question: str,
    answer: dict[str, Any],
    *,
    request_meta: dict[str, str] | None = None,
) -> None:
    if not config.CHAT_STATS_ENABLED or not config.CHAT_STATS_PAGE_ID:
        return
    clean_question = (question or "").strip()
    if not clean_question:
        return
    try:
        now = _now()
        date = _date_key(now)
        daily_db_id, log_db_id = _ensure_databases()
        _create_log_page(log_db_id, question=clean_question, answer=answer, now=now, request_meta=request_meta)
        logs = _query_logs_for_date(log_db_id, date)
        _upsert_daily_page(daily_db_id, date=date, logs=logs, now=now)
    except Exception as exc:
        logger.warning("[CHAT_STATS] Notion stats update failed: %s", exc)


def record_chat_interaction_async(
    question: str,
    answer: dict[str, Any],
    *,
    request_meta: dict[str, str] | None = None,
) -> None:
    if not config.CHAT_STATS_ENABLED:
        return
    thread = threading.Thread(
        target=record_chat_interaction,
        args=(question, answer),
        kwargs={"request_meta": request_meta},
        daemon=True,
    )
    thread.start()
