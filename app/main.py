from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import router as api_router
from app.core import config
from app.services.notion_tree import sync_priority_pages

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Bug Fairy BUNI")

@app.middleware("http")
async def allow_iframe_embed(request: Request, call_next):
    response = await call_next(request)

    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]

    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' "
        "https://www.notion.so "
        "https://notion.so "
        "https://*.notion.so "
        "https://*.notion.site "
        "https://mhjang-qa.github.io;"
    )

    return response



def _index_needs_startup_sync() -> bool:
    if not config.STARTUP_SYNC_PRIORITY:
        return False
    if not config.QA_INDEX_PATH.exists():
        return True
    max_age = max(config.STARTUP_SYNC_MAX_INDEX_AGE_HOURS, 0) * 3600
    if max_age <= 0:
        return True
    return time.time() - config.QA_INDEX_PATH.stat().st_mtime > max_age


def _startup_sync_priority() -> None:
    if not _index_needs_startup_sync():
        return
    try:
        sync_priority_pages()
    except Exception as exc:
        print(f"[startup-sync] priority sync failed: {exc}")


@app.on_event("startup")
def startup_sync() -> None:
    if config.STARTUP_SYNC_PRIORITY:
        threading.Thread(target=_startup_sync_priority, daemon=True).start()


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not config.AUTH_REQUIRED:
            return await call_next(request)
        path = request.url.path
        public_paths = {
            "/",
            "/login",
            "/logout",
            "/health",
            "/healthz",
            "/favicon.ico",
            "/bug-report-guide",
            "/bug-report-guide.html",
            "/bug_report_guide.html",
        }
        if path in public_paths or path.startswith("/static"):
            return await call_next(request)
        if not request.session.get("auth"):
            if path.startswith("/api"):
                return PlainTextResponse("Unauthorized", status_code=401)
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)


app.add_middleware(AuthGateMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://mhjang-qa.github.io",
        "http://127.0.0.1:8020",
        "http://localhost:8020",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(api_router, prefix="/api")


def is_authed(request: Request) -> bool:
    return bool(request.session.get("auth"))


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/healthz", methods=["GET", "HEAD"])
def health():
    return {"ok": True}


@app.head("/")
def head_root():
    return Response(status_code=200)


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if config.AUTH_REQUIRED and not is_authed(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("chat.html", {"request": request, "auth_required": config.AUTH_REQUIRED})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authed(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == config.TEMP_ID and password == config.TEMP_PW:
        request.session["auth"] = True
        request.session["user"] = username
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "아이디 또는 비밀번호가 잘못되었습니다."},
        status_code=401,
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/favicon.ico")
def favicon():
    return HTMLResponse(status_code=204)


@app.get("/bug-report-guide")
@app.get("/bug-report-guide.html")
@app.get("/bug_report_guide.html")
def bug_report_guide():
    return FileResponse(BASE_DIR.parent / "bug_report_guide.html")
