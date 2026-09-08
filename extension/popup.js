const captureButton = document.querySelector("#capture");
const statusText = document.querySelector("#status");
const previewForm = document.querySelector("#preview");
const companyInput = document.querySelector("#company");
const titleInput = document.querySelector("#title");
const urlInput = document.querySelector("#url");
const jdInput = document.querySelector("#jd");
const draftList = document.querySelector("#draft-list");
const draftCount = document.querySelector("#draft-count");
const connectionText = document.querySelector("#connection");
const connectionDot = document.querySelector("#connection-dot");

function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function refreshDrafts() {
  const { drafts = [] } = await send({ type: "getDrafts" });
  draftCount.textContent = String(drafts.length);
  draftList.replaceChildren();
  if (!drafts.length) {
    const empty = document.createElement("p");
    empty.className = "draft-empty";
    empty.textContent = "暂无离线草稿";
    draftList.append(empty);
    return;
  }
  for (const draft of drafts) {
    const row = document.createElement("div");
    row.className = "draft-row";
    const title = document.createElement("strong");
    title.textContent = draft.title || "未命名岗位";
    const company = document.createElement("small");
    company.textContent = draft.company || new URL(draft.url).hostname;
    const actions = document.createElement("div");
    actions.className = "draft-actions";
    const open = document.createElement("button");
    open.textContent = "打开";
    open.addEventListener("click", () => void send({ type: "openDraft", id: draft.id }));
    const remove = document.createElement("button");
    remove.className = "secondary";
    remove.textContent = "删除";
    remove.addEventListener("click", async () => {
      await send({ type: "removeDraft", id: draft.id });
      await refreshDrafts();
    });
    actions.append(open, remove);
    row.append(title, company, actions);
    draftList.append(row);
  }
}

async function checkConnection() {
  const { online } = await send({ type: "checkApi" });
  connectionText.textContent = online ? "JobFlow API 在线" : "API 离线，草稿仍会保存在本机";
  connectionDot.classList.toggle("online", online);
}

captureButton.addEventListener("click", async () => {
  captureButton.disabled = true;
  statusText.textContent = "";
  try {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab?.id) throw new Error("无法读取当前页面");
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: () => {
        const firstText = (...selectors) => {
          for (const selector of selectors) {
            const value = document.querySelector(selector)?.textContent?.trim();
            if (value) return value;
          }
          return "";
        };
        const host = location.hostname;
        const selected = window.getSelection()?.toString().trim() ?? "";
        const adapters = host.includes("linkedin.com")
          ? { title: [".job-details-jobs-unified-top-card__job-title", "h1"], company: [".job-details-jobs-unified-top-card__company-name"], jd: [".jobs-description__content"] }
          : host.includes("zhipin.com")
            ? { title: [".job-banner .name", "h1"], company: [".company-info .name"], jd: [".job-sec-text"] }
            : host.includes("liepin.com")
              ? { title: [".job-apply-content .name", "h1"], company: [".company-card h3"], jd: [".job-intro-container"] }
              : { title: ["h1", "title"], company: ["[itemprop='hiringOrganization']", ".company-name"], jd: ["[itemprop='description']", "main"] };
        const description = document.querySelector('meta[name="description"]')?.content ?? "";
        const visibleText = document.body?.innerText ?? "";
        return {
          company: firstText(...adapters.company).slice(0, 160),
          title: firstText(...adapters.title).slice(0, 200) || document.title.slice(0, 200),
          url: location.href,
          jd: (selected || firstText(...adapters.jd) || description || visibleText).slice(0, 4000),
          source: host.replace(/^www\./, ""),
        };
      },
    });
    if (!result?.result) throw new Error("页面内容为空");
    companyInput.value = result.result.company;
    titleInput.value = result.result.title;
    urlInput.value = result.result.url;
    jdInput.value = result.result.jd;
    previewForm.hidden = false;
    captureButton.hidden = true;
  } catch (error) {
    statusText.textContent = error instanceof Error ? error.message : "采集失败，请复制后手动录入";
    captureButton.disabled = false;
  }
});

document.querySelector("#cancel").addEventListener("click", () => {
  previewForm.hidden = true;
  captureButton.hidden = false;
  captureButton.disabled = false;
});

previewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusText.textContent = "";
  const draft = {
    company: companyInput.value.trim(),
    title: titleInput.value.trim(),
    url: urlInput.value.trim(),
    jd: jdInput.value.trim(),
  };
  try {
    const { id } = await send({ type: "queueDraft", draft });
    await refreshDrafts();
    await send({ type: "openDraft", id });
    window.close();
  } catch (error) {
    statusText.textContent = error instanceof Error ? error.message : "保存草稿失败";
  }
});

await Promise.all([checkConnection(), refreshDrafts()]);
