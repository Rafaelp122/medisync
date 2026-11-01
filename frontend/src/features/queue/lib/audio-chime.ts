/**
 * Sintetizador Web Audio API nativo para toque de convocação médica (Ring Chime).
 * Emite sinal sonoro harmonioso de dois tons (523Hz C5 / 659Hz E5) em loop suave a cada 2.5s.
 * Atende aos requisitos de notificação audiovisual (RF-03, RN02 e WCAG 2.1 AA).
 * Precedente canônico: samu-emergency-modal.tsx.
 */
export function iniciarToqueChamadaMedica(): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }

  let isRunning = true;
  let intervalId: ReturnType<typeof setInterval> | null = null;
  let audioCtx: AudioContext | null = null;

  function tocarPulso() {
    if (!isRunning) return;

    try {
      const AudioCtxClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;

      if (!AudioCtxClass) return;

      if (!audioCtx || audioCtx.state === "closed") {
        audioCtx = new AudioCtxClass();
      }

      if (audioCtx.state === "suspended") {
        try {
          const res = audioCtx.resume();
          if (res && typeof res.catch === "function") {
            res.catch(() => {});
          }
        } catch {
          // ignora
        }
      }

      const now = audioCtx.currentTime;

      // Nota 1: Dó 5 (523.25 Hz)
      const osc1 = audioCtx.createOscillator();
      const gain1 = audioCtx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(523.25, now);
      gain1.gain.setValueAtTime(0.2, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(audioCtx.destination);
      osc1.start(now);
      osc1.stop(now + 0.35);

      // Nota 2: Mi 5 (659.25 Hz)
      const osc2 = audioCtx.createOscillator();
      const gain2 = audioCtx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(659.25, now + 0.2);
      gain2.gain.setValueAtTime(0.22, now + 0.2);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.65);
      osc2.connect(gain2);
      gain2.connect(audioCtx.destination);
      osc2.start(now + 0.2);
      osc2.stop(now + 0.65);
    } catch {
      // Silencioso em caso de restrição de autoplay ou ambiente sem suporte a áudio
    }
  }

  // Toca o primeiro pulso imediatamente
  tocarPulso();

  // Repete o chime a cada 2.5 segundos
  intervalId = setInterval(tocarPulso, 2500);

  return function pararToque() {
    isRunning = false;
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
    if (audioCtx) {
      try {
        const p = audioCtx.close();
        if (p && typeof p.catch === "function") {
          p.catch(() => {});
        }
      } catch {
        // ignora
      }
      audioCtx = null;
    }
  };
}
