// Shared by GitHub Pages and the FastAPI pages. No external translation service for UI text.
(() => {
  const dictionary = {
  "버그요정 버니의 결함 제보 가이드": "BUNI Bug Reporting Guide",
  "버그요정 버니": "Bug Fairy BUNI",
  "QA팀과 함께 결함 제보, 테스트 현황, 운영 모니터링을 도와드립니다.": "Here to help the QA team with bug reports, test status, and operations monitoring.",
  "준비 중": "Getting ready",
  "동기화": "Sync",
  "전송": "Send",
  "로그아웃": "Log out",
  "코치마크 바로가기 ↗": "Open guided tour ↗",
  "질문을 입력하세요.": "Enter your question.",
  "버니가 준비 중입니다": "BUNI is getting ready",
  "버니가 노션에서 깨어나는 중입니다.": "BUNI is waking up in Notion.",
  "버니가 버그를 정리 중입니다.": "BUNI is organizing bug reports.",
  "QA 문서를 펼쳐보고 있습니다.": "Opening the QA documents.",
  "결함 제보함을 준비하고 있습니다.": "Preparing the bug report inbox.",
  "초기 접속은 조금 더 걸릴 수 있습니다": "The first visit may take a little longer",
  "버니를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.": "Unable to load BUNI. Please refresh in a moment.",
  "스타일을 불러오지 못했습니다. Render가 깨어나는 중이면 잠시 후 새로고침해 주세요.": "Unable to load styles. The server may be starting. Please refresh in a moment.",
  "챗봇을 불러오지 못했습니다. Render가 깨어나는 중이면 잠시 후 다시 시도해 주세요.": "Unable to load the chatbot. The server may be starting. Please try again shortly.",
  "버그요정 버니의 채팅형 결함 제보 가이드": "BUNI's Chat-Based Bug Reporting Guide",
  "BUNI 결함 제보 안내": "BUNI Bug Reporting Guide",
  "재현 가능한 제보는 빠른 분석과 수정에 큰 도움이 됩니다.": "A reproducible report helps us investigate and fix bugs faster.",
  "현재 단계": "Current step",
  "결함 제보 시작": "Start a bug report",
  "BUNI 메모": "BUNI's note",
  "채팅창에 `결함 제보`, `결함 등록`, `이슈 제보`처럼 입력해 주세요. 이 입력이 제보 플로우를 시작합니다.": "Type `report a bug`, `submit a bug`, or `report an issue` in the chat to start the reporting flow.",
  "채팅창에 `결함 제보`를 입력하면 버니가 단계형 제보 모드로 전환합니다.": "Type `report a bug` in the chat to start BUNI's guided reporting flow.",
  "채팅창에 `결함 제보`를 입력해 주세요. 이 입력이 있어야 챗봇이 일반 검색이 아니라 제보 수집 흐름으로 진입합니다.": "Type `report a bug` in the chat to start collecting a report.",
  "어느 서비스의 결함인지 먼저 선택해 주세요. 현재 챗봇은 한패스와 방한홈 제보 플로우를 지원합니다.": "First, select the affected service. BUNI supports bug reports for Hanpass and GoHanpass.",
  "발생 플랫폼을 선택해 주세요. 버튼 선택이 가능하고, 필요하면 텍스트로 여러 값을 입력할 수도 있습니다.": "Select the affected platform using a button, or type multiple platforms separated by commas.",
  "제보자 이름을 입력해 주세요. Notion 등록 시 제보자 정보와 함께 기록됩니다.": "Enter your name. It will be saved with the report in Notion.",
  "결함 제목은 증상이 한 줄에 보이게 작성해 주세요. 기능명과 실패 증상을 같이 쓰는 편이 좋습니다.": "Write a one-line title with the feature name and the failure you observed.",
  "제보 내용에는 재현 경로, 기대 결과, 실제 결과를 함께 적어 주세요. 이 단계가 제보 품질을 가장 크게 좌우합니다.": "Include steps to reproduce, expected results, and actual results. These details help QA investigate your report.",
  "스크린샷, 영상, 로그 파일을 첨부해 주세요. 파일이 없다면 `첨부 없음`으로 진행할 수 있습니다.": "Attach screenshots, videos, or logs. If you have no files, choose `No attachments`.",
  "최종 요약을 확인한 뒤 `등록`을 선택하면 챗봇이 Notion 제보함에 페이지를 생성합니다. 등록 후 QA 검토가 이어집니다.": "Review the summary and choose `Submit` to create a report in Notion. QA will review it afterward.",
  "채팅형 결함 제보": "Report a bug in chat",
  "버그요정 버니가 순서대로 필요한 항목을 묻습니다.": "BUNI asks for each required detail, step by step.",
  "결함 제보": "Report a bug",
  "결함 제보를 시작합니다.": "Let's report a bug.",
  "어느 서비스의 결함인가요?": "Which service has the bug?",
  "한패스": "Hanpass",
  "방한홈": "GoHanpass",
  "방한홈 결함 제보로 진행합니다.": "Reporting a bug for GoHanpass.",
  "발생 플랫폼을 선택해 주세요.": "Select the affected platform.",
  "제보자 이름을 입력해 주세요.": "Enter the reporter's name.",
  "결함 제목을 입력해 주세요.": "Enter a bug title.",
  "제보 내용을 입력해 주세요. 재현 경로, 기대 결과, 실제 결과를 함께 적어주면 좋습니다.": "Describe the bug, including steps to reproduce, expected results, and actual results.",
  "첨부파일을 업로드해 주세요. 파일이 없으면 첨부 없음 버튼을 눌러 주세요.": "Upload attachments, or choose No attachments to continue.",
  "이곳으로 파일을 드래그해서 업로드해 주세요": "Drag files here to upload",
  "첨부 없음": "No attachments",
  "다음": "Next",
  "제보 내용을 확인해 주세요.": "Review your bug report.",
  "서비스": "Service",
  "플랫폼": "Platforms",
  "제보자": "Reporter",
  "홍길동": "Alex Kim",
  "제목": "Title",
  "결제 버튼 클릭 시 결제창 미노출": "Payment window does not open when clicking Pay",
  "첨부파일": "Attachments",
  "등록": "Submit",
  "취소": "Cancel",
  "등록 완료되었습니다. 제보 ID: GO-BR-018": "Report submitted. Report ID: GO-BR-018",
  "이전": "Previous",
  "처음부터 보기": "Start over",
  "등록 이후에는 QA 검토를 거쳐 결함 등록 또는 반려가 진행될 수 있으며, 정보가 부족하면 보완 요청이 이어질 수 있습니다.": "After submission, QA will review and accept or reject the report. You may be asked for more information.",
  "서비스 선택": "Select a service",
  "버니가 제보 대상 서비스를 묻습니다. 현재 한패스와 방한홈 중 하나를 선택해 주세요.": "BUNI asks which service is affected. Choose Hanpass or GoHanpass.",
  "서비스 선택이 먼저 있어야 올바른 Notion 제보함으로 연결됩니다.": "Selecting a service routes the report to the correct Notion inbox.",
  "플랫폼 선택": "Select platforms",
  "발생 플랫폼을 선택해 주세요. 버튼으로 고를 수 있고, 필요하면 텍스트 입력도 가능합니다.": "Select a platform using a button or type its name.",
  "플랫폼 정보는 재현과 담당 분류에 직접 쓰입니다.": "Platform details help reproduce the bug and assign it to the right team.",
  "제보자 이름 입력": "Enter your name",
  "제보자 이름을 입력해 주세요. 등록 이력과 후속 확인에 사용됩니다.": "Enter your name so QA can follow up on the report.",
  "QA 검토나 보완 요청이 필요한 경우 제보자 정보가 기준이 됩니다.": "QA uses the reporter's details when a review or follow-up is needed.",
  "결함 제목 입력": "Enter a bug title",
  "결함 제목은 한 줄로 증상이 보이게 작성해 주세요. 기능과 실패 증상을 함께 쓰는 편이 좋습니다.": "Write a one-line title that includes the feature and the observed failure.",
  "제목만 보고도 어떤 문제인지 바로 파악할 수 있어야 합니다.": "The title should make the problem clear at a glance.",
  "제보 내용 입력": "Describe the bug",
  "재현 경로, 기대 결과, 실제 결과를 함께 입력해 주세요. 이 단계가 제보 품질을 좌우합니다.": "Include steps to reproduce, expected results, and actual results for an actionable report.",
  "채팅형 제보에서는 이 단계에 핵심 내용을 모아서 입력해 주세요.": "Enter all the key details together at this step.",
  "첨부파일 업로드": "Upload attachments",
  "스크린샷, 영상, 로그 파일을 첨부해 주세요. 파일이 없으면 `첨부 없음`으로 진행할 수 있습니다.": "Attach screenshots, videos, or logs, or choose `No attachments` to continue.",
  "드래그 업로드 또는 클릭 업로드 후 `다음`으로 넘어갑니다.": "Drag files in or click to upload, then choose `Next`.",
  "최종 확인 후 등록": "Review and submit",
  "요약 내용을 확인한 뒤 `등록`을 선택하면 Notion 제보함에 페이지가 생성됩니다.": "Review the summary and choose `Submit` to create a report in Notion.",
  "등록 완료 메시지와 제보 ID가 표시되면 챗봇 등록은 끝입니다.": "A confirmation message and report ID mean the report has been submitted."
};
  const reverse = new Map(Object.entries(dictionary).map(([ko, en]) => [en, ko]));
  const nodeTranslations = new WeakMap();
  const originalTitle = document.title;
  let language = "ko";
  const requested = new URLSearchParams(location.search).get("lang");
  try { language = localStorage.getItem("buni-language") === "en" ? "en" : "ko"; } catch {}
  if (requested === "en" || requested === "ko") language = requested;
  function t(ko, en = dictionary[ko] || ko) {
    dictionary[ko] = en;
    reverse.set(en, ko);
    return language === "en" ? en : ko;
  }
  function translateFor(value, target) {
    const text = value.trim();
    const ko = Object.hasOwn(dictionary, text) ? text : (reverse.get(text) || text);
    const translated = target === "en" ? (Object.hasOwn(dictionary, ko) ? dictionary[ko] : null) : ko;
    if (translated && translated !== text) return value.replace(text, translated);
    if (value.includes("\n")) return value.split("\n").map(line => translateFor(line, target)).join("\n");
    return value;
  }
  function translate(value, target = language) { return translateFor(value, target); }
  function apply() {
    document.documentElement.lang = language;
    document.title = language === "en" ? (dictionary[originalTitle] || originalTitle) : originalTitle;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.parentElement.closest("script, style, textarea, .msg.user, [data-preserve]")) continue;
      let entry = nodeTranslations.get(node);
      if (!entry || entry.last !== node.nodeValue) {
        const value = node.nodeValue;
        entry = { ko: translateFor(value, "ko"), en: translateFor(value, "en"), last: value };
        nodeTranslations.set(node, entry);
      }
      const next = language === "en" ? entry.en : entry.ko;
      if (next !== node.nodeValue) node.nodeValue = next;
      entry.last = next;
    }
    document.querySelectorAll("[placeholder]").forEach(el => el.placeholder = translate(el.placeholder));
    document.querySelectorAll("[data-coachmark-link]").forEach(el => {
      const url = new URL(el.href, location.href);
      url.searchParams.set("lang", language);
      el.href = url.href;
    });
    const button = document.getElementById("btnLanguage");
    if (button) {
      button.textContent = language === "en" ? "🌐 한국어" : "🌐 English";
      button.setAttribute("aria-label", language === "en" ? "Switch to Korean" : "영어로 변경");
      button.title = button.getAttribute("aria-label");
    }
  }
  function setLanguage(value) {
    language = value === "en" ? "en" : "ko";
    try { localStorage.setItem("buni-language", language); } catch {}
    const url = new URL(location.href);
    url.searchParams.set("lang", language);
    try { history.replaceState(null, "", url); } catch {}
    apply();
    window.dispatchEvent(new CustomEvent("buni:language"));
  }
  window.BuniI18n = { t, translate, apply, setLanguage, get language() { return language; } };
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.getElementById("btnLanguage")?.addEventListener("click", () => setLanguage(language === "en" ? "ko" : "en"));
  });
})();
