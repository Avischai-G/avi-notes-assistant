/* Electricity border for live sessions.
   A calm glow breathes with the agent's loudness; discrete lightning bolts
   spawn at random spots along the edges — more often and brighter the louder
   the voice — hold their shape for a moment, flicker, and fade. The canvas is
   pointer-events: none, so the app stays fully operable underneath. */
(() => {
  const GLOW = "#60a5fa";
  let canvas = null;
  let context = null;
  let raf = 0;
  let active = false;
  let target = 0;
  let level = 0;
  let bolts = [];
  const MAX_BOLTS = 14;
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

  // Midpoint displacement along the edge normal: generated once per bolt, so
  // each flash holds a natural, stable shape while it lives.
  function jaggedLine(a, b, normal, amplitude) {
    let points = [a, b];
    let amp = amplitude;
    for (let depth = 0; depth < 5; depth += 1) {
      const next = [points[0]];
      for (let index = 0; index < points.length - 1; index += 1) {
        const p = points[index];
        const q = points[index + 1];
        const offset = (Math.random() - 0.5) * 2 * amp;
        next.push(
          [
            (p[0] + q[0]) / 2 + normal[0] * offset,
            (p[1] + q[1]) / 2 + normal[1] * offset,
          ],
          q,
        );
      }
      points = next;
      amp *= 0.55;
    }
    return points;
  }

  function clampInward(points, normal, inset, depth) {
    for (const point of points) {
      if (normal[0]) {
        const from = normal[0] > 0 ? inset : innerWidth - inset;
        point[0] = normal[0] > 0
          ? Math.min(Math.max(point[0], from), inset + depth)
          : Math.max(Math.min(point[0], from), innerWidth - inset - depth);
      } else {
        const from = normal[1] > 0 ? inset : innerHeight - inset;
        point[1] = normal[1] > 0
          ? Math.min(Math.max(point[1], from), inset + depth)
          : Math.max(Math.min(point[1], from), innerHeight - inset - depth);
      }
    }
    return points;
  }

  function spawnBolt(now, major) {
    const w = innerWidth;
    const h = innerHeight;
    const edges = [
      { from: [0, 3], to: [w, 3], normal: [0, 1], length: w },
      { from: [0, h - 3], to: [w, h - 3], normal: [0, -1], length: w },
      { from: [3, 0], to: [3, h], normal: [1, 0], length: h },
      { from: [w - 3, 0], to: [w - 3, h], normal: [-1, 0], length: h },
    ];
    const edge = edges[Math.floor(Math.random() * edges.length)];
    const span = major ? 0.9 : 0.12 + Math.random() * 0.35;
    const start = Math.random() * (1 - span);
    const point = (t) => [
      edge.from[0] + (edge.to[0] - edge.from[0]) * t,
      edge.from[1] + (edge.to[1] - edge.from[1]) * t,
    ];
    const amplitude = (major ? 14 : 8) + level * 22 + Math.random() * 6;
    const depthLimit = major ? 64 : 44;
    const points = clampInward(
      jaggedLine(point(start), point(start + span), edge.normal, amplitude),
      edge.normal,
      1,
      depthLimit,
    );

    const branches = [];
    const branchCount = Math.random() < 0.55 ? 1 + (major ? 1 : 0) : 0;
    for (let index = 0; index < branchCount; index += 1) {
      const origin = points[2 + Math.floor(Math.random() * (points.length - 4))];
      const reach = 14 + Math.random() * (major ? 46 : 26);
      const drift = (Math.random() - 0.5) * reach;
      const tip = [
        origin[0] + edge.normal[0] * reach + (edge.normal[0] ? 0 : drift),
        origin[1] + edge.normal[1] * reach + (edge.normal[1] ? 0 : drift),
      ];
      branches.push(jaggedLine(origin, tip, edge.normal, amplitude * 0.4));
    }

    bolts.push({
      points,
      branches,
      born: now,
      life: (major ? 260 : 110) + Math.random() * 240,
      peak: Math.min(1, (major ? 0.65 : 0.4) + level * 0.6),
      width: major ? 1.6 : 1.1,
    });
    if (bolts.length > MAX_BOLTS) bolts.shift();
  }

  function strokePath(points, style, width, blur, alpha) {
    context.beginPath();
    context.moveTo(points[0][0], points[0][1]);
    for (let index = 1; index < points.length; index += 1) {
      context.lineTo(points[index][0], points[index][1]);
    }
    context.strokeStyle = style;
    context.lineWidth = width;
    context.globalAlpha = alpha;
    context.shadowColor = GLOW;
    context.shadowBlur = blur;
    context.stroke();
    context.globalAlpha = 1;
  }

  function drawBolt(bolt, now) {
    const age = (now - bolt.born) / bolt.life;
    if (age >= 1) return false;
    // Sharp attack, slow decay, and a nervous flicker while it lives.
    const envelope = age < 0.12 ? 1 : (1 - age) ** 1.6;
    const flicker = 0.78 + Math.random() * 0.22;
    const alpha = bolt.peak * envelope * flicker;
    for (const path of [bolt.points, ...bolt.branches]) {
      strokePath(path, "rgba(96, 165, 250, 0.9)", bolt.width * 2.6, 18, alpha * 0.7);
      strokePath(path, "rgba(240, 247, 255, 0.95)", bolt.width, 0, alpha);
    }
    return true;
  }

  function frame(now) {
    if (!active) return;
    level += (target - level) * (target > level ? 0.5 : 0.055);
    const w = innerWidth;
    const h = innerHeight;
    context.clearRect(0, 0, w, h);

    // The calm base: a soft border glow that breathes with the voice.
    context.strokeStyle = `rgba(96, 165, 250, ${0.08 + level * 0.5})`;
    context.lineWidth = 2;
    context.shadowColor = GLOW;
    context.shadowBlur = 14 + level * 40;
    context.strokeRect(1.5, 1.5, w - 3, h - 3);

    if (!reducedMotion.matches) {
      // Louder voice → more frequent, brighter strikes; silence → rare sparks.
      if (Math.random() < 0.012 + level * 0.14) spawnBolt(now, false);
      if (level > 0.4 && Math.random() < level * 0.03) spawnBolt(now, true);
      bolts = bolts.filter((bolt) => drawBolt(bolt, now));
    }
    raf = requestAnimationFrame(frame);
  }

  window.LiveFx = {
    start() {
      ensureCanvas();
      active = true;
      bolts = [];
      canvas.style.opacity = "1";
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(frame);
    },
    stop() {
      active = false;
      target = 0;
      level = 0;
      bolts = [];
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
