// Bounded PCM playback for one focused client. Construct/resume on a user gesture.
class PCMPlayer {
  constructor() {
    const Audio = window.AudioContext || window.webkitAudioContext;
    this.context = new Audio();
    this.nextTime = 0;
  }

  async resume() {
    await this.context.resume();
  }

  push(data, rate) {
    const context = this.context;
    if (context.state !== "running" || this.nextTime > context.currentTime + 0.25) return;
    const values = new DataView(data);
    const buffer = context.createBuffer(1, values.byteLength / 2, rate);
    const output = buffer.getChannelData(0);
    for (let index = 0; index < output.length; index++)
      output[index] = values.getInt16(index * 2, true) / 32768;
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    this.nextTime = Math.max(context.currentTime + 0.04, this.nextTime);
    source.start(this.nextTime);
    this.nextTime += buffer.duration;
  }

  close() {
    this.context.close().catch(() => {});
  }
}
