const messages = document.getElementById("messages");
const question = document.getElementById("question");
const btnSend = document.getElementById("btnSend");
const btnSync = document.getElementById("btnSync");
const syncStatus = document.getElementById("syncStatus");

let inFlight = false;
let syncing = false;
let composing = false;
let reportFlow = null;

const reportTargets = {
  hanpass: { label: "한패스", platforms: ["AOS", "iOS"] },
  visit_home: { label: "방한홈", platforms: ["AOS", "iOS", "Web-Chrome", "Web-Safari", "Web-기타"] },
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

  for (const ch of content) {
    el.textContent += ch;
    scrollBottom();

    let delay = baseMs;
    if (ch === "\n") delay += 90;
    else if (".!?。？！".includes(ch)) delay += 70;
    else if (",，:;".includes(ch)) delay += 35;

    await sleep(delay);
  }

  el.classList.remove("typing");
}

function addMessage(role, text) {
  const row = document.createElement("div");
  row.className = `msg ${role}`;
  if (role === "bot") {
    const avatar = document.createElement("img");
    avatar.className = "hanq-avatar msg-avatar";
    avatar.src = "/static/hanq.png";
    avatar.alt = "HanQ";
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
  title.textContent = "근거";
  title.className = "sources-title";
  wrap.appendChild(title);

  sources.slice(0, 4).forEach((source, index) => {
    const link = document.createElement("a");
    link.href = source.url || "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "source-button";
    link.textContent = sources.length > 1 ? `노션 바로가기 ${index + 1}` : "노션 바로가기";
    link.title = source.title || "Notion 원문";
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
        more.textContent = `더보기 ${items.length - visibleCount}`;
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
  const compact = (text || "").replace(/\s+/g, "");
  return /결함(제보|등록|신고|접수)|버그(제보|등록|신고|접수)|오류(제보|등록|신고|접수)|이슈(제보|등록|신고|접수)|장애(제보|등록|신고|접수)/.test(compact);
}

function reportPrompt() {
  if (!reportFlow) return "";
  if (reportFlow.step === "target") return "어느 서비스의 결함인가요?";
  if (reportFlow.step === "platform") return "발생 플랫폼을 선택해 주세요. 여러 개면 쉼표로 입력해도 됩니다.";
  if (reportFlow.step === "reporter") return "제보자 이름을 입력해 주세요.";
  if (reportFlow.step === "title") return "결함 제목을 입력해 주세요.";
  if (reportFlow.step === "description") return "제보 내용을 입력해 주세요. 재현 경로, 기대 결과, 실제 결과를 함께 적어주면 좋습니다.";
  if (reportFlow.step === "attachments") return "첨부파일 URL이 있으면 입력해 주세요. 여러 개는 줄바꿈 또는 쉼표로 구분합니다. 없으면 `없음`이라고 입력하세요.";
  if (reportFlow.step === "confirm") return "아래 내용으로 Notion에 등록할까요? 등록 / 취소";
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
  const bubble = addMessage("bot", "결함 제보를 시작합니다.\n어느 서비스의 결함인가요?");
  bubble.appendChild(
    choiceButtons(
      [
        { key: "hanpass", label: "한패스" },
        { key: "visit_home", label: "방한홈" },
      ],
      (item) => {
        if (!reportFlow || reportFlow.step !== "target") return;
        addMessage("user", item.label);
        reportFlow.targetKey = item.key;
        reportFlow.step = "platform";
        showPlatformStep(`${reportTargets[item.key].label} 결함 제보로 진행합니다.\n발생 플랫폼을 선택해 주세요.`);
      },
    ),
  );
  scrollBottomSoon();
}

function showPlatformStep(message) {
  const platforms = platformList();
  const bubble = addMessage("bot", `${message}\n${platforms.map((x) => `- ${x}`).join("\n")}`);
  bubble.appendChild(
    choiceButtons(
      platforms.map((platform) => ({ key: platform, label: platform })),
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
  const bubble = addMessage("bot", "첨부파일을 업로드해 주세요. 파일이 없으면 첨부 없음 버튼을 눌러 주세요.");
  const drop = document.createElement("div");
  drop.className = "upload-dropzone";
  drop.innerHTML = "<strong>이곳으로 파일을 드래그해서 업로드해 주세요</strong><span>또는 클릭해서 파일 선택</span>";

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
  skip.textContent = "첨부 없음";
  skip.addEventListener("click", () => {
    if (!reportFlow || reportFlow.step !== "attachments") return;
    reportFlow.uploadedFiles = [];
    reportFlow.attachmentUrls = [];
    reportFlow.step = "confirm";
    showConfirmStep();
  });

  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "다음";
  next.disabled = true;
  next.addEventListener("click", () => {
    if (!reportFlow || reportFlow.step !== "attachments") return;
    reportFlow.step = "confirm";
    showConfirmStep();
  });

  async function uploadFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length || !reportFlow || reportFlow.step !== "attachments") return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    drop.classList.add("uploading");
    status.textContent = "Notion에 파일을 업로드하는 중입니다.";
    try {
      const res = await fetch("/api/bug-report/files", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        status.textContent = `업로드 실패: ${data.detail || `HTTP ${res.status}`}`;
        return;
      }
      reportFlow.uploadedFiles.push(...(data.files || []));
      const names = reportFlow.uploadedFiles.map((file) => `- ${file.name}`).join("\n");
      status.textContent = `업로드 완료\n${names}`;
      next.disabled = false;
    } catch {
      status.textContent = "업로드 실패: 네트워크 연결을 확인해 주세요.";
    } finally {
      drop.classList.remove("uploading");
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
    : "없음";
  return [
    "제보 내용을 확인해 주세요.",
    "",
    `서비스: ${target}`,
    `플랫폼: ${reportFlow.platforms.join(", ")}`,
    `제보자: ${reportFlow.reporterName}`,
    `제목: ${reportFlow.title}`,
    "제보 내용:",
    reportFlow.description,
    "첨부파일:",
    files,
    "",
    "등록 / 취소",
  ].join("\n");
}

function showConfirmStep() {
  const bubble = addMessage("bot", reportSummary());
  bubble.appendChild(
    choiceButtons(
      [
        { key: "submit", label: "등록" },
        { key: "cancel", label: "취소" },
      ],
      (item) => {
        if (!reportFlow || reportFlow.step !== "confirm") return;
        addMessage("user", item.label);
        if (item.key === "submit") submitReport();
        else {
          reportFlow = null;
          addMessage("bot", "결함 제보를 취소했습니다.");
        }
      },
    ),
  );
  scrollBottomSoon();
}

async function submitReport() {
  const loading = addMessage("bot", "Notion에 결함 제보를 등록하는 중입니다.");
  try {
    const res = await fetch("/api/bug-report", {
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
      loading.textContent = `등록 실패: ${data.detail || `HTTP ${res.status}`}`;
      return;
    }
    loading.textContent = `등록 완료되었습니다.\n제보 ID: ${data.report_id}`;
    if (data.url) {
      const sources = sourceBlock([{ title: data.title, url: data.url }]);
      loading.appendChild(sources);
    }
    reportFlow = null;
  } catch {
    loading.textContent = "등록 실패: 네트워크 연결을 확인해 주세요.";
  }
}

async function handleReportInput(text) {
  if (!reportFlow) return false;
  const value = (text || "").trim();
  if (!value) return true;
  if (/^(취소|cancel)$/i.test(value)) {
    reportFlow = null;
    addMessage("bot", "결함 제보를 취소했습니다.");
    return true;
  }

  if (reportFlow.step === "target") {
    const compact = value.replace(/\s+/g, "").toLowerCase();
    if (compact.includes("한패스") || compact.includes("hanpass")) reportFlow.targetKey = "hanpass";
    else if (compact.includes("방한홈") || compact.includes("gohanpass") || compact.includes("go")) reportFlow.targetKey = "visit_home";
    else {
      addMessage("bot", "서비스를 `한패스` 또는 `방한홈` 중에서 선택해 주세요.");
      return true;
    }
    reportFlow.step = "platform";
    showPlatformStep("발생 플랫폼을 선택해 주세요.");
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "platform") {
    const allowed = platformList();
    const selected = parseList(value).map((entry) => {
      const hit = allowed.find((x) => x.toLowerCase() === entry.toLowerCase());
      return hit || entry;
    });
    const invalid = selected.filter((x) => !allowed.includes(x));
    if (invalid.length) {
      addMessage("bot", `사용할 수 없는 플랫폼입니다: ${invalid.join(", ")}\n가능한 값: ${allowed.join(", ")}`);
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
    reportFlow.attachmentUrls = /^(없음|없어요|skip|no)$/i.test(value) ? [] : parseList(value);
    reportFlow.uploadedFiles = [];
    reportFlow.step = "confirm";
    showConfirmStep();
    scrollBottomSoon();
    return true;
  }

  if (reportFlow.step === "confirm") {
    if (/^(등록|확인|예|yes|y)$/i.test(value)) {
      await submitReport();
      return true;
    }
    addMessage("bot", "등록하려면 `등록`, 중단하려면 `취소`라고 입력해 주세요.");
    return true;
  }

  return true;
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    const text = data.synced_at
      ? `동기화됨: ${data.pages}개 페이지 / ${data.text_pages}개 텍스트 페이지`
      : "아직 동기화되지 않았습니다";
    syncStatus.textContent = text;
  } catch {
    syncStatus.textContent = "상태 확인 실패";
  }
}

async function syncNotion() {
  if (syncing) return;
  syncing = true;
  btnSync.disabled = true;
  const bubble = addMessage("meta", "노션 QA 페이지를 동기화하는 중입니다.");
  syncStatus.textContent = "동기화 중";

  try {
    const res = await fetch("/api/sync", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail || `HTTP ${res.status}`;
      bubble.textContent = `동기화 실패: ${detail}`;
      syncStatus.textContent = "동기화 실패";
      return;
    }
    bubble.textContent = `동기화 완료: ${data.pages}개 페이지, ${data.text_pages}개 텍스트 페이지`;
    await refreshStatus();
  } catch {
    bubble.textContent = "동기화 실패: 네트워크 오류";
    syncStatus.textContent = "동기화 실패";
  } finally {
    syncing = false;
    btnSync.disabled = false;
  }
}

async function sendQuestion() {
  const text = (question.value || "").trim();
  if (!text || inFlight) return;

  inFlight = true;
  btnSend.disabled = true;
  addMessage("user", text);
  question.value = "";
  question.style.height = "auto";

  if (await handleReportInput(text)) {
    inFlight = false;
    btnSend.disabled = false;
    focusQuestion();
    return;
  }

  if (isReportIntent(text)) {
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
    focusQuestion();
    return;
  }

  const loading = addMessage("bot", "답변을 준비하고 있습니다.");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      loading.textContent = `오류: HTTP ${res.status}`;
      return;
    }
    loading.textContent = "";
    const answerText = document.createElement("div");
    answerText.className = "answer-text";
    loading.appendChild(answerText);
    await typeText(answerText, data.answer || "답변이 없습니다.");
    const items = answerItemsBlock(data.items);
    if (items) {
      loading.appendChild(items);
    } else {
      const sources = sourceBlock(data.sources);
      if (sources) loading.appendChild(sources);
    }
    scrollBottom();
  } catch {
    loading.textContent = "오류: 네트워크 연결 실패";
  } finally {
    inFlight = false;
    btnSend.disabled = false;
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

typeText(addMessage("bot", ""), "안녕하세요. QA 전용 챗봇 Hyo.Chat 입니다.\n사용 방법이 궁금하시면 '사용가이드'를 입력해주세요", 20);
refreshStatus();
