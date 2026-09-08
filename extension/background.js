const STORAGE_KEY = "jobflow_capture_drafts";

async function getDrafts() {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  return Array.isArray(stored[STORAGE_KEY]) ? stored[STORAGE_KEY] : [];
}

async function saveDrafts(drafts) {
  await chrome.storage.local.set({ [STORAGE_KEY]: drafts.slice(0, 50) });
}

function draftUrl(draft) {
  const params = new URLSearchParams({
    capture: "1",
    company: draft.company || "",
    title: draft.title || "",
    url: draft.url || "",
    jd: draft.jd || "",
  });
  return `http://localhost:5173/?${params.toString()}`;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    if (message.type === "getDrafts") return { drafts: await getDrafts() };
    if (message.type === "queueDraft") {
      const drafts = await getDrafts();
      const id = crypto.randomUUID();
      drafts.unshift({ ...message.draft, id, createdAt: new Date().toISOString() });
      await saveDrafts(drafts);
      return { id };
    }
    if (message.type === "removeDraft") {
      await saveDrafts((await getDrafts()).filter((draft) => draft.id !== message.id));
      return { ok: true };
    }
    if (message.type === "openDraft") {
      const draft = (await getDrafts()).find((item) => item.id === message.id);
      if (!draft) throw new Error("草稿不存在");
      await chrome.tabs.create({ url: draftUrl(draft) });
      return { ok: true };
    }
    if (message.type === "checkApi") {
      try {
        const response = await fetch("http://localhost:8000/health", { signal: AbortSignal.timeout(1500) });
        return { online: response.ok };
      } catch {
        return { online: false };
      }
    }
    return { ok: false };
  })().then(sendResponse).catch((error) => sendResponse({ error: String(error) }));
  return true;
});
