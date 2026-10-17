// AudioWorklet runs microphone capture off the page's rendering thread.
class ClientPCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(Math.round(sampleRate / 50));
    this.offset = 0;
    this.waiting = false;
    this.port.onmessage = () => {
      this.waiting = false;
    };
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const sample of input) {
      this.buffer[this.offset++] = Math.round(Math.max(-1, Math.min(1, sample)) * 32767);
      if (this.offset === this.buffer.length) {
        // One outstanding message bounds main-thread backlog on slow devices.
        if (!this.waiting) {
          this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
          this.waiting = true;
          this.buffer = new Int16Array(Math.round(sampleRate / 50));
        }
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("client-pcm", ClientPCMProcessor);
