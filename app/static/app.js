const roomList = document.getElementById("room-list");
const refreshRoomsButton = document.getElementById("refresh-rooms-button");
const createRoomButton = document.getElementById("create-room-button");
const newRoomNameInput = document.getElementById("new-room-name");
const newRoomPasswordInput = document.getElementById("new-room-password");
const nicknameInput = document.getElementById("nickname");
const roomPasswordInput = document.getElementById("room-password");
const disconnectButton = document.getElementById("disconnect-button");
const deleteRoomButton = document.getElementById("delete-room-button");
const sendButton = document.getElementById("send-button");
const messageInput = document.getElementById("message-input");
const messageList = document.getElementById("message-list");
const userList = document.getElementById("user-list");
const connectionStatus = document.getElementById("connection-status");
const roomTitle = document.getElementById("room-title");
const roomMeta = document.getElementById("room-meta");

let socket = null;
let currentRoomId = null;

function setStatus(online) {
  connectionStatus.textContent = online ? "온라인" : "오프라인";
  connectionStatus.className = `status-chip ${online ? "online" : "offline"}`;
}

function formatTimestamp(value) {
  if (!value) {
    return "";
  }

  const parsed = new Date(`${value}Z`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
}

function appendMessage(entry) {
  const card = document.createElement("article");
  card.className = `message-card ${entry.event_type}`;

  const metaLine = document.createElement("div");
  metaLine.className = "message-meta";

  if (entry.event_type === "system") {
    metaLine.textContent = `시스템 · ${formatTimestamp(entry.created_at)}`;
  } else {
    metaLine.textContent = `${entry.nickname} · ${formatTimestamp(entry.created_at)}`;
  }

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = entry.message;

  card.append(metaLine, body);
  messageList.appendChild(card);
  messageList.scrollTop = messageList.scrollHeight;
}

function renderMessages(entries) {
  messageList.innerHTML = "";

  if (!entries.length) {
    appendMessage({
      event_type: "system",
      message: "아직 메시지가 없습니다. 첫 메시지를 보내 보세요.",
      created_at: "",
    });
    return;
  }

  entries.forEach(appendMessage);
}

function renderUsers(users) {
  userList.innerHTML = "";

  if (!users.length) {
    const empty = document.createElement("li");
    empty.textContent = "현재 접속 중인 사용자가 없습니다.";
    userList.appendChild(empty);
    return;
  }

  users.forEach((user) => {
    const item = document.createElement("li");
    item.textContent = user;
    userList.appendChild(item);
  });
}

function updateRoomHeader(room, users) {
  const privacyLabel = room.is_private ? "비공개" : "공개";
  roomTitle.textContent = `${room.name} (#${room.id})`;
  roomMeta.textContent = `누적 메시지 ${room.message_count}개 · 현재 접속 ${users.length}명`;
  roomMeta.textContent += ` · ${privacyLabel} 방`;
}

function renderRooms(rooms) {
  roomList.innerHTML = "";

  if (!rooms.length) {
    const empty = document.createElement("div");
    empty.className = "room-card empty";
    empty.textContent = "아직 생성된 채팅방이 없습니다.";
    roomList.appendChild(empty);
    return;
  }

  rooms.forEach((room) => {
    const card = document.createElement("article");
    card.className = `room-card ${room.id === currentRoomId ? "active" : ""}`;

    const heading = document.createElement("div");
    heading.className = "room-card-title";
    heading.textContent = room.name;

    const meta = document.createElement("div");
    meta.className = "room-card-meta";
    meta.textContent = `메시지 ${room.message_count}개 · ${room.is_private ? "비공개" : "공개"}`;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "join-button";
    button.textContent = room.id === currentRoomId ? "입장 중" : "입장";
    button.addEventListener("click", () => joinRoom(room.id));

    card.append(heading, meta, button);
    roomList.appendChild(card);
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "요청 처리에 실패했습니다.");
  }

  return payload;
}

async function loadRooms() {
  try {
    const payload = await fetchJson("/api/rooms");
    renderRooms(payload.rooms);
  } catch (error) {
    renderMessages([
      {
        event_type: "system",
        message: error.message,
        created_at: "",
      },
    ]);
  }
}

async function createRoom() {
  const name = newRoomNameInput.value.trim();
  const password = newRoomPasswordInput.value.trim();
  if (!name) {
    renderMessages([
      {
        event_type: "system",
        message: "방 이름을 먼저 입력해 주세요.",
        created_at: "",
      },
    ]);
    return;
  }

  try {
    const payload = await fetchJson("/api/rooms", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name, password }),
    });

    newRoomNameInput.value = "";
    newRoomPasswordInput.value = "";
    await loadRooms();
    await joinRoom(payload.room.id);
  } catch (error) {
    renderMessages([
      {
        event_type: "system",
        message: error.message,
        created_at: "",
      },
    ]);
  }
}

function closeSocket() {
  if (socket) {
    socket.close();
    socket = null;
  }
}

async function joinRoom(roomId) {
  const nickname = nicknameInput.value.trim();
  const password = roomPasswordInput.value.trim();
  if (!nickname) {
    renderMessages([
      {
        event_type: "system",
        message: "입장 전에 닉네임을 입력해 주세요.",
        created_at: "",
      },
    ]);
    return;
  }

  closeSocket();
  currentRoomId = roomId;
  setStatus(false);

  try {
    const payload = await fetchJson(`/api/rooms/${roomId}/join`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ nickname, password }),
    });
    renderMessages(payload.messages);
    renderUsers(payload.users);
    updateRoomHeader(payload.room, payload.users);
    renderRooms((await fetchJson("/api/rooms")).rooms);
  } catch (error) {
    currentRoomId = null;
    renderMessages([
      {
        event_type: "system",
        message: error.message,
        created_at: "",
      },
    ]);
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(
    `${protocol}://${window.location.host}/ws/${roomId}?nickname=${encodeURIComponent(nickname)}&password=${encodeURIComponent(password)}`
  );

  socket.addEventListener("open", () => {
    setStatus(true);
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    appendMessage(payload);
    renderUsers(payload.users || []);

    if (payload.room) {
      updateRoomHeader(payload.room, payload.users || []);
      loadRooms();
    }
  });

  socket.addEventListener("close", () => {
    setStatus(false);
  });
}

async function deleteRoom() {
  if (!currentRoomId) {
    appendMessage({
      event_type: "system",
      message: "먼저 삭제할 방에 입장해 주세요.",
      created_at: "",
    });
    return;
  }

  const confirmed = window.confirm("현재 방을 삭제할까요? 저장된 메시지도 함께 삭제됩니다.");
  if (!confirmed) {
    return;
  }

  try {
    await fetchJson(`/api/rooms/${currentRoomId}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ password: roomPasswordInput.value.trim() }),
    });
    currentRoomId = null;
    roomPasswordInput.value = "";
    leaveRoom();
  } catch (error) {
    appendMessage({
      event_type: "system",
      message: error.message,
      created_at: "",
    });
  }
}

function leaveRoom() {
  closeSocket();
  currentRoomId = null;
  setStatus(false);
  roomTitle.textContent = "아직 입장한 방이 없습니다";
  roomMeta.textContent = "왼쪽에서 방을 선택한 뒤 입장해 주세요.";
  renderUsers([]);
  renderMessages([]);
  loadRooms();
}

function sendMessage() {
  const message = messageInput.value.trim();
  if (!message) {
    return;
  }

  if (!socket || socket.readyState !== WebSocket.OPEN) {
    appendMessage({
      event_type: "system",
      message: "먼저 채팅방에 입장해 주세요.",
      created_at: "",
    });
    return;
  }

  socket.send(message);
  messageInput.value = "";
  messageInput.focus();
}

refreshRoomsButton.addEventListener("click", loadRooms);
createRoomButton.addEventListener("click", createRoom);
disconnectButton.addEventListener("click", leaveRoom);
deleteRoomButton.addEventListener("click", deleteRoom);
sendButton.addEventListener("click", sendMessage);

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

newRoomNameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    createRoom();
  }
});

newRoomPasswordInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    createRoom();
  }
});

renderUsers([]);
renderMessages([]);
loadRooms();
