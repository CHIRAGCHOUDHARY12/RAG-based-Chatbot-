(function () {
  "use strict";

  const shell = document.getElementById("shell");
  const chatScroll = document.getElementById("chat-scroll");
  const emptyState = document.getElementById("empty-state");
  const messagesEl = document.getElementById("messages");
  const composer = document.getElementById("composer");
  const composerInput = document.getElementById("composer-input");
  const sendBtn = document.getElementById("send-btn");
  const conversationList = document.getElementById("conversation-list");
  const newChatBtn = document.getElementById("new-chat-btn");
  const collapseBtn = document.getElementById("collapse-sidebar");
  const expandBtn = document.getElementById("expand-sidebar");
  const suggestedPrompts = document.getElementById("suggested-prompts");

  let activeConversationId = null;
  let isStreaming = false;

  const ICON_COPY = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 15V6a2 2 0 0 1 2-2h9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  const ICON_CHECK = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const ICON_PAGE = '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path d="M7 3h7l5 5v13H7z M14 3v5h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';

  const mobileQuery = window.matchMedia("(max-width: 820px)");
  const isMobile = () => mobileQuery.matches;

  function openDrawer() { shell.classList.add("sidebar-open"); }
  function closeDrawer() { shell.classList.remove("sidebar-open"); }

  // The "show sidebar" button is always available on small screens (it opens the
  // drawer) and on desktop only while the sidebar is collapsed.
  function syncSidebarControls() {
    expandBtn.hidden = !(isMobile() || shell.classList.contains("sidebar-collapsed"));
    if (!isMobile()) closeDrawer();
  }

  // ---------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function scrollToBottom() {
    chatScroll.scrollTop = chatScroll.scrollHeight;
  }

  function setEmptyStateVisible(visible) {
    emptyState.style.display = visible ? "block" : "none";
  }

  async function apiFetch(url, options) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("Not authenticated");
    }
    return res;
  }

  // ---------------------------------------------------------------
  // Conversation list
  // ---------------------------------------------------------------

  function renderConversationList(conversations) {
    conversationList.innerHTML = "";
    if (!conversations.length) {
      const p = document.createElement("p");
      p.className = "conversation-list__empty";
      p.textContent = "No conversations yet.";
      conversationList.appendChild(p);
      return;
    }
    for (const c of conversations) {
      conversationList.appendChild(buildConversationItem(c));
    }
    highlightActiveConversation();
  }

  function buildConversationItem(c) {
    const item = document.createElement("div");
    item.className = "conversation-item";
    item.dataset.id = c.id;

    const openBtn = document.createElement("button");
    openBtn.className = "conversation-item__open";
    openBtn.dataset.id = c.id;
    openBtn.textContent = c.title;
    openBtn.addEventListener("click", () => openConversation(c.id));

    const actions = document.createElement("div");
    actions.className = "conversation-item__actions";

    const renameBtn = document.createElement("button");
    renameBtn.className = "icon-btn icon-btn--tiny";
    renameBtn.setAttribute("aria-label", "Rename conversation");
    renameBtn.title = "Rename";
    renameBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M4 20h4L19 9l-4-4L4 16v4Z" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>';
    renameBtn.addEventListener("click", (e) => { e.stopPropagation(); openRenameModal(c.id, c.title); });

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "icon-btn icon-btn--tiny";
    deleteBtn.setAttribute("aria-label", "Delete conversation");
    deleteBtn.title = "Delete";
    deleteBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M5 7h14M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m2 0-1 13a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1L6 7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
    deleteBtn.addEventListener("click", (e) => { e.stopPropagation(); openDeleteModal(c.id); });

    actions.appendChild(renameBtn);
    actions.appendChild(deleteBtn);
    item.appendChild(openBtn);
    item.appendChild(actions);
    return item;
  }

  function highlightActiveConversation() {
    document.querySelectorAll(".conversation-item").forEach((el) => {
      el.classList.toggle("is-active", Number(el.dataset.id) === activeConversationId);
    });
  }

  async function refreshConversationList() {
    const res = await apiFetch("/api/conversations");
    const data = await res.json();
    renderConversationList(data.conversations || []);
  }

  // The server renders existing conversations on the first page load, but
  // those HTML buttons do not have JavaScript listeners yet. Re-render the
  // list from the API during startup so every open/rename/delete button uses
  // the same handlers as newly created conversations.
  async function initializeConversationList() {
    try {
      await refreshConversationList();
    } catch (err) {
      console.error("Could not initialize conversation list", err);
    }
  }

  async function createConversation() {
    const res = await apiFetch("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "New conversation" }),
    });
    const conversation = await res.json();
    await refreshConversationList();
    await openConversation(conversation.id);
  }

  async function openConversation(id) {
    activeConversationId = id;
    if (isMobile()) closeDrawer();
    highlightActiveConversation();
    messagesEl.innerHTML = "";
    setEmptyStateVisible(false);

    const res = await apiFetch(`/api/conversations/${id}/messages`);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.messages.length) {
      setEmptyStateVisible(true);
    } else {
      for (const m of data.messages) {
        renderMessage(m.role, m.content, m.sources);
      }
      scrollToBottom();
    }
    composerInput.focus();
  }

  // ---------------------------------------------------------------
  // Rename / delete modals
  // ---------------------------------------------------------------

  const renameModal = document.getElementById("rename-modal");
  const renameInput = document.getElementById("rename-input");
  let renameTargetId = null;

  function openRenameModal(id, currentTitle) {
    renameTargetId = id;
    renameInput.value = currentTitle;
    renameModal.hidden = false;
    renameInput.focus();
    renameInput.select();
  }
  document.getElementById("rename-cancel").addEventListener("click", () => { renameModal.hidden = true; });
  renameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); document.getElementById("rename-confirm").click(); }
  });
  document.getElementById("rename-confirm").addEventListener("click", async () => {
    const title = renameInput.value.trim();
    if (!title || renameTargetId == null) { renameModal.hidden = true; return; }
    await apiFetch(`/api/conversations/${renameTargetId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    renameModal.hidden = true;
    await refreshConversationList();
  });

  const deleteModal = document.getElementById("delete-modal");
  let deleteTargetId = null;

  function openDeleteModal(id) {
    deleteTargetId = id;
    deleteModal.hidden = false;
    document.getElementById("delete-cancel").focus();
  }
  document.getElementById("delete-cancel").addEventListener("click", () => { deleteModal.hidden = true; });
  document.getElementById("delete-confirm").addEventListener("click", async () => {
    if (deleteTargetId == null) { deleteModal.hidden = true; return; }
    await apiFetch(`/api/conversations/${deleteTargetId}`, { method: "DELETE" });
    const wasActive = deleteTargetId === activeConversationId;
    deleteModal.hidden = true;
    await refreshConversationList();
    if (wasActive) {
      activeConversationId = null;
      messagesEl.innerHTML = "";
      setEmptyStateVisible(true);
    }
  });

  // ---------------------------------------------------------------
  // Message rendering
  // ---------------------------------------------------------------

  function renderMessage(role, content, sources) {
    const wrapper = document.createElement("div");
    wrapper.className = `msg msg-${role}`;

    const bubble = document.createElement("div");
    bubble.className = "msg__bubble";
    if (role === "assistant") {
      renderAssistantMarkdown(bubble, content);
    } else {
      bubble.textContent = content;
    }
    wrapper.appendChild(bubble);

    if (role === "assistant" && sources && sources.length) {
      wrapper.appendChild(buildSourcesBlock(sources));
    }
    if (role === "assistant" && content) {
      wrapper.appendChild(buildMessageTools(bubble));
    }

    messagesEl.appendChild(wrapper);
    return wrapper;
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    // Fallback for non-secure origins (e.g. opened over a LAN address)
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    if (!ok) throw new Error("Copy failed");
  }

  function buildMessageTools(bubble) {
    const tools = document.createElement("div");
    tools.className = "msg__tools";

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "msg__tool";
    copyBtn.innerHTML = ICON_COPY + "<span>Copy</span>";

    let resetTimer = null;
    copyBtn.addEventListener("click", async () => {
      const label = copyBtn.querySelector("span");
      try {
        await copyText(bubble.innerText.trim());
        copyBtn.classList.add("is-done");
        copyBtn.innerHTML = ICON_CHECK + "<span>Copied</span>";
      } catch (err) {
        copyBtn.innerHTML = ICON_COPY + "<span>Couldn't copy</span>";
      }
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        copyBtn.classList.remove("is-done");
        copyBtn.innerHTML = ICON_COPY + "<span>Copy</span>";
      }, 1800);
    });

    tools.appendChild(copyBtn);
    return tools;
  }

  function appendInlineMarkdown(parent, text) {
    // Escape first; then replace only a deliberately small, safe subset of
    // Markdown. No model-generated HTML is ever inserted into the page.
    const safe = escapeHtml(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_]+)__/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/_([^_]+)_/g, '<em>$1</em>');
    const template = document.createElement("template");
    template.innerHTML = safe;
    parent.appendChild(template.content.cloneNode(true));
  }

  function splitMarkdownTableRow(line) {
    let value = line.trim();
    if (!value.startsWith("|") || !value.includes("|", 1)) return null;
    if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);
    value = value.slice(1);
    const cells = [];
    let cell = "";
    for (let i = 0; i < value.length; i += 1) {
      const ch = value[i];
      if (ch === "\\" && value[i + 1] === "|") {
        cell += "|";
        i += 1;
      } else if (ch === "|") {
        cells.push(cell.trim());
        cell = "";
      } else {
        cell += ch;
      }
    }
    cells.push(cell.trim());
    return cells;
  }

  function isMarkdownSeparatorRow(cells) {
    return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")));
  }

  function renderTable(parent, rows) {
    if (rows.length < 2 || !isMarkdownSeparatorRow(rows[1])) return false;
    const width = rows[0].length;
    if (width < 2 || rows.some((row) => row.length !== width)) return false;

    const wrap = document.createElement("div");
    wrap.className = "markdown-table-wrap";
    const table = document.createElement("table");
    table.className = "markdown-table";

    const thead = document.createElement("thead");
    const header = document.createElement("tr");
    rows[0].forEach((cell) => {
      const th = document.createElement("th");
      appendInlineMarkdown(th, cell);
      header.appendChild(th);
    });
    thead.appendChild(header);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    rows.slice(2).forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        appendInlineMarkdown(td, cell || "—");
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    parent.appendChild(wrap);
    return true;
  }

  function renderAssistantMarkdown(parent, content) {
    const lines = String(content || "").replace(/\r/g, "").split("\n");
    let i = 0;
    let paragraph = [];

    function flushParagraph() {
      if (!paragraph.length) return;
      const p = document.createElement("p");
      appendInlineMarkdown(p, paragraph.join(" ").trim());
      parent.appendChild(p);
      paragraph = [];
    }

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        flushParagraph();
        i += 1;
        continue;
      }

      // Markdown table: collect the contiguous pipe rows and validate before
      // rendering. Invalid model output stays plain text instead of breaking
      // the page layout.
      if (trimmed.startsWith("|") && i + 1 < lines.length) {
        const candidate = [];
        let j = i;
        while (j < lines.length) {
          const row = splitMarkdownTableRow(lines[j]);
          if (!row) break;
          candidate.push(row);
          j += 1;
        }
        if (candidate.length >= 2 && isMarkdownSeparatorRow(candidate[1]) && candidate.every((row) => row.length === candidate[0].length)) {
          flushParagraph();
          renderTable(parent, candidate);
          i = j;
          continue;
        }
      }

      const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        const h = document.createElement(`h${heading[1].length + 2}`);
        appendInlineMarkdown(h, heading[2]);
        parent.appendChild(h);
        i += 1;
        continue;
      }

      const bullet = trimmed.match(/^[-*•]\s+(.+)$/);
      const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (bullet || numbered) {
        flushParagraph();
        const list = document.createElement(numbered ? "ol" : "ul");
        let j = i;
        while (j < lines.length) {
          const current = lines[j].trim();
          const match = numbered ? current.match(/^\d+[.)]\s+(.+)$/) : current.match(/^[-*•]\s+(.+)$/);
          if (!match) break;
          const li = document.createElement("li");
          appendInlineMarkdown(li, match[1]);
          list.appendChild(li);
          j += 1;
        }
        parent.appendChild(list);
        i = j;
        continue;
      }

      paragraph.push(trimmed);
      i += 1;
    }
    flushParagraph();
  }

  function buildSourcesBlock(sources) {
    const block = document.createElement("div");
    block.className = "sources";

    const label = document.createElement("div");
    label.className = "sources__label";
    label.textContent = sources.length === 1 ? "1 source" : `${sources.length} sources`;
    block.appendChild(label);

    const list = document.createElement("div");
    list.className = "source-list";
    block.appendChild(list);

    sources.forEach((s, i) => {
      const tab = document.createElement("button");
      tab.className = "source-tab";
      tab.type = "button";
      const pageLabel = s.page_start === s.page_end ? `Page ${s.page_start}` : `Pages ${s.page_start}-${s.page_end}`;
      tab.setAttribute("aria-expanded", "false");
      tab.innerHTML = ICON_PAGE;
      const tabLabel = document.createElement("span");
      tabLabel.textContent = pageLabel;
      tab.appendChild(tabLabel);

      const detail = document.createElement("div");
      detail.className = "source-detail";
      const pageEl = document.createElement("span");
      pageEl.className = "source-detail__page";
      pageEl.textContent = s.section_title ? `${pageLabel} — ${s.section_title}` : pageLabel;
      detail.appendChild(pageEl);
      const excerptEl = document.createElement("span");
      excerptEl.textContent = s.excerpt;
      detail.appendChild(excerptEl);

      tab.addEventListener("click", () => {
        const open = detail.classList.toggle("is-open");
        tab.setAttribute("aria-expanded", String(open));
      });

      list.appendChild(tab);
      block.appendChild(detail);
    });

    return block;
  }

  function renderErrorBanner(message) {
    const banner = document.createElement("div");
    banner.className = "error-banner";
    banner.textContent = message;
    messagesEl.appendChild(banner);
    scrollToBottom();
  }

  // ---------------------------------------------------------------
  // Composer
  // ---------------------------------------------------------------

  function autoGrow() {
    composerInput.style.height = "auto";
    composerInput.style.height = Math.min(composerInput.scrollHeight, 160) + "px";
  }
  composerInput.addEventListener("input", () => {
    autoGrow();
    sendBtn.disabled = !composerInput.value.trim() || isStreaming;
  });
  composerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composer.requestSubmit();
    }
  });

  if (suggestedPrompts) {
    suggestedPrompts.querySelectorAll(".suggestion-chip").forEach((chip) => {
      chip.addEventListener("click", async () => {
        composerInput.value = chip.textContent;
        await ensureConversationAndSend();
      });
    });
  }

  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    await ensureConversationAndSend();
  });

  async function ensureConversationAndSend() {
    const question = composerInput.value.trim();
    if (!question || isStreaming) return;

    if (!activeConversationId) {
      const res = await apiFetch("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ title: "New conversation" }),
      });
      const conversation = await res.json();
      activeConversationId = conversation.id;
      await refreshConversationList();
    }
    await sendMessage(question);
  }

  async function sendMessage(question) {
    setEmptyStateVisible(false);
    composerInput.value = "";
    autoGrow();
    isStreaming = true;
    sendBtn.disabled = true;

    renderMessage("user", question, null);
    scrollToBottom();

    const thinkingWrapper = document.createElement("div");
    thinkingWrapper.className = "msg msg-assistant is-streaming";
    const thinkingBubble = document.createElement("div");
    thinkingBubble.className = "msg__bubble";
    thinkingBubble.innerHTML = '<span class="thinking"><span></span><span></span><span></span></span>';
    thinkingWrapper.appendChild(thinkingBubble);
    messagesEl.appendChild(thinkingWrapper);
    scrollToBottom();

    let accumulated = "";
    let firstFragmentReceived = false;
    let errored = false;

    try {
      const res = await fetch("/api/chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: activeConversationId, question }),
      });
      if (res.status === 401) { window.location.href = "/login"; return; }
      if (!res.ok || !res.body) throw new Error("Request failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop(); // keep any partial event for next chunk

        for (const evt of events) {
          const line = evt.trim();
          if (!line.startsWith("data:")) continue;
          const payload = JSON.parse(line.slice(5).trim());

          if (payload.error) {
            errored = true;
            thinkingWrapper.remove();
            renderErrorBanner(payload.error);
            break;
          }
          if (payload.delta) {
            if (!firstFragmentReceived) {
              firstFragmentReceived = true;
              thinkingBubble.innerHTML = "";
            }
            accumulated += payload.delta;
            thinkingBubble.textContent = accumulated;
            scrollToBottom();
          }
          if (payload.done) {
            thinkingWrapper.classList.remove("is-streaming");
          }
        }
        if (errored) break;
      }
    } catch (err) {
      if (!errored) {
        thinkingWrapper.remove();
        renderErrorBanner("Something went wrong talking to the server. Please try again.");
      }
    } finally {
      isStreaming = false;
      sendBtn.disabled = !composerInput.value.trim();
      if (!errored && accumulated) {
        // Re-fetch the persisted message so citations render from the
        // server's canonical data rather than being reconstructed client-side.
        await refreshLastAssistantMessage();
      }
      await refreshConversationList();
    }
  }

  async function refreshLastAssistantMessage() {
    if (!activeConversationId) return;
    const res = await apiFetch(`/api/conversations/${activeConversationId}/messages`);
    if (!res.ok) return;
    const data = await res.json();
    const last = data.messages[data.messages.length - 1];
    if (!last || last.role !== "assistant") return;

    const streamingEl = messagesEl.querySelector(".msg-assistant.is-streaming, .msg-assistant:last-child");
    if (streamingEl) streamingEl.remove();
    renderMessage("assistant", last.content, last.sources);
    scrollToBottom();
  }

  // ---------------------------------------------------------------
  // Sidebar collapse (desktop) / drawer (mobile)
  // ---------------------------------------------------------------

  collapseBtn.addEventListener("click", () => {
    if (isMobile()) {
      closeDrawer();
    } else {
      shell.classList.add("sidebar-collapsed");
    }
    syncSidebarControls();
  });
  expandBtn.addEventListener("click", () => {
    if (isMobile()) {
      openDrawer();
    } else {
      shell.classList.remove("sidebar-collapsed");
    }
    syncSidebarControls();
  });

  // Clicking the dimmed area beside the mobile drawer closes it.
  shell.addEventListener("click", (e) => {
    if (e.target === shell && shell.classList.contains("sidebar-open")) closeDrawer();
  });

  // Clicking a modal's backdrop closes it.
  [renameModal, deleteModal].forEach((modal) => {
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.hidden = true; });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!renameModal.hidden) renameModal.hidden = true;
    else if (!deleteModal.hidden) deleteModal.hidden = true;
    else if (shell.classList.contains("sidebar-open")) closeDrawer();
  });

  if (mobileQuery.addEventListener) mobileQuery.addEventListener("change", syncSidebarControls);

  newChatBtn.addEventListener("click", createConversation);

  // ---------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------

  setEmptyStateVisible(messagesEl.children.length === 0);
  syncSidebarControls();
  initializeConversationList();
})();
