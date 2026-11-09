// The pet owns one microphone stream for the whole session.
(() => {
  const api = window.sion;
  let generation = 0;
  let inputEpoch = 0;
  let active = false;
  let stream, context, gate;
  let playing = false;
  let recognizing = false;
  let defaultInput = null;
  let deviceCheck = 0;

  function cleanup() {
    active = false;
    recognizing = false;
    defaultInput = null;
    gate?.disconnect();
    gate = null;
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    const previous = context;
    context = null;
    void previous?.close().catch(() => {});
  }

  function updateGate() {
    gate?.port.postMessage({playing, paused: recognizing, inputEpoch});
  }

  function fail(id) {
    if (id !== generation || !active) return;
    cleanup();
    void api.invoke('voice-phase', {generation: id, phase: 'failed'}).catch(() => {});
  }

  async function checkDefaultInput(id) {
    if (!active || !stream) return;
    const check = ++deviceCheck;
    let device;
    try {
      device = (await navigator.mediaDevices.enumerateDevices()).find(item => item.kind === 'audioinput');
    } catch {
      return;
    }
    if (!active || id !== generation || check !== deviceCheck || !device?.deviceId) return;
    // Chromium's virtual "default" id stays the same when the underlying device changes.
    if (device.deviceId === 'default' && !device.groupId && !device.label) return;
    const current = JSON.stringify([device.deviceId, device.groupId, device.label]);
    if (defaultInput && defaultInput !== current) {
      cleanup();
      void api.invoke('voice-phase', {generation: id, phase: 'device-changed'}).catch(() => {});
    } else {
      defaultInput = current;
    }
  }

  function wavBase64(samples, rate) {
    const bytes = new Uint8Array(44 + samples.byteLength);
    const view = new DataView(bytes.buffer);
    const tag = (at, text) => bytes.set(new TextEncoder().encode(text), at);
    tag(0, 'RIFF'); view.setUint32(4, bytes.length - 8, true); tag(8, 'WAVE');
    tag(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, rate, true);
    view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    tag(36, 'data'); view.setUint32(40, samples.byteLength, true);
    bytes.set(new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength), 44);
    let binary = '';
    for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
    return btoa(binary);
  }

  async function receiveClip(message, id) {
    if (id !== generation || !active) return;
    if (message.type === 'input-signal') {
      void api.invoke('voice-phase', {generation: id, phase: 'signal', available: message.available}).catch(() => {});
      return;
    }
    if (message.inputEpoch !== inputEpoch) return;
    if (message.type === 'start') {
      void api.invoke('voice-phase', {generation: id, inputEpoch, phase: 'speaking'}).catch(() => {});
      return;
    }
    if (message.type !== 'utterance') return;
    recognizing = true;
    try {
      await api.invoke('speech-transcribe', {
        generation: id, inputEpoch, mime: 'audio/wav', audio: wavBase64(message.audio, message.sampleRate),
        duringPlayback: message.duringPlayback
      });
    } catch {
      // Main owns the visible status and resumes the session after errors.
    } finally {
      if (id === generation && active) {
        recognizing = false;
        updateGate();
      }
    }
  }

  async function start(id) {
    cleanup();
    generation = id;
    inputEpoch = 0;
    active = true;
    try {
      const mic = await navigator.mediaDevices.getUserMedia({
        audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true},
        video: false
      });
      if (id !== generation || !active) {
        mic.getTracks().forEach(track => track.stop());
        return;
      }
      stream = mic;
      const tracks = mic.getAudioTracks();
      if (!tracks.length || tracks.some(track => track.readyState === 'ended')) {
        fail(id);
        return;
      }
      for (const track of tracks) track.addEventListener('ended', () => fail(id), {once: true});
      void checkDefaultInput(id);
      const listener = new AudioContext({sampleRate: 16000});
      context = listener;
      await listener.audioWorklet.addModule(new URL('voice-gate.js', location.href));
      if (id !== generation || !active) return;
      await listener.resume();
      if (id !== generation || !active) return;
      gate = new AudioWorkletNode(listener, 'sion-voice-gate', {numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1]});
      gate.port.onmessage = ({data}) => void receiveClip(data, id);
      gate.onprocessorerror = () => fail(id);
      listener.createMediaStreamSource(mic).connect(gate);
      // The processor leaves its output silent, so the microphone is never played back.
      gate.connect(listener.destination);
      updateGate();
      await api.invoke('voice-phase', {generation: id, phase: 'listening'});
    } catch {
      fail(id);
    }
  }

  api.subscribe(event => {
    if (event.type === 'voice-session') {
      if (event.enabled) void start(event.generation);
      else {
        generation = event.generation;
        cleanup();
      }
    }
    if (event.type === 'voice-discard' && active && event.generation === generation) {
      inputEpoch = event.inputEpoch;
      updateGate();
    }
    if (event.type === 'state' && playing !== event.state.voicePlaying) {
      playing = event.state.voicePlaying;
      updateGate();
    }
  });
  navigator.mediaDevices?.addEventListener('devicechange', () => void checkDefaultInput(generation));
  window.addEventListener('pagehide', cleanup);
})();
