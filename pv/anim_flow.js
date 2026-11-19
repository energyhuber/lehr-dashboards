// Energieflüsse eines Tages im Zeitraffer: PV, Haus, Batterie, Netz.
// Erwartet globales Objekt C: Stundenarrays pv, last, direkt, lade, entl, einsp, bezug, soc; kap; L.
(function () {
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const H = 520; let W = 900;
  function resize() { const d = window.devicePixelRatio || 1; W = Math.max(320, cv.clientWidth);
    cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0); }
  resize(); new ResizeObserver(resize).observe(cv);

  let t = 6, speed = 1, play = true;                       // Stunden; 1 h pro Sekunde
  const bar = document.getElementById('bar');
  function btn(txt, fn) { const b = document.createElement('button'); b.textContent = txt; b.onclick = () => fn(b); bar.appendChild(b); return b; }
  btn('⏯', () => { play = !play; });
  btn('×0,5', () => { speed = 0.5; }); btn('×1', () => { speed = 1; }); btn('×3', () => { speed = 3; });
  const clockEl = document.createElement('span'); clockEl.style.marginLeft = '10px'; clockEl.style.fontWeight = 'bold'; bar.appendChild(clockEl);

  let SR = C.pv.findIndex(p => p > 0.005), SS = 24 - [...C.pv].reverse().findIndex(p => p > 0.005);
  if (SR < 0) { SR = 8; SS = 16; }
  SR = Math.max(0, SR - 0.5); SS = Math.min(24, SS + 0.5);
  const val = (arr, tt) => { const h = Math.floor(tt) % 24, n = (h + 1) % 24, f = tt - Math.floor(tt); return arr[h] * (1 - f) + arr[n] * f; };
  const vstep = (arr, tt) => arr[Math.floor(tt) % 24];
  const dots = { pv_haus: [], pv_bat: [], pv_netz: [], bat_haus: [], netz_haus: [] };
  const acc = { pv_haus: 0, pv_bat: 0, pv_netz: 0, bat_haus: 0, netz_haus: 0 };

  function nodes() {
    return {
      pv: [W * 0.22, 100], haus: [W * 0.55, 225], bat: [W * 0.22, 320], netz: [W * 0.85, 225],
    };
  }
  const COL = { pv_haus: '#f59f00', pv_bat: '#f59f00', pv_netz: '#f59f00', bat_haus: '#2b8a3e', netz_haus: '#868e96' };

  function edge(a, b, key, P) {
    const [x1, y1] = a, [x2, y2] = b;
    const w = Math.min(14, 1.5 + P * 2.2);
    ctx.strokeStyle = P > 0.02 ? COL[key] + '55' : '#e9ecef'; ctx.lineWidth = P > 0.02 ? w : 2;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    // Punkte
    const L = Math.hypot(x2 - x1, y2 - y1);
    for (const d of dots[key]) {
      const f = d / L; ctx.fillStyle = COL[key];
      ctx.beginPath(); ctx.arc(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, 4.5, 0, 2 * Math.PI); ctx.fill();
    }
    if (P > 0.02) {
      ctx.fillStyle = '#222'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center';
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fillRect(mx - 30, my - 18, 60, 16);
      ctx.fillStyle = '#222'; ctx.fillText(`${P.toFixed(2)} kW`, mx, my - 6);
    }
    return L;
  }
  function moveDots(key, P, L, dt) {
    const v = 140;                                          // px/s, Dichte ∝ Leistung
    acc[key] += P * dt * 3.2 * speed;
    while (acc[key] >= 1) { acc[key] -= 1; dots[key].push(Math.random() * 6); }
    dots[key] = dots[key].map(d => d + v * dt).filter(d => d < L);
  }

  function house(x, y, P) {
    ctx.fillStyle = '#f1f3f5'; ctx.strokeStyle = '#495057'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x - 50, y - 5); ctx.lineTo(x, y - 50); ctx.lineTo(x + 50, y - 5); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.fillRect(x - 40, y - 5, 80, 60); ctx.strokeRect(x - 40, y - 5, 80, 60);
    ctx.fillStyle = '#ffe066'; ctx.fillRect(x - 28, y + 8, 16, 16); ctx.fillRect(x + 12, y + 8, 16, 16);
    ctx.fillStyle = '#222'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(`${C.L.haus}`, x, y + 74); ctx.font = '12px sans-serif'; ctx.fillText(`${P.toFixed(2)} kW`, x, y + 90);
  }
  function panel(x, y, P, sunUp) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(-0.25);
    ctx.fillStyle = '#1d3557'; ctx.fillRect(-55, -18, 110, 36);
    ctx.strokeStyle = '#8ecae6'; ctx.lineWidth = 1;
    for (let i = 1; i < 6; i++) { ctx.beginPath(); ctx.moveTo(-55 + i * 110 / 6, -18); ctx.lineTo(-55 + i * 110 / 6, 18); ctx.stroke(); }
    ctx.beginPath(); ctx.moveTo(-55, 0); ctx.lineTo(55, 0); ctx.stroke();
    if (sunUp && P > 0.05) { ctx.fillStyle = `rgba(255,230,120,${Math.min(0.5, P / 8)})`; ctx.fillRect(-55, -18, 110, 36); }
    ctx.restore();
    ctx.fillStyle = '#222'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('PV', x, y + 40); ctx.font = '12px sans-serif'; ctx.fillText(`${P.toFixed(2)} kW`, x, y + 56);
  }
  function battery(x, y, soc) {
    const w = 46, h = 70;
    ctx.strokeStyle = '#495057'; ctx.lineWidth = 2.5; ctx.strokeRect(x - w / 2, y - h / 2, w, h);
    ctx.fillStyle = '#495057'; ctx.fillRect(x - 9, y - h / 2 - 7, 18, 7);
    const f = C.kap > 0 ? soc / C.kap : 0;
    ctx.fillStyle = f > 0.2 ? '#40c057' : '#fa5252';
    ctx.fillRect(x - w / 2 + 4, y + h / 2 - 4 - (h - 8) * f, w - 8, (h - 8) * f);
    ctx.fillStyle = '#222'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(C.kap > 0 ? `${C.L.bat} ${C.kap.toFixed(0)} kWh` : C.L.nobat, x, y + h / 2 + 20);
    if (C.kap > 0) { ctx.font = '12px sans-serif'; ctx.fillText(`${(f * 100).toFixed(0)} %`, x, y + h / 2 + 36); }
  }
  function grid(x, y) {
    ctx.strokeStyle = '#495057'; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(x - 25, y + 55); ctx.lineTo(x, y - 45); ctx.lineTo(x + 25, y + 55);
    ctx.moveTo(x - 30, y - 25); ctx.lineTo(x + 30, y - 25); ctx.moveTo(x - 22, y); ctx.lineTo(x + 22, y);
    ctx.moveTo(x - 14, y + 25); ctx.lineTo(x + 14, y - 25); ctx.moveTo(x + 14, y + 25); ctx.lineTo(x - 14, y - 25); ctx.stroke();
    ctx.fillStyle = '#222'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(C.L.netz, x, y + 74);
  }

  function draw(dt) {
    if (play) t = (t + dt * speed) % 24;
    const N = nodes();
    // Himmel
    const sunH = (t > SR && t < SS) ? Math.sin(Math.PI * (t - SR) / (SS - SR)) : 0;
    const sky = ctx.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, sunH > 0.05 ? `rgb(${190 + 40 * sunH},${215 + 25 * sunH},255)` : '#2b3a55');
    sky.addColorStop(1, '#ffffff');
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H - 90);
    ctx.fillStyle = '#fff'; ctx.fillRect(0, H - 90, W, 90);
    // Sonne
    if (sunH > 0) {
      const sx = W * 0.06 + W * 0.88 * ((t - SR) / (SS - SR)), sy = 150 - 115 * sunH;
      ctx.fillStyle = '#ffd43b'; ctx.beginPath(); ctx.arc(sx, sy, 16, 0, 2 * Math.PI); ctx.fill();
    } else {
      ctx.fillStyle = '#e9ecef'; ctx.beginPath(); ctx.arc(W * 0.9, 40, 12, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = '#2b3a55'; ctx.beginPath(); ctx.arc(W * 0.9 + 6, 36, 11, 0, 2 * Math.PI); ctx.fill();
    }
    const P = k => vstep(C[k], t);
    const flows = [['pv_haus', N.pv, N.haus, P('direkt')], ['pv_bat', N.pv, N.bat, P('lade')],
      ['pv_netz', N.pv, N.netz, P('einsp')], ['bat_haus', N.bat, N.haus, P('entl')], ['netz_haus', N.netz, N.haus, P('bezug')]];
    for (const [k, a, b, p] of flows) {
      if (C.kap <= 0 && (k === 'pv_bat' || k === 'bat_haus')) continue;
      const L = edge(a, b, k, p); moveDots(k, p, L, dt);
    }
    panel(N.pv[0], N.pv[1], P('pv'), sunH > 0);
    house(N.haus[0], N.haus[1], P('last'));
    battery(N.bat[0], N.bat[1], val(C.soc, t));
    grid(N.netz[0], N.netz[1]);

    // Tagesverlauf unten
    const gx = 50, gw = W - 100, gy = H - 18, gh = 60;
    const pm = Math.max(0.5, ...C.pv, ...C.last);
    const X = h => gx + gw * h / 24, Y = p => gy - gh * p / pm;
    ctx.fillStyle = 'rgba(245,159,0,0.35)'; ctx.beginPath(); ctx.moveTo(X(0), gy);
    for (let h = 0; h < 24; h++) { ctx.lineTo(X(h), Y(C.pv[h])); ctx.lineTo(X(h + 1), Y(C.pv[h])); } ctx.lineTo(X(24), gy); ctx.fill();
    ctx.strokeStyle = '#222'; ctx.lineWidth = 1.8; ctx.beginPath();
    for (let h = 0; h < 24; h++) { h ? ctx.lineTo(X(h), Y(C.last[h])) : ctx.moveTo(X(h), Y(C.last[h])); ctx.lineTo(X(h + 1), Y(C.last[h])); } ctx.stroke();
    ctx.strokeStyle = '#c92a2a'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(X(t), gy); ctx.lineTo(X(t), gy - gh - 4); ctx.stroke();
    ctx.fillStyle = '#555'; ctx.font = '11px sans-serif'; ctx.textAlign = 'center';
    for (let h = 0; h <= 24; h += 6) ctx.fillText(`${h}:00`, X(h), gy + 13);
    ctx.textAlign = 'left'; ctx.fillStyle = '#e67700'; ctx.fillText(C.L.pv_leg, gx, gy - gh - 6);
    ctx.fillStyle = '#222'; ctx.fillText(C.L.last_leg, gx + 120, gy - gh - 6);
    const hh = Math.floor(t), mm = Math.floor((t - hh) * 60);
    clockEl.textContent = `🕒 ${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
  }
  let last = performance.now();
  function loop(now) { const dt = Math.min(0.05, (now - last) / 1000); last = now; draw(dt); requestAnimationFrame(loop); }
  requestAnimationFrame(loop);
})();
