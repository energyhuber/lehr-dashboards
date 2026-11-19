// MPP-Tracking (Perturb & Observe) an einem 60-Zellen-Modul mit 3 Teilstrings und Bypassdioden.
// Erwartet globales Objekt C: G, T, L (Beschriftungen).
(function () {
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const H = 430; let W = 900;
  function resize() { const d = window.devicePixelRatio || 1; W = Math.max(320, cv.clientWidth);
    cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0); }
  resize(); new ResizeObserver(resize).observe(cv);

  // ---------- Modulmodell
  const ISC = 10.0, VOC_CELL = 0.68, NS = 20, NSUB = 3, NID = 1.3, ALPHA = 0.0005, BETA = 0.003;
  let cloud = false, shade = false, stepBig = false;
  let Geff = C.G;                    // geglättete Einstrahlung (Wolke zieht langsam auf)
  function subParams(Gk) {
    const Vt = 8.617e-5 * (C.T + 273.15), a = NID * Vt * NS;
    const Iph = ISC * Gk / 1000 * (1 + ALPHA * (C.T - 25));
    const Voc = Math.max(0.05, NS * VOC_CELL * (1 - BETA * (C.T - 25)) + a * Math.log(Math.max(Gk, 1) / 1000));
    const I0 = Iph / (Math.exp(Voc / a) - 1);
    return { a, Iph, I0 };
  }
  let curve = [], Voc = 1, gmpp = { V: 0, P: 0 }, Imax = 1;
  function build() {
    const subs = [];
    for (let k = 0; k < NSUB; k++) subs.push(subParams(Geff * (shade && k === NSUB - 1 ? 0.25 : 1)));
    Imax = Math.max(...subs.map(s => s.Iph));
    const Vof = I => { let V = 0; for (const s of subs) V += I < s.Iph ? s.a * Math.log((s.Iph - I) / s.I0 + 1) : -0.5; return V; };
    const Is = [];
    for (let i = 0; i <= 300; i++) Is.push(Imax * i / 300);
    for (const s of subs) for (let k = 0; k <= 120; k++) Is.push(s.Iph * (1 - Math.pow(10, -6 * k / 120)));
    const pts = [];
    for (const I of Is) { const V = Vof(I); if (V >= 0) pts.push({ V, I, P: V * I }); }
    // Punkt bei U = 0 (Kurzschluss) per Bisektion
    let lo = 0, hi = Imax;
    for (let k = 0; k < 60; k++) { const m = (lo + hi) / 2; if (Vof(m) > 0) lo = m; else hi = m; }
    pts.push({ V: 0, I: lo, P: 0 });
    pts.sort((p, q) => p.V - q.V);
    curve = pts; Voc = pts[pts.length - 1].V;
    gmpp = pts.reduce((m, p) => p.P > m.P ? p : m, { V: 0, P: -1 });
  }
  function IofV(V) {
    if (V <= curve[0].V) return curve[0].I;
    for (let i = 1; i < curve.length; i++) if (curve[i].V >= V) {
      const a = curve[i - 1], b = curve[i], t = (V - a.V) / Math.max(1e-9, b.V - a.V);
      return a.I + (b.I - a.I) * t;
    }
    return 0;
  }

  // ---------- Tracker
  let Vop = 0, Pprev = 0, dir = 1, tick = 0;
  const hist = [];                     // [t, P, Pmpp]
  let simT = 0;
  build(); Vop = 0.6 * Voc;

  // ---------- Bedienung
  const bar = document.getElementById('bar');
  function btn(txt, fn) { const b = document.createElement('button'); b.textContent = txt; b.onclick = () => { fn(); b.classList.toggle('on'); }; bar.appendChild(b); return b; }
  btn(C.L.cloud, () => { cloud = !cloud; });
  btn(C.L.shade, () => { shade = !shade; });
  btn(C.L.bigstep, () => { stepBig = !stepBig; });
  const rb = document.createElement('button'); rb.textContent = C.L.restart; bar.appendChild(rb);
  rb.onclick = () => { Vop = 0.15 * Voc; Pprev = 0; dir = 1; };

  // ---------- Zeichnen
  function axes(x0, y0, w, h, xmax, ymax, xl, yl, col, right) {
    ctx.strokeStyle = '#999'; ctx.lineWidth = 1; ctx.fillStyle = '#555'; ctx.font = '11px sans-serif';
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + w, y0); ctx.stroke();
    const xa = right ? x0 + w : x0;
    ctx.strokeStyle = col; ctx.beginPath(); ctx.moveTo(xa, y0); ctx.lineTo(xa, y0 - h); ctx.stroke();
    ctx.textAlign = 'center';
    for (let i = 0; i <= 5; i++) { const v = xmax * i / 5; ctx.fillText(v.toFixed(0), x0 + w * i / 5, y0 + 14); }
    ctx.fillText(xl, x0 + w / 2, y0 + 30);
    ctx.fillStyle = col; ctx.textAlign = right ? 'left' : 'right';
    for (let i = 0; i <= 4; i++) { const v = ymax * i / 4; ctx.fillText(v.toFixed(0), xa + (right ? 6 : -6), y0 - h * i / 4 + 4); }
    ctx.save(); ctx.translate(xa + (right ? 42 : -38), y0 - h / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText(yl, 0, 0); ctx.restore();
  }
  function draw(dt) {
    simT += dt;
    const target = C.G * (cloud ? 0.3 : 1);
    Geff += (target - Geff) * Math.min(1, dt * 0.8);
    build();
    // Tracker-Schritt
    tick += dt;
    const period = 0.18;
    while (tick > period) {
      tick -= period;
      const P = Vop * IofV(Vop);
      if (P < Pprev) dir = -dir;
      Pprev = P;
      Vop = Math.max(0.5, Math.min(Voc - 0.2, Vop + dir * (stepBig ? 2.0 : 0.5)));
      hist.push([simT, P, gmpp.P]); if (hist.length > 400) hist.shift();
    }
    const Iop = IofV(Vop), Pop = Vop * Iop;

    ctx.fillStyle = '#fbfcfe'; ctx.fillRect(0, 0, W, H);
    // Kennlinien
    const gx = 60, gy = H - 50, gw = W * 0.56 - 110, gh = H - 100;
    const Vmax = 50, IM = 11, PM = 400;
    axes(gx, gy, gw, gh, Vmax, IM, C.L.u, C.L.i, '#1c7ed6', false);
    axes(gx, gy, gw, gh, Vmax, PM, C.L.u, C.L.p, '#e8590c', true);
    const X = v => gx + gw * v / Vmax, YI = i => gy - gh * i / IM, YP = p => gy - gh * p / PM;
    ctx.lineWidth = 3; ctx.strokeStyle = '#1c7ed6'; ctx.beginPath();
    curve.forEach((p, k) => k ? ctx.lineTo(X(p.V), YI(p.I)) : ctx.moveTo(X(p.V), YI(p.I))); ctx.stroke();
    ctx.strokeStyle = '#e8590c'; ctx.beginPath();
    curve.forEach((p, k) => k ? ctx.lineTo(X(p.V), YP(p.P)) : ctx.moveTo(X(p.V), YP(p.P))); ctx.stroke();
    // globales MPP
    ctx.fillStyle = '#2b8a3e'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center';
    ctx.beginPath(); ctx.arc(X(gmpp.V), YP(gmpp.P), 6, 0, 2 * Math.PI); ctx.fill();
    ctx.fillText('MPP', X(gmpp.V), YP(gmpp.P) - 12);
    // Arbeitspunkt
    ctx.setLineDash([4, 4]); ctx.strokeStyle = '#555'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(X(Vop), gy); ctx.lineTo(X(Vop), YP(Pop)); ctx.stroke(); ctx.setLineDash([]);
    for (const [y, col] of [[YI(Iop), '#1c7ed6'], [YP(Pop), '#e8590c']]) {
      ctx.fillStyle = '#fff'; ctx.strokeStyle = col; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(X(Vop), y, 7, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    }
    // Richtungspfeil
    ctx.fillStyle = '#333'; ctx.font = 'bold 18px sans-serif'; ctx.fillText(dir > 0 ? '→' : '←', X(Vop), gy - 8);

    // Rechte Seite: Leistung über Zeit
    const rx = W * 0.56 + 20, rw = W - rx - 20, ry = 70, rh = 170;
    ctx.fillStyle = '#334'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'left';
    ctx.fillText(C.L.hist, rx, ry - 12);
    ctx.strokeStyle = '#ccc'; ctx.lineWidth = 1; ctx.strokeRect(rx, ry, rw, rh);
    const t0 = simT - 30, Xt = t => rx + rw * (t - t0) / 30, Yh = p => ry + rh - rh * p / PM;
    ctx.strokeStyle = '#2b8a3e'; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5; ctx.beginPath();
    hist.filter(h => h[0] >= t0).forEach((h, k) => k ? ctx.lineTo(Xt(h[0]), Yh(h[2])) : ctx.moveTo(Xt(h[0]), Yh(h[2]))); ctx.stroke();
    ctx.setLineDash([]); ctx.strokeStyle = '#e8590c'; ctx.lineWidth = 2.5; ctx.beginPath();
    hist.filter(h => h[0] >= t0).forEach((h, k) => k ? ctx.lineTo(Xt(h[0]), Yh(h[1])) : ctx.moveTo(Xt(h[0]), Yh(h[1]))); ctx.stroke();
    ctx.font = '11px sans-serif'; ctx.fillStyle = '#2b8a3e'; ctx.fillText(C.L.pmpp, rx + 6, ry + 14);
    ctx.fillStyle = '#e8590c'; ctx.fillText(C.L.pop, rx + 6, ry + 28);

    // Kennzahlen
    const eta = gmpp.P > 1 ? Pop / gmpp.P : 0;
    const lines = [
      [`${C.L.g_eff}`, `${Geff.toFixed(0)} W/m²`],
      ['U', `${Vop.toFixed(1)} V`], ['I', `${Iop.toFixed(2)} A`], ['P', `${Pop.toFixed(0)} W`],
      ['P_MPP', `${gmpp.P.toFixed(0)} W  (${gmpp.V.toFixed(1)} V)`],
      [C.L.eta, `${(eta * 100).toFixed(1)} %`],
    ];
    ctx.font = '13px sans-serif';
    lines.forEach(([a, b], k) => { ctx.fillStyle = '#555'; ctx.fillText(a, rx, ry + rh + 30 + k * 21); ctx.fillStyle = '#111'; ctx.font = 'bold 13px sans-serif'; ctx.fillText(b, rx + 150, ry + rh + 30 + k * 21); ctx.font = '13px sans-serif'; });
    if (shade && eta < 0.93) {
      ctx.fillStyle = '#c92a2a'; ctx.font = 'bold 13px sans-serif';
      ctx.fillText(C.L.local, rx, ry + rh + 30 + lines.length * 21 + 6);
    }
  }
  let last = performance.now();
  function loop(now) { const dt = Math.min(0.05, (now - last) / 1000); last = now; draw(dt); requestAnimationFrame(loop); }
  requestAnimationFrame(loop);
})();
