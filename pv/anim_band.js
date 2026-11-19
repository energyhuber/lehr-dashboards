// Absorption eines Photons, Thermalisierung, nutzbare Energie ≈ E_g.
// Erwartet globales Objekt C mit Eph, Eg, lam, Uoc und Beschriftungen L.
(function () {
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const H = 360; let W = 700;
  function resize() { const d = window.devicePixelRatio || 1; W = Math.max(300, cv.clientWidth);
    cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0); }
  resize(); new ResizeObserver(resize).observe(cv);

  const Eph = C.Eph, Eg = C.Eg, absorbed = Eph >= Eg;
  const sc = Math.min(110, 265 / Math.max(Eph, Eg + 0.6));    // px je eV
  const yV = 320, yC = yV - Eg * sc, yPh = yV - Eph * sc;
  function lamColor(l) {                                       // sichtbare Farbe der Wellenlänge
    if (l < 380) return '#7b2cbf'; if (l > 750) return '#9c3d2e';
    const stops = [[380, [123, 44, 191]], [440, [60, 70, 255]], [490, [0, 190, 220]], [530, [40, 200, 60]],
      [580, [240, 220, 0]], [620, [255, 130, 0]], [750, [200, 20, 20]]];
    for (let i = 0; i < stops.length - 1; i++) if (l <= stops[i + 1][0]) {
      const [a, ca] = stops[i], [b, cb] = stops[i + 1], t = (l - a) / (b - a);
      return `rgb(${ca.map((v, k) => Math.round(v + (cb[k] - v) * t)).join(',')})`;
    }
    return '#c00';
  }
  const pc = lamColor(C.lam);
  let t = 0, last = performance.now();
  const T = 4.2;                                               // Zyklusdauer s

  function arrowV(x, y1, y2, col, lab, side) {
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, y1); ctx.lineTo(x, y2); ctx.stroke();
    const d = y2 < y1 ? 1 : -1;
    for (const yy of [y1, y2]) { const s = yy === y2 ? d : -d;
      ctx.beginPath(); ctx.moveTo(x, yy); ctx.lineTo(x - 5, yy + 8 * s); ctx.lineTo(x + 5, yy + 8 * s); ctx.fill(); }
    ctx.font = '12px sans-serif'; ctx.textAlign = side === 'l' ? 'right' : 'left';
    ctx.fillText(lab, x + (side === 'l' ? -8 : 8), (y1 + y2) / 2 + 4);
  }

  function draw(dt) {
    t = (t + dt) % T;
    ctx.fillStyle = '#fbfcfe'; ctx.fillRect(0, 0, W, H);
    const xa = W * 0.55, bL = W * 0.22, bR = W * 0.72;
    // Bänder
    ctx.fillStyle = '#dbe7f6'; ctx.fillRect(bL, yC - 40, bR - bL, 40);
    ctx.fillStyle = '#f6dede'; ctx.fillRect(bL, yV, bR - bL, 30);
    ctx.fillStyle = '#1c7ed6'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'left';
    ctx.fillText(C.L.cb, bL + 6, yC - 8);
    ctx.fillStyle = '#e03131'; ctx.fillText(C.L.vb, bL + 6, yV + 18);
    ctx.strokeStyle = '#1c7ed6'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(bL, yC); ctx.lineTo(bR, yC); ctx.stroke();
    ctx.strokeStyle = '#e03131'; ctx.beginPath(); ctx.moveTo(bL, yV); ctx.lineTo(bR, yV); ctx.stroke();
    arrowV(bL - 30, yV, yC, '#555', `E_g = ${Eg.toFixed(2)} eV`, 'l');

    // Photon fliegt ein
    const tIn = 1.0, xs = 20, xe = absorbed ? xa : W - 20;
    const tp = Math.min(1, t / (absorbed ? tIn : 2.2));
    const xp = xs + (xe - xs) * tp, yp = absorbed ? yV - 2 : (yC + yV) / 2;
    if (!absorbed || t < tIn) {
      ctx.strokeStyle = pc; ctx.lineWidth = 3; ctx.beginPath();
      for (let k = 0; k < 60; k++) { const xx = xp - k * 1.5; const yy = yp + 6 * Math.sin(xx * 0.25); k ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy); }
      ctx.stroke();
      ctx.fillStyle = pc; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'left';
      ctx.fillText(`${C.L.photon}  λ = ${C.lam.toFixed(0)} nm,  E = ${Eph.toFixed(2)} eV`, 14, 22);
    }
    if (!absorbed) {
      ctx.fillStyle = '#868e96'; ctx.font = 'bold 14px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText(C.L.transmit, W / 2, 60);
      return;
    }
    // Elektron springt hoch, thermalisiert auf E_L
    const tJ = tIn, tR = tIn + 0.35, tT = tR + 1.3;
    let ye;
    if (t < tJ) ye = null;
    else if (t < tR) ye = yV - (yV - yPh) * (t - tJ) / (tR - tJ);
    else if (t < tT) ye = yPh + (yC - yPh) * (t - tR) / (tT - tR);
    else ye = yC;
    if (t >= tJ) {
      // Loch im Valenzband
      ctx.fillStyle = '#fff'; ctx.strokeStyle = '#e03131'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(xa, yV + 10, 6, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      // Sprungpfeil
      ctx.setLineDash([4, 3]); ctx.strokeStyle = pc; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(xa, yV); ctx.lineTo(xa, Math.min(yV, ye)); ctx.stroke(); ctx.setLineDash([]);
      // Elektron
      ctx.fillStyle = '#1c7ed6'; ctx.beginPath(); ctx.arc(xa, ye, 6.5, 0, 2 * Math.PI); ctx.fill();
      // Wärme-Wellen während Thermalisierung
      if (t >= tR && t < tT + 0.6 && Eph - Eg > 0.05) {
        ctx.strokeStyle = 'rgba(224,49,49,0.75)'; ctx.lineWidth = 2;
        for (let k = 0; k < 3; k++) {
          const ph = ((t - tR) * 2 + k / 3) % 1, xx = xa + 18 + ph * 70, yy = ye + (k - 1) * 10;
          ctx.globalAlpha = 1 - ph; ctx.beginPath();
          for (let j = 0; j < 14; j++) { const x2 = xx + j * 2; const y2 = yy + 3 * Math.sin(j * 1.2); j ? ctx.lineTo(x2, y2) : ctx.moveTo(x2, y2); }
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
    }
    // Energieaufteilung rechts
    const xb = W * 0.12;
    if (Eph - Eg > 0.02) arrowV(bR + 70, yC, yPh, '#e03131', `${C.L.heat} ${(Eph - Eg).toFixed(2)} eV`, 'r');
    arrowV(bR + 70 + (Eph - Eg > 0.02 ? 0 : 0), yV, yC, '#2b8a3e', `${C.L.usable} ≈ ${Eg.toFixed(2)} eV`, 'r');
    ctx.setLineDash([3, 3]); ctx.strokeStyle = '#999'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(xa, yPh); ctx.lineTo(bR + 70, yPh); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#333'; ctx.font = '12px sans-serif'; ctx.textAlign = 'left';
    ctx.fillText(`${C.L.voc}`, 14, H - 10);
  }
  function loop(now) { const dt = Math.min(0.05, (now - last) / 1000); last = now; draw(dt); requestAnimationFrame(loop); }
  requestAnimationFrame(loop);
})();
