// Server microphone PCM is independent of CV so model inference cannot queue audio.
const serverAudio = (() => {
  let socket = null,
    context = null,
    nextTime = 0,
    generation = null;
  let available = false,
    allowed = false,
    token = 0;
  let monitor = null,
    startedAt = 0,
    receivedAt = 0,
    signalAt = 0;
  const element = (id) => document.getElementById(id);

  function stop(message = "Audio off. Press Listen to hear the server microphone.") {
    token++;
    const previous = socket;
    socket = null;
    if (previous) {
      previous.onclose = null;
      previous.close(1000, "Listener stopped");
    }
    if (context) context.close().catch(() => {});
    context = null;
    nextTime = 0;
    clearInterval(monitor);
    monitor = null;
    element("audioLevel").value = 0;
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
      element("audioDevice").replaceChildren();
      const automatic = document.createElement("option");
      automatic.value = "";
      automatic.textContent = data.default_label
        ? `Automatic — ${data.default_label}`
        : "Automatic (Windows microphone)";
      element("audioDevice").append(automatic);
      for (const device of data.devices) {
        const option = document.createElement("option");
        option.value = device.value;
        option.textContent = device.label;
        element("audioDevice").append(option);
      }
      if (!available)
        stop(
          "No server microphone available. Check Windows input devices and microphone permissions.",
        );
      element("listenAudio").disabled = !allowed || !available;
    } catch (error) {
      stop(error.message);
    }
  }

  function update(state, selectedSource) {
    allowed =
      selectedSource === "laptop" && state.config.source === "laptop" && state.phase === "running";
    if (socket && (!allowed || generation !== state.generation)) stop();
    generation = state.generation;
    element("listenAudio").disabled = !allowed || !available;
  }

  element("listenAudio").addEventListener("click", async () => {
    if (socket) {
      stop();
      return;
    }
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
      const connection = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/audio${device ? `?device=${encodeURIComponent(device)}` : ""}`,
      );
      socket = connection;
      connection.binaryType = "arraybuffer";
      let rate = 16000;
      startedAt = signalAt = performance.now();
      receivedAt = 0;
      monitor = setInterval(() => {
        if (!context) return;
        if (context.state !== "running") {
          element("audioStatus").textContent =
            "Browser playback is paused. Mute, then Listen again; check this tab’s sound permission.";
        } else if (performance.now() - (receivedAt || startedAt) > 3000) {
          element("audioLevel").value = 0;
          element("audioStatus").textContent =
            "No audio frames received. Reconnect or check the server microphone connection.";
        }
      }, 500);
      element("listenAudio").textContent = "Mute";
      element("listenAudio").setAttribute("aria-pressed", "true");
      element("audioStatus").textContent = "Connecting to server microphone…";
      connection.onmessage = (event) => {
        if (current !== token || !context) return;
        if (typeof event.data === "string") {
          const info = JSON.parse(event.data);
          if (info.error) {
            stop(info.error);
            return;
          }
          rate = info.sample_rate;
          element("audioStatus").textContent =
            `Microphone connected${info.device_name ? `: ${info.device_name}` : ""}. Waiting for input…`;
          return;
        }
        // Discard delayed packets rather than building an ever-growing audio queue.
        if (context.state !== "running") {
          nextTime = 0;
          return;
        }
        if (nextTime > context.currentTime + 0.25) return;
        const samples = new DataView(event.data);
        const buffer = context.createBuffer(1, samples.byteLength / 2, rate);
        const output = buffer.getChannelData(0);
        let energy = 0;
        for (let i = 0; i < output.length; i++) {
          output[i] = samples.getInt16(i * 2, true) / 32768;
          energy += output[i] * output[i];
        }
        receivedAt = performance.now();
        const rms = Math.sqrt(energy / Math.max(1, output.length));
        element("audioLevel").value = Math.max(
          0,
          Math.min(100, ((20 * Math.log10(Math.max(rms, 1e-6)) + 72) / 72) * 100),
        );
        if (rms > 0.0001) signalAt = receivedAt;
        element("audioStatus").textContent =
          receivedAt - signalAt > 2000
            ? "Microphone is silent. Check the laptop’s mic-mute key, Windows input volume, and microphone access."
            : rms > 0.0001
              ? "Input signal received · playback running. Nothing is recorded."
              : "Receiving audio · waiting for sound…";
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
        if (current === token)
          stop("Audio connection failed. Check the server microphone and try again.");
      };
    } catch (error) {
      if (current === token) stop(error.message);
    }
  });
  element("audioDevice").addEventListener("change", () => stop());
  element("testSpeaker").addEventListener("click", async () => {
    const Audio = window.AudioContext || window.webkitAudioContext;
    let test = null;
    try {
      if (!Audio) throw new Error("Audio playback is unsupported in this browser.");
      test = new Audio();
      await test.resume();
      const tone = test.createOscillator(),
        gain = test.createGain();
      tone.frequency.value = 600;
      gain.gain.setValueAtTime(0, test.currentTime);
      gain.gain.linearRampToValueAtTime(0.08, test.currentTime + 0.02);
      gain.gain.linearRampToValueAtTime(0, test.currentTime + 0.35);
      tone.connect(gain).connect(test.destination);
      tone.onended = () => test.close();
      tone.start();
      tone.stop(test.currentTime + 0.4);
      if (!socket)
        element("audioStatus").textContent =
          "Playing a test tone. If inaudible, check the tab’s mute setting, system volume, and speaker output.";
    } catch (error) {
      if (test) test.close().catch(() => {});
      element("audioStatus").textContent = error.message;
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
  });
  return { stop, update, loadDevices };
})();
