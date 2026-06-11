from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.answerer import answer_question
from app.services.bug_reporter import bug_report_targets, create_bug_report, upload_file_to_notion
from app.services.notion_tree import NotionSyncError, sync_priority_pages, sync_qa_pages
from app.services.retriever import load_index

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


@router.post("/chat")
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        return {"answer": "질문을 입력해 주세요.", "sources": [], "origin": "SYSTEM", "mode": "empty"}
    return answer_question(question, allow_llm=req.allow_llm)


@router.get("/bug-report/targets")
def bug_report_options():
    return {"targets": bug_report_targets()}


@router.post("/bug-report")
def bug_report(req: BugReportRequest):
    try:
        return create_bug_report(
            target_key=req.target_key,
            reporter_name=req.reporter_name,
            title=req.title,
            description=req.description,
            platforms=req.platforms,
            attachment_urls=req.attachment_urls,
            uploaded_files=req.uploaded_files,
        )
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
