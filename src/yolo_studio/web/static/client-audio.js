// Microphone sharing is separate from video so denial/muting never stops the camera.
const clientMicrophone = (() => {
  let stream = null,
    context = null,
    node = null,
    socket = null,
    token = 0;
  const status = (text) => {
    document.getElementById("clientAudioStatus").textContent = text;
  };

  function stop(message = "Microphone off.") {
    token++;
    if (socket) {
      socket.onclose = null;
      socket.close(1000, "Microphone stopped");
    }
    socket = null;
    if (node) {
      node.port.onmessage = null;
      node.disconnect();
    }
    node = null;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    if (context) context.close().catch(() => {});
    context = null;
    status(message);
  }

  async function start(generation) {
    stop();
    const current = token;
    status("Requesting microphone permission…");
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio || !navigator.mediaDevices?.getUserMedia)
        throw new Error("Microphone sharing requires HTTPS and a supported browser.");
      const audio = new Audio({ sampleRate: 16000 });
      context = audio;
      const resumed = audio.resume();
      resumed.catch(() => {}); // Stop can close the context while permission is pending.
      const microphone = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        video: false,
      });
      if (current !== token) {
        microphone.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = microphone;
      await Promise.race([
        resumed,
        new Promise((_, reject) =>
          setTimeout(
            () =>
              reject(
                new Error(
                  "Browser paused microphone processing. Toggle microphone sharing to retry.",
                ),
              ),
            3000,
          ),
        ),
      ]);
      await audio.audioWorklet.addModule("/static/client-audio-worklet.js");
      if (current !== token) return;
      node = new AudioWorkletNode(audio, "client-pcm");
      const mute = audio.createGain();
      mute.gain.value = 0;
      audio
        .createMediaStreamSource(microphone)
        .connect(node)
        .connect(mute)
        .connect(audio.destination);
      const connection = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/client-audio?generation=${generation}`,
      );
      socket = connection;
      connection.onopen = () => {
        if (current !== token) return;
        connection.send(JSON.stringify({ sample_rate: audio.sampleRate }));
        status("Microphone shared with the server operator. Uncheck Share microphone to mute.");
      };
      node.port.onmessage = (event) => {
        if (current !== token) return;
        node.port.postMessage("ready");
        if (connection.readyState === WebSocket.OPEN && connection.bufferedAmount < 64000)
          connection.send(event.data);
      };
      connection.onclose = () => {
        if (current === token)
          stop("Microphone sharing disconnected. Toggle sharing to reconnect.");
      };
      connection.onerror = () => {
        if (current === token)
          stop("Microphone connection failed. Video can continue; toggle sharing to retry.");
      };
    } catch (error) {
      if (current === token) stop(`Microphone unavailable: ${error.message}. Video continues.`);
    }
  }
  return { start, stop };
})();
