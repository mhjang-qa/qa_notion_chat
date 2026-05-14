from __future__ import annotations

import os
import re
import subprocess
from collections import Counter

from app.core import config
from app.services.retriever import SearchHit, load_index, search, source_payload


NOT_FOUND = "요청한 조건과 일치하는 내용을 QA Notion에서 찾지 못했습니다."


_GREETING_RE = re.compile(r"^(안녕|안녕하세요|하이|hi|hello|헬로|ㅎㅇ|반가워)[.!?~\s]*$", re.IGNORECASE)
_CALL_RE = re.compile(r"^(hanq|한큐|큐|하니|봇|챗봇)[.!?~\s]*$", re.IGNORECASE)
_HELP_KEYWORDS = (
    "사용법",
    "어떻게 써",
    "어떻게 사용",
    "help",
    "도움말",
    "가이드",
)
_CAPABILITY_KEYWORDS = (
    "할수있는일",
    "할 수 있는 일",
    "뭐 할 수",
    "무엇을 할 수",
    "기능",
    "뭘 할 수",
    "너 뭐해",
)
_REPORT_RE = re.compile(
    r"결함\s*(제보|등록|신고|접수)|버그\s*(제보|등록|신고|접수)|오류\s*(제보|등록|신고|접수)|이슈\s*(제보|등록|신고|접수)|장애\s*(제보|등록|신고|접수)",
    re.IGNORECASE,
)
_DEFECT_STATUS_RE = re.compile(r"(현재)?\s*(결함|이슈|버그|장애)\s*(현황|상태|요약|summary)", re.IGNORECASE)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _fixed_response(question: str) -> dict | None:
    raw = (question or "").strip()
    compact = _compact(raw)

    if not raw:
        return {
            "answer": "질문을 입력해 주세요.",
            "sources": [],
            "origin": "SYSTEM",
            "mode": "empty",
        }

    if _DEFECT_STATUS_RE.search(raw):
        return _defect_status_summary()

    if _GREETING_RE.match(raw) or _CALL_RE.match(raw):
        return {
            "answer": "안녕하세요. QA 전용 챗봇 Hyo.Chat 입니다.\n저는 QA Notion에 정리된 테스트 계획, 테스트 결과, 결함/이슈, 회귀 테스트, QA 프로세스 내용을 기준으로 답변합니다.",
            "sources": [],
            "origin": "SYSTEM",
            "mode": "greeting",
        }

    if _REPORT_RE.search(raw):
        return {
            "answer": "결함 제보를 시작할 수 있습니다. 화면에서 서비스, 플랫폼, 제보자, 제목, 제보 내용, 첨부파일을 순서대로 입력해 주세요.",
            "sources": [],
            "origin": "SYSTEM",
            "mode": "bug_report_guide",
        }

    if any(keyword in compact for keyword in [_compact(k) for k in _HELP_KEYWORDS]):
        return {
            "answer": (
                "Hyo.Chat 사용법입니다.\n"
                "1. QA 문서에 있는 키워드로 질문하세요. 예: `5.20.0 테스트 결과`, `현재 진행 중인 테스트`, `결함 현황`.\n"
                "2. 테스트 결과서, 테스트 계획서, 결함/이슈는 우선 검색 영역으로 조회합니다.\n"
                "3. `결함제보`라고 입력하면 단계별로 제보 내용을 받아 Notion에 등록합니다.\n"
                "4. 답변 하단의 노션 바로가기 버튼을 눌러 원문을 확인할 수 있습니다.\n"
                "5. Notion에서 확인되지 않는 내용은 추측하지 않고 찾지 못했다고 답합니다."
            ),
            "sources": [],
            "origin": "SYSTEM",
            "mode": "help",
        }

    if any(keyword in compact for keyword in [_compact(k) for k in _CAPABILITY_KEYWORDS]):
        return {
            "answer": (
                "제가 할 수 있는 일입니다.\n"
                "- 현재 진행 중인 테스트와 QA 업무 현황 검색\n"
                "- 과거 테스트 결과서와 출시 테스트 보고서 검색\n"
                "- 결함, 장애, 이슈, Critical/Major/Minor 결과 검색\n"
                "- 테스트 계획서와 테스트 범위 확인\n"
                "- 한패스/방한홈 결함 제보를 Notion 제보 DB에 등록\n"
                "- QA 프로세스, 회귀 테스트, 운영 배포 테스트 관련 문서 검색\n"
                "- QA Notion에 있는 용어/정책성 문서 기반 답변"
            ),
            "sources": [],
            "origin": "SYSTEM",
            "mode": "capabilities",
        }

    return None


def _context_from_hits(hits: list[SearchHit]) -> str:
    blocks: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[근거 {idx}]",
                    f"제목: {hit.chunk.title}",
                    f"경로: {' > '.join(hit.chunk.path)}",
                    f"URL: {hit.chunk.url}",
                    hit.chunk.text,
                ]
            ).strip()
        )
    return "\n\n---\n\n".join(blocks)


def _gemini_answer(question: str, hits: list[SearchHit]) -> str:
    context = _context_from_hits(hits)
    prompt = f"""
너는 QA 전용 Notion 챗봇이다.
아래 [노션 근거]에 있는 내용만 사용해서 한국어로 답변한다.
근거에 없는 내용은 추측하지 말고 "노션 QA 페이지에서 확인되지 않습니다."라고 말한다.
답변은 실무자가 바로 이해할 수 있게 간결하게 정리한다.
답변 본문에는 경로, 관찰자, 우선순위를 쓰지 않는다. 원문 링크는 별도 버튼으로 제공된다.

[질문]
{question}

[노션 근거]
{context}

[답변]
""".strip()

    cmd = [config.GEMINI_CLI_BIN]
    if config.GEMINI_MODEL:
        cmd.extend(["--model", config.GEMINI_MODEL])
    cmd.extend(["-p", prompt])

    proc = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
        env={**os.environ, "CI": "1"},
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Gemini CLI 실패").strip())
    answer = (proc.stdout or proc.stderr or "").strip()
    if not answer:
        raise RuntimeError("Gemini CLI 빈 응답")
    return answer


def _dedupe_hits(hits: list[SearchHit], limit: int = 3) -> list[SearchHit]:
    out: list[SearchHit] = []
    seen: set[str] = set()
    for hit in hits:
        key = hit.chunk.page_id or hit.chunk.title
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
        if len(out) >= limit:
            break
    return out


def _dedupe_all_hits(hits: list[SearchHit], limit: int = 8) -> list[SearchHit]:
    return _dedupe_hits(hits, limit=limit)


def _selected_lines(text: str, wanted: tuple[str, ...], limit: int = 8) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in wanted):
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _summary_lines(text: str, limit: int = 5) -> list[str]:
    skip_prefixes = (
        "페이지:",
        "경로:",
        "title:",
        "데이터베이스:",
        "결함 검색",
        "관찰자:",
        "우선순위:",
        "참여자:",
    )
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip(" -")
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        if line.startswith("하위 데이터베이스") or line.startswith("하위 페이지"):
            continue
        if len(line) > 180:
            line = line[:180].rstrip() + "..."
        out.append(line)
        if len(out) >= limit:
            break
    return out


def _item_text(hit: SearchHit, idx: int) -> str:
        chunk = hit.chunk
        path = " > ".join(chunk.path)
        lines = [f"{idx}. {chunk.title}"]

        if "QA_ISSUES" in path:
            selected = _selected_lines(
                chunk.text,
                ("목표버전:", "타겟 정보:", "심각도:", "상태:", "결함 유형:", "결함 요약:", "조치 담당자:"),
                limit=7,
            )
        else:
            selected = _summary_lines(chunk.text, limit=5)

        for line in selected:
            lines.append(f"- {line}")
        return "\n".join(lines).strip()


def _extractive_items(hits: list[SearchHit], limit: int = 8) -> list[dict]:
    unique_hits = _dedupe_all_hits(hits, limit=limit)
    sources = source_payload(unique_hits)
    items: list[dict] = []
    for idx, hit in enumerate(unique_hits, start=1):
        source = sources[idx - 1] if idx - 1 < len(sources) else None
        items.append({"text": _item_text(hit, idx), "source": source})
    return items


def _extractive_answer(hits: list[SearchHit]) -> str:
    items = _extractive_items(hits, limit=3)
    lines = ["QA Notion에서 확인한 관련 내용입니다."]
    lines.extend(item["text"] for item in items)
    return "\n\n".join(lines).strip()


def _issue_status(text: str) -> str:
    match = re.search(r"^상태:\s*(.+)$", text or "", re.M)
    return match.group(1).strip() if match else "상태 없음"


def _defect_status_summary() -> dict:
    pages = load_index().get("pages") or []
    statuses: Counter[str] = Counter()
    total = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        if "QA_ISSUES" not in " > ".join(str(x) for x in (page.get("path") or [])):
            continue
        total += 1
        statuses[_issue_status(str(page.get("text") or ""))] += 1

    done = sum(
        count
        for status, count in statuses.items()
        if any(key in status.lower() for key in ("완료 (done)", "결함 아님", "추후", "not an issue"))
    )
    ready = sum(
        count
        for status, count in statuses.items()
        if any(key in status.lower() for key in ("qa 검증", "qa verification", "개발 완료", "dev done"))
    )
    in_progress = max(total - done - ready, 0)
    top_statuses = "\n".join(f"- {status}: {count}건" for status, count in statuses.most_common(6))

    answer = (
        "현재 등록된 결함 현황 요약입니다.\n\n"
        f"- 전체 등록 결함: {total}건\n"
        f"- 수정중: {in_progress}건\n"
        f"- 테스트 예정: {ready}건\n"
        f"- 완료: {done}건\n\n"
        "상태별 상세 분포:\n"
        f"{top_statuses}\n\n"
        "특정 항목을 자세히 보려면 `상세 결함 검색 \"검색어\"` 형식으로 입력해 주세요.\n"
        "예: `상세 결함 검색 회원가입`, `상세 결함 검색 5.20.0`"
    )

    return {
        "answer": answer,
        "sources": [],
        "items": [],
        "origin": "NOTION",
        "mode": "defect_status_summary",
    }


def answer_question(question: str) -> dict:
    fixed = _fixed_response(question)
    if fixed is not None:
        return fixed

    hits = search(question)
    if not hits:
        return {
            "answer": NOT_FOUND,
            "sources": [],
            "origin": "NOTION",
            "mode": "not_found",
        }

    mode = "extractive"
    items = _extractive_items(hits, limit=8)
    if config.USE_GEMINI:
        try:
            answer = _gemini_answer(question, hits)
            mode = "gemini_grounded"
            items = []
        except Exception:
            answer = "QA Notion에서 확인한 관련 내용입니다."
            mode = "extractive"
    else:
        answer = "QA Notion에서 확인한 관련 내용입니다."

    return {
        "answer": answer,
        "sources": [item["source"] for item in items if item.get("source")] if items else source_payload(hits),
        "items": items,
        "origin": "NOTION",
        "mode": mode,
    }
