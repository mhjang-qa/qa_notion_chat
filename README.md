# QA Notion Chatbot

QA 전용 Notion 챗봇입니다. 지정한 Notion QA 페이지와 하위 페이지를 재귀적으로 수집해 로컬 인덱스를 만들고, 챗봇은 인덱스에 있는 내용만 근거로 답변합니다.

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
USE_GEMINI=false
STARTUP_SYNC_PRIORITY=true
STARTUP_SYNC_MAX_INDEX_AGE_HOURS=12
```

Render 무료 인스턴스는 파일시스템이 휘발성이므로 런타임에 생성한 인덱스가 재시작/스핀다운 후 사라질 수 있습니다. `STARTUP_SYNC_PRIORITY=true`를 켜면 서버 시작 시 우선 검색 인덱스를 백그라운드로 자동 동기화합니다.

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
