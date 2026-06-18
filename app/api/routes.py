from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.services.answerer import answer_question
from app.services.bug_reporter import bug_report_targets, create_bug_report, upload_file_to_notion
from app.services.chat_stats import record_chat_interaction_async
from app.services.notion_tree import NotionSyncError, sync_priority_pages, sync_qa_pages
from app.services.retriever import load_index

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    allow_llm: bool = False


class BugReportRequest(BaseModel):
    target_key: str
    reporter_name: str
    title: str
    description: str
    platforms: list[str]
    attachment_urls: list[str] = []
    uploaded_files: list[dict[str, str]] = []


def _request_meta(request: Request) -> dict[str, str]:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    return {
        "ip": (
            request.headers.get("cf-connecting-ip")
            or request.headers.get("x-real-ip")
            or (forwarded_for.split(",")[0].strip() if forwarded_for else "")
            or (request.client.host if request.client else "")
        ),
        "user_agent": request.headers.get("user-agent", ""),
        "referer": request.headers.get("referer", ""),
    }


@router.post("/chat")
def chat(req: ChatRequest, request: Request):
    question = (req.question or "").strip()
    if not question:
        return {"answer": "질문을 입력해 주세요.", "sources": [], "origin": "SYSTEM", "mode": "empty"}
    request_meta = _request_meta(request)
    try:
        answer = answer_question(question, allow_llm=req.allow_llm)
        record_chat_interaction_async(question, answer, request_meta=request_meta)
        return answer
    except Exception as exc:
        logger.exception("[CHAT] answer generation failed: %s", exc)
        answer = {
            "answer": "답변 처리 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "sources": [],
            "items": [],
            "origin": "SYSTEM",
            "mode": "server_error",
        }
        record_chat_interaction_async(question, answer, request_meta=request_meta)
        return answer


@router.get("/bug-report/targets")
def bug_report_options():
    return {"targets": bug_report_targets()}


@router.post("/bug-report")
def bug_report(req: BugReportRequest, request: Request):
    try:
        result = create_bug_report(
            target_key=req.target_key,
            reporter_name=req.reporter_name,
            title=req.title,
            description=req.description,
            platforms=req.platforms,
            attachment_urls=req.attachment_urls,
            uploaded_files=req.uploaded_files,
        )
        record_chat_interaction_async(
            f"[결함 등록 완료] {result.get('report_id', '')} {req.title}".strip(),
            {
                "answer": (
                    f"{result.get('target', '')} 결함 제보가 등록되었습니다. "
                    f"제보 ID: {result.get('report_id', '')} / "
                    f"플랫폼: {', '.join(result.get('platforms') or [])} / "
                    f"첨부파일: {result.get('attachments', 0)}개 / "
                    f"Notion: {result.get('url', '')}"
                ),
                "sources": [{"title": "등록된 결함", "url": result.get("url", "")}],
                "items": [],
                "origin": "NOTION",
                "mode": "bug_report_created",
            },
            request_meta=_request_meta(request),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotionSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/bug-report/files")
async def bug_report_files(files: list[UploadFile] = File(...)):
    uploaded = []
    try:
        for file in files:
            content = await file.read()
            uploaded.append(
                upload_file_to_notion(
                    filename=file.filename or "attachment",
                    content_type=file.content_type or "application/octet-stream",
                    content=content,
                )
            )
    except NotionSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"files": uploaded}


@router.post("/sync")
def sync():
    try:
        result = sync_priority_pages()
        return {
            **result,
            "pages": result.get("total_pages", 0),
            "text_pages": result.get("total_pages", 0),
        }
    except NotionSyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync/priority")
def sync_priority():
    try:
        result = sync_priority_pages()
        return {
            **result,
            "pages": result.get("total_pages", 0),
            "text_pages": result.get("total_pages", 0),
        }
    except NotionSyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
def status():
    index = load_index()
    pages = index.get("pages") or []
    return {
        "ok": True,
        "synced_at": index.get("synced_at"),
        "pages": len(pages),
        "text_pages": sum(1 for page in pages if str(page.get("text") or "").strip()),
    }
