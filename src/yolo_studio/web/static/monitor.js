const $ = (id) => document.getElementById(id);
const cards = new Map();
let currentClient = "",
  alive = true,
  requestGeneration = 0;
let audioSocket = null,
  player = null,
  audioToken = 0;

function stopAudio(message = "Audio muted. Tap Listen to hear the focused client.") {
  audioToken++;
  if (audioSocket) {
    audioSocket.onclose = null;
    audioSocket.close(1000, "Operator muted");
  }
  audioSocket = null;
  if (player) player.close();
  player = null;
  $("clientListen").textContent = "Listen to client";
  $("clientListen").setAttribute("aria-pressed", "false");
  $("clientAudioState").textContent = message;
}

function focusClient(identifier) {
  if (identifier !== currentClient) stopAudio();
  currentClient = identifier;
  $("client").value = identifier;
  $("feed").hidden = true;
  $("empty").hidden = false;
  const state = cards.get(identifier);
  if (state?.url) {
    $("feed").src = state.url;
    $("feed").hidden = false;
    $("empty").hidden = true;
  }
  for (const [id, card] of cards) card.element.classList.toggle("focused", id === identifier);
  updateFocused();
}

function updateFocused() {
  const state = cards.get(currentClient);
  $("status").textContent = state
    ? `${state.client.label} · ${state.client.metrics.resolution || "waiting for video"}`
    : "No client selected";
  $("clientListen").disabled = !state?.client.audio_shared;
  if (audioSocket && !state?.client.audio_shared)
    stopAudio("The client has muted microphone sharing.");
}

$("client").onchange = () => focusClient($("client").value);
$("kind").onchange = () => {
  requestGeneration++;
  for (const card of cards.values()) card.frameId = -1;
};
$("fullscreen").onclick = () => toggleViewerFullscreen($("viewer"));
$("clientListen").onclick = async () => {
  if (audioSocket) {
    stopAudio();
    return;
  }
  if (!currentClient) return;
  const token = ++audioToken;
  try {
    player = new PCMPlayer();
    await player.resume();
    if (token !== audioToken) return;
    const socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/operator/audio/${currentClient}`,
    );
    socket.binaryType = "arraybuffer";
    audioSocket = socket;
    let rate = 16000;
    $("clientListen").textContent = "Mute client audio";
    $("clientListen").setAttribute("aria-pressed", "true");
    $("clientAudioState").textContent = "Waiting for the client microphone…";
    socket.onmessage = (event) => {
      if (token !== audioToken || !player) return;
      if (typeof event.data === "string") {
        rate = JSON.parse(event.data).sample_rate;
        return;
      }
      player.push(event.data, rate);
      $("clientAudioState").textContent = "Playing the focused client’s microphone.";
    };
    socket.onclose = () => {
      if (token === audioToken) stopAudio("Client audio stopped or sharing was disabled.");
    };
    socket.onerror = () => {
      if (token === audioToken)
        stopAudio(
          "Client audio unavailable. Check microphone sharing and permission on that client.",
        );
    };
  } catch (error) {
    if (token === audioToken) stopAudio(error.message);
  }
};

async function pollCard(card) {
  while (alive && cards.get(card.client.id) === card) {
    const token = requestGeneration;
    try {
      const response = await fetch(
        `/api/operator/frame/${card.client.id}?kind=${$("kind").value}&after=${card.frameId}`,
      );
      if (response.status === 200) {
        const blob = await response.blob();
        if (token !== requestGeneration || cards.get(card.client.id) !== card) continue;
        const next = URL.createObjectURL(blob),
          previous = card.url;
        card.url = next;
        card.frameId = Number(response.headers.get("X-Frame-Id"));
        card.image.src = next;
        await card.image.decode().catch(() => {});
        if (currentClient === card.client.id) {
          $("feed").src = next;
          await $("feed")
            .decode()
            .catch(() => {});
          $("feed").hidden = false;
          $("empty").hidden = true;
        }
        if (previous) URL.revokeObjectURL(previous);
      } else if (response.status === 403 || response.status === 404) {
        card.image.removeAttribute("src");
        if (currentClient === card.client.id) {
          $("feed").hidden = true;
          $("empty").hidden = false;
        }
      }
    } catch {
      /* The session list reports disconnections. */
    }
    await new Promise((resolve) =>
      setTimeout(resolve, currentClient === card.client.id ? 50 : 150),
    );
  }
}

function addCard(client) {
  const element = document.createElement("article"),
    image = document.createElement("img"),
    button = document.createElement("button"),
    note = document.createElement("p");
  element.className = "client-card";
  element.dataset.clientId = client.id;
  image.alt = client.label;
  button.type = "button";
  button.textContent = `Focus ${client.label}`;
  button.onclick = () => focusClient(client.id);
  note.className = "hint";
  element.append(image, button, note);
  $("clientGrid").append(element);
  const card = { client, element, image, note, frameId: -1, url: null };
  cards.set(client.id, card);
  pollCard(card);
}

async function clients() {
  while (alive) {
    try {
      const response = await fetch("/api/operator/sessions");
      if (!response.ok)
        throw new Error("Open the monitor on the backend laptop at http://127.0.0.1:8765/monitor.");
      const data = await response.json(),
        ids = new Set(data.sessions.map((client) => client.id));
      $("error").hidden = true;
      for (const [id, card] of cards) {
        if (!ids.has(id)) {
          cards.delete(id);
          card.element.remove();
          if (card.url) URL.revokeObjectURL(card.url);
        }
      }
      for (const client of data.sessions) {
        if (!cards.has(client.id)) addCard(client);
        const card = cards.get(client.id);
        card.client = client;
        card.note.textContent = `${client.phase} · ${client.audio_shared ? (client.audio_ready ? "Microphone live" : "Waiting for microphone") : "Microphone muted"}`;
      }
      $("client").replaceChildren(
        ...(data.sessions.length
          ? data.sessions.map((client) => new Option(client.label, client.id))
          : [new Option("No sharing clients connected", "")]),
      );
      if (!ids.has(currentClient)) focusClient(data.sessions[0]?.id || "");
      $("client").value = currentClient;
      updateFocused();
    } catch (error) {
      $("error").textContent = error.message;
      $("error").hidden = false;
      stopAudio("Monitor connection interrupted.");
      $("feed").hidden = true;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
window.onpagehide = () => {
  alive = false;
  stopAudio();
  for (const card of cards.values()) if (card.url) URL.revokeObjectURL(card.url);
};
clients();
