/* Electricity border for live sessions: lightning strands hugging the screen
   edges whose amplitude, glow, and branching follow the agent's output
   loudness. pointer-events: none — the app stays fully operable underneath. */
(() => {
  const GLOW = "#60a5fa";
  const CORE = "rgba(236, 245, 255, 1)";
  let canvas = null;
  let context = null;
  let raf = 0;
  let active = false;
  let target = 0;
  let level = 0;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function ensureCanvas() {
    if (canvas) return;
    canvas = document.createElement("canvas");
    canvas.className = "live-fx";
    canvas.setAttribute("aria-hidden", "true");
    document.body.append(canvas);
    context = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
  }

  function resize() {
    if (!canvas) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.round(innerWidth * ratio);
    canvas.height = Math.round(innerHeight * ratio);
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  // One jagged strand along an edge. (x0,y0)->(x1,y1) with inward jitter.
  function strand(x0, y0, x1, y1, inwardX, inwardY, amp, alpha) {
    const length = Math.hypot(x1 - x0, y1 - y0);
    const steps = Math.max(6, Math.round(length / 24));
    const points = [[x0, y0]];
    for (let index = 1; index < steps; index += 1) {
      const t = index / steps;
      // Quadratic bias keeps the strand hugging the border with rare flares.
      const jitter = Math.random() ** 2 * amp;
      points.push([
        x0 + (x1 - x0) * t + inwardX * jitter,
        y0 + (y1 - y0) * t + inwardY * jitter,
      ]);
    }
    points.push([x1, y1]);

    for (const pass of ["glow", "core"]) {
      context.beginPath();
      context.moveTo(points[0][0], points[0][1]);
      for (let index = 1; index < points.length; index += 1) {
        context.lineTo(points[index][0], points[index][1]);
      }
      if (pass === "glow") {
        context.strokeStyle = `rgba(96, 165, 250, ${alpha * 0.85})`;
        context.lineWidth = 3.2;
        context.shadowColor = GLOW;
        context.shadowBlur = 12 + level * 34;
      } else {
        context.strokeStyle = CORE;
        context.globalAlpha = alpha;
        context.lineWidth = 1.1;
        context.shadowBlur = 0;
      }
      context.stroke();
      context.globalAlpha = 1;
    }

    // Occasional inward branches — more of them the louder the agent is.
    for (let index = 1; index < points.length - 1; index += 1) {
      if (Math.random() > 0.03 + level * 0.12) continue;
      const [bx, by] = points[index];
      context.beginPath();
      context.moveTo(bx, by);
      const reach = amp * (0.8 + Math.random() * 0.8);
      context.lineTo(
        bx + inwardX * reach + (Math.random() - 0.5) * 10,
        by + inwardY * reach + (Math.random() - 0.5) * 10,
      );
      context.strokeStyle = `rgba(147, 197, 253, ${alpha * 0.7})`;
      context.lineWidth = 0.9;
      context.shadowColor = GLOW;
      context.shadowBlur = 8;
      context.stroke();
    }
  }

  function frame() {
    if (!active) return;
    level += (target - level) * (target > level ? 0.5 : 0.07);
    const w = innerWidth;
    const h = innerHeight;
    context.clearRect(0, 0, w, h);
    const alpha = Math.min(1, 0.1 + level * 0.9);

    if (reducedMotion.matches) {
      // A calm glow that only breathes with loudness — no crackle.
      context.strokeStyle = `rgba(96, 165, 250, ${alpha * 0.8})`;
      context.lineWidth = 2.5;
      context.shadowColor = GLOW;
      context.shadowBlur = 16 + level * 40;
      context.strokeRect(3, 3, w - 6, h - 6);
    } else {
      const amp = 2 + level * 16;
      for (const scale of [1, 0.45]) {
        strand(0, 2, w, 2, 0, 1, amp * scale, alpha);          // top, jitters down
        strand(0, h - 2, w, h - 2, 0, -1, amp * scale, alpha); // bottom, jitters up
        strand(2, 0, 2, h, 1, 0, amp * scale, alpha);          // left, jitters right
        strand(w - 2, 0, w - 2, h, -1, 0, amp * scale, alpha); // right, jitters left
      }
    }
    raf = requestAnimationFrame(frame);
  }

  window.LiveFx = {
    start() {
      ensureCanvas();
      active = true;
      canvas.style.opacity = "1";
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(frame);
    },
    stop() {
      active = false;
      target = 0;
      level = 0;
      cancelAnimationFrame(raf);
      if (canvas) {
        canvas.style.opacity = "0";
        window.setTimeout(() => {
          if (!active && context) context.clearRect(0, 0, innerWidth, innerHeight);
        }, 250);
      }
    },
    setLevel(value) {
      target = Math.max(0, Math.min(1, value));
    },
  };
})();
