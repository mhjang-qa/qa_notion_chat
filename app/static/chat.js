const t = window.BuniI18n.t;
const messages = document.getElementById("messages");
const question = document.getElementById("question");
const btnSend = document.getElementById("btnSend");
const btnSync = document.getElementById("btnSync");
const syncStatus = document.getElementById("syncStatus");
const API_BASE = (window.HYO_CHAT_API_BASE || "").replace(/\/$/, "");
const ASSET_BASE = (window.HYO_CHAT_ASSET_BASE || "").replace(/\/$/, "");

let inFlight = false;
let syncing = false;
let composing = false;
let reportFlow = null;
let llmOffer = null;
let reportSubmitting = false;
let uploading = false;

function applyViewportHeight() {
  const height = window.innerHeight || document.documentElement.clientHeight || 0;
  if (height > 0) {
    document.documentElement.style.setProperty("--app-height", `${height}px`);
  }
}

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function assetUrl(path) {
  return `${ASSET_BASE}${path}`;
}

const reportTargets = {
  hanpass: { get label() { return t("한패스", "Hanpass"); }, platforms: ["AOS", "iOS"] },
  visit_home: { get label() { return t("방한홈", "GoHanpass"); }, platforms: ["AOS", "iOS", "Web-Chrome", "Web-Safari", "Web-기타"] },
};

function scrollBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function scrollBottomSoon() {
  scrollBottom();
  requestAnimationFrame(scrollBottom);
  setTimeout(scrollBottom, 80);
}

function focusQuestion() {
  if (reportFlow) return;
  question.focus({ preventScroll: true });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function typeText(el, text, baseMs = 18) {
  const content = text || "";
  el.textContent = "";
  el.classList.add("typing");

  if (content.length > 260) {
    const chunkSize = Math.max(4, Math.ceil(content.length / 120));
    for (let index = 0; index < content.length; index += chunkSize) {
      el.textContent += content.slice(index, index + chunkSize);
      scrollBottom();
      await sleep(8);
    }
  } else {
    for (const ch of content) {
      el.textContent += ch;
      scrollBottom();

      let delay = baseMs;
      if (ch === "\n") delay += 90;
      else if (".!?。？！".includes(ch)) delay += 70;
      else if (",，:;".includes(ch)) delay += 35;

      await sleep(delay);
    }
  }

  el.classList.remove("typing");
}

function addMessage(role, text) {
  const row = document.createElement("div");
  row.className = `msg ${role}`;
  if (role === "bot") {
    const avatar = document.createElement("img");
    avatar.className = "hanq-avatar msg-avatar";
    avatar.src = assetUrl("/static/hanq.png");
    avatar.alt = "BUNI";
    row.appendChild(avatar);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text || "";
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollBottom();
  return bubble;
}

function sourceBlock(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return null;
  const wrap = document.createElement("div");
  wrap.className = "sources";
  const title = document.createElement("div");
  title.textContent = t("근거", "Sources");
  title.className = "sources-title";
  wrap.appendChild(title);

  sources.slice(0, 4).forEach((source, index) => {
    const link = document.createElement("a");
    link.href = localizedLink(source.url || "#");
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "source-button";
    link.textContent = source.button_label || (sources.length > 1 ? t(`노션 바로가기 ${index + 1}`, `Open in Notion ${index + 1}`) : t("노션 바로가기", "Open in Notion"));
    link.title = source.title || t("Notion 원문", "Notion source");
    wrap.appendChild(link);
  });

  return wrap;
}

function answerItemsBlock(items) {
  if (!Array.isArray(items) || items.length === 0) return null;

  const wrap = document.createElement("div");
  wrap.className = "answer-items";
  let visibleCount = Math.min(3, items.length);

  function render() {
    wrap.textContent = "";
    items.forEach((item, index) => {
      const block = document.createElement("div");
      block.className = "answer-item";
      if (index >= visibleCount) block.hidden = true;

      const text = document.createElement("div");
      text.className = "answer-text";
      text.textContent = item.text || "";
      block.appendChild(text);

      const footer = document.createElement("div");
      footer.className = "answer-item-footer";
      const sources = sourceBlock(item.source ? [item.source] : []);
      if (sources) footer.appendChild(sources);

      if (index === visibleCount - 1 && visibleCount < items.length) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "source-button more-button";
        more.textContent = t(`더보기 ${items.length - visibleCount}`, `Show more (${items.length - visibleCount})`);
        more.addEventListener("click", () => {
          visibleCount = Math.min(visibleCount + 3, items.length);
          render();
          scrollBottomSoon();
        });
        footer.appendChild(more);
      }

      if (footer.childNodes.length > 0) block.appendChild(footer);
      const line = document.createElement("div");
      line.className = "answer-cutline";
      line.textContent = "-----";
      block.appendChild(line);
      wrap.appendChild(block);
    });
  }

  render();
  return wrap;
}

function choiceButtons(items, onPick) {
  const wrap = document.createElement("div");
  wrap.className = "choice-buttons";
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.label;
    button.addEventListener("click", () => {
      onPick(item);
      scrollBottomSoon();
    });
    wrap.appendChild(button);
  });
  scrollBottomSoon();
  return wrap;
}

function isReportIntent(text) {
  if (isReportGuideIntent(text)) return false;
  const compact = (text || "").replace(/\s+/g, "");
  return /^\s*(?:(?:i (?:want|need|would like) to|please|can you)\s+)?(?:(?:report|submit|file)\s+(?:a\s+)?(?:bug|defect|issue)|(?:bug|defect|issue)\s+report)[.!?\s]*$/i.test(text) || /결함(제보|등록|신고|접수)|버그(제보|등록|신고|접수)|오류(제보|등록|신고|접수)|이슈(제보|등록|신고|접수)|장애(제보|등록|신고|접수)/.test(compact);
}

function isReportGuideIntent(text) {
  const compact = (text || "").replace(/\s+/g, "").toLowerCase();
  return (
    (/\b(?:guide|instructions|help)\b|\bhow\s+(?:to|do|can|should)\b/i.test(text) && /\b(?:report|submit|file|reporting)\b/i.test(text) && /\b(?:bug|defect|issue)s?\b/i.test(text)) ||
    /(결함|버그|오류|이슈|장애)(제보|등록|신고|접수)(가이드|방법|어떻게|절차|프로세스|안내|링크)/.test(compact) ||
    /(가이드|방법|어떻게|절차|프로세스|안내|링크)(결함|버그|오류|이슈|장애)(제보|등록|신고|접수)/.test(compact)
  );
}

function isYesIntent(text) {
  return /^(예|네|응|ㅇㅇ|좋아|진행|해줘|yes|y|ok|okay)$/i.test((text || "").trim());
}

function isNoIntent(text) {
  return /^(아니오|아니요|아니|ㄴㄴ|취소|그만|no|n)$/i.test((text || "").trim());
}

function reportPrompt() {
  if (!reportFlow) return "";
  if (reportFlow.step === "target") return t("어느 서비스의 결함인가요?", "Which service has the bug?");
  if (reportFlow.step === "platform") return t("발생 플랫폼을 선택해 주세요. 여러 개면 쉼표로 입력해도 됩니다.", "Select the affected platform. Separate multiple platforms with commas.");
  if (reportFlow.step === "reporter") return t("제보자 이름을 입력해 주세요.", "Enter the reporter's name.");
  if (reportFlow.step === "title") return t("결함 제목을 입력해 주세요.", "Enter a bug title.");
  if (reportFlow.step === "description") return t("제보 내용을 입력해 주세요. 재현 경로, 기대 결과, 실제 결과를 함께 적어주면 좋습니다.", "Describe the bug, including steps to reproduce, expected results, and actual results.");
  if (reportFlow.step === "attachments") return t("첨부파일 URL이 있으면 입력해 주세요. 여러 개는 줄바꿈 또는 쉼표로 구분합니다. 없으면 `없음`이라고 입력하세요.", "Enter attachment URLs separated by commas or new lines, or type `none`.");
  if (reportFlow.step === "confirm") return t("아래 내용으로 Notion에 등록할까요? 등록 / 취소", "Submit this report to Notion? Submit / Cancel");
  return "";
}

function platformList() {
  const target = reportTargets[reportFlow?.targetKey];
  return target ? target.platforms : [];
}

function parseList(text) {
  return (text || "")
    .split(/[\n,]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function showReportTargetStep() {
  const bubble = addMessage("bot", t("결함 제보를 시작합니다.\n어느 서비스의 결함인가요?", "Let's report a bug.\nWhich service has the bug?"));
  bubble.appendChild(
    choiceButtons(
      [
        { key: "hanpass", get label() { return t("한패스", "Hanpass"); } },
        { key: "visit_home", get label() { return t("방한홈", "GoHanpass"); } },
      ],
      (item) => {
        if (!reportFlow || reportFlow.step !== "target") return;
        addMessage("user", item.label);
        reportFlow.targetKey = item.key;
        reportFlow.step = "platform";
        showPlatformStep(t(`${item.key === "hanpass" ? "한패스" : "방한홈"} 결함 제보로 진행합니다.`, `Reporting a bug for ${item.key === "hanpass" ? "Hanpass" : "GoHanpass"}.`) + "\n" + t("발생 플랫폼을 선택해 주세요.", "Select the affected platform."));
      },
    ),
  );
  scrollBottomSoon();
}

function showPlatformStep(message) {
  const platforms = platformList();
  const bubble = addMessage("bot", `${message}\n${platforms.map((x) => `- ${platformLabel(x)}`).join("\n")}`);
  bubble.appendChild(
    choiceButtons(
      platforms.map((platform) => ({ key: platform, label: platformLabel(platform) })),
      (item) => {
        if (!reportFlow || reportFlow.step !== "platform") return;
        addMessage("user", item.label);
        reportFlow.platforms = [item.key];
        reportFlow.step = "reporter";
        addMessage("bot", reportPrompt());
      },
    ),
  );
  scrollBottomSoon();
}

function showAttachmentStep() {
  const bubble = addMessage("bot", t("첨부파일을 업로드해 주세요. 파일이 없으면 첨부 없음 버튼을 눌러 주세요.", "Upload attachments, or choose No attachments to continue."));
  const drop = document.createElement("div");
  drop.className = "upload-dropzone";
  const uploadTitle = document.createElement("strong");
  uploadTitle.textContent = t("이곳으로 파일을 드래그해서 업로드해 주세요", "Drag files here to upload");
  const uploadHint = document.createElement("span");
  uploadHint.textContent = t("또는 클릭해서 파일 선택", "or click to choose files");
  drop.append(uploadTitle, uploadHint);

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.multiple = true;
  fileInput.className = "upload-input";

  const status = document.createElement("div");
  status.className = "upload-status";

  const actions = document.createElement("div");
  actions.className = "choice-buttons";

  const skip = document.createElement("button");
  skip.type = "button";
  skip.textContent = t("첨부 없음", "No attachments");
  skip.addEventListener("click", () => {
    if (!reportFlow || reportFlow.step !== "attachments") return;
    reportFlow.uploadedFiles = [];
    reportFlow.attachmentUrls = [];
    reportFlow.step = "confirm";
    showConfirmStep();
  });

  const next = document.createElement("button");
  next.type = "button";
  next.textContent = t("다음", "Next");
  next.disabled = reportFlow.uploadedFiles.length === 0;
  status.textContent = reportFlow.uploadedFiles.map(file => `- ${file.name}`).join("\n");
  next.addEventListener("click", () => {
    if (!reportFlow || reportFlow.step !== "attachments" || drop.classList.contains("uploading")) return;
    reportFlow.step = "confirm";
    showConfirmStep();
  });

  async function uploadFiles(fileList) {
    if (drop.classList.contains("uploading")) return;
    const files = Array.from(fileList || []);
    if (!files.length || !reportFlow || reportFlow.step !== "attachments") return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    drop.classList.add("uploading");
    uploading = true;
    btnSend.disabled = true;
    skip.disabled = true;
    next.disabled = true;
    document.getElementById("btnLanguage").disabled = true;
    status.textContent = t("Notion에 파일을 업로드하는 중입니다.", "Uploading files to Notion.");
    try {
      const res = await fetch(apiUrl("/api/bug-report/files"), { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        status.textContent = t(`업로드 실패: ${data.detail || `HTTP ${res.status}`}`, `Upload failed: ${englishError(data.detail, res.status)}`);
        return;
      }
      reportFlow.uploadedFiles.push(...(data.files || []));
      const names = reportFlow.uploadedFiles.map((file) => `- ${file.name}`).join("\n");
      status.textContent = t(`업로드 완료\n${names}`, `Upload complete\n${names}`);
      next.disabled = false;
    } catch {
      status.textContent = t("업로드 실패: 네트워크 연결을 확인해 주세요.", "Upload failed. Check your network connection.");
    } finally {
      drop.classList.remove("uploading");
      uploading = false;
      btnSend.disabled = inFlight;
      skip.disabled = false;
      next.disabled = reportFlow?.uploadedFiles.length === 0;
      document.getElementById("btnLanguage").disabled = inFlight;
    }
  }

  drop.addEventListener("click", () => fileInput.click());
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("dragging");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("dragging");
    uploadFiles(event.dataTransfer.files);
  });
  fileInput.addEventListener("change", () => uploadFiles(fileInput.files));

  actions.appendChild(skip);
  actions.appendChild(next);
  bubble.appendChild(drop);
  bubble.appendChild(fileInput);
  bubble.appendChild(status);
  bubble.appendChild(actions);
  scrollBottomSoon();
}

function reportSummary() {
  const target = reportTargets[reportFlow.targetKey]?.label || "";
  const uploaded = reportFlow.uploadedFiles.map((file) => file.name);
  const files = uploaded.length || reportFlow.attachmentUrls.length
    ? [...uploaded, ...reportFlow.attachmentUrls].join("\n")
    : t("없음", "None");
  return [
    t("제보 내용을 확인해 주세요.", "Review your bug report."),
    "",
    t(`서비스: ${target}`, `Service: ${target}`),
    t(`플랫폼: ${reportFlow.platforms.join(", ")}`, `Platforms: ${reportFlow.platforms.map(platformLabel).join(", ")}`),
    t(`제보자: ${reportFlow.reporterName}`, `Reporter: ${reportFlow.reporterName}`),
    t(`제목: ${reportFlow.title}`, `Title: ${reportFlow.title}`),
    t("제보 내용:", "Description:"),
    reportFlow.description,
    t("첨부파일:", "Attachments:"),
    files,
    "",
    t("등록 / 취소", "Submit / Cancel"),
  ].join("\n");
}

function showConfirmStep() {
  const bubble = addMessage("bot", reportSummary());
  bubble.appendChild(
    choiceButtons(
      [
        { key: "submit", label: t("등록", "Submit") },
        { key: "cancel", label: t("취소", "Cancel") },
      ],
      (item) => {
        if (!reportFlow || reportFlow.step !== "confirm" || reportSubmitting) return;
        addMessage("user", item.label);
        if (item.key === "submit") submitReport();
        else {
          reportFlow = null;
          addMessage("bot", t("결함 제보를 취소했습니다.", "Bug report cancelled."));
        }
      },
    ),
  );
  scrollBottomSoon();
}

async function submitReport() {
  if (reportSubmitting || !reportFlow) return;
  reportSubmitting = true;
  document.getElementById("btnLanguage").disabled = true;
  btnSend.disabled = true;
  const loading = addMessage("bot", t("Notion에 결함 제보를 등록하는 중입니다.", "Submitting your bug report to Notion."));
  try {
    const res = await fetch(apiUrl("/api/bug-report"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_key: reportFlow.targetKey,
        reporter_name: reportFlow.reporterName,
        title: reportFlow.title,
        description: reportFlow.description,
        platforms: reportFlow.platforms,
        attachment_urls: reportFlow.attachmentUrls,
        uploaded_files: reportFlow.uploadedFiles,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      loading.textContent = t(`등록 실패: ${data.detail || `HTTP ${res.status}`}`, `Submission failed: ${englishError(data.detail, res.status)}`);
      return;
    }
    loading.textContent = t(`등록 완료되었습니다.\n제보 ID: ${data.report_id}`, `Report submitted.\nReport ID: ${data.report_id}`);
    if (data.url) {
      const sources = sourceBlock([{ title: data.title, url: data.url }]);
      loading.appendChild(sources);
    }
    reportFlow = null;
  } catch {
    loading.textContent = t("등록 실패: 네트워크 연결을 확인해 주세요.", "Submission failed. Check your network connection.");
  } finally {
    reportSubmitting = false;
    btnSend.disabled = false;
    document.getElementById("btnLanguage").disabled = inFlight;
  }
}

async function handleReportInput(text) {
  if (!reportFlow) return false;
  const value = (text || "").trim();
  if (!value) return true;
  if (/^(취소|cancel)$/i.test(value)) {
    reportFlow = null;
    addMessage("bot", t("결함 제보를 취소했습니다.", "Bug report cancelled."));
    return true;
  }

  if (reportFlow.step === "target") {
    const compact = value.replace(/\s+/g, "").toLowerCase();
    if (compact.includes("방한홈") || compact.includes("gohanpass") || compact === "go") reportFlow.targetKey = "visit_home";
    else if (compact.includes("한패스") || compact.includes("hanpass")) reportFlow.targetKey = "hanpass";
    else {
      addMessage("bot", t("서비스를 `한패스` 또는 `방한홈` 중에서 선택해 주세요.", "Choose `Hanpass` or `GoHanpass`."));
      return true;
    }
    reportFlow.step = "platform";
    showPlatformStep(t("발생 플랫폼을 선택해 주세요.", "Select the affected platform."));
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "platform") {
    const allowed = platformList();
    const selected = parseList(value).map((entry) => {
      const hit = allowed.find((x) => x.toLowerCase() === entry.toLowerCase() || platformLabel(x).toLowerCase() === entry.toLowerCase());
      return hit || entry;
    });
    const invalid = selected.filter((x) => !allowed.includes(x));
    if (invalid.length) {
      addMessage("bot", t(`사용할 수 없는 플랫폼입니다: ${invalid.join(", ")}\n가능한 값: ${allowed.join(", ")}`, `Unsupported platform: ${invalid.join(", ")}\nAvailable values: ${allowed.map(platformLabel).join(", ")}`));
      return true;
    }
    reportFlow.platforms = selected;
    reportFlow.step = "reporter";
    addMessage("bot", reportPrompt());
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "reporter") {
    reportFlow.reporterName = value;
    reportFlow.step = "title";
    addMessage("bot", reportPrompt());
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "title") {
    reportFlow.title = value;
    reportFlow.step = "description";
    addMessage("bot", reportPrompt());
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "description") {
    reportFlow.description = value;
    reportFlow.step = "attachments";
    showAttachmentStep();
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "attachments") {
    reportFlow.attachmentUrls = /^(없음|없어요|none|skip|no)$/i.test(value) ? [] : parseList(value);
    reportFlow.uploadedFiles = [];
    reportFlow.step = "confirm";
    showConfirmStep();
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "confirm") {
    if (/^(등록|확인|예|submit|confirm|yes|y)$/i.test(value)) {
      await submitReport();
      return true;
    }
    addMessage("bot", t("등록하려면 `등록`, 중단하려면 `취소`라고 입력해 주세요.", "Type `submit` to submit, or `cancel` to stop."));
    return true;
  }

  return true;
}

async function refreshStatus() {
  try {
    const res = await fetch(apiUrl("/api/status"));
    if (!res.ok) return;
    const data = await res.json();
    const text = data.synced_at
      ? t(`동기화됨: ${data.pages}개 페이지 / ${data.text_pages}개 텍스트 페이지`, `Synced: ${data.pages} pages / ${data.text_pages} text pages`)
      : t("아직 동기화되지 않았습니다", "Not synced yet");
    syncStatus.textContent = text;
  } catch {
    syncStatus.textContent = t("상태 확인 실패", "Unable to check status");
  }
}

async function syncNotion() {
  if (syncing) return;
  syncing = true;
  btnSync.disabled = true;
  const bubble = addMessage("meta", t("노션 우선 검색 영역을 동기화하는 중입니다.", "Syncing priority Notion pages."));
  syncStatus.textContent = t("동기화 중", "Syncing");

  try {
    const res = await fetch(apiUrl("/api/sync/priority"), { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail || `HTTP ${res.status}`;
      bubble.textContent = t(`동기화 실패: ${detail}`, `Sync failed: ${englishError(detail)}`);
      syncStatus.textContent = t("동기화 실패", "Sync failed");
      return;
    }
    const pageCount = data.total_pages || data.pages || 0;
    const priorityCount = data.priority_pages || 0;
    bubble.textContent = t(`동기화 완료: ${pageCount}개 페이지 / 우선 검색 ${priorityCount}개 페이지`, `Sync complete: ${pageCount} pages / ${priorityCount} priority pages`);
    await refreshStatus();
  } catch {
    bubble.textContent = t("동기화 실패: 네트워크 오류", "Sync failed: network error");
    syncStatus.textContent = t("동기화 실패", "Sync failed");
  } finally {
    syncing = false;
    btnSync.disabled = false;
  }
}

async function sendQuestion() {
  const text = (question.value || "").trim();
  if (!text || inFlight || reportSubmitting || uploading) return;

  inFlight = true;
  document.getElementById("btnLanguage").disabled = true;
  btnSend.disabled = true;
  addMessage("user", text);
  question.value = "";
  question.style.height = "auto";
  let requestText = text;
  let allowLlm = false;

  if (llmOffer) {
    const pendingQuestion = llmOffer.question;
    if (isYesIntent(text)) {
      requestText = pendingQuestion;
      allowLlm = true;
      llmOffer = null;
    } else if (isNoIntent(text)) {
      llmOffer = null;
      addMessage("bot", t("알겠습니다. LLM 보조 답변은 진행하지 않겠습니다.", "Okay. I won't generate an LLM-assisted answer."));
      inFlight = false;
      btnSend.disabled = false;
      document.getElementById("btnLanguage").disabled = false;
      focusQuestion();
      return;
    } else {
      addMessage("bot", t("`예` 또는 `아니오`로 답해 주세요. LLM 답변을 원하지 않으면 `아니오`라고 입력하면 됩니다.", "Please reply `yes` or `no`. Choose `no` to skip the LLM-assisted answer."));
      inFlight = false;
      btnSend.disabled = false;
      document.getElementById("btnLanguage").disabled = false;
      focusQuestion();
      return;
    }
  }

  const reportGuideIntent = isReportGuideIntent(text);

  if (!reportGuideIntent && await handleReportInput(text)) {
    inFlight = false;
    btnSend.disabled = false;
    document.getElementById("btnLanguage").disabled = false;
    focusQuestion();
    return;
  }

  if (!reportGuideIntent && isReportIntent(text)) {
    reportFlow = {
      step: "target",
      targetKey: "",
      platforms: [],
      reporterName: "",
      title: "",
      description: "",
      attachmentUrls: [],
      uploadedFiles: [],
    };
    showReportTargetStep();
    scrollBottomSoon();
    inFlight = false;
    btnSend.disabled = false;
    document.getElementById("btnLanguage").disabled = false;
    focusQuestion();
    return;
  }

const loading = addMessage("bot", t("답변을 준비하고 있습니다.", "Preparing your answer."));

try {
  const res = await fetch(apiUrl("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: requestText, allow_llm: allowLlm, language: window.BuniI18n.language }),
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    loading.textContent = t(`오류: HTTP ${res.status}`, `Error: HTTP ${res.status}`);
    return;
  }

  if (data.mode === "llm_offer") {
    llmOffer = { question: data.pending_question || requestText };
  } else {
    llmOffer = null;
  }

  loading.textContent = "";

  const answerText = document.createElement("div");
  answerText.className = "answer-text";
  loading.appendChild(answerText);

  const answer = data.answer || t("답변이 없습니다.", "No answer is available.");
  const instantAnswer = data.origin === "LLM" || String(data.mode || "").startsWith("llm_");
  const lines = answer.split("\n");

  if (instantAnswer) {
    const body = document.createElement("div");
    body.className = "answer-body";
    body.textContent = answer;
    answerText.appendChild(body);
  } else if (lines.length > 1) {
    const title = document.createElement("div");
    title.className = "answer-title";
    title.textContent = lines[0];
    answerText.appendChild(title);

    const body = document.createElement("div");
    body.className = "answer-body";
    answerText.appendChild(body);

    await typeText(body, lines.slice(1).join("\n"));
  } else {
    await typeText(answerText, answer);
  }

  // 커스텀 버튼 지원
  if (data.button && data.button.url) {
    const buttonWrap = document.createElement("div");
    buttonWrap.className = "sources";

    const guideButton = document.createElement("a");
    guideButton.href = localizedLink(data.button.url);
    guideButton.target = "_blank";
    guideButton.rel = "noopener noreferrer";
    guideButton.className = "source-button";
    guideButton.textContent = data.button.label || t("바로가기", "Open link");

    buttonWrap.appendChild(guideButton);
    loading.appendChild(buttonWrap);
  }

  const items = answerItemsBlock(data.items);

  if (items) {
    loading.appendChild(items);
  } else {
    const sources = sourceBlock(data.sources);
    if (sources) {
      loading.appendChild(sources);
    }
  }

  scrollBottom();
} catch {
  loading.textContent = t("오류: 네트워크 연결 실패", "Error: network connection failed");
} finally {
  inFlight = false;
  btnSend.disabled = false;
  document.getElementById("btnLanguage").disabled = false;
  focusQuestion();
}
}
question.addEventListener("compositionstart", () => {
  composing = true;
});

question.addEventListener("compositionend", () => {
  composing = false;
});

question.addEventListener("input", () => {
  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 120)}px`;
});

question.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || composing) return;
  event.preventDefault();
  sendQuestion();
});

btnSend.addEventListener("click", sendQuestion);
btnSync.addEventListener("click", syncNotion);
window.addEventListener("resize", applyViewportHeight);
window.addEventListener("orientationchange", applyViewportHeight);
window.visualViewport?.addEventListener("resize", applyViewportHeight);

applyViewportHeight();

addMessage("bot", t("안녕하세요. QA팀과 함께 일하는 버그요정 버니(BUNI)입니다.\n사용 방법이 궁금하시면 '사용가이드'를 입력해주세요.\n결함 제보의 경우 '결함 제보'를 입력해주세요.", "Hello! I'm BUNI, the bug fairy working with the QA team.\nType 'help' for instructions.\nType 'report a bug' to submit a bug report."));
refreshStatus();

function platformLabel(value) { return value === "Web-기타" ? t("Web-기타", "Web-Other") : value; }
function englishError(detail, status) {
  return detail && !/[가-힣]/.test(String(detail)) ? detail : `Request failed${status ? ` (HTTP ${status})` : ""}. Please try again.`;
}
function localizedLink(value) {
  const url = new URL(value, location.href);
  if (/bug[-_]report[-_]guide/.test(url.pathname)) url.searchParams.set("lang", window.BuniI18n.language);
  return url.href;
}
window.addEventListener("buni:language", () => {
  refreshStatus();
  messages.querySelectorAll(".choice-buttons button, .upload-input").forEach(el => el.disabled = true);
  messages.querySelectorAll(".upload-dropzone").forEach(el => el.style.pointerEvents = "none");
  if (!reportFlow) return;
  if (reportFlow.step === "target") showReportTargetStep();
  else if (reportFlow.step === "platform") showPlatformStep(reportPrompt());
  else if (reportFlow.step === "attachments") showAttachmentStep();
  else if (reportFlow.step === "confirm") showConfirmStep();
  else addMessage("bot", reportPrompt());
});
