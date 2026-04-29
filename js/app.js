const REST_URL = "/api";
// On Vercel, we might need to connect to a different WebSocket server.
// For now, we use the same host but warn if it's likely to fail.
const WS_URL = window.location.hostname.includes("vercel.app") 
    ? `wss://your-java-server.onrender.com` // Placeholder for user to update
    : `ws://${window.location.hostname}:5001`;

if (window.location.hostname.includes("vercel.app")) {
    console.warn("WebSocket connections to port 5001 usually fail on Vercel. Ensure your Java server is hosted elsewhere and update WS_URL in app.js.");
}

let socket = null;
let currentUsername = null;
let currentPassword = null; // Kept in memory to derive keys
let accessToken = null;
let refreshToken = null;

let mySeed = null;
let myIdentity = null;

let activeChatUser = null;
const sharedKeys = {}; // cache: username -> CryptoKey
let friendsList = [];
const unreadCounts = {};
let settingsOpen = false;
let notifEnabled = true;
let soundEnabled = true;
let editingMessageId = null;

// DOM Elements
const authContainer = document.getElementById("auth-container");
const chatContainer = document.getElementById("chat-container");
const authError = document.getElementById("auth-error");

function showError(msg, isSuccess = false) {
  if (isSuccess) showToast(msg);
  else {
    authError.textContent = msg;
    authError.classList.remove("hidden");
    authError.style.color = "red";
  }
}

function showToast(msg) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.innerHTML = `<span>${msg}</span>`;
  container.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// =========================================================
// AUTH
// =========================================================

document.getElementById("login-btn").addEventListener("click", async () => {
  const u = document.getElementById("username").value.trim();
  const p = document.getElementById("password").value.trim();
  if (!u || !p) return showError("Enter username and password");

  try {
    myIdentity = await derivePublicIdentity(u, p);
    const res = await fetch(`${REST_URL}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p, identity_hash: myIdentity })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);

    accessToken = data.access_token;
    refreshToken = data.refresh_token;
    currentUsername = String(data.username).trim();
    currentPassword = p;
    mySeed = await getPersistentKeyPair(currentUsername, currentPassword);

    localStorage.setItem("chat_access_token", accessToken);
    localStorage.setItem("chat_refresh_token", refreshToken);
    localStorage.setItem("chat_username", currentUsername);

    await fetchFriends();
    connectSocket();

    authContainer.classList.add("hidden");
    chatContainer.classList.remove("hidden");
    if (!activeChatUser) openChat({ username: currentUsername, is_online: true });
  } catch (e) { showError(e.message); }
});

document.getElementById("register-btn").addEventListener("click", async () => {
  const u = document.getElementById("username").value.trim();
  const p = document.getElementById("password").value.trim();
  if (!u || !p) return showError("Enter username and password");

  try {
    const identity = await derivePublicIdentity(u, p);
    const res = await fetch(`${REST_URL}/auth/register`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p, identity_hash: identity })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    showError("Registration successful. Please login.", true);
  } catch (e) { showError(e.message); }
});

// =========================================================
// FRIENDS & UI
// =========================================================

async function fetchFriends() {
  try {
    const res = await fetchWithAuth(`${REST_URL}/friends/list`);
    const data = await res.json();
    if (res.ok) {
      friendsList = data;
      renderFriends();
    }
  } catch (e) { console.error("Fetch friends failed", e); }
}

function renderFriends() {
  const list = document.getElementById("contact-list");
  if (!list) return;
  list.innerHTML = "";

  const q = (document.getElementById("contact-search-input")?.value || "").toLowerCase();

  // 1. Manually add "You" (Self-chat) at the top
  if (!q || currentUsername.toLowerCase().includes(q)) {
    const selfDiv = document.createElement("div");
    selfDiv.className = "contact-item";
    if (activeChatUser && activeChatUser.username === currentUsername) selfDiv.classList.add("active");
    
    const selfCount = unreadCounts[currentUsername] || 0;
    const selfBadge = selfCount > 0 ? `<span class="unread-badge">${selfCount}</span>` : "";
    
    selfDiv.innerHTML = `
      <div class="contact-avatar" style="background: var(--primary-green);">${currentUsername.charAt(0).toUpperCase()}</div>
      <div class="contact-info">
        <div class="contact-top"><span class="contact-name">${currentUsername} (You)</span></div>
        <div class="contact-bottom">
          <span class="contact-last-msg" id="last-msg-${currentUsername}">Message yourself</span>
          ${selfBadge}
        </div>
      </div>
    `;
    selfDiv.onclick = () => openChat({ username: currentUsername, is_online: true });
    list.appendChild(selfDiv);
  }

  // 2. Add friends
  friendsList.filter(f => f.username.toLowerCase().includes(q)).forEach(f => {
    const div = document.createElement("div");
    div.className = "contact-item";
    div.id = `contact-row-${f.username}`;
    if (activeChatUser && activeChatUser.username === f.username) div.classList.add("active");
    
    const count = unreadCounts[f.username] || 0;
    const badgeHtml = count > 0 ? `<span class="unread-badge">${count}</span>` : "";
    const timeHtml = count > 0 ? `<span class="contact-time" style="color:var(--primary-green);">${count} new</span>` : `<span class="contact-time"></span>`;
    
    div.innerHTML = `
      <div class="contact-avatar">${f.username.charAt(0).toUpperCase()}</div>
      <div class="contact-info">
        <div class="contact-top"><span class="contact-name">${f.username}</span>${timeHtml}</div>
        <div class="contact-bottom">
          <span class="contact-last-msg" id="last-msg-${f.username}">No messages yet</span>
          ${badgeHtml}
        </div>
      </div>
    `;
    div.onclick = () => openChat(f);
    div.oncontextmenu = (e) => {
      e.preventDefault();
      showContactContextMenu(e, f);
    };
    list.appendChild(div);
  });
}

async function openChat(friend) {
  activeChatUser = friend;

  unreadCounts[friend.username] = 0;
  updateTotalUnreadBadge();

  document.getElementById("empty-chat").classList.add("hidden");
  document.getElementById("active-chat").classList.remove("hidden");
  document.getElementById("chat-with-name").textContent = friend.username;
  document.getElementById("active-chat-avatar").textContent = friend.username.charAt(0).toUpperCase();
  updatePresenceUI(friend.username, friend.is_online, friend.last_seen);
  document.getElementById("message-list").innerHTML = "";

  if (socket && socket.readyState === WebSocket.OPEN) {
    wsSend("fetch_history", { withUser: friend.username }, true)
      .then(async msgs => {
        if (msgs && msgs.length > 0) {
          for (const m of msgs) await appendMessage(m);
        }
        wsSend("mark_read", { sender: friend.username });
      })
      .catch(err => console.warn("[WS] fetch_history failed:", err));
  }

  renderFriends();
}

function updateTotalUnreadBadge() {
  const total = Object.values(unreadCounts).reduce((a, b) => a + b, 0);
  const badge = document.getElementById("total-unread-badge");
  if (!badge) return;
  if (total > 0) {
    badge.textContent = total > 99 ? "99+" : total;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }
}

function updatePresenceUI(username, isOnline, lastSeen) {
  if (!activeChatUser || activeChatUser.username !== username) return;
  const statusEl = document.getElementById("chat-with-status");
  if (!statusEl) return;
  if (isOnline) {
    statusEl.textContent = "online";
  } else if (lastSeen) {
    statusEl.textContent = `last seen ${new Date(lastSeen).toLocaleTimeString()}`;
  } else {
    statusEl.textContent = "";
  }
}

// =========================================================
// MESSAGING
// =========================================================

const messageInput = document.getElementById("message-input");
let typingTimeout = null;

messageInput.addEventListener("input", () => {
  if (activeChatUser) {
    wsSend("typing", { receiver: activeChatUser.username, is_typing: true });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
      wsSend("typing", { receiver: activeChatUser.username, is_typing: false });
    }, 2000);
  }
});

document.getElementById("send-btn").addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

async function sendMessage() {
  const msgText = messageInput.value.trim();
  if (!msgText || !activeChatUser) return;

  const key = await getSharedKey(activeChatUser.username);
  const { ciphertext, iv } = await encryptMessage(key, msgText);

  if (editingMessageId) {
    wsSend("edit_message", { message_id: editingMessageId, ciphertext, iv });
    const msgEl = document.getElementById(`msg-${editingMessageId}`);
    if (msgEl) {
      const span = msgEl.querySelector("span");
      if (span) span.textContent = msgText;
    }
    cancelEdit();
    return;
  }

  messageInput.value = "";
  // Optimistic UI
  await appendMessage({ sender: currentUsername, receiver: activeChatUser.username, ciphertext, iv, timestamp: Date.now(), status: "sent" }, msgText);
  // Send via WebSocket
  wsSend("send_message", { receiver: activeChatUser.username, ciphertext, iv });
  wsSend("typing", { receiver: activeChatUser.username, is_typing: false });
}

async function getSharedKey(targetUser) {
  if (sharedKeys[targetUser]) return sharedKeys[targetUser];
  
  let friend = friendsList.find(f => f.username === targetUser);
  if (targetUser === currentUsername) {
    friend = { identity_hash: myIdentity };
  }
  
  if (!friend || !friend.identity_hash) {
    await fetchFriends();
    friend = friendsList.find(f => f.username === targetUser);
  }
  
  if (!friend || !friend.identity_hash) throw new Error("Could not find identity for user: " + targetUser);
  
  const key = await getSharedChatKey(mySeed, friend.identity_hash);
  sharedKeys[targetUser] = key;
  return key;
}

async function appendMessage(data, preDecrypted = null) {
  const list = document.getElementById("message-list");
  if (!list) return;

  const isMe = String(data.sender).trim().toLowerCase() === String(currentUsername).trim().toLowerCase();
  const isFile = !!data.file_id;

  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${isMe ? "sent" : "received"}`;
  if (data._id) {
    msgDiv.id = `msg-${data._id}`;
    msgDiv.dataset.msgId = data._id;
    msgDiv.dataset.isMe = isMe;
  }

  if (data.deleted) {
    msgDiv.classList.add("deleted");
    const span = document.createElement("span");
    span.textContent = isMe ? "🚫 You deleted this message" : "🚫 This message was deleted";
    msgDiv.appendChild(span);
    msgDiv.appendChild(buildMeta(data, isMe));
    list.appendChild(msgDiv);
    list.scrollTop = list.scrollHeight;
    return;
  }

  if (data.starred) {
    msgDiv.classList.add("starred-msg-highlight");
  }

  if (isFile) {
    const fileUrl = `${REST_URL}/media/download/${data.file_id}`;
    const fileBubble = document.createElement("div");
    fileBubble.className = "file-bubble";
    if (data.file_type && data.file_type.startsWith("image/")) {
      const img = document.createElement("img");
      img.className = "image-preview";
      img.alt = data.file_name || "Image";
      img.onclick = () => window.open(fileUrl, "_blank");
      fetchWithAuth(fileUrl).then(r => r.blob()).then(blob => { img.src = URL.createObjectURL(blob); });
      fileBubble.appendChild(img);
    } else {
      const link = document.createElement("a");
      link.className = "file-attachment";
      link.onclick = (e) => { e.preventDefault(); fetchWithAuth(fileUrl).then(r => r.blob()).then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = data.file_name || 'download';
        a.click();
      }); };
      
      let iconClass = "ph-file";
      if (data.file_type?.includes("pdf")) iconClass = "ph-file-pdf";
      else if (data.file_type?.includes("zip") || data.file_type?.includes("archive")) iconClass = "ph-file-archive";
      else if (data.file_type?.includes("word") || data.file_name?.endsWith(".doc") || data.file_name?.endsWith(".docx")) iconClass = "ph-file-doc";
      
      link.innerHTML = `
        <i class="ph-bold ${iconClass}"></i>
        <div class="file-attachment-info">
          <div class="file-attachment-name">${data.file_name || "File"}</div>
          <div class="file-attachment-size">Tap to download</div>
        </div>
        <i class="ph ph-download-simple" style="font-size:18px;color:var(--primary-green);"></i>
      `;
      fileBubble.appendChild(link);
    }
    msgDiv.appendChild(fileBubble);
    msgDiv.appendChild(buildMeta(data, isMe));
    if (isMe) attachContextMenu(msgDiv, data._id);
    list.appendChild(msgDiv);
    list.scrollTop = list.scrollHeight;
    return;
  }

  // Text message decryption
  const content = document.createElement("span");
  if (preDecrypted) {
    content.textContent = preDecrypted;
  } else if (data.ciphertext && data.iv) {
    content.textContent = "...";
    const chatPartner = isMe ? data.receiver : data.sender;
    (async () => {
      try {
        const key = await getSharedKey(chatPartner);
        const text = await decryptMessage(key, data.ciphertext, data.iv);
        content.textContent = text;
        const el = document.getElementById(`last-msg-${chatPartner}`);
        if (el) el.textContent = text;
      } catch (e) { content.textContent = "[Decryption Failed]"; }
    })();
  } else {
    content.textContent = data.text || "[No content]";
  }

  msgDiv.appendChild(content);
  msgDiv.appendChild(buildMeta(data, isMe));
  if (isMe) attachContextMenu(msgDiv, data._id);
  list.appendChild(msgDiv);
  list.scrollTop = list.scrollHeight;

  const partner = isMe ? data.receiver : data.sender;
  const el = document.getElementById(`last-msg-${partner}`);
  if (el && content.textContent !== "...") el.textContent = content.textContent;
}

function buildMeta(data, isMe) {
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const time = new Date(data.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  let editedLabel = data.edited ? `<span class="edited-label">edited</span>` : "";
  let starIcon = data.starred ? `<i class="ph-fill ph-star" style="color:#8696a0; font-size:10px; margin-right:4px;"></i>` : "";
  let ticks = "";
  if (isMe) {
    const isRead = data.status === "read";
    const icon = data.status === "sent" ? "ph-check" : "ph-checks";
    const color = isRead ? "#53bdeb" : "var(--text-secondary)";
    ticks = `<i class="ph-bold ${icon}" style="color: ${color};"></i>`;
  }
  meta.innerHTML = `${starIcon}${editedLabel}<span>${time}</span>${ticks}`;
  return meta;
}

// =========================================================
// WEBSOCKET
// =========================================================

function connectSocket() {
  if (socket) socket.close();
  socket = new WebSocket(`${WS_URL}?token=${accessToken}`);

  socket.onopen = () => {
    console.log("[WS] Connected");
    // Re-fetch history for active chat after connect/reconnect
    if (activeChatUser) {
      document.getElementById("message-list").innerHTML = "";
      wsSend("fetch_history", { withUser: activeChatUser.username }, true)
        .then(async msgs => {
          if (msgs && msgs.length > 0) {
            for (const m of msgs) await appendMessage(m);
          }
          wsSend("mark_read", { sender: activeChatUser.username });
        })
        .catch(() => {});
    }
  };
  socket.onclose = () => {
    console.log("[WS] Disconnected. Reconnecting...");
    setTimeout(connectSocket, 3000);
  };

  socket.onmessage = async (event) => {
    const { type, payload, reqId } = JSON.parse(event.data);

    if (reqId && pendingRequests[reqId]) {
      pendingRequests[reqId](payload);
      delete pendingRequests[reqId];
      return;
    }

    switch (type) {
      case "receive_message":
        if (activeChatUser && activeChatUser.username === payload.sender) {
          await appendMessage(payload);
          wsSend("mark_read", { message_id: payload._id, sender: payload.sender });
        } else {
          unreadCounts[payload.sender] = (unreadCounts[payload.sender] || 0) + 1;
          updateTotalUnreadBadge();
          if (soundEnabled) playNotifSound();
          renderFriends();
        }
        break;

      case "message_edited":
        const editEl = document.getElementById(`msg-${payload.message_id}`);
        if (editEl) {
          const chatPartner = activeChatUser?.username;
          (async () => {
             try {
               const key = await getSharedKey(chatPartner);
               const text = await decryptMessage(key, payload.ciphertext, payload.iv);
               const span = editEl.querySelector("span");
               if (span) span.textContent = text;
             } catch(e) {}
          })();
          const meta = editEl.querySelector(".message-meta");
          if (meta && !meta.querySelector(".edited-label")) {
            meta.insertAdjacentHTML("afterbegin", `<span class="edited-label">edited</span>`);
          }
        }
        break;

      case "message_deleted":
        applyDeletedStyle(payload.message_id, false);
        break;

      case "status_update":
        if (activeChatUser && activeChatUser.username === payload.username) {
          activeChatUser.is_online = payload.is_online;
          activeChatUser.last_seen = payload.last_seen;
          updatePresenceUI(payload.username, payload.is_online, payload.last_seen);
        }
        const f = friendsList.find(u => u.username === payload.username);
        if (f) {
          f.is_online = payload.is_online;
          f.last_seen = payload.last_seen;
        }
        break;

      case "typing_event":
        if (activeChatUser && activeChatUser.username === payload.sender) {
          const statusEl = document.getElementById("chat-with-status");
          if (statusEl) {
            if (payload.is_typing) statusEl.textContent = "typing...";
            else updatePresenceUI(activeChatUser.username, activeChatUser.is_online, activeChatUser.last_seen);
          }
        }
        break;

      case "delivery_receipt":
        const msgEl = document.getElementById(`msg-${payload.message_id}`);
        if (msgEl) {
          const tick = msgEl.querySelector(".ph-check");
          if (tick) {
            tick.classList.remove("ph-check");
            tick.classList.add("ph-checks");
          }
        }
        break;

      case "read_receipt":
        const readMsgEl = document.getElementById(`msg-${payload.message_id}`);
        if (readMsgEl) {
          const ticks = readMsgEl.querySelector(".ph-checks");
          if (ticks) ticks.style.color = "#53bdeb";
        }
        break;

      // CALLING EVENTS
      case "incoming_call":
        handleIncomingCall(payload);
        break;
      case "call_response":
        onCallResponse(payload);
        break;
      case "webrtc_signal":
        onWebRtcSignal(payload);
        break;
      case "ice_candidate":
        onIceCandidate(payload);
        break;
      case "call_end":
        endCall();
        break;
      case "call_error":
        alert(payload.message);
        endCall();
        break;
    }
  };
}

const pendingRequests = {};
function wsSend(type, payload = {}, expectsResponse = false) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return Promise.reject("Socket not open");
  const reqId = expectsResponse ? Math.random().toString(36).substring(2, 9) : null;
  const msg = { type, payload, reqId };
  socket.send(JSON.stringify(msg));

  if (expectsResponse) {
    return new Promise((resolve) => {
      pendingRequests[reqId] = resolve;
    });
  }
  return Promise.resolve();
}

// =========================================================
// CONTEXT MENU
// =========================================================

const contextMenu = document.getElementById("msg-context-menu");
let contextTargetId = null;
let contextTargetText = null;

function attachContextMenu(msgDiv, msgId) {
  msgDiv.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    contextTargetId = msgId;
    const span = msgDiv.querySelector("span");
    contextTargetText = span ? span.textContent : "";
    const isTextMsg = !msgDiv.querySelector(".file-bubble");
    document.getElementById("ctx-edit").style.display = isTextMsg ? "flex" : "none";
    contextMenu.style.left = Math.min(e.clientX, window.innerWidth - 180) + "px";
    contextMenu.style.top = Math.min(e.clientY, window.innerHeight - 200) + "px";
    
    // Add star/unstar option
    let starBtn = document.getElementById("ctx-star");
    if (!starBtn) {
      starBtn = document.createElement("div");
      starBtn.id = "ctx-star";
      starBtn.className = "context-item";
      contextMenu.prepend(starBtn);
    }
    const isStarred = msgDiv.classList.contains("starred-msg-highlight");
    starBtn.innerHTML = isStarred ? `<i class="ph ph-star-half"></i> Unstar` : `<i class="ph ph-star"></i> Star`;
    starBtn.onclick = () => toggleStar(msgId, !isStarred);

    contextMenu.classList.remove("hidden");
  });
}

document.addEventListener("click", () => contextMenu.classList.add("hidden"));

document.getElementById("ctx-copy")?.addEventListener("click", () => {
  if (contextTargetText) navigator.clipboard.writeText(contextTargetText);
});

document.getElementById("ctx-edit")?.addEventListener("click", () => {
  if (!contextTargetId) return;
  editingMessageId = contextTargetId;
  const msgEl = document.getElementById(`msg-${contextTargetId}`);
  const text = msgEl?.querySelector("span")?.textContent || "";
  messageInput.value = text;
  messageInput.focus();
  document.getElementById("edit-indicator").classList.remove("hidden");
});

document.getElementById("cancel-edit-btn")?.addEventListener("click", cancelEdit);
function cancelEdit() {
  editingMessageId = null;
  messageInput.value = "";
  document.getElementById("edit-indicator").classList.add("hidden");
}

document.getElementById("ctx-delete")?.addEventListener("click", () => {
  document.getElementById("delete-modal").classList.remove("hidden");
});

document.getElementById("delete-for-everyone-btn")?.addEventListener("click", () => {
  if (!contextTargetId) return;
  wsSend("delete_message", { message_id: contextTargetId, delete_type: "for_everyone" });
  document.getElementById("delete-modal").classList.add("hidden");
});

document.getElementById("delete-for-me-btn")?.addEventListener("click", () => {
  if (!contextTargetId) return;
  wsSend("delete_message", { message_id: contextTargetId, delete_type: "for_me" });
  applyDeletedStyle(contextTargetId, true);
  document.getElementById("delete-modal").classList.add("hidden");
});

document.getElementById("delete-cancel-btn")?.addEventListener("click", () => {
  document.getElementById("delete-modal").classList.add("hidden");
});

async function toggleStar(msgId, starred) {
  try {
    const res = await fetchWithAuth(`${REST_URL}/messages/star`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: msgId, starred: starred })
    });
    if (res.ok) {
      showToast(starred ? "Message starred" : "Message unstarred");
      const el = document.getElementById(`msg-${msgId}`);
      if (el) {
        if (starred) el.classList.add("starred-msg-highlight");
        else el.classList.remove("starred-msg-highlight");
        
        // Update meta UI (star icon)
        const meta = el.querySelector(".message-meta");
        if (meta) {
          const starIcon = meta.querySelector(".ph-star");
          if (starred && !starIcon) {
            meta.insertAdjacentHTML("afterbegin", `<i class="ph-fill ph-star" style="color:#8696a0; font-size:10px; margin-right:4px;"></i>`);
          } else if (!starred && starIcon) {
            starIcon.remove();
          }
        }
      }
    }
  } catch (e) { showToast("Failed to update star"); }
}

const contactContextMenu = document.getElementById("contact-context-menu");
function showContactContextMenu(e, friend) {
  contactContextMenu.style.left = Math.min(e.clientX, window.innerWidth - 180) + "px";
  contactContextMenu.style.top = Math.min(e.clientY, window.innerHeight - 200) + "px";
  
  const archiveBtn = document.getElementById("ctx-archive");
  archiveBtn.innerHTML = friend.is_archived ? `<i class="ph ph-archive-box"></i> Unarchive` : `<i class="ph ph-archive"></i> Archive`;
  archiveBtn.onclick = () => toggleArchive(friend.id, !friend.is_archived);
  
  contactContextMenu.classList.remove("hidden");
}

async function toggleArchive(friendId, archive) {
  try {
    const res = await fetchWithAuth(`${REST_URL}/friends/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ friend_id: friendId, archive: archive })
    });
    if (res.ok) {
      showToast(archive ? "Chat archived" : "Chat restored");
      fetchFriends();
      if (archive && activeChatUser && activeChatUser.id === friendId) {
        document.getElementById("active-chat").classList.add("hidden");
        document.getElementById("empty-chat").classList.remove("hidden");
      }
    }
  } catch (e) { showToast("Failed to update archive"); }
}

document.addEventListener("click", () => contactContextMenu.classList.add("hidden"));

function applyDeletedStyle(msgId, isMe) {
  const el = document.getElementById(`msg-${msgId}`);
  if (!el) return;
  el.classList.add("deleted");
  const span = el.querySelector("span");
  if (span) span.textContent = isMe ? "🚫 You deleted this message" : "🚫 This message was deleted";
}

// =========================================================
// FILE UPLOAD
// =========================================================

document.getElementById("attach-btn")?.addEventListener("click", () => {
  document.getElementById("file-input").click();
});

document.getElementById("file-input")?.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file || !activeChatUser) return;
  e.target.value = "";
  
  const list = document.getElementById("message-list");
  const progressDiv = document.createElement("div");
  progressDiv.className = "message sent";
  progressDiv.innerHTML = `<div class="upload-progress"><div class="spinner"></div> Uploading ${file.name}...</div>`;
  list.appendChild(progressDiv);
  list.scrollTop = list.scrollHeight;

  try {
    const formData = new FormData();
    formData.append("file", file);
    
    const res = await fetchWithAuth(`${REST_URL}/media/upload`, { method: "POST", body: formData });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || "Upload failed");
    
    progressDiv.remove();
    
    const filePayload = {
      receiver: activeChatUser.username,
      file_id: result.file_id,
      file_name: result.file_name || file.name,
      file_type: result.file_type || file.type
    };
    wsSend("send_message", filePayload);
    
    await appendMessage({
      sender: currentUsername,
      receiver: activeChatUser.username,
      file_id: result.file_id,
      file_name: result.file_name || file.name,
      file_type: result.file_type || file.type,
      timestamp: Date.now(),
      status: "sent",
      deleted: false,
      edited: false
    });
  } catch (err) {
    progressDiv.remove();
    console.error("[Upload] Error:", err);
    alert("Upload failed: " + err.message);
  }
});

// =========================================================
// SEARCH & ADD FRIENDS
// =========================================================

const addFriendModal = document.getElementById("add-friend-modal");
const globalSearchInput = document.getElementById("global-search-input");
const globalSearchResults = document.getElementById("global-search-results");

document.querySelector(".ph-note-pencil")?.addEventListener("click", () => {
  addFriendModal.classList.remove("hidden");
  globalSearchInput.value = "";
  globalSearchResults.innerHTML = "";
  globalSearchInput.focus();
});

document.querySelectorAll(".close-modal").forEach(btn => {
  btn.onclick = () => {
    addFriendModal.classList.add("hidden");
    document.getElementById("fingerprint-modal").classList.add("hidden");
  };
});

globalSearchInput?.addEventListener("input", async () => {
  const q = globalSearchInput.value.trim();
  if (q.length < 2) {
    globalSearchResults.innerHTML = "";
    return;
  }

  try {
    const res = await fetchWithAuth(`${REST_URL}/friends/search?q=${q}`);
    const users = await res.json();
    globalSearchResults.innerHTML = "";

    users.forEach(u => {
      if (u.username === currentUsername) return;

      const div = document.createElement("div");
      div.className = "contact-item";
      div.style.padding = "10px";
      
      let btnText = "Add";
      let btnDisabled = false;
      if (u.status === "friend") { btnText = "Friend"; btnDisabled = true; }
      else if (u.status === "request_sent") { btnText = "Pending"; btnDisabled = true; }
      else if (u.status === "request_received") { btnText = "Respond"; }

      div.innerHTML = `
        <div class="contact-avatar">${u.username.charAt(0).toUpperCase()}</div>
        <div class="contact-info">
          <div class="contact-name">${u.username}</div>
          <div class="contact-bottom" style="font-size:12px;">${u.status_message || ""}</div>
        </div>
        <button class="auth-btn" style="width: 80px; padding: 6px; font-size: 12px; height: auto;" ${btnDisabled ? "disabled" : ""}>${btnText}</button>
      `;

      div.querySelector("button").onclick = async () => {
        if (u.status === "request_received") {
          addFriendModal.classList.add("hidden");
          loadPendingRequests();
          return;
        }
        try {
          const addRes = await fetchWithAuth(`${REST_URL}/friends/request`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: u.username })
          });
          if (addRes.ok) {
            showToast(`Request sent to ${u.username}`);
            globalSearchInput.value = "";
            globalSearchResults.innerHTML = "";
          }
        } catch (e) { showToast("Failed to send request"); }
      };
      globalSearchResults.appendChild(div);
    });
  } catch (e) { console.error("Global search failed", e); }
});

async function loadPendingRequests() {
  const list = document.getElementById("pending-requests-list");
  const section = document.getElementById("pending-requests-section");
  if (!list) return;
  
  try {
    const res = await fetchWithAuth(`${REST_URL}/friends/requests/received`);
    const data = await res.json();
    if (data.length > 0) {
      section.classList.remove("hidden");
      list.innerHTML = "";
      data.forEach(req => {
        const div = document.createElement("div");
        div.className = "contact-item";
        div.style.padding = "10px 0";
        div.innerHTML = `
          <div class="contact-info">
            <div class="contact-name">${req.sender_username}</div>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="auth-btn" style="padding:4px 8px; font-size:12px;" onclick="respondToRequest('${req.request_id}', 'accept')">Accept</button>
            <button class="auth-btn" style="padding:4px 8px; font-size:12px; background:#54656f;" onclick="respondToRequest('${req.request_id}', 'reject')">Reject</button>
          </div>
        `;
        list.appendChild(div);
      });
    } else {
      section.classList.add("hidden");
    }
  } catch (e) { console.error(e); }
}

async function respondToRequest(reqId, action) {
  try {
    const res = await fetchWithAuth(`${REST_URL}/friends/requests/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: reqId, action: action })
    });
    if (res.ok) {
      showToast(action === 'accept' ? "Friend added!" : "Request rejected");
      loadPendingRequests();
      fetchFriends();
    }
  } catch (e) { showToast("Connection error"); }
}
window.respondToRequest = respondToRequest;

document.getElementById("add-friend-btn")?.addEventListener("click", () => {
  addFriendModal.classList.remove("hidden");
  loadPendingRequests();
});

// =========================================================
// API HELPERS
// =========================================================

async function fetchWithAuth(url, options = {}) {
  options.headers = options.headers || {};
  options.headers["Authorization"] = `Bearer ${accessToken}`;
  let res = await fetch(url, options);
  if (res.status === 401) {
    const refreshed = await refreshTokenFunc();
    if (refreshed) {
      options.headers["Authorization"] = `Bearer ${accessToken}`;
      res = await fetch(url, options);
    } else {
      doLogout();
    }
  }
  return res;
}

async function refreshTokenFunc() {
  try {
    const res = await fetch(`${REST_URL}/auth/refresh`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    const data = await res.json();
    if (res.ok) {
      accessToken = data.access_token;
      refreshToken = data.refresh_token;
      localStorage.setItem("chat_access_token", accessToken);
      localStorage.setItem("chat_refresh_token", refreshToken);
      return true;
    }
  } catch (e) {}
  return false;
}

// =========================================================
// NOTIFICATION SOUND
// =========================================================

function playNotifSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.05);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
  } catch(e) {}
}

const columns = ["chats-column", "settings-column", "status-column", "calls-column", "starred-column", "archived-column"];

function showColumn(id) {
  columns.forEach(c => {
    const el = document.getElementById(c);
    if (el) {
      if (c === id) el.classList.remove("hidden");
      else el.classList.add("hidden");
    }
  });
  
  // Highlight active nav item
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.remove("active");
  });
  
  const navMap = {
    "chats-column": "nav-chats",
    "status-column": "nav-status",
    "calls-column": "nav-calls",
    "starred-column": "nav-starred",
    "archived-column": "nav-archived"
  };
  
  const navId = navMap[id];
  if (navId) document.getElementById(navId)?.classList.add("active");
}

document.getElementById("nav-chats")?.addEventListener("click", () => showColumn("chats-column"));
document.getElementById("nav-status")?.addEventListener("click", () => { showColumn("status-column"); loadStatuses(); });
document.getElementById("nav-calls")?.addEventListener("click", () => { showColumn("calls-column"); loadCallHistory(); });
document.getElementById("nav-starred")?.addEventListener("click", () => { showColumn("starred-column"); loadStarredMessages(); });
document.getElementById("nav-archived")?.addEventListener("click", () => { showColumn("archived-column"); loadArchivedChats(); });
document.getElementById("settings-btn")?.addEventListener("click", () => {
  showColumn("settings-column");
  const usernameEl = document.getElementById("settings-username-display");
  const avatarEl = document.getElementById("settings-avatar");
  if (usernameEl && currentUsername) usernameEl.textContent = currentUsername;
  if (avatarEl && currentUsername) avatarEl.textContent = currentUsername.charAt(0).toUpperCase();
});

document.querySelectorAll(".nav-back-btn").forEach(btn => {
  btn.onclick = () => showColumn("chats-column");
});
document.getElementById("settings-back-btn")?.addEventListener("click", () => showColumn("chats-column"));

document.getElementById("upload-status-btn")?.addEventListener("click", async () => {
  const content = prompt("Enter your status update:");
  if (!content) return;
  
  try {
    const res = await fetchWithAuth("/api/status/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content, type: "text" })
    });
    if (res.ok) {
      showToast("Status updated!");
      loadStatuses();
    }
  } catch (e) { showToast("Failed to upload status"); }
});

document.getElementById("setting-dark-mode")?.addEventListener("change", (e) => {
  document.body.classList.toggle("dark-mode", e.target.checked);
  localStorage.setItem("setting_dark_mode", e.target.checked);
});

function loadSavedSettings() {
  const dark = localStorage.getItem("setting_dark_mode") === "true";
  document.body.classList.toggle("dark-mode", dark);
  const darkEl = document.getElementById("setting-dark-mode");
  if (darkEl) darkEl.checked = dark;
}

// =========================================================
// FEATURE LOADERS
// =========================================================

async function loadStatuses() {
  const list = document.getElementById("status-list");
  if (!list) return;
  list.innerHTML = `<div class="loading-spinner"></div>`;
  
  try {
    const res = await fetch("/api/status/list", {
      headers: { "Authorization": `Bearer ${accessToken}` }
    });
    const data = await res.json();
    if (data.length === 0) {
      list.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-secondary);">No updates yet</div>`;
      return;
    }
    list.innerHTML = "";
    data.forEach(item => {
      const div = document.createElement("div");
      div.className = "contact-item";
      div.innerHTML = `
        <div class="contact-avatar" style="border: 2px solid var(--primary-green);">${item.username.charAt(0).toUpperCase()}</div>
        <div class="contact-info">
          <div class="contact-name">${item.username}</div>
          <div class="contact-last-msg">${item.statuses.length} status updates</div>
        </div>
      `;
      list.appendChild(div);
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:20px; text-align:center; color:red;">Error loading status</div>`;
  }
}

async function loadCallHistory() {
  const list = document.getElementById("call-history-list");
  if (!list) return;
  list.innerHTML = `<div class="loading-spinner"></div>`;
  
  try {
    const res = await fetch("/api/calls/history", {
      headers: { "Authorization": `Bearer ${accessToken}` }
    });
    const data = await res.json();
    if (data.length === 0) {
      list.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-secondary);">No recent calls</div>`;
      return;
    }
    list.innerHTML = "";
    data.forEach(call => {
      const div = document.createElement("div");
      div.className = "contact-item";
      const icon = call.direction === 'incoming' ? 'ph-arrow-down-left' : 'ph-arrow-up-right';
      const color = call.direction === 'incoming' ? '#ea0038' : '#00a884';
      div.innerHTML = `
        <div class="contact-avatar">${call.with_username.charAt(0).toUpperCase()}</div>
        <div class="contact-info">
          <div class="contact-name">${call.with_username}</div>
          <div class="contact-last-msg" style="display:flex;align-items:center;gap:4px;">
            <i class="ph ${icon}" style="color:${color};"></i>
            ${new Date(call.timestamp).toLocaleString()}
          </div>
        </div>
        <i class="ph ph-phone" style="color:var(--primary-green);font-size:20px;"></i>
      `;
      list.appendChild(div);
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:20px; text-align:center; color:red;">Error loading calls</div>`;
  }
}

async function loadStarredMessages() {
  const list = document.getElementById("starred-messages-list");
  if (!list) return;
  list.innerHTML = `<div class="loading-spinner"></div>`;
  
  try {
    const res = await fetch("/api/messages/starred", {
      headers: { "Authorization": `Bearer ${accessToken}` }
    });
    const data = await res.json();
    if (data.length === 0) {
      list.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-secondary);">No starred messages</div>`;
      return;
    }
    list.innerHTML = "";
    data.forEach(msg => {
      const div = document.createElement("div");
      div.className = "contact-item";
      div.innerHTML = `
        <div class="contact-info">
          <div class="contact-name">${msg.sender}</div>
          <div class="contact-last-msg">${msg.text || 'Media message'}</div>
        </div>
      `;
      list.appendChild(div);
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:20px; text-align:center; color:red;">Error loading starred</div>`;
  }
}

async function loadArchivedChats() {
  const list = document.getElementById("archived-list");
  if (!list) return;
  list.innerHTML = `<div class="loading-spinner"></div>`;
  
  try {
    const res = await fetch("/api/friends/list?archived=true", {
      headers: { "Authorization": `Bearer ${accessToken}` }
    });
    const data = await res.json();
    if (data.length === 0) {
      list.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-secondary);">No archived chats</div>`;
      return;
    }
    list.innerHTML = "";
    data.forEach(friend => {
      const div = document.createElement("div");
      div.className = "contact-item";
      div.innerHTML = `
        <div class="contact-avatar">${friend.username.charAt(0).toUpperCase()}</div>
        <div class="contact-info">
          <div class="contact-name">${friend.username}</div>
          <div class="contact-last-msg">Archived</div>
        </div>
      `;
      div.onclick = () => { showColumn("chats-column"); selectContact(friend); };
      list.appendChild(div);
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:20px; text-align:center; color:red;">Error loading archived</div>`;
  }
}

// Add context menu listeners for starring and archiving
document.getElementById("ctx-reply")?.addEventListener("click", () => showToast("Reply coming soon"));

document.getElementById("nav-archived")?.addEventListener("click", () => {
  showToast("Archiving enabled");
});

document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", () => {
    if (item.id !== "nav-chats") {
      document.getElementById("empty-chat").classList.remove("hidden");
      document.getElementById("active-chat").classList.add("hidden");
    }
  });
});

// =========================================================
// LOGOUT
// =========================================================

function doLogout() {
  if (socket) socket.close();
  localStorage.removeItem("chat_access_token");
  localStorage.removeItem("chat_refresh_token");
  localStorage.removeItem("chat_username");
  location.reload();
}

document.getElementById("logout-btn").addEventListener("click", doLogout);
document.getElementById("logout-settings-btn")?.addEventListener("click", doLogout);

// =========================================================
// AUTO-LOGIN
// =========================================================

window.onload = async () => {
  accessToken = localStorage.getItem("chat_access_token");
  refreshToken = localStorage.getItem("chat_refresh_token");
  const storedUser = localStorage.getItem("chat_username");
  currentUsername = storedUser && storedUser !== "null" ? String(storedUser).trim() : null;

  loadSavedSettings();

  if (accessToken && currentUsername) {
    document.getElementById("username").value = currentUsername;
    document.getElementById("password").focus();
  }
};
