// Server microphone PCM is independent of CV so model inference cannot queue audio.
const serverAudio = (() => {
  let socket = null, context = null, nextTime = 0, generation = null;
  let available = false, allowed = false, token = 0;
  const element = (id) => document.getElementById(id);

  function stop(message = "Audio off. Press Listen to hear the server microphone.") {
    token++;
    const previous = socket;
    socket = null;
    if (previous) { previous.onclose = null; previous.close(1000, "Listener stopped"); }
    if (context) context.close().catch(() => {});
    context = null;
    nextTime = 0;
    element("listenAudio").textContent = "Listen";
    element("listenAudio").setAttribute("aria-pressed", "false");
    element("audioStatus").textContent = message;
  }

  async function loadDevices() {
    try {
      const response = await fetch("/api/audio/devices");
      if (!response.ok) throw new Error("Unable to query server microphones.");
      const data = await response.json();
      available = data.available;
      for (const device of data.devices) {
        const option = document.createElement("option");
        option.value = device.value;
        option.textContent = device.label;
        element("audioDevice").append(option);
      }
      if (!available) stop("No server microphone available. Check Windows input devices and microphone permissions.");
      element("listenAudio").disabled = !allowed || !available;
    } catch (error) { stop(error.message); }
  }

  function update(state, selectedSource) {
    allowed = selectedSource === "laptop" && state.config.source === "laptop" && state.phase === "running";
    if (socket && (!allowed || generation !== state.generation)) stop();
    generation = state.generation;
    element("listenAudio").disabled = !allowed || !available;
  }

  element("listenAudio").addEventListener("click", async () => {
    if (socket) { stop(); return; }
    if (!allowed || !available) return;
    const current = ++token;
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error("Audio playback is unsupported in this browser.");
      context = new Audio();
      // Called within a tap/click to satisfy mobile autoplay restrictions.
      await context.resume();
      if (current !== token) return;
      const device = element("audioDevice").value;
      const connection = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/audio${device ? `?device=${encodeURIComponent(device)}` : ""}`);
      socket = connection;
      connection.binaryType = "arraybuffer";
      let rate = 16000;
      element("listenAudio").textContent = "Mute";
      element("listenAudio").setAttribute("aria-pressed", "true");
      element("audioStatus").textContent = "Connecting to server microphone…";
      connection.onmessage = (event) => {
        if (current !== token || !context) return;
        if (typeof event.data === "string") {
          const info = JSON.parse(event.data);
          if (info.error) { stop(info.error); return; }
          rate = info.sample_rate;
          element("audioStatus").textContent = "Listening to the server microphone. Nothing is recorded.";
          return;
        }
        // Discard delayed packets rather than building an ever-growing audio queue.
        if (context.state !== "running") { nextTime = 0; return; }
        if (nextTime > context.currentTime + 0.25) return;
        const samples = new DataView(event.data);
        const buffer = context.createBuffer(1, samples.byteLength / 2, rate);
        const output = buffer.getChannelData(0);
        for (let i = 0; i < output.length; i++) output[i] = samples.getInt16(i * 2, true) / 32768;
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        nextTime = Math.max(nextTime, context.currentTime + 0.04);
        source.start(nextTime);
        nextTime += buffer.duration;
      };
      connection.onclose = () => {
        if (current === token) stop("Audio disconnected. Press Listen to reconnect.");
      };
      connection.onerror = () => {
        if (current === token) stop("Audio connection failed. Check the server microphone and try again.");
      };
    } catch (error) { if (current === token) stop(error.message); }
  });
  element("audioDevice").addEventListener("change", () => stop());
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  return { stop, update, loadDevices };
})();
