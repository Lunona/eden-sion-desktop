class VoiceGate extends AudioWorkletProcessor {
  constructor() {
    super();
    this.preroll = new Int16Array(Math.round(sampleRate * 0.38));
    this.offset = 0;
    this.filled = 0;
    this.frames = null;
    this.voiced = 0;
    this.quiet = 0;
    this.playing = false;
    this.paused = false;
    this.inputEpoch = 0;
    this.discardUntilQuiet = false;
    this.silentSamples = 0;
    this.inputSilent = false;
    this.port.onmessage = ({data}) => {
      this.playing = data.playing;
      if (data.inputEpoch !== this.inputEpoch) {
        // The tail of a cancelled utterance should not become a new command.
        const quiet = this.quiet;
        this.discardUntilQuiet ||= Boolean(this.frames || this.voiced);
        this.reset();
        if (this.discardUntilQuiet) this.quiet = quiet;
        this.inputEpoch = data.inputEpoch;
      }
      if (data.paused && !this.paused) this.reset();
      this.paused = data.paused;
    };
  }

  reset() {
    this.frames = null;
    this.offset = 0;
    this.filled = 0;
    this.voiced = 0;
    this.quiet = 0;
  }

  process(inputs, outputs) {
    const input = inputs[0]?.[0];
    if (this.paused) return true;
    const count = input?.length || outputs?.[0]?.[0]?.length || 0;
    if (!count) return true;
    let energy = 0;
    if (input) for (const value of input) energy += value * value;
    const meanSquare = energy / count;
    const silenceLimit = sampleRate * 2.5;
    this.silentSamples = meanSquare <= 1e-10 ? Math.min(silenceLimit, this.silentSamples + count) : 0;
    const inputSilent = this.silentSamples >= silenceLimit;
    if (inputSilent !== this.inputSilent) {
      this.inputSilent = inputSilent;
      this.port.postMessage({type: 'input-signal', available: !inputSilent});
    }
    if (!input?.length) return true;
    const loud = Math.sqrt(meanSquare) >= (this.playing ? 0.033 : 0.013);
    const quietLimit = sampleRate * 0.78;
    if (this.discardUntilQuiet) {
      this.quiet = loud ? 0 : this.quiet + count;
      if (this.quiet >= quietLimit) {
        this.discardUntilQuiet = false;
        this.reset();
      }
      return true;
    }

    if (!this.frames) {
      for (const value of input) {
        this.preroll[this.offset] = Math.max(-32768, Math.min(32767, value * 32768));
        this.offset = (this.offset + 1) % this.preroll.length;
      }
      this.filled = Math.min(this.preroll.length, this.filled + count);
      this.voiced = loud ? this.voiced + count : Math.max(0, this.voiced - count * 2);
      if (this.voiced < sampleRate * (this.playing ? 0.29 : 0.13)) return true;

      this.frames = new Int16Array(sampleRate * 18);
      this.length = this.filled;
      const start = (this.offset - this.filled + this.preroll.length) % this.preroll.length;
      for (let i = 0; i < this.filled; i++) this.frames[i] = this.preroll[(start + i) % this.preroll.length];
      this.duringPlayback = this.playing;
      this.port.postMessage({type: 'start', inputEpoch: this.inputEpoch});
      return true;
    }

    this.duringPlayback ||= this.playing;
    this.quiet = loud ? 0 : this.quiet + count;
    const remaining = Math.min(count, this.frames.length - this.length);
    for (let i = 0; i < remaining; i++) {
      this.frames[this.length++] = Math.max(-32768, Math.min(32767, input[i] * 32768));
    }
    if (this.quiet >= quietLimit || this.length === this.frames.length) {
      const audio = this.frames.slice(0, this.length);
      this.port.postMessage({type: 'utterance', audio, sampleRate, inputEpoch: this.inputEpoch,
        duringPlayback: this.duringPlayback}, [audio.buffer]);
      this.reset();
      this.paused = true;
    }
    return true;
  }
}

registerProcessor('sion-voice-gate', VoiceGate);
