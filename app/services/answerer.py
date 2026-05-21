from __future__ import annotations

import os
import re
import subprocess
from collections import Counter

from app.core import config
from app.services.retriever import SearchHit, load_index, search, source_payload


NOT_FOUND = "요청한 조건과 일치하는 내용을 QA Notion에서 찾지 못했습니다."


_GREETING_RE = re.compile(r"^(안녕|안녕하세요|하이|hi|hello|헬로|ㅎㅇ|반가워)[.!?~\s]*$", re.IGNORECASE)
_CALL_RE = re.compile(r"^(buni|버니|버그요정|hanq|한큐|큐|하니|봇|챗봇)[.!?~\s]*$", re.IGNORECASE)
_CASUAL_CHAT_RE = re.compile(
    r"(너|넌|너는|버니|buni|버그요정|한큐|hanq|hyo\.?chat|챗봇|봇).*(뭐야|누구|정체|사람|ai|인공지능|닮|같아|예쁘|이쁘|귀엽|기분|나이|취미)|"
    r"(잡담|심심|놀아줘|농담|기분\s*어때|점심|저녁|뭐\s*먹|누구를\s*닮|누구\s*닮)",
    re.IGNORECASE,
)
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
_REPORT_GUIDE_RE = re.compile(
    r"(결함|버그|오류|이슈|장애)\s*(제보|등록|신고|접수).*(가이드|방법|어떻게|절차|프로세스|안내|링크)|"
    r"(가이드|방법|어떻게|절차|프로세스|안내|링크).*(결함|버그|오류|이슈|장애)\s*(제보|등록|신고|접수)",
    re.IGNORECASE,
)
_DEFECT_STATUS_RE = re.compile(
    r"(현재|현재까지|지금|전체)?\s*(결함|이슈|버그|장애)\s*(현황|상태|요약|개수|수|건수|몇\s*개|summary|count)|"
    r"(결함|이슈|버그|장애).*(몇\s*개|몇개|개수|건수|수량|카운트)",
    re.IGNORECASE,
)
_CURRENT_WORK_RE = re.compile(
    r"(현재|지금|진행\s*중|진행중).*(테스트|업무|항목|현황)|"
    r"(테스트|업무|항목).*(현재|지금|진행\s*중|진행중|현황)",
    re.IGNORECASE,
)
_PENDING_WORK_RE = re.compile(
    r"(시작\s*(전|이전)|시작전|예정|대기).*(테스트|업무|항목|현황)|"
    r"(테스트|업무|항목).*(시작\s*(전|이전)|시작전|예정|대기)",
    re.IGNORECASE,
)
_DONE_WORK_RE = re.compile(
    r"(완료|종료|끝난).*(테스트|업무|항목|현황)|"
    r"(테스트|업무|항목).*(완료|종료|끝난)",
    re.IGNORECASE,
)


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

    if _PENDING_WORK_RE.search(raw):
        progress = _work_status_summary("pending")
        if progress is not None:
            return progress

    if _DONE_WORK_RE.search(raw):
        progress = _work_status_summary("done")
        if progress is not None:
            return progress

    if _CURRENT_WORK_RE.search(raw):
        progress = _work_status_summary("active")
        if progress is not None:
            return progress

    if _CASUAL_CHAT_RE.search(raw):
        return _casual_chat_response(raw)

    if _REPORT_GUIDE_RE.search(raw) or any(
        token in compact
        for token in (
            "결함제보가이드",
            "버그제보가이드",
            "이슈제보가이드",
            "결함제보방법",
            "버그제보방법",
            "결함제보어떻게",
            "버그제보어떻게",
        )
    ):
        guide_url = "https://mhjang-qa.github.io/qa_notion_chat/bug_report_guide.html"
        return {
            "answer": (
                "결함 제보 방법은 전용 가이드에서 바로 확인할 수 있습니다.\n"
                "아래 버튼으로 `결함 제보 가이드`를 열어 주세요.\n"
                "실제 제보를 바로 시작하려면 채팅창에 `결함 제보`를 입력해 주세요."
            ),
            "sources": [
                {
                    "title": "결함 제보 가이드",
                    "url": guide_url,
                    "button_label": "결함 제보 가이드 열기",
                }
            ],
            "origin": "SYSTEM",
            "mode": "bug_report_guide_link",
        }

    if _GREETING_RE.match(raw) or _CALL_RE.match(raw):
        return {
            "answer": "안녕하세요. QA팀과 함께 일하는 버그요정 버니(BUNI)입니다.\n저는 QA Notion에 정리된 테스트 계획, 테스트 결과, 결함/이슈\n노션 내용을 기준으로 빠르게 도와드립니다.",
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
                "버그요정 버니(BUNI) 사용법입니다.\n"
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


def _casual_chat_response(question: str) -> dict:
    compact = _compact(question)
    if any(token in compact for token in ("뭐야", "누구", "정체", "ai", "인공지능")):
        answer = (
            "저는 QA Notion 문서를 기준으로 답변하는 버그요정 버니(BUNI)입니다.\n"
            "일상 대화나 개인적인 판단은 정해진 범위 밖이라 길게 답하긴 어렵습니다.\n"
            "대신 `진행중인 테스트 항목`, `시작 전 테스트 항목`, `결함 현황`, `결함 제보`처럼 QA 업무 질문을 주시면 확인해드릴게요."
        )
    elif any(token in compact for token in ("닮", "예쁘", "이쁘", "귀엽", "기분", "취미", "나이")):
        answer = (
            "그런 질문은 잡담에 가까워서 제가 판단해서 답변하긴 어렵습니다.\n"
            "저는 QA Notion에 있는 내용과 정해진 안내 답변만 기준으로 답합니다.\n"
            "QA 문서, 테스트 현황, 결함 검색, 결함 제보 관련으로 질문해 주세요."
        )
    else:
        answer = (
            "일상 대화는 지원 범위가 제한되어 있습니다.\n"
            "저는 QA Notion 문서에 있는 내용과 정해진 QA 안내만 답변할 수 있습니다.\n"
            "예: `현재 진행중 테스트`, `시작 전 테스트 항목`, `5.21.0 테스트 결과서`, `결함 현황`, `결함 제보`"
        )
    return {
        "answer": answer,
        "sources": [],
        "items": [],
        "origin": "SYSTEM",
        "mode": "casual_guardrail",
    }


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


def _defect_count_status_group(status: str) -> str:
    lowered = (status or "").lower()
    if any(token in lowered for token in ("추후", "백로그 이관", "backlog")):
        return "later"
    if any(token in lowered for token in ("완료", "done", "결함 아님", "not an issue")):
        return "done"
    return "active"


def _defect_service_group(page: dict) -> str:
    haystack = "\n".join(
        [
            str(page.get("title") or ""),
            str(page.get("text") or ""),
            " > ".join(str(x) for x in (page.get("path") or [])),
        ]
    ).lower()
    if re.search(r"go\s*hanpass|gohanpass|go\.hanpass|방한\s*홈|방한홈", haystack, re.IGNORECASE):
        return "go hanpass"
    return "한패스"


def _line_value(text: str, names: tuple[str, ...]) -> str:
    for raw in (text or "").splitlines():
        line = raw.strip()
        for name in names:
            match = re.match(rf"^{re.escape(name)}\s*:\s*(.+)$", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""


def _is_progress_doc(page: dict) -> bool:
    path = " > ".join(str(x) for x in (page.get("path") or []))
    return any(keyword in path for keyword in ("업무 진행 현황", "QA 업무 진행 현황", "테스트 진행 현황"))


def _is_active_work(text: str) -> bool:
    status = _line_value(text, ("상태", "진행 상태", "진행상태", "Status", "status"))
    lowered_status = status.lower()
    if status and any(done in lowered_status for done in ("완료", "done", "종료", "closed", "cancel", "취소")):
        return False
    if status and any(active in lowered_status for active in ("진행", "progress", "ongoing", "개발", "검증", "대기", "예정")):
        return True
    return bool(re.search(r"진행\s*중|in\s*progress|ongoing|개발\s*중|검증\s*중", text or "", re.IGNORECASE))


def _work_status_group(text: str) -> str:
    status = _line_value(text, ("상태", "진행 상태", "진행상태", "Status", "status"))
    lowered = status.lower()
    if status and any(done in lowered for done in ("완료", "done", "종료", "closed", "cancel", "취소")):
        return "done"
    if status and any(pending in lowered for pending in ("시작 전", "시작전", "예정", "대기", "todo", "not started", "before start")):
        return "pending"
    if status and any(active in lowered for active in ("진행", "progress", "ongoing", "개발", "검증")):
        return "active"
    if re.search(r"시작\s*(전|이전)|시작전|not\s*started|todo", text or "", re.IGNORECASE):
        return "pending"
    if re.search(r"진행\s*중|in\s*progress|ongoing|개발\s*중|검증\s*중", text or "", re.IGNORECASE):
        return "active"
    return "other"


def _priority_rank(text: str) -> int:
    priority = _line_value(text, ("우선순위", "우선 순위", "Priority", "priority", "중요도"))
    haystack = priority.lower()
    if any(token in haystack for token in ("p0", "critical", "긴급", "최상", "highest")):
        return 0
    if any(token in haystack for token in ("p1", "high", "높음", "상")):
        return 1
    if any(token in haystack for token in ("p2", "medium", "보통", "중")):
        return 2
    if any(token in haystack for token in ("p3", "low", "낮음", "하")):
        return 3
    return 9


def _progress_item_text(page: dict, idx: int) -> str:
    text = str(page.get("text") or "")
    title = str(page.get("title") or "제목 없음")
    lines = [f"{idx}. {title}"]
    selected = _selected_lines(
        text,
        (
            "상태:",
            "진행 상태:",
            "진행상태:",
            "우선순위:",
            "우선 순위:",
            "담당자:",
            "담당:",
            "일정:",
            "기간:",
            "목표:",
            "서비스:",
            "버전:",
            "진행률:",
            "테스트:",
        ),
        limit=8,
    )
    if not selected:
        selected = _summary_lines(text, limit=5)
    for line in selected:
        lines.append(f"- {line}")
    return "\n".join(lines).strip()


def _work_status_summary(status_group: str) -> dict | None:
    pages = [page for page in (load_index().get("pages") or []) if isinstance(page, dict) and _is_progress_doc(page)]
    if not pages:
        return None

    matched_pages = [page for page in pages if _work_status_group(str(page.get("text") or "")) == status_group]
    labels = {
        "active": ("현재 진행중인", "current_work_status"),
        "pending": ("시작 전인", "pending_work_status"),
        "done": ("완료된", "done_work_status"),
    }
    label, mode = labels.get(status_group, ("요청한 상태의", "work_status"))

    if not matched_pages:
        return {
            "answer": f"업무 진행 현황에서 {label} 항목을 찾지 못했습니다.",
            "sources": [],
            "items": [],
            "origin": "NOTION",
            "mode": mode,
        }

    matched_pages.sort(
        key=lambda page: (
            _priority_rank(str(page.get("text") or "")),
            str(page.get("last_edited_time") or ""),
            str(page.get("title") or ""),
        )
    )

    items: list[dict] = []
    for idx, page in enumerate(matched_pages[:8], start=1):
        source = {
            "title": str(page.get("title") or "제목 없음"),
            "url": str(page.get("url") or ""),
            "path": " > ".join(str(x) for x in (page.get("path") or [])),
            "score": 0,
            "preview": str(page.get("text") or "")[:300],
        }
        items.append({"text": _progress_item_text(page, idx), "source": source})

    return {
        "answer": f"업무 진행 현황에서 {label} 항목 {len(matched_pages)}건을 확인했습니다. 우선순위가 높은 항목부터 보여드립니다.",
        "sources": [item["source"] for item in items if item.get("source")],
        "items": items,
        "origin": "NOTION",
        "mode": mode,
    }


def _defect_status_summary() -> dict:
    pages = load_index().get("pages") or []
    groups = {
        "전체": Counter(),
        "한패스": Counter(),
        "go hanpass": Counter(),
    }
    for page in pages:
        if not isinstance(page, dict):
            continue
        if "QA_ISSUES" not in " > ".join(str(x) for x in (page.get("path") or [])):
            continue
        text = str(page.get("text") or "")
        status_group = _defect_count_status_group(_issue_status(text))
        service_group = _defect_service_group(page)
        groups["전체"][status_group] += 1
        groups[service_group][status_group] += 1

    def line(label: str, counter: Counter[str]) -> str:
        total = sum(counter.values())
        done = counter["done"]
        active = counter["active"]
        later = counter["later"]
        return f"- {label} 결함 개수: {total}건 / 완료 {done}건 / 진행중 {active}건 / 추후 수정 {later}건"

    notion_url = "https://www.notion.so/21473fbd1951800d8321fc2e34c2548e?v=21473fbd195180caab27000c0264da96&source=copy_link"

    answer = (
        "현재까지 등록된 결함 개수 요약입니다.\n\n"
        f"{line('전체', groups['전체'])}\n"
        f"{line('한패스', groups['한패스'])}\n"
        f"{line('go hanpass', groups['go hanpass'])}\n\n"
        "특정 항목을 자세히 보려면 `상세 결함 검색 \"검색어\"` 형식으로 입력해 주세요.\n"
        "예: `상세 결함 검색 회원가입`, `상세 결함 검색 5.20.0`"
    )

    return {
        "answer": answer,
        "sources": [
            {
                "title": "결함 현황",
                "url": notion_url,
                "button_label": "결함 현황 바로가기",
            }
        ],
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
