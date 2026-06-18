# 버그요정 버니 (Bug Fairy BUNI)

QA팀과 함께 일하는 친근한 버그요정 컨셉의 Notion QA 챗봇입니다. 지정한 Notion QA 페이지와 하위 페이지를 재귀적으로 수집해 로컬 인덱스를 만들고, 챗봇은 인덱스에 있는 내용만 근거로 답변합니다.

## 로컬 실행

```bash
cd qa_notion_chatbot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 `NOTION_TOKEN`, `SESSION_SECRET`, `TEMP_PW`를 설정한 뒤 실행합니다.

```bash
uvicorn app.main:app --reload --port 8010
```

브라우저에서 `http://127.0.0.1:8010`으로 접속합니다.

기본값은 Notion 임베드 사용을 위해 로그인 없이 열립니다. 로그인 게이트를 다시 켜려면 `.env`에 아래 값을 설정합니다.

```bash
AUTH_REQUIRED=true
```

## 동기화

화면 오른쪽 아래 챗봇 패널에서 `동기화` 버튼을 누르거나 API를 호출합니다.

```bash
curl -X POST http://127.0.0.1:8010/api/sync
```

우선 검색 영역만 빠르게 갱신하려면 아래 API를 사용합니다.

```bash
curl -X POST http://127.0.0.1:8010/api/sync/priority
```

## Render 배포

이 저장소에는 Render Blueprint용 `render.yaml`이 포함되어 있습니다.

Render Web Service 설정값:

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

Render 환경 변수에 최소 아래 값은 직접 설정해야 합니다.

```bash
NOTION_TOKEN=...
AUTH_REQUIRED=false
USE_GEMINI=true
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
STARTUP_SYNC_PRIORITY=true
STARTUP_SYNC_MAX_INDEX_AGE_HOURS=12
SLACK_WEBHOOK_URL=...
SLACK_CHANNEL_NAME=slice_gh-test
SLACK_NOTIFY_ENABLED=true
CHAT_STATS_ENABLED=true
CHAT_STATS_PAGE_ID=38173fbd195180a8a0f1d7bffbc221da
```

Render 무료 인스턴스는 파일시스템이 휘발성이므로 런타임에 생성한 인덱스가 재시작/스핀다운 후 사라질 수 있습니다. `STARTUP_SYNC_PRIORITY=true`를 켜면 서버 시작 시 우선 검색 인덱스를 백그라운드로 자동 동기화합니다.

## LLM 보조 답변

정형 질문이나 Notion 검색 결과로 답할 수 없는 경우, 챗봇은 즉시 LLM 답변을 만들지 않고 사용자에게 먼저 확인합니다. 사용자가 `예`라고 답한 경우에만 `allow_llm=true`로 다시 요청해 LLM 보조 답변을 생성합니다.

LLM 보조 답변은 한패스/GoHanpass/핀테크 업무 범위에 제한됩니다. 범위 밖 질문은 일반 LLM 답변을 생성하지 않습니다.

Render 또는 로컬 `.env`에 아래 값을 설정합니다.

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=<Google Gemini API Key>
GEMINI_MODEL=gemini-2.5-flash
USE_GEMINI=true
```

`GEMINI_API_KEY`가 있으면 Gemini CLI 없이 API로 동작합니다. API Key가 없고 `USE_GEMINI=true`인 경우 기존 `GEMINI_CLI_BIN` 경로를 사용합니다.

## 챗봇 이용 통계

`/api/chat`으로 질문이 들어오거나 `/api/bug-report`에서 결함 등록이 완료되면 비동기로 Notion 통계 페이지에 데이터를 적재합니다. 통계 적재가 실패해도 사용자 답변이나 결함 등록 결과는 실패하지 않습니다.

기본 통계 페이지:

```bash
CHAT_STATS_PAGE_ID=38173fbd195180a8a0f1d7bffbc221da
CHAT_STATS_ENABLED=true
```

최초 실행 시 해당 페이지 하위에 아래 데이터베이스를 자동 생성합니다.

- `BUNI Chat Daily Stats`: 일자별 총 인입, 고유 질문, LLM 요청, Notion 답변, 고정 응답, 결함 등록 완료 건수, 범위 밖 질문, 고유 IP, IP 목록, 주요 주제, 최근 질문
- `BUNI Chat Question Logs`: 질문별 원문, 일자/시각, 응답 모드, 출처, 주제, LLM 여부, 응답 요약, 질문 키, IP 주소, User Agent, Referer

Notion 통계 페이지가 비어 있어도 자동으로 데이터베이스를 만들지만, Notion Integration이 해당 페이지에 접근 권한을 가지고 있어야 합니다.

Notion 임베드와 로그인 비활성 구조에서는 특정 사용자를 안정적으로 식별할 수 없습니다. 대신 Render 요청 헤더 기준 IP 후보(`CF-Connecting-IP`, `X-Real-IP`, `X-Forwarded-For`)와 User Agent를 질문 로그에 저장합니다.

일자별 통계 페이지 본문에는 답변 품질 확인을 위해 당일 질문/답변 목록을 질문별 콜아웃 카드로 자동 작성합니다. 각 카드에는 질문, 답변 요약, 분류, 응답 모드, 출처, 시각, IP가 함께 정리됩니다. 자동 작성 영역은 `[BUNI_STATS_BODY]` 마커 이후를 매번 갱신하므로, 수동 메모는 마커 위쪽에 작성하세요.

## Slack 결함 등록 알림

챗봇에서 결함 제보가 Notion DB에 정상 등록되면 Slack Incoming Webhook으로 `#slice_gh-test` 채널에 Block Kit 알림을 보냅니다. Notion 등록이 실패하거나 Validation Error/Notion API Error가 발생하면 Slack은 호출하지 않습니다. Slack 전송이 실패해도 Notion 등록 성공 상태는 유지됩니다.

### Slack Webhook 생성 방법

1. Slack App 관리 화면에서 Incoming Webhooks를 활성화합니다.
2. `#slice_gh-test` 채널을 대상으로 Webhook URL을 생성합니다.
3. 생성된 URL을 `SLACK_WEBHOOK_URL` 환경변수에 넣습니다.

### 환경변수

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL_NAME=slice_gh-test
SLACK_NOTIFY_ENABLED=true
```

`SLACK_NOTIFY_ENABLED=false`이면 결함 등록은 그대로 동작하지만 Slack 알림은 전송하지 않습니다.

### 로컬 실행

`.env`에 Slack 환경변수를 추가한 뒤 서버를 실행합니다.

```bash
uvicorn app.main:app --reload --port 8010
```

브라우저에서 `http://127.0.0.1:8010` 접속 후 `결함 제보` 플로우로 실제 등록을 진행하면 Notion 등록 성공 이후 Slack 알림이 전송됩니다.

### Render 설정 방법

Render Dashboard의 Web Service에서 `Environment` 메뉴에 아래 값을 추가합니다.

```bash
SLACK_WEBHOOK_URL=<Slack Incoming Webhook URL>
SLACK_CHANNEL_NAME=slice_gh-test
SLACK_NOTIFY_ENABLED=true
```

`render.yaml`에도 `SLACK_CHANNEL_NAME`, `SLACK_NOTIFY_ENABLED`, `SLACK_WEBHOOK_URL` 항목이 포함되어 있습니다. Webhook URL은 secret 값이므로 Render에서 직접 입력해야 합니다.

### 테스트 시나리오

- TC-001: 결함 등록 성공 -> Slack 알림 전송, `결함 보기` 버튼에 Notion URL 포함
- TC-002: 결함 등록 성공 + Slack Webhook 오류 -> 사용자에게 결함 등록 성공으로 표시, 서버 로그에 `[WARN] [SLACK] Notification failed`
- TC-003: 결함 등록 실패 또는 Notion API Error -> Slack 알림 미전송
- TC-004: `SLACK_NOTIFY_ENABLED=false` -> Slack 알림 미전송
- TC-005: Slack 메시지에 제목, 심각도, 우선순위, 상태, 등록자, 등록일시, Notion 링크 포함

## Render 무료 인스턴스 콜드스타트 완화

Render 무료 Web Service는 일정 시간 요청이 없으면 스핀다운됩니다. 업무 시간에만 깨워두려면 외부 스케줄러에서 `/health`를 주기적으로 호출하세요.

권장 ping 주기:

- 한국 시간 평일 08:50-18:10
- 10-12분 간격
- URL: `https://<render-service>.onrender.com/health`

GitHub Actions를 사용할 경우 UTC 기준으로 KST 평일 09:00-18:00은 `0 0-9 * * 1-5`에 가깝습니다. 10분 간격이면 `*/10 0-9 * * 1-5`를 사용하고, 워크플로 안에서 `/health`를 호출하면 됩니다.

GitHub Actions를 사용하려면 GitHub 저장소의 `Settings > Secrets and variables > Actions`에 아래 secret을 추가하세요.

```bash
RENDER_SERVICE_URL=https://<render-service>.onrender.com
```

워크플로는 KST 평일 09:00-17:50 동안 10분마다 `/health`를 호출하면 됩니다. 마지막 호출 이후 약 15분 동안은 Render가 스핀다운하지 않으므로 18:00 전후까지 유지됩니다.

## 답변 정책

- `NOTION_ROOT_PAGE_ID` 페이지와 하위 페이지에서 가져온 텍스트만 사용합니다.
- 관련 근거가 없으면 답변하지 않고, 노션에서 찾지 못했다고 응답합니다.
- Gemini CLI가 있으면 검색된 문맥 안에서만 문장을 정리합니다.
- Gemini CLI가 없거나 실패하면 검색된 원문 발췌를 반환합니다.
