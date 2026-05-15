from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app.core import config


class NotionSyncError(RuntimeError):
    pass


@dataclass
class NotionPageDoc:
    page_id: str
    title: str
    url: str
    parent_id: str
    path: list[str]
    text: str
    last_edited_time: str


def normalize_notion_id(raw: str) -> str:
    return (raw or "").strip().replace("-", "")


def _headers() -> dict[str, str]:
    if not config.NOTION_TOKEN:
        raise NotionSyncError("NOTION_TOKEN이 설정되지 않았습니다.")
    return {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Notion-Version": config.NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.notion.com/v1{path}"
    last_error = ""
    for attempt in range(1, 4):
        try:
            response = requests.request(method, url, headers=_headers(), json=payload, timeout=40)
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(0.6 * attempt)
            continue

        if response.status_code == 429 or 500 <= response.status_code <= 599:
            last_error = response.text
            time.sleep(0.8 * attempt)
            continue
        if response.status_code >= 400:
            raise NotionSyncError(f"Notion API 오류 ({response.status_code}): {response.text}")
        return response.json() if response.content else {}
    raise NotionSyncError(f"Notion API 호출 실패: {last_error}")


def _plain_text(rich_text: Any) -> str:
    if not isinstance(rich_text, list):
        return ""
    return "".join(str(x.get("plain_text") or "") for x in rich_text if isinstance(x, dict)).strip()


def _page_title(page: dict[str, Any]) -> str:
    props = page.get("properties") or {}
    for prop in props.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title = _plain_text(prop.get("title"))
            if title:
                return title
    return (page.get("id") or "제목 없음").replace("-", "")


def _database_title(database: dict[str, Any]) -> str:
    title = _plain_text(database.get("title"))
    return title or (database.get("id") or "데이터베이스").replace("-", "")


def retrieve_page(page_id: str) -> dict[str, Any]:
    return _request("GET", f"/pages/{normalize_notion_id(page_id)}")


def retrieve_database(database_id: str) -> dict[str, Any]:
    return _request("GET", f"/databases/{normalize_notion_id(database_id)}")


def _api_id(raw: str) -> str:
    return (raw or "").strip()


def iter_block_children(block_id: str) -> list[dict[str, Any]]:
    block_id = _api_id(block_id)
    cursor = None
    out: list[dict[str, Any]] = []
    while True:
        query = f"?page_size=100"
        if cursor:
            query += f"&start_cursor={cursor}"
        data = _request("GET", f"/blocks/{block_id}/children{query}")
        results = data.get("results") or []
        out.extend([x for x in results if isinstance(x, dict)])
        if not data.get("has_more"):
            return out
        cursor = data.get("next_cursor")
        if not cursor:
            return out


def _block_text(block: dict[str, Any]) -> str:
    btype = block.get("type")
    body = block.get(btype) if btype else None
    if not isinstance(body, dict):
        return ""

    if btype == "child_page":
        return f"하위 페이지: {(body.get('title') or '').strip()}".strip()
    if btype == "child_database":
        return f"하위 데이터베이스: {(body.get('title') or '').strip()}".strip()
    if btype == "to_do":
        checked = "[x]" if body.get("checked") else "[ ]"
        return f"{checked} {_plain_text(body.get('rich_text'))}".strip()
    if btype in {"bulleted_list_item", "numbered_list_item"}:
        text = _plain_text(body.get("rich_text"))
        return f"- {text}".strip()
    if btype == "toggle":
        text = _plain_text(body.get("rich_text"))
        return f"{text}".strip()
    if btype == "table_row":
        cells = body.get("cells") or []
        values = [_plain_text(cell) for cell in cells if isinstance(cell, list)]
        return " | ".join([v for v in values if v]).strip()
    if "rich_text" in body:
        return _plain_text(body.get("rich_text"))
    if btype in {"image", "file", "pdf", "video", "bookmark", "embed"}:
        caption = _plain_text(body.get("caption"))
        url = ""
        typed = body.get(btype)
        if isinstance(typed, dict):
            url = typed.get("url") or ""
        return " ".join([caption, url]).strip()
    return ""


def _property_text(prop: dict[str, Any]) -> str:
    ptype = prop.get("type")
    if ptype in {"title", "rich_text"}:
        return _plain_text(prop.get(ptype))
    if ptype == "select":
        selected = prop.get("select") or {}
        return str(selected.get("name") or "").strip() if isinstance(selected, dict) else ""
    if ptype == "status":
        status = prop.get("status") or {}
        return str(status.get("name") or "").strip() if isinstance(status, dict) else ""
    if ptype == "multi_select":
        values = prop.get("multi_select") or []
        return ", ".join(str(x.get("name") or "").strip() for x in values if isinstance(x, dict)).strip()
    if ptype == "date":
        value = prop.get("date") or {}
        if not isinstance(value, dict):
            return ""
        return " ~ ".join([x for x in [value.get("start"), value.get("end")] if x]).strip()
    if ptype in {"number", "checkbox", "url", "email", "phone_number"}:
        value = prop.get(ptype)
        return "" if value is None else str(value).strip()
    if ptype == "people":
        people = prop.get("people") or []
        return ", ".join(str(x.get("name") or "").strip() for x in people if isinstance(x, dict)).strip()
    return ""


def _page_properties_text(page: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    props = page.get("properties") or {}
    if not isinstance(props, dict):
        return lines
    for name, prop in props.items():
        if not isinstance(prop, dict):
            continue
        value = _property_text(prop)
        if value:
            lines.append(f"{name}: {value}")
    return lines


def _version_tuple(raw: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw or "")
    if not match:
        return None
    return tuple(int(x) for x in match.groups())


def _issue_target_text(page: dict[str, Any]) -> str:
    props = page.get("properties") or {}
    if not isinstance(props, dict):
        return ""

    preferred_names = ("타겟 정보", "타겟정보", "Target Info", "Target", "목표버전", "목표 버전")
    values: list[str] = []

    for name in preferred_names:
        prop = props.get(name)
        if isinstance(prop, dict):
            value = _property_text(prop)
            if value:
                values.append(value)

    if values:
        return " ".join(values)

    for name, prop in props.items():
        if not isinstance(prop, dict):
            continue
        lowered = str(name).lower().replace(" ", "")
        if any(key in lowered for key in ("타겟", "target", "목표버전", "목표")):
            value = _property_text(prop)
            if value:
                values.append(value)
    return " ".join(values)


def _issue_target_version_allowed(page: dict[str, Any]) -> bool:
    min_version = _version_tuple(config.QA_ISSUE_MIN_TARGET_VERSION)
    if min_version is None:
        return True
    target_text = _issue_target_text(page)
    version = _version_tuple(target_text)
    if version is None:
        return False
    return version >= min_version


def _database_page_doc(
    page: dict[str, Any],
    *,
    database_id: str,
    database_title: str,
    database_url: str,
    label: str,
    path_prefix: list[str] | None = None,
) -> NotionPageDoc | None:
    page_id = normalize_notion_id(page.get("id") or "")
    if not page_id:
        return None
    if label == "결함 검색" and not _issue_target_version_allowed(page):
        return None
    title = _page_title(page)
    prop_lines = _page_properties_text(page)
    text = _clean_text("\n".join([label, f"데이터베이스: {database_title}", *prop_lines]))
    if not text:
        return None
    return NotionPageDoc(
        page_id=page_id,
        title=title,
        url=(page.get("url") or database_url or "").strip(),
        parent_id=normalize_notion_id(database_id),
        path=[*(path_prefix or ["우선 검색 영역", database_title]), title],
        text=text,
        last_edited_time=(page.get("last_edited_time") or "").strip(),
    )


def _query_database_pages(database_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    cursor = None
    out: list[dict[str, Any]] = []
    while True:
        remaining = None if limit is None else max(limit - len(out), 0)
        if remaining == 0:
            return out
        payload: dict[str, Any] = {"page_size": min(100, remaining or 100)}
        if cursor:
            payload["start_cursor"] = cursor
        data = _request("POST", f"/databases/{_api_id(database_id)}/query", payload=payload)
        results = data.get("results") or []
        out.extend([x for x in results if isinstance(x, dict) and x.get("object") == "page"])
        if limit is not None and len(out) >= limit:
            return out[:limit]
        if not data.get("has_more"):
            return out
        cursor = data.get("next_cursor")
        if not cursor:
            return out


def _collect_block_text(block_id: str, child_pages: list[str], child_databases: list[str]) -> list[str]:
    lines: list[str] = []
    for block in iter_block_children(block_id):
        btype = block.get("type")
        body = block.get(btype) if btype else None
        text = _block_text(block)
        if text:
            lines.append(text)

        if btype == "child_page" and isinstance(body, dict):
            child_pages.append(block.get("id") or "")
            continue
        if btype == "child_database" and isinstance(body, dict):
            child_databases.append(block.get("id") or "")
            continue

        if block.get("has_children"):
            child_lines = _collect_block_text(block.get("id") or "", child_pages, child_databases)
            lines.extend(child_lines)
    return lines


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def crawl_page_tree(root_page_id: str) -> list[NotionPageDoc]:
    root_page_id = normalize_notion_id(root_page_id)
    visited: set[str] = set()
    visited_databases: set[str] = set()
    docs: list[NotionPageDoc] = []

    def visit(
        page_id: str,
        parent_id: str = "",
        parent_path: list[str] | None = None,
        depth: int = 0,
    ) -> None:
        norm_id = normalize_notion_id(page_id)
        if not norm_id or norm_id in visited:
            return
        if len(visited) >= config.NOTION_MAX_PAGES:
            return
        if depth > config.NOTION_MAX_DEPTH:
            return
        visited.add(norm_id)

        page = retrieve_page(norm_id)
        title = _page_title(page)
        path = [*(parent_path or []), title]
        child_pages: list[str] = []
        child_databases: list[str] = []
        lines = [*_page_properties_text(page), *_collect_block_text(page_id, child_pages, child_databases)]
        text = _clean_text("\n".join(lines))

        docs.append(
            NotionPageDoc(
                page_id=norm_id,
                title=title,
                url=(page.get("url") or "").strip(),
                parent_id=normalize_notion_id(parent_id),
                path=path,
                text=text,
                last_edited_time=(page.get("last_edited_time") or "").strip(),
            )
        )

        for child_id in child_pages:
            visit(child_id, norm_id, path, depth + 1)
        for database_id in child_databases:
            db_norm = normalize_notion_id(database_id)
            if not db_norm or db_norm in visited_databases:
                continue
            if len(visited_databases) >= config.NOTION_MAX_DATABASES:
                continue
            visited_databases.add(db_norm)
            try:
                db_pages = _query_database_pages(database_id, limit=max(config.NOTION_MAX_PAGES - len(visited), 0))
            except NotionSyncError:
                continue
            for db_page in db_pages:
                if len(visited) >= config.NOTION_MAX_PAGES:
                    return
                visit(db_page.get("id") or "", norm_id, path, depth + 1)

    def visit_priority_target(raw_id: str, label: str) -> None:
        target_id = normalize_notion_id(raw_id)
        if not target_id:
            return

        before = len(docs)
        try:
            visit(target_id, root_page_id, ["우선 검색 영역"], 1)
            if len(docs) > before:
                return
        except NotionSyncError:
            pass

        db_norm = normalize_notion_id(target_id)
        if db_norm in visited_databases or len(visited_databases) >= config.NOTION_MAX_DATABASES:
            return

        try:
            database = retrieve_database(target_id)
            db_title = _database_title(database) or label
            db_pages = _query_database_pages(target_id, limit=max(config.NOTION_MAX_PAGES - len(visited), 0))
        except NotionSyncError:
            return

        visited_databases.add(db_norm)
        docs.append(
            NotionPageDoc(
                page_id=db_norm,
                title=db_title,
                url=(database.get("url") or "").strip(),
                parent_id=normalize_notion_id(root_page_id),
                path=["우선 검색 영역", db_title],
                text=f"{label}\n하위 데이터베이스: {db_title}",
                last_edited_time=(database.get("last_edited_time") or "").strip(),
            )
        )
        for db_page in db_pages:
            if len(visited) >= config.NOTION_MAX_PAGES:
                return
            page_id = normalize_notion_id(db_page.get("id") or "")
            if page_id in visited:
                continue
            doc = _database_page_doc(
                db_page,
                database_id=db_norm,
                database_title=db_title,
                database_url=(database.get("url") or "").strip(),
                label=label,
            )
            if doc is None:
                continue
            visited.add(page_id)
            docs.append(doc)

    visit(root_page_id)
    visit_priority_target(config.QA_PRIORITY_DEFECT_PAGE_ID, "결함 검색")
    visit_priority_target(config.QA_PRIORITY_RESULT_PAGE_ID, "테스트 결과서")
    visit_priority_target(config.QA_PRIORITY_PLAN_PAGE_ID, "테스트 계획서")
    visit_priority_target(config.QA_PRIORITY_PROGRESS_DB_ID, "업무 진행 현황")
    return docs


def crawl_priority_targets(limit: int = 180) -> list[NotionPageDoc]:
    docs: list[NotionPageDoc] = []
    seen: set[str] = set()
    seen_databases: set[str] = set()

    def add_page_target(
        raw_id: str,
        label: str,
        *,
        parent_id: str | None = None,
        parent_path: list[str] | None = None,
        depth: int = 0,
        max_depth: int = 3,
        max_docs: int = 140,
        max_total: int | None = None,
    ) -> None:
        cap = max_total if max_total is not None else len(docs) + max_docs
        if len(docs) >= cap:
            return
        page_id = normalize_notion_id(raw_id)
        if not page_id or page_id in seen:
            return
        try:
            page = retrieve_page(page_id)
            title = _page_title(page)
            child_pages: list[str] = []
            child_databases: list[str] = []
            lines = [label, *_page_properties_text(page), *_collect_block_text(page_id, child_pages, child_databases)]
        except NotionSyncError:
            return
        seen.add(page_id)
        path = [*(parent_path or ["우선 검색 영역"]), title]
        docs.append(
            NotionPageDoc(
                page_id=page_id,
                title=title,
                url=(page.get("url") or "").strip(),
                parent_id=normalize_notion_id(parent_id or config.NOTION_ROOT_PAGE_ID),
                path=path,
                text=_clean_text("\n".join(lines)),
                last_edited_time=(page.get("last_edited_time") or "").strip(),
            )
        )

        if depth >= max_depth:
            return
        for database_id in child_databases:
            remaining = max(cap - len(docs), 0)
            if remaining <= 0:
                return
            add_database_target(database_id, label, remaining, parent_path=path)
        for child_id in child_pages:
            add_page_target(
                child_id,
                label,
                parent_id=page_id,
                parent_path=path,
                depth=depth + 1,
                max_depth=max_depth,
                max_docs=max_docs,
                max_total=cap,
            )

    def add_database_target(
        raw_id: str,
        label: str,
        max_pages: int,
        *,
        parent_path: list[str] | None = None,
        include_page_body: bool = False,
    ) -> bool:
        db_id = normalize_notion_id(raw_id)
        if not db_id or db_id in seen_databases:
            return False
        try:
            database = retrieve_database(db_id)
            db_title = _database_title(database) or label
            db_pages = _query_database_pages(db_id, limit=max_pages)
        except NotionSyncError:
            return False

        seen_databases.add(db_id)
        path_prefix = [*(parent_path or ["우선 검색 영역"]), db_title]
        for db_page in db_pages:
            if include_page_body:
                page_id = normalize_notion_id(db_page.get("id") or "")
                title = _page_title(db_page)
                child_pages: list[str] = []
                child_databases: list[str] = []
                lines = [
                    label,
                    f"데이터베이스: {db_title}",
                    *_page_properties_text(db_page),
                    *_collect_block_text(page_id, child_pages, child_databases),
                ]
                doc = NotionPageDoc(
                    page_id=page_id,
                    title=title,
                    url=(db_page.get("url") or database.get("url") or "").strip(),
                    parent_id=db_id,
                    path=[*path_prefix, title],
                    text=_clean_text("\n".join(lines)),
                    last_edited_time=(db_page.get("last_edited_time") or "").strip(),
                )
            else:
                doc = _database_page_doc(
                    db_page,
                    database_id=db_id,
                    database_title=db_title,
                    database_url=(database.get("url") or "").strip(),
                    label=label,
                    path_prefix=path_prefix,
                )
            if doc is None or doc.page_id in seen:
                continue
            seen.add(doc.page_id)
            docs.append(doc)
        return True

    if not add_database_target(config.QA_PRIORITY_DEFECT_PAGE_ID, "결함 검색", max(limit, 800)):
        add_page_target(config.QA_PRIORITY_DEFECT_PAGE_ID, "결함 검색")
    if not add_database_target(config.QA_PRIORITY_RESULT_PAGE_ID, "테스트 결과서", 60):
        add_page_target(config.QA_PRIORITY_RESULT_PAGE_ID, "테스트 결과서", max_docs=160)
    if not add_database_target(config.QA_PRIORITY_PLAN_PAGE_ID, "테스트 계획서", 60):
        add_page_target(config.QA_PRIORITY_PLAN_PAGE_ID, "테스트 계획서", max_docs=160)
    if not add_database_target(config.QA_PRIORITY_PROGRESS_DB_ID, "업무 진행 현황", 120, include_page_body=True):
        add_page_target(config.QA_PRIORITY_PROGRESS_DB_ID, "업무 진행 현황", max_docs=160)
    if not add_database_target(config.QA_PRIORITY_WORKSPACE_DB_ID, "업무 공간", 160):
        add_page_target(config.QA_PRIORITY_WORKSPACE_DB_ID, "업무 공간", max_docs=160)
    if not add_database_target(config.QA_PRIORITY_MISC_DB_ID, "기타 자료", 120, include_page_body=True):
        add_page_target(config.QA_PRIORITY_MISC_DB_ID, "기타 자료", max_docs=160)
    return docs


def sync_priority_pages(limit: int = 180) -> dict[str, Any]:
    priority_docs = crawl_priority_targets(limit=limit)
    if not priority_docs:
        raise NotionSyncError("우선 검색 영역을 동기화하지 못했습니다. 기존 인덱스는 유지됩니다.")
    existing: dict[str, Any] = {}
    if config.QA_INDEX_PATH.exists():
        try:
            existing = json.loads(config.QA_INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    by_id: dict[str, dict[str, Any]] = {}
    priority_container_ids = {
        normalize_notion_id(config.QA_PRIORITY_DEFECT_PAGE_ID),
        normalize_notion_id(config.QA_PRIORITY_PROGRESS_DB_ID),
        normalize_notion_id(config.QA_PRIORITY_WORKSPACE_DB_ID),
        normalize_notion_id(config.QA_PRIORITY_MISC_DB_ID),
    }
    for page in existing.get("pages") or []:
        if isinstance(page, dict) and page.get("page_id"):
            page_id = str(page["page_id"])
            if page_id in priority_container_ids:
                continue
            if "QA_ISSUES" in " > ".join(str(x) for x in (page.get("path") or [])):
                continue
            if "업무 공간" in " > ".join(str(x) for x in (page.get("path") or [])):
                continue
            if "업무 진행 현황" in " > ".join(str(x) for x in (page.get("path") or [])):
                continue
            if "기타 자료" in " > ".join(str(x) for x in (page.get("path") or [])):
                continue
            by_id[page_id] = page
    for doc in priority_docs:
        by_id[doc.page_id] = doc.__dict__

    payload = {
        "root_page_id": normalize_notion_id(config.NOTION_ROOT_PAGE_ID),
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pages": list(by_id.values()),
    }
    config.QA_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.QA_INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "synced_at": payload["synced_at"],
        "priority_pages": len(priority_docs),
        "total_pages": len(payload["pages"]),
        "index_path": str(config.QA_INDEX_PATH),
    }


def write_index(docs: list[NotionPageDoc], path: Path | None = None) -> dict[str, Any]:
    target = path or config.QA_INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root_page_id": normalize_notion_id(config.NOTION_ROOT_PAGE_ID),
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pages": [doc.__dict__ for doc in docs],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def sync_qa_pages() -> dict[str, Any]:
    docs = crawl_page_tree(config.NOTION_ROOT_PAGE_ID)
    payload = write_index(docs)
    return {
        "root_page_id": payload["root_page_id"],
        "synced_at": payload["synced_at"],
        "pages": len(docs),
        "text_pages": sum(1 for doc in docs if doc.text.strip()),
        "index_path": str(config.QA_INDEX_PATH),
    }
