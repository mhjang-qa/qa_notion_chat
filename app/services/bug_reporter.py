from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from app.core import config
from app.services.notion_tree import NotionSyncError, _request, normalize_notion_id, retrieve_database
from app.services.slack_notifier import send_slack_notification


@dataclass(frozen=True)
class BugReportTarget:
    key: str
    label: str
    database_id: str
    platforms: tuple[str, ...]


TARGETS = {
    "hanpass": BugReportTarget(
        key="hanpass",
        label="한패스",
        database_id=config.HANPASS_BUG_REPORT_DB_ID,
        platforms=("AOS", "iOS"),
    ),
    "visit_home": BugReportTarget(
        key="visit_home",
        label="방한홈",
        database_id=config.VISIT_HOME_BUG_REPORT_DB_ID,
        platforms=("AOS", "iOS", "Web-Chrome", "Web-Safari", "Web-기타"),
    ),
}
FILE_UPLOAD_NOTION_VERSION = "2026-03-11"


def bug_report_targets() -> list[dict[str, Any]]:
    return [
        {"key": target.key, "label": target.label, "platforms": list(target.platforms)}
        for target in TARGETS.values()
    ]


def _rich_text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": text[:2000]}}


def _valid_external_url(raw: str) -> bool:
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _attachment_files(urls: list[str]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for idx, raw in enumerate(urls, start=1):
        url = (raw or "").strip()
        if not url:
            continue
        if not _valid_external_url(url):
            raise ValueError(f"첨부 URL 형식이 올바르지 않습니다: {url}")
        name = url.rstrip("/").rsplit("/", 1)[-1] or f"attachment-{idx}"
        files.append({"name": name[:100], "type": "external", "external": {"url": url}})
    return files


def _uploaded_file_objects(files: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for file in files:
        file_id = (file.get("id") or "").strip()
        name = (file.get("name") or "attachment").strip()
        if not file_id:
            continue
        out.append({"name": name[:100], "type": "file_upload", "file_upload": {"id": file_id}})
    return out


def _upload_headers(*, json_content: bool = True) -> dict[str, str]:
    if not config.NOTION_TOKEN:
        raise NotionSyncError("NOTION_TOKEN이 설정되지 않았습니다.")
    headers = {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Notion-Version": FILE_UPLOAD_NOTION_VERSION,
    }
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _upload_request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.notion.com/v1{path}"
    try:
        response = requests.request(method, url, headers=_upload_headers(), json=payload, timeout=60)
    except requests.RequestException as exc:
        raise NotionSyncError(f"Notion API 호출 실패: {exc}") from exc
    if response.status_code >= 400:
        raise NotionSyncError(f"Notion API 오류 ({response.status_code}): {response.text}")
    return response.json() if response.content else {}


def _matching_people(name: str) -> list[dict[str, str]]:
    query = re.sub(r"\s+", " ", name or "").strip().lower()
    if not query:
        return []
    users: list[dict[str, Any]] = []
    cursor = None
    while True:
        path = "/users?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = _upload_request("GET", path)
        users.extend([x for x in data.get("results") or [] if isinstance(x, dict) and x.get("type") == "person"])
        if not data.get("has_more") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

    exact: list[dict[str, str]] = []
    partial: list[dict[str, str]] = []
    for user in users:
        user_id = str(user.get("id") or "")
        user_name = str(user.get("name") or "")
        if not user_id or not user_name:
            continue
        normalized = user_name.lower()
        item = {"id": user_id, "name": user_name}
        if normalized == query:
            exact.append(item)
        elif query in normalized or normalized in query:
            partial.append(item)
    return exact or partial[:1]


def upload_file_to_notion(*, filename: str, content_type: str, content: bytes) -> dict[str, str]:
    clean_filename = (filename or "attachment").strip()[:240]
    upload = _upload_request(
        "POST",
        "/file_uploads",
        payload={"filename": clean_filename, "content_type": content_type or "application/octet-stream"},
    )
    upload_id = upload.get("id")
    if not upload_id:
        raise NotionSyncError("Notion 파일 업로드 객체를 생성하지 못했습니다.")

    try:
        response = requests.post(
            f"https://api.notion.com/v1/file_uploads/{upload_id}/send",
            headers=_upload_headers(json_content=False),
            files={"file": (clean_filename, content, content_type or "application/octet-stream")},
            timeout=120,
        )
    except requests.RequestException as exc:
        raise NotionSyncError(f"Notion 파일 업로드 실패: {exc}") from exc
    if response.status_code >= 400:
        raise NotionSyncError(f"Notion 파일 업로드 오류 ({response.status_code}): {response.text}")
    return {"id": str(upload_id), "name": clean_filename}


def _query_database_rows(database_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = None
    while True:
        payload: dict[str, Any] = {"page_size": page_size}
        if cursor:
            payload["start_cursor"] = cursor
        data = _request("POST", f"/databases/{normalize_notion_id(database_id)}/query", payload=payload)
        rows.extend([x for x in data.get("results") or [] if isinstance(x, dict)])
        if not data.get("has_more") or not data.get("next_cursor"):
            return rows
        cursor = data.get("next_cursor")


def _schema_properties(database_id: str) -> dict[str, Any]:
    database = retrieve_database(database_id)
    return database.get("properties") or {}


def _norm_prop_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()


def _property_name(properties: dict[str, Any], desired: str, ptype: str) -> str | None:
    desired_norm = _norm_prop_name(desired)
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if prop.get("type") == ptype and _norm_prop_name(name) == desired_norm:
            return name
    return None


def _required_property_name(properties: dict[str, Any], desired: str, ptype: str) -> str:
    name = _property_name(properties, desired, ptype)
    if name:
        return name
    raise ValueError(f"Notion DB에 `{desired}`({ptype}) 컬럼이 없습니다.")


def _property_plain_value(page: dict[str, Any], prop_name: str) -> str:
    prop = (page.get("properties") or {}).get(prop_name) or {}
    ptype = prop.get("type")
    values = prop.get(ptype) or []
    return "".join(str(x.get("plain_text") or "") for x in values if isinstance(x, dict)).strip()


def _report_id(target: BugReportTarget, report_id_property: str) -> str:
    prefix = "HP" if target.key == "hanpass" else "GO"
    pattern = re.compile(rf"^{re.escape(prefix)}-BR-(\d+)$")
    max_number = 0
    for row in _query_database_rows(target.database_id):
        report_id = _property_plain_value(row, report_id_property)
        match = pattern.match(report_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"{prefix}-BR-{max_number + 1:03d}"


def _normalize_platforms(target: BugReportTarget, platforms: list[str]) -> list[str]:
    allowed = {x.lower(): x for x in target.platforms}
    out: list[str] = []
    for raw in platforms:
        key = (raw or "").strip().lower()
        if not key:
            continue
        if key not in allowed:
            raise ValueError(f"'{raw}' 플랫폼은 {target.label} 제보 DB에서 사용할 수 없습니다.")
        value = allowed[key]
        if value not in out:
            out.append(value)
    if not out:
        raise ValueError("발생 플랫폼을 1개 이상 선택해 주세요.")
    return out


def _notion_page_url(page: dict[str, Any]) -> str:
    url = str(page.get("url") or "").strip()
    if url:
        return url
    page_id = normalize_notion_id(str(page.get("id") or ""))
    return f"https://www.notion.so/{page_id}" if page_id else ""


def create_bug_report(
    *,
    target_key: str,
    reporter_name: str,
    title: str,
    description: str,
    platforms: list[str],
    attachment_urls: list[str] | None = None,
    uploaded_files: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    target = TARGETS.get((target_key or "").strip())
    if target is None:
        raise ValueError("제보 대상을 선택해 주세요.")

    clean_title = re.sub(r"\s+", " ", title or "").strip()
    clean_reporter = re.sub(r"\s+", " ", reporter_name or "").strip()
    clean_description = (description or "").strip()
    if not clean_reporter:
        raise ValueError("제보자 이름을 입력해 주세요.")
    if not clean_title:
        raise ValueError("제목을 입력해 주세요.")
    if not clean_description:
        raise ValueError("제보 내용을 입력해 주세요.")

    selected_platforms = _normalize_platforms(target, platforms)
    files = [*_uploaded_file_objects(uploaded_files or []), *_attachment_files(attachment_urls or [])]
    schema = _schema_properties(target.database_id)
    title_prop = _required_property_name(schema, "제목", "title")
    report_id_prop = _required_property_name(schema, "제보 ID", "rich_text")
    description_prop = _required_property_name(schema, "제보 내용", "rich_text")
    platform_prop = _required_property_name(schema, "발생 플랫폼", "multi_select")
    attachment_prop = _property_name(schema, "첨부파일", "files")
    reporter_prop = _property_name(schema, "제보자", "people")
    report_id = _report_id(target, report_id_prop)

    properties: dict[str, Any] = {
        title_prop: {"title": [_rich_text(clean_title)]},
        report_id_prop: {"rich_text": [_rich_text(report_id)]},
        description_prop: {"rich_text": [_rich_text(clean_description)]},
        platform_prop: {"multi_select": [{"name": value} for value in selected_platforms]},
    }
    if files and attachment_prop:
        properties[attachment_prop] = {"files": files}
    people = _matching_people(clean_reporter)
    if people and reporter_prop:
        properties[reporter_prop] = {"people": [{"id": person["id"]} for person in people]}

    payload = {
        "parent": {"database_id": normalize_notion_id(target.database_id)},
        "properties": properties,
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [_rich_text(clean_title)]},
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [_rich_text(f"제보자: {clean_reporter}\n\n{clean_description}")]},
            },
        ],
    }

    try:
        page = _upload_request("POST", "/pages", payload=payload)
    except NotionSyncError:
        raise

    notion_url = _notion_page_url(page)
    try:
        send_slack_notification(
            title=clean_title,
            severity="미지정",
            priority="미지정",
            status="Open",
            reporter="QA Chatbot",
            notion_url=notion_url,
        )
    except Exception as exc:
        print(f"[WARN] Slack notification failed: {exc}", flush=True)

    return {
        "report_id": report_id,
        "target": target.label,
        "reporter": clean_reporter,
        "title": clean_title,
        "url": notion_url,
        "platforms": selected_platforms,
        "attachments": len(files),
    }
