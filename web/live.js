/* Live voice session: mic PCM up the WebSocket, agent PCM back out the
   speakers, transcription deltas to the chat, loudness to LiveFx. */
(() => {
  const INPUT_RATE = 16000;
  const OUTPUT_RATE = 24000;
  const WORKLET_URL = URL.createObjectURL(
    new Blob(
      [
        `registerProcessor("live-capture", class extends AudioWorkletProcessor {
          process(inputs) {
            const channel = inputs[0] && inputs[0][0];
            if (channel) this.port.postMessage(channel.slice(0));
            return true;
          }
        });`,
      ],
      { type: "application/javascript" },
    ),
  );

  let socket = null;
  let micStream = null;
  let micContext = null;
  let playContext = null;
  let analyser = null;
  let gain = null;
  let playTime = 0;
  let sources = [];
  let levelRaf = 0;
  let handlers = {};
  let pending = [];

  function toBase64(int16) {
    const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength);
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return btoa(binary);
  }

  function fromBase64(data) {
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return new Int16Array(bytes.buffer);
  }

  function downsample(float32, fromRate) {
    const ratio = fromRate / INPUT_RATE;
    const length = Math.floor(float32.length / ratio);
    const result = new Int16Array(length);
    for (let index = 0; index < length; index += 1) {
      const sample = float32[Math.floor(index * ratio)] || 0;
      result[index] = Math.max(-1, Math.min(1, sample)) * 0x7fff;
    }
    return result;
  }

  function playChunk(int16) {
    if (!playContext) return;
    const float32 = new Float32Array(int16.length);
    for (let index = 0; index < int16.length; index += 1) {
      float32[index] = int16[index] / 0x8000;
    }
    const buffer = playContext.createBuffer(1, float32.length, OUTPUT_RATE);
    buffer.copyToChannel(float32, 0);
    const source = playContext.createBufferSource();
    source.buffer = buffer;
    source.connect(gain);
    playTime = Math.max(playTime, playContext.currentTime + 0.04);
    source.start(playTime);
    playTime += buffer.duration;
    sources.push(source);
    source.onended = () => {
      sources = sources.filter((item) => item !== source);
    };
  }

  function stopPlayback() {
    for (const source of sources) {
      try { source.stop(); } catch { /* already ended */ }
    }
    sources = [];
    playTime = 0;
  }

  function watchLevel() {
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let index = 0; index < data.length; index += 1) {
        const centered = (data[index] - 128) / 128;
        sum += centered * centered;
      }
      window.LiveFx.setLevel(Math.min(1, Math.sqrt(sum / data.length) * 3.2));
      levelRaf = requestAnimationFrame(tick);
    };
    levelRaf = requestAnimationFrame(tick);
  }

  async function startMic() {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    micContext = new AudioContext();
    await micContext.audioWorklet.addModule(WORKLET_URL);
    const sourceNode = micContext.createMediaStreamSource(micStream);
    const capture = new AudioWorkletNode(micContext, "live-capture");
    sourceNode.connect(capture);
    capture.port.onmessage = (event) => {
      pending.push(event.data);
      const total = pending.reduce((count, chunk) => count + chunk.length, 0);
      if (total < micContext.sampleRate / 10) return; // ~100ms batches
      const merged = new Float32Array(total);
      let offset = 0;
      for (const chunk of pending) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }
      pending = [];
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          type: "audio",
          data: toBase64(downsample(merged, micContext.sampleRate)),
        }));
      }
    };
  }

  async function start(channelId, sessionHandlers) {
    handlers = sessionHandlers || {};
    playContext = new AudioContext();
    gain = playContext.createGain();
    analyser = playContext.createAnalyser();
    analyser.fftSize = 512;
    gain.connect(analyser);
    gain.connect(playContext.destination);

    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${location.host}/api/live/${encodeURIComponent(channelId)}`);
    socket.onmessage = (event) => {
      const frame = JSON.parse(event.data);
      if (frame.type === "audio") playChunk(fromBase64(frame.data));
      else if (frame.type === "user_text") handlers.onUserText?.(frame.text);
      else if (frame.type === "agent_text") handlers.onAgentText?.(frame.text);
      else if (frame.type === "interrupted") { stopPlayback(); handlers.onInterrupted?.(); }
      else if (frame.type === "turn_complete") handlers.onTurnComplete?.();
      else if (frame.type === "error") { handlers.onError?.(frame.message); stop(); }
    };
    socket.onclose = () => { if (window.LiveSession.active) stop(); };

    await new Promise((resolve, reject) => {
      socket.onopen = resolve;
      socket.onerror = () => reject(new Error("Could not reach the live session"));
    });
    await startMic();
    window.LiveFx.start();
    watchLevel();
    window.LiveSession.active = true;
    handlers.onState?.(true);
  }

  function stop() {
    window.LiveSession.active = false;
    cancelAnimationFrame(levelRaf);
    window.LiveFx.stop();
    stopPlayback();
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "end" }));
    }
    socket?.close();
    socket = null;
    micStream?.getTracks().forEach((track) => track.stop());
    micStream = null;
    micContext?.close();
    micContext = null;
    playContext?.close();
    playContext = null;
    pending = [];
    handlers.onState?.(false);
  }

  window.LiveSession = { active: false, start, stop };
})();
