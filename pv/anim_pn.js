// pn-Übergang: Diffusion, Raumladungszone, E-Feld, Ladungstrennung durch Licht.
// Erwartet globales Objekt C (Beschriftungen) – wird vor diesem Skript gesetzt.
(function () {
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const H = 560;
  let W = 900;
  function resize() {
    const d = window.devicePixelRatio || 1;
    const nw = Math.max(320, cv.clientWidth);
    if (ready && Math.abs(nw - W) < 2) return;
    W = nw;
    cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0);
    layout();
    if (ready) { const s = step; step = 0; reset(); setStep(s); }
  }
  let ready = false;
  // Geometrie
  let xL, xR, x0, wR, devT, devB, wireY;
  function layout() {
    xL = 70; xR = W - 70; x0 = W / 2; wR = (xR - xL) * 0.18;
    devT = 100; devB = 300; wireY = 48;
  }

  // ---------- Teilchen
  let ions = [], carriers = [], flashes = [], photons = [], current = [];
  function reset() {
    ions = []; carriers = []; flashes = []; photons = []; current = [];
    const cols = 10, rows = 6;
    for (const side of ['n', 'p']) {
      const a = side === 'n' ? xL : x0, b = side === 'n' ? x0 : xR;
      for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
        const x = a + (i + 0.5) * (b - a) / cols, y = devT + (j + 0.5) * (devB - devT) / rows;
        ions.push({ x, y, side });
        carriers.push({ x: x + (Math.random() - .5) * 14, y: y + (Math.random() - .5) * 14,
          t: side === 'n' ? 'e' : 'h', s: 'free', vx: 0, vy: 0 });
      }
    }
  }
  const inRLZ = x => Math.abs(x - x0) < wR / 2;

  // ---------- Schrittsteuerung
  let step = 0, bend = 0, auto = false, autoT = 0;
  const stepBtns = [];
  function setStep(s) {
    s = Math.max(0, Math.min(3, s));
    if (s === 0) { reset(); bend = 0; }
    if (step === 0 && s >= 1) {
      for (const c of carriers) if (inRLZ(c.x)) c.s = 'diff';
      if (s >= 2) carriers = carriers.filter(c => c.s !== 'diff');
    }
    if (s < 3) { photons = []; current = []; carriers = carriers.filter(c => c.s === 'free' || c.s === 'diff'); }
    step = s;
    stepBtns.forEach((b, i) => b.classList.toggle('on', i === step));
    document.getElementById('cap').innerHTML = `<b>${C.steps[step][0]}</b> – ${C.steps[step][1]}`;
  }
  function ui() {
    const bar = document.getElementById('bar');
    const mk = (txt, fn, cls) => { const b = document.createElement('button'); b.textContent = txt; b.onclick = fn; if (cls) b.className = cls; bar.appendChild(b); return b; };
    mk('◀', () => { auto = false; setStep(step - 1); });
    C.steps.forEach((s, i) => stepBtns.push(mk(`${i + 1}. ${s[0]}`, () => { auto = false; setStep(i); }, 'st')));
    mk('▶', () => { auto = false; setStep(step + 1); });
    const ab = mk(C.auto, () => { auto = !auto; ab.classList.toggle('on', auto); autoT = 0; if (auto && step === 3) setStep(0); });
  }

  // ---------- Zeichnen
  function wirePath() {
    return [[xL - 4, devT], [xL - 4, wireY], [xR + 4, wireY], [xR + 4, devT]];
  }
  function along(path, d) {               // Punkt nach Weglänge d
    for (let i = 0; i < path.length - 1; i++) {
      const [ax, ay] = path[i], [bx, by] = path[i + 1], L = Math.hypot(bx - ax, by - ay);
      if (d <= L) return [ax + (bx - ax) * d / L, ay + (by - ay) * d / L, false];
      d -= L;
    }
    const e = path[path.length - 1]; return [e[0], e[1], true];
  }
  let lamp = 0;

  function draw(dt) {
    ctx.fillStyle = '#fbfcfe'; ctx.fillRect(0, 0, W, H);
    // Gebiete
    ctx.fillStyle = '#e4eefb'; ctx.fillRect(xL, devT, x0 - xL, devB - devT);
    ctx.fillStyle = '#fbe9e7'; ctx.fillRect(x0, devT, xR - x0, devB - devT);
    if (step >= 1) {
      const a = step === 1 ? Math.min(1, bend) : 1;
      ctx.fillStyle = `rgba(255,236,170,${0.75 * a})`;
      ctx.fillRect(x0 - wR / 2, devT, wR, devB - devT);
    }
    ctx.strokeStyle = '#8895a2'; ctx.lineWidth = 1.5; ctx.strokeRect(xL, devT, xR - xL, devB - devT);
    // Kontakte
    ctx.fillStyle = '#9aa3ad'; ctx.fillRect(xL - 10, devT, 8, devB - devT); ctx.fillRect(xR + 2, devT, 8, devB - devT);
    ctx.fillStyle = '#334'; ctx.font = 'bold 15px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(C.nside, (xL + x0) / 2, devB + 22); ctx.fillText(C.pside, (x0 + xR) / 2, devB + 22);
    if (step >= 1) { ctx.font = '12px sans-serif'; ctx.fillStyle = '#8a6d00'; ctx.fillText(C.rlz, x0, devT - 8); }

    // Stromkreis mit Lampe (nur Schritt 4)
    if (step === 3) {
      ctx.strokeStyle = '#555'; ctx.lineWidth = 2.5; ctx.beginPath();
      wirePath().forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke();
      const g = ctx.createRadialGradient(x0, wireY, 2, x0, wireY, 40);
      g.addColorStop(0, `rgba(255,220,80,${Math.min(1, lamp)})`); g.addColorStop(1, 'rgba(255,220,80,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x0, wireY, 40, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.strokeStyle = '#333'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x0, wireY, 13, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x0 - 9, wireY - 9); ctx.lineTo(x0 + 9, wireY + 9); ctx.moveTo(x0 + 9, wireY - 9); ctx.lineTo(x0 - 9, wireY + 9); ctx.stroke();
      ctx.fillStyle = '#333'; ctx.font = '12px sans-serif'; ctx.fillText(C.load, x0, wireY - 20);
      ctx.fillText('−', xL - 22, devT + 14); ctx.fillText('+', xR + 22, devT + 14);
    }

    // Ionen
    for (const io of ions) {
      const exposed = step >= 1 && inRLZ(io.x) && (step >= 2 || bend > 0.5);
      ctx.fillStyle = exposed ? (io.side === 'n' ? '#e8590c' : '#7048e8') : 'rgba(120,130,140,0.35)';
      ctx.font = exposed ? 'bold 16px sans-serif' : '13px sans-serif';
      ctx.fillText(io.side === 'n' ? '+' : '−', io.x, io.y + 5);
    }

    // E-Feld
    if (step >= 2) {
      ctx.strokeStyle = '#c92a2a'; ctx.fillStyle = '#c92a2a'; ctx.lineWidth = 2;
      for (let k = 0; k < 4; k++) {
        const y = devT + 25 + k * (devB - devT - 50) / 3, a = x0 - wR * 0.38, b = x0 + wR * 0.38;
        ctx.beginPath(); ctx.moveTo(a, y - 10); ctx.lineTo(b, y - 10); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(b + 6, y - 10); ctx.lineTo(b - 2, y - 15); ctx.lineTo(b - 2, y - 5); ctx.fill();
      }
      ctx.font = 'bold 15px sans-serif'; ctx.fillText('E', x0, devB - 8);
    }

    // Ladungsträger
    const nB = [xL + 4, x0 - (step >= 2 ? wR / 2 : 0) - 3], pB = [x0 + (step >= 2 ? wR / 2 : 0) + 3, xR - 4];
    for (const c of carriers) {
      if (c.s === 'free') {
        c.vx += (Math.random() - .5) * 600 * dt; c.vy += (Math.random() - .5) * 600 * dt;
        c.vx *= 0.9; c.vy *= 0.9;
        c.x += c.vx * dt; c.y += c.vy * dt;
        const B = c.t === 'e' ? (step === 0 ? [xL + 4, x0 - 3] : nB) : (step === 0 ? [x0 + 3, xR - 4] : pB);
        if (c.x < B[0]) { c.x = B[0]; c.vx = Math.abs(c.vx); } if (c.x > B[1]) { c.x = B[1]; c.vx = -Math.abs(c.vx); }
        if (c.y < devT + 4) { c.y = devT + 4; c.vy = Math.abs(c.vy); } if (c.y > devB - 4) { c.y = devB - 4; c.vy = -Math.abs(c.vy); }
      } else if (c.s === 'diff') {             // Diffusion über die Grenze, Rekombination
        c.x += (c.t === 'e' ? 1 : -1) * 55 * dt; c.y += (Math.random() - .5) * 40 * dt;
        const over = c.t === 'e' ? c.x > x0 + wR * 0.2 : c.x < x0 - wR * 0.2;
        if (over || Math.random() < 0.6 * dt) { c.s = 'dead'; flashes.push({ x: c.x, y: c.y, a: 1 }); }
      } else if (c.s === 'ph_e') {             // Photoelektron: Feld treibt nach links
        if (c.d === undefined) {
          c.x -= 170 * dt;
          if (c.x <= xL) { c.d = 0; }
        } else {
          c.d += 230 * dt; const [x, y, end] = along(wirePath(), c.d); c.x = x; c.y = y;
          if (Math.abs(x - x0) < 15 && y === wireY) lamp = Math.min(1.4, lamp + 0.25);
          if (end) c.s = 'dead';
        }
      } else if (c.s === 'ph_h') {             // Loch: nach rechts zum p-Kontakt
        c.x += 120 * dt; if (c.x >= xR) c.s = 'dead';
      }
      if (c.s === 'dead') continue;
      if (c.t === 'e') { ctx.fillStyle = '#1c7ed6'; ctx.beginPath(); ctx.arc(c.x, c.y, 4.2, 0, 2 * Math.PI); ctx.fill(); }
      else { ctx.fillStyle = '#fff'; ctx.strokeStyle = '#e03131'; ctx.lineWidth = 1.8; ctx.beginPath(); ctx.arc(c.x, c.y, 4.2, 0, 2 * Math.PI); ctx.fill(); ctx.stroke(); }
    }
    carriers = carriers.filter(c => c.s !== 'dead');
    lamp *= Math.pow(0.25, dt);
    for (const f of flashes) {
      ctx.fillStyle = `rgba(255,200,0,${f.a})`; ctx.beginPath(); ctx.arc(f.x, f.y, 9 * (1.4 - f.a), 0, 2 * Math.PI); ctx.fill();
      f.a -= dt * 1.5;
    }
    flashes = flashes.filter(f => f.a > 0);

    // Photonen
    if (step === 3) {
      if (Math.random() < 2.2 * dt) photons.push({ x: x0 + (Math.random() - .5) * wR * 0.9, y: devT - 40, ty: devT + 15 + Math.random() * (devB - devT - 30) });
      ctx.strokeStyle = '#f08c00'; ctx.lineWidth = 2;
      for (const p of photons) {
        p.y += 260 * dt;
        ctx.beginPath();
        for (let k = 0; k < 30; k++) { const yy = p.y - k * 1.6; const xx = p.x + 4 * Math.sin(yy * 0.35); k ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy); }
        ctx.stroke();
        if (p.y >= p.ty) {
          p.done = true; flashes.push({ x: p.x, y: p.y, a: 0.8 });
          carriers.push({ x: p.x - 4, y: p.y, t: 'e', s: 'ph_e' }); carriers.push({ x: p.x + 4, y: p.y, t: 'h', s: 'ph_h' });
        }
      }
      photons = photons.filter(p => !p.done);
      ctx.fillStyle = '#f08c00'; ctx.font = '12px sans-serif'; ctx.textAlign = 'left';
      ctx.fillText(C.light, x0 + wR / 2 + 8, devT - 20); ctx.textAlign = 'center';
    }

    // Bänderdiagramm
    if (step === 1) bend = Math.min(1, bend + dt * 0.5); else if (step >= 2) bend = 1; else bend = 0;
    drawBands();

    // Legende
    ctx.textAlign = 'left'; ctx.font = '12px sans-serif';
    let lx = 12, ly = H - 12;
    ctx.fillStyle = '#1c7ed6'; ctx.beginPath(); ctx.arc(lx + 4, ly - 4, 4, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = '#333'; ctx.fillText(C.leg_e, lx + 12, ly);
    lx += ctx.measureText(C.leg_e).width + 30;
    ctx.fillStyle = '#fff'; ctx.strokeStyle = '#e03131'; ctx.beginPath(); ctx.arc(lx + 4, ly - 4, 4, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#333'; ctx.fillText(C.leg_h, lx + 12, ly);
    lx += ctx.measureText(C.leg_h).width + 30;
    ctx.fillStyle = '#e8590c'; ctx.font = 'bold 14px sans-serif'; ctx.fillText('+', lx, ly); ctx.fillStyle = '#7048e8'; ctx.fillText('−', lx + 10, ly);
    ctx.fillStyle = '#333'; ctx.font = '12px sans-serif'; ctx.fillText(C.leg_ion, lx + 24, ly);
  }

  function drawBands() {
    const top = 340, Ec0 = 385, Eg = 72, sh = 46;            // Pixel
    ctx.fillStyle = '#334'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'left';
    ctx.fillText(C.bands, xL, top);
    const f = x => 0.5 * (1 + Math.tanh((x - x0) / (wR / 4)));
    const Ec = x => Ec0 - sh * bend * f(x), Ev = x => Ec(x) + Eg;
    if (step === 0) {                                          // getrennte Bänder
      const gap = 14;
      for (const [a, b] of [[xL, x0 - gap], [x0 + gap, xR]]) {
        ctx.strokeStyle = '#1c7ed6'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(a, Ec0); ctx.lineTo(b, Ec0); ctx.stroke();
        ctx.strokeStyle = '#e03131'; ctx.beginPath(); ctx.moveTo(a, Ec0 + Eg); ctx.lineTo(b, Ec0 + Eg); ctx.stroke();
      }
    } else {
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = '#1c7ed6'; ctx.beginPath(); for (let x = xL; x <= xR; x += 3) x === xL ? ctx.moveTo(x, Ec(x)) : ctx.lineTo(x, Ec(x)); ctx.stroke();
      ctx.strokeStyle = '#e03131'; ctx.beginPath(); for (let x = xL; x <= xR; x += 3) x === xL ? ctx.moveTo(x, Ev(x)) : ctx.lineTo(x, Ev(x)); ctx.stroke();
    }
    // Fermi-Niveau
    ctx.setLineDash([5, 4]); ctx.strokeStyle = '#555'; ctx.lineWidth = 1.3;
    const EFn = Ec0 + 12, EFp0 = Ec0 + Eg - 12, EFp = EFp0 - sh * bend;
    if (step === 3) {
      const split = 16;
      ctx.beginPath(); ctx.moveTo(xL, EFn); ctx.lineTo(x0, EFn); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x0, EFn + split); ctx.lineTo(xR, EFn + split); ctx.stroke();
      ctx.setLineDash([]); ctx.strokeStyle = '#2b8a3e'; ctx.fillStyle = '#2b8a3e'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(xR - 30, EFn); ctx.lineTo(xR - 30, EFn + split); ctx.stroke();
      ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'left'; ctx.fillText('e·U', xR - 24, EFn + 12);
    } else {
      ctx.beginPath(); ctx.moveTo(xL, EFn); ctx.lineTo(step === 0 ? x0 - 14 : xR, step === 0 ? EFn : EFn); ctx.stroke();
      if (step === 0) { ctx.beginPath(); ctx.moveTo(x0 + 14, EFp0); ctx.lineTo(xR, EFp0); ctx.stroke(); }
      else if (bend < 1) { ctx.globalAlpha = 1 - bend; ctx.beginPath(); ctx.moveTo(x0 + 14, EFp); ctx.lineTo(xR, EFp); ctx.stroke(); ctx.globalAlpha = 1; }
    }
    ctx.setLineDash([]);
    ctx.font = '11px sans-serif'; ctx.textAlign = 'right'; ctx.fillStyle = '#1c7ed6'; ctx.fillText('E_L', xL - 6, Ec(xL) + 4);
    ctx.fillStyle = '#e03131'; ctx.fillText('E_V', xL - 6, Ev(xL) + 4);
    ctx.fillStyle = '#555'; ctx.fillText('E_F', xL - 6, EFn + 4);
    if (step >= 2) {
      ctx.fillStyle = '#c92a2a'; ctx.textAlign = 'left'; ctx.font = '12px sans-serif';
      ctx.fillText(C.barrier, x0 + wR / 2 + 6, Ec(x0) - 6);
    }
    if (step === 3) {                                          // Absorption im Bänderdiagramm
      const xa = x0, y1 = Ev(xa), y2 = Ec(xa);
      ctx.strokeStyle = '#f08c00'; ctx.fillStyle = '#f08c00'; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(xa, y1); ctx.lineTo(xa, y2 + 6); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(xa, y2); ctx.lineTo(xa - 5, y2 + 9); ctx.lineTo(xa + 5, y2 + 9); ctx.fill();
      ctx.strokeStyle = '#1c7ed6'; ctx.fillStyle = '#1c7ed6';
      ctx.beginPath(); ctx.moveTo(xa - 6, y2 - 3); ctx.lineTo(xa - wR * 0.7, Ec(xa - wR * 0.7) - 3); ctx.stroke();
      ctx.font = '11px sans-serif'; ctx.textAlign = 'right'; ctx.fillText(C.e_rolls, xa - wR * 0.7 - 4, Ec(xa - wR * 0.7) - 6);
      ctx.strokeStyle = '#e03131'; ctx.fillStyle = '#e03131';
      ctx.beginPath(); ctx.moveTo(xa + 6, y1 + 3); ctx.lineTo(xa + wR * 0.7, Ev(xa + wR * 0.7) + 3); ctx.stroke();
      ctx.textAlign = 'left'; ctx.fillText(C.h_rises, xa + wR * 0.7 + 4, Ev(xa + wR * 0.7) + 14);
    }
  }

  // ---------- Schleife
  let last = performance.now();
  function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (auto) { autoT += dt; if (autoT > 7) { autoT = 0; setStep(step === 3 ? 0 : step + 1); } }
    draw(dt); requestAnimationFrame(loop);
  }
  resize(); reset(); ui(); setStep(0); ready = true;
  new ResizeObserver(resize).observe(cv);
  requestAnimationFrame(loop);
})();
