"""Betz-Gesetz interaktiv – Streamlit-Dashboard für die Lehre.

Strahltheorie (Rankine/Froude/Betz):
    v'   = (v1 + v2) / 2                     Geschwindigkeit in der Rotorebene
    m    = rho * A * v'                      Massenstrom durch den Rotor
    P    = 1/2 * m * (v1^2 - v2^2)           entnommene Leistung
    P0   = 1/2 * rho * A * v1^3              Leistung des ungestörten Windes durch A
    cP   = P / P0 = 1/2 (1 + x)(1 - x^2),    x = v2 / v1
    max  cP = 16/27 bei x = 1/3
"""

import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Betz-Gesetz", page_icon="🌬️", layout="wide")

# ---------------------------------------------------------------- Sprache
LANG = st.sidebar.radio("Sprache / Language", ["Deutsch", "English"], horizontal=True)
DE = LANG == "Deutsch"


def t(de: str, en: str) -> str:
    return de if DE else en


BETZ = 16 / 27

# ---------------------------------------------------------------- Eingaben
st.sidebar.header(t("Eingaben", "Inputs"))
v1 = st.sidebar.slider(t("v₁ – Windgeschwindigkeit vor dem Rotor [m/s]",
                         "v₁ – wind speed upstream [m/s]"), 3.0, 25.0, 10.0, 0.5)

if "x_ratio" not in st.session_state:
    st.session_state.x_ratio = 0.70

c1, c2 = st.sidebar.columns(2)
if c1.button(t("Betz-Optimum", "Betz optimum"), use_container_width=True):
    st.session_state.x_ratio = 1 / 3
if c2.button(t("Kein Eingriff", "No turbine"), use_container_width=True):
    st.session_state.x_ratio = 1.0

x = st.sidebar.slider(t("v₂ / v₁ – Abbremsung hinter dem Rotor",
                        "v₂ / v₁ – slow-down behind the rotor"),
                      0.0, 1.0, key="x_ratio", step=0.01,
                      help=t("v₂ = Geschwindigkeit weit hinter dem Rotor (Nachlauf). "
                             "Als Verhältnis eingestellt, damit v₂ ≤ v₁ bleibt.",
                             "v₂ = far-wake speed behind the rotor. Set as a ratio "
                             "so that v₂ ≤ v₁ always holds."))
v2 = x * v1

st.sidebar.markdown("---")
D = st.sidebar.slider(t("Rotordurchmesser D [m]", "Rotor diameter D [m]"), 10, 200, 120, 5)
rho = st.sidebar.number_input(t("Luftdichte ρ [kg/m³]", "Air density ρ [kg/m³]"),
                              1.00, 1.35, 1.225, 0.005, format="%.3f")
animate = st.sidebar.checkbox(t("Animation abspielen", "Play animation"), value=True)

# ---------------------------------------------------------------- Physik
A = np.pi * D**2 / 4
vp = (v1 + v2) / 2
mdot = rho * A * vp
P = 0.5 * mdot * (v1**2 - v2**2)
P0 = 0.5 * rho * A * v1**3
P_in = 0.5 * mdot * v1**2          # Leistung im tatsächlich durchströmten Stromrohr
P_wake = 0.5 * mdot * v2**2
cp = P / P0
a = 1 - vp / v1                    # axialer Induktionsfaktor
F = mdot * (v1 - v2)               # Schub


def fmt_power(w: float) -> str:
    if w >= 1e6:
        return f"{w / 1e6:,.2f} MW"
    return f"{w / 1e3:,.0f} kW"


# ---------------------------------------------------------------- Kopf
st.title(t("🌬️ Betz-Gesetz: Wie viel Energie kann ein Windrad dem Wind entziehen?",
           "🌬️ Betz's law: how much energy can a wind turbine extract?"))
st.markdown(t(
    "Ein Windrad gewinnt Energie, indem es den Wind **abbremst** – von **v₁** vor dem Rotor "
    "auf **v₂** dahinter. Bremst es zu wenig, bleibt Energie ungenutzt. Bremst es zu stark, "
    "staut sich die Luft und **strömt am Rotor vorbei** statt hindurch. "
    "Das Optimum liegt bei **v₂ = v₁/3** mit **c_P = 16/27 ≈ 59,3 %**.",
    "A wind turbine extracts energy by **slowing the wind down** – from **v₁** upstream to "
    "**v₂** downstream. Too little braking leaves energy unused; too much braking blocks the "
    "flow so that air **bypasses the rotor**. The optimum is **v₂ = v₁/3** with "
    "**c_P = 16/27 ≈ 59.3 %**."))

m = st.columns(6)
m[0].metric("v₁", f"{v1:.1f} m/s")
m[1].metric(t("v' (Rotorebene)", "v' (rotor plane)"), f"{vp:.1f} m/s")
m[2].metric("v₂", f"{v2:.1f} m/s")
m[3].metric("c_P", f"{cp * 100:.1f} %", f"{(cp - BETZ) * 100:+.1f} %-Pkt. vs. Betz"
            if DE else f"{(cp - BETZ) * 100:+.1f} pp vs. Betz",
            delta_color="off" if abs(cp - BETZ) < 1e-3 else "normal")
m[4].metric(t("Leistung P", "Power P"), fmt_power(P))
m[5].metric(t("Wind durch A (P₀)", "Wind through A (P₀)"), fmt_power(P0))

# ---------------------------------------------------------------- Animation
labels = {
    "tube": t("Stromröhre", "stream tube"),
    "profile": t("Geschwindigkeit entlang der Stromröhre  v(x)/v₁",
                 "velocity along the stream tube  v(x)/v₁"),
    "up": t("vor dem Rotor", "upstream"),
    "rotor": t("Rotor", "rotor"),
    "down": t("Nachlauf", "wake"),
    "clip": t("Stromröhre → ∞ (Luft staut sich)", "stream tube → ∞ (flow blocked)"),
    "paused": t("Animation pausiert", "animation paused"),
}
cfg = dict(v1=v1, v2=v2, cp=cp, animate=animate, L=labels)

ANIM_HTML = """
<div id="wrap" style="width:100%;">
<canvas id="cv" style="width:100%;height:470px;display:block;border-radius:10px;"></canvas>
</div>
<script>
const C = __CFG__;
const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
let W = 1000, H = 470;
function resize(){
  const dpr = window.devicePixelRatio || 1;
  W = cv.clientWidth; H = 470;
  cv.width = W*dpr; cv.height = H*dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
}
resize(); window.addEventListener('resize', resize);

const v1 = C.v1, v2 = C.v2, vp = (v1+v2)/2;
const sceneH = 340, cy = 175;
const Rr = 62;                       // Rotorradius in px
const Rmax = 160;                    // Darstellungsgrenze Stromröhre
function x0(){ return W*0.45; }
function Lx(){ return Math.max(60, W*0.09); }
function vel(x){                     // stetige Abbremsung, v(x0) = v'
  const s = (x - x0())/Lx();
  return v1 + (v2 - v1)*(1 + Math.tanh(s))/2;
}
function Rtube(x){                   // Kontinuität: A(x) v(x) = A v'
  const v = Math.max(vel(x), 1e-6);
  return Math.min(Rr*Math.sqrt(vp/v), Rmax);
}
function col(r){                     // r = v/v1 : 1 blau, 0 rot
  r = Math.max(0, Math.min(1, r));
  const a = [214, 69, 65], b = [33, 113, 181];
  const c = a.map((ai,i)=>Math.round(ai + (b[i]-ai)*r));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// Partikel
const N = 320, P = [];
function newP(xInit){
  const inside = Math.random() < 0.62;
  let eta = inside ? (Math.random()*2-1) : (1 + Math.random()*1.6)*(Math.random()<0.5?-1:1);
  return {x: xInit, eta: eta, inside: inside};
}
for (let i=0;i<N;i++) P.push(newP(Math.random()*1400));

const kpx = 16;                      // px pro (m/s · s)
let theta = 0, last = performance.now();
const omega = 7.0*C.cp/0.593;        // symbolisch: Drehzahl ∝ c_P

function yOf(p){
  const R = Rtube(p.x);
  if (p.inside) return cy + p.eta*R;
  const s = Math.sign(p.eta);
  return cy + s*(R + (Math.abs(p.eta)-1)*Rr*0.95);
}
function speedOf(p){
  if (p.inside) return vel(p.x);
  // außerhalb: annähernd ungestört, leicht beschleunigt am Rand
  const d = Math.abs(p.eta)-1;
  return v1*(1 + 0.12*(1-v2/v1)*Math.exp(-d*2)*Math.exp(-Math.pow((p.x-x0())/(2*Lx()),2)));
}

function arrow(xa, ya, len, color, label){
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(xa, ya); ctx.lineTo(xa+len, ya); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(xa+len+10, ya); ctx.lineTo(xa+len, ya-6); ctx.lineTo(xa+len, ya+6); ctx.fill();
  ctx.font = 'bold 15px sans-serif'; ctx.textAlign = 'left';
  ctx.fillText(label, xa, ya-10);
}

function draw(now){
  const dt = Math.min(0.05, (now-last)/1000); last = now;
  const X0 = x0();
  // Hintergrund
  const g = ctx.createLinearGradient(0,0,0,sceneH);
  g.addColorStop(0,'#eaf3fb'); g.addColorStop(1,'#f8fbfe');
  ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  ctx.fillStyle = '#e3eadf'; ctx.fillRect(0, sceneH-22, W, 22);

  // Stromröhre
  ctx.setLineDash([6,5]); ctx.strokeStyle = 'rgba(40,60,90,0.55)'; ctx.lineWidth = 1.5;
  for (const s of [-1,1]){
    ctx.beginPath();
    for (let xx=0; xx<=W; xx+=4){ const y = cy + s*Rtube(xx); xx===0?ctx.moveTo(xx,y):ctx.lineTo(xx,y); }
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(30,50,80,0.75)'; ctx.font = '12px sans-serif'; ctx.textAlign='left';
  ctx.fillText(C.L.tube, 8, cy - Rtube(0) - 6);
  if (Rtube(W) >= Rmax-0.5){ ctx.textAlign='right'; ctx.fillText(C.L.clip, W-8, cy - Rmax - 6); }

  // Partikel
  for (const p of P){
    const v = speedOf(p);
    if (C.animate) p.x += v*kpx*dt;
    if (p.x > W+20){ Object.assign(p, newP(-Math.random()*60)); continue; }
    if (p.x < -60) continue;
    const y = yOf(p);
    const len = 2 + v*1.1;
    ctx.strokeStyle = col(v/v1); ctx.lineWidth = p.inside ? 2.2 : 1.3;
    ctx.globalAlpha = p.inside ? 0.9 : 0.35;
    ctx.beginPath(); ctx.moveTo(p.x-len, y); ctx.lineTo(p.x, y); ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Turm & Gondel
  ctx.fillStyle = '#9aa5b1';
  ctx.beginPath(); ctx.moveTo(X0+10, cy+8); ctx.lineTo(X0+20, cy+8); ctx.lineTo(X0+25, sceneH-22); ctx.lineTo(X0+5, sceneH-22); ctx.fill();
  ctx.fillStyle = '#c3ccd5'; ctx.fillRect(X0+2, cy-9, 36, 18);
  ctx.beginPath(); ctx.ellipse(X0, cy, 9, 10, 0, 0, 2*Math.PI); ctx.fillStyle='#d7dee5'; ctx.fill();

  // Rotorblätter (Seitenansicht, perspektivisch)
  if (C.animate) theta += omega*dt;
  const blades = [0,1,2].map(k=>{ const ph = theta + k*2*Math.PI/3; return {ph, depth: Math.cos(ph)}; })
                        .sort((a,b)=>a.depth-b.depth);
  for (const b of blades){
    const ty = cy + Rr*Math.sin(b.ph);
    const tx = X0 - 4*b.depth;
    const shade = Math.round(120 + 70*b.depth);
    ctx.fillStyle = `rgb(${shade},${shade+8},${shade+16})`;
    ctx.strokeStyle = 'rgba(30,40,55,0.9)'; ctx.lineWidth = 1.2;
    const w = 14*(0.35+0.65*Math.abs(b.depth));
    ctx.beginPath();
    ctx.moveTo(X0 - w/2, cy); ctx.lineTo(tx - 1, ty); ctx.lineTo(X0 + w/2, cy); ctx.closePath();
    ctx.fill(); ctx.stroke();
  }
  ctx.beginPath(); ctx.arc(X0, cy, 6, 0, 2*Math.PI); ctx.fillStyle='#8895a2'; ctx.fill();

  // Pfeile / Beschriftung
  const sc = 5.5;
  arrow(20, 40, v1*sc, col(1), `v₁ = ${v1.toFixed(1)} m/s`);
  arrow(X0 - vp*sc - 30, sceneH-40, vp*sc, col(vp/v1), `v' = ${vp.toFixed(1)} m/s`);
  arrow(W - 30 - Math.max(v2*sc, 90), 40, Math.max(v2*sc,1), col(v2/v1), `v₂ = ${v2.toFixed(1)} m/s`);
  ctx.font = '12px sans-serif'; ctx.fillStyle='#445'; ctx.textAlign='center';
  ctx.fillText(C.L.up, W*0.14, sceneH-6); ctx.fillText(C.L.rotor, X0, sceneH-6); ctx.fillText(C.L.down, W*0.84, sceneH-6);

  // Profil v(x)/v1
  const top = sceneH+18, bot = H-14, ph = bot-top;
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, sceneH, W, H-sceneH);
  ctx.strokeStyle = '#ccd'; ctx.lineWidth = 1;
  for (const f of [0, 1/3, 0.5, 1]){
    const y = bot - f*ph; ctx.beginPath(); ctx.moveTo(40,y); ctx.lineTo(W-8,y); ctx.stroke();
    ctx.fillStyle='#667'; ctx.font='11px sans-serif'; ctx.textAlign='right';
    ctx.fillText(f===1/3?'1/3':f===0.5?'1/2':String(f), 36, y+4);
  }
  ctx.beginPath(); ctx.moveTo(X0, top-4); ctx.lineTo(X0, bot); ctx.strokeStyle='#99a'; ctx.setLineDash([3,3]); ctx.stroke(); ctx.setLineDash([]);
  ctx.lineWidth = 3;
  for (let xx=40; xx<W-8; xx+=3){
    const r1 = vel(xx)/v1, r2 = vel(xx+3)/v1;
    ctx.strokeStyle = col(r1);
    ctx.beginPath(); ctx.moveTo(xx, bot-r1*ph); ctx.lineTo(xx+3, bot-r2*ph); ctx.stroke();
  }
  ctx.beginPath(); ctx.arc(X0, bot - (vp/v1)*ph, 5, 0, 2*Math.PI); ctx.fillStyle = col(vp/v1); ctx.fill();
  ctx.fillStyle='#334'; ctx.font='12px sans-serif'; ctx.textAlign='left';
  ctx.fillText(C.L.profile, 46, top-4);

  if (!C.animate){ ctx.fillStyle='rgba(40,40,60,0.6)'; ctx.textAlign='right'; ctx.fillText(C.L.paused, W-10, 18); }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script>
"""
components.html(ANIM_HTML.replace("__CFG__", json.dumps(cfg)), height=480)

st.caption(t(
    "Farbe = lokale Geschwindigkeit (blau = v₁, rot = langsam). Die Stromröhre weitet sich "
    "hinter dem Rotor auf, weil durch jeden Querschnitt derselbe Massenstrom fließt "
    "(A·v = konst.). Rotordrehzahl hier symbolisch ∝ c_P.",
    "Colour = local speed (blue = v₁, red = slow). The stream tube widens behind the rotor "
    "because the same mass flow passes every cross-section (A·v = const.). Rotor speed is "
    "drawn symbolically ∝ c_P."))

# ---------------------------------------------------------------- Diagramme
xs = np.linspace(0, 1, 401)
cp_curve = 0.5 * (1 + xs) * (1 - xs**2)
mass_n = (1 + xs) / 2
dE_n = 1 - xs**2

col_l, col_r = st.columns([3, 2])

with col_l:
    st.subheader(t("Warum gibt es ein Optimum?", "Why is there an optimum?"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=mass_n, name=t("Massenstrom  ṁ/ṁ₀ = (1+x)/2",
                                                    "mass flow  ṁ/ṁ₀ = (1+x)/2"),
                             line=dict(color="#2171b5", width=2, dash="dash")))
    fig.add_trace(go.Scatter(x=xs, y=dE_n, name=t("entnommene Energie je kg  1−x²",
                                                  "energy taken per kg  1−x²"),
                             line=dict(color="#d6453f", width=2, dash="dot")))
    fig.add_trace(go.Scatter(x=xs, y=cp_curve, name="c_P = ½ (1+x)(1−x²)",
                             line=dict(color="#222", width=3.5)))
    fig.add_hline(y=BETZ, line=dict(color="#888", width=1, dash="dash"),
                  annotation_text="16/27 ≈ 0,593" if DE else "16/27 ≈ 0.593",
                  annotation_position="top left")
    fig.add_vline(x=1 / 3, line=dict(color="#888", width=1, dash="dash"))
    fig.add_trace(go.Scatter(x=[x], y=[cp], mode="markers", showlegend=False,
                             marker=dict(size=15, color="#f4a300", line=dict(color="#222", width=2)),
                             hovertemplate="x = %{x:.2f}<br>c_P = %{y:.3f}<extra></extra>"))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title="x = v₂ / v₁", yaxis_title=t("normiert", "normalised"),
                      yaxis_range=[0, 1.05], xaxis_range=[0, 1],
                      legend=dict(orientation="h", y=-0.22), template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(t(
        "**x → 1:** fast der volle Massenstrom, aber jedes kg Luft gibt kaum Energie ab.  \n"
        "**x → 0:** jedes kg gibt viel ab, aber nur noch halb so viel Luft strömt durch den Rotor.  \n"
        "Das Produkt beider Effekte ist bei **x = 1/3** maximal.",
        "**x → 1:** almost full mass flow, but each kg of air gives up hardly any energy.  \n"
        "**x → 0:** each kg gives up a lot, but only half as much air passes the rotor.  \n"
        "The product of both effects peaks at **x = 1/3**."))

with col_r:
    st.subheader(t("Energiebilanz im Stromrohr", "Energy balance of the stream tube"))
    bar = go.Figure()
    bar.add_trace(go.Bar(name=t("entnommen (P)", "extracted (P)"), x=[t("Stromrohr", "Stream tube")],
                         y=[P / 1e6], marker_color="#f4a300",
                         text=[f"{P / P_in * 100:.0f} %"], textposition="inside"))
    bar.add_trace(go.Bar(name=t("bleibt im Nachlauf", "left in the wake"), x=[t("Stromrohr", "Stream tube")],
                         y=[P_wake / 1e6], marker_color="#d6453f",
                         text=[f"{P_wake / P_in * 100:.0f} %"], textposition="inside"))
    bar.add_trace(go.Bar(name=t("Wind durch A ohne Anlage (P₀)", "wind through A without turbine (P₀)"),
                         x=[t("Referenz", "Reference")], y=[P0 / 1e6], marker_color="#2171b5"))
    bar.add_hline(y=BETZ * P0 / 1e6, line=dict(color="#222", dash="dash", width=1.5),
                  annotation_text=t("Betz-Grenze 59,3 % von P₀", "Betz limit 59.3 % of P₀"),
                  annotation_position="top left")
    bar.update_layout(barmode="stack", height=420, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis_title=t("Leistung [MW]", "Power [MW]"), template="plotly_white",
                      legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(bar, use_container_width=True)
    st.caption(t(
        "Linker Balken: die Luft, die tatsächlich durch den Rotor strömt (½ ṁ v₁²) – sie ist "
        "kleiner als P₀, weil sich die Strömung vor dem Rotor aufstaut.",
        "Left bar: air that actually passes the rotor (½ ṁ v₁²) – smaller than P₀ because the "
        "flow is blocked ahead of the rotor."))

# ---------------------------------------------------------------- Leistung über v2
st.subheader(t(f"Leistung über v₂ bei v₁ = {v1:.1f} m/s und D = {D} m",
               f"Power vs. v₂ at v₁ = {v1:.1f} m/s and D = {D} m"))
v2s = xs * v1
Ps = 0.5 * rho * A * (v1 + v2s) / 2 * (v1**2 - v2s**2)
f2 = go.Figure()
f2.add_trace(go.Scatter(x=v2s, y=Ps / 1e6, name="P(v₂)", line=dict(color="#222", width=3)))
f2.add_hline(y=P0 / 1e6, line=dict(color="#2171b5", dash="dot"),
             annotation_text=f"P₀ = {fmt_power(P0)}", annotation_position="bottom right")
f2.add_trace(go.Scatter(x=[v2], y=[P / 1e6], mode="markers", showlegend=False,
                        marker=dict(size=14, color="#f4a300", line=dict(color="#222", width=2))))
f2.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), template="plotly_white",
                 xaxis_title="v₂ [m/s]", yaxis_title="P [MW]", showlegend=False)
st.plotly_chart(f2, use_container_width=True)

k = st.columns(4)
k[0].metric(t("Massenstrom ṁ", "Mass flow ṁ"), f"{mdot / 1e3:,.1f} t/s")
k[1].metric(t("Induktionsfaktor a = 1 − v'/v₁", "Induction factor a = 1 − v'/v₁"), f"{a:.3f}")
k[2].metric(t("Schub F = ṁ (v₁ − v₂)", "Thrust F = ṁ (v₁ − v₂)"), f"{F / 1e3:,.0f} kN")
k[3].metric(t("Rotorfläche A", "Rotor area A"), f"{A:,.0f} m²")

# ---------------------------------------------------------------- Herleitung
with st.expander(t("📐 Herleitung", "📐 Derivation"), expanded=False):
    st.markdown(t("**1. Leistung = Massenstrom × Änderung der kinetischen Energie je kg**",
                  "**1. Power = mass flow × change of kinetic energy per kg**"))
    st.latex(r"P = \tfrac12\,\dot m\,(v_1^2 - v_2^2), \qquad \dot m = \rho\,A\,v'")
    st.markdown(t("**2. Leistung = Schub × Geschwindigkeit in der Rotorebene** (Froude)",
                  "**2. Power = thrust × velocity in the rotor plane** (Froude)"))
    st.latex(r"P = F\,v' = \dot m\,(v_1 - v_2)\,v' \;\Rightarrow\; v' = \frac{v_1 + v_2}{2}")
    st.markdown(t("**3. Einsetzen und auf die Windleistung durch A beziehen**",
                  "**3. Substitute and normalise by the wind power through A**"))
    st.latex(r"c_P = \frac{P}{\tfrac12 \rho A v_1^3} = \tfrac12\,(1+x)(1-x^2), \qquad x = \frac{v_2}{v_1}")
    st.markdown(t("**4. Maximum suchen**", "**4. Find the maximum**"))
    st.latex(r"\frac{dc_P}{dx} = \tfrac12\,(1 - 2x - 3x^2) = 0 \;\Rightarrow\; x = \tfrac13"
             r"\;\Rightarrow\; c_{P,\max} = \tfrac{16}{27} \approx 0{,}593")

with st.expander(t("🎓 Fragen zum Ausprobieren", "🎓 Questions to explore"), expanded=False):
    st.markdown(t(
        "1. Stelle v₂/v₁ = 1 ein. Warum ist die Leistung null, obwohl der volle Wind durch den Rotor strömt?\n"
        "2. Stelle v₂/v₁ = 0 ein. Warum ist c_P nicht 100 %, obwohl die Luft komplett abgebremst wird?\n"
        "3. Ändere v₁ von 5 auf 10 m/s. Um welchen Faktor steigt P? Ändert sich c_P?\n"
        "4. Wie verhält sich der Schub F im Betz-Optimum im Vergleich zu v₂/v₁ = 0,6? Was bedeutet das für die Turmlast?\n"
        "5. Reale Anlagen erreichen c_P ≈ 0,45–0,50. Welche Verluste fehlen in der Strahltheorie?",
        "1. Set v₂/v₁ = 1. Why is the power zero although the full wind passes the rotor?\n"
        "2. Set v₂/v₁ = 0. Why is c_P not 100 % although the air is stopped completely?\n"
        "3. Change v₁ from 5 to 10 m/s. By what factor does P rise? Does c_P change?\n"
        "4. How does the thrust F at the Betz optimum compare with v₂/v₁ = 0.6? What does this mean for tower loads?\n"
        "5. Real turbines reach c_P ≈ 0.45–0.50. Which losses are missing in momentum theory?"))


# =================================================================== Teil 2: Auftrieb
st.divider()
st.header(t("✈️ Auftriebsläufer: Wie das Rotorblatt die Kraft erzeugt",
            "✈️ Lift-driven rotors: how the blade produces its force"))
st.markdown(t(
    "Die Strahltheorie oben sagt, **wie viel** Energie man entnehmen kann – aber nicht, **wie**. "
    "Moderne Windräder sind **Auftriebsläufer**: Das Blatt bewegt sich quer zum Wind, ähnlich "
    "einem Flugzeugflügel. Es „sieht“ deshalb nicht nur den Wind v', sondern auch den **Fahrtwind** "
    "aus seiner eigenen Bewegung u = ω·r. Beides zusammen ergibt die **Anströmung w**. "
    "Am Profil entsteht **Auftrieb L senkrecht zu w** und ein kleiner **Widerstand D parallel zu w**. "
    "Zerlegt man diese Kräfte, bleibt eine **Umfangskraft in Drehrichtung** (treibt den Rotor an) "
    "und ein **Schub in Windrichtung** (belastet den Turm).",
    "Momentum theory above tells **how much** energy can be extracted – not **how**. Modern wind "
    "turbines are **lift-driven**: the blade moves across the wind like an aircraft wing. It "
    "therefore sees not only the wind v' but also the **head wind** from its own motion u = ω·r. "
    "Together they form the **relative wind w**. The airfoil produces **lift L perpendicular to w** "
    "and a small **drag D parallel to w**. Resolving these forces leaves a **tangential force in the "
    "direction of rotation** (drives the rotor) and an **axial thrust** (loads the tower)."))

CL_MAX_A = 12.0


def polar(alpha_deg):
    """Vereinfachte Profilpolare (gewölbtes Profil, Strömungsabriss ab 12°)."""
    a_ = np.asarray(alpha_deg, dtype=float)
    cl_ = np.where(a_ <= CL_MAX_A, 0.3 + 0.1 * a_,
                   np.maximum(1.5 - 0.06 * (a_ - CL_MAX_A), 0.6))
    cl_ = np.maximum(cl_, -1.0)
    cd_ = np.where(np.abs(a_) <= CL_MAX_A, 0.007 + 0.00012 * a_**2,
                   0.007 + 0.00012 * CL_MAX_A**2 + 0.03 * (np.abs(a_) - CL_MAX_A))
    return cl_, cd_


al_grid = np.linspace(-10, 30, 801)
cl_g, cd_g = polar(al_grid)
ALPHA_OPT = float(al_grid[np.argmax(cl_g / cd_g)])

lc1, lc2, lc3 = st.columns(3)
lam = lc1.slider(t("Schnelllaufzahl λ = u_Spitze / v₁", "Tip-speed ratio λ = u_tip / v₁"),
                 1.0, 12.0, 7.0, 0.5)
rr = lc2.slider(t("Betrachteter Radius r / R", "Blade section r / R"), 0.2, 1.0, 0.75, 0.05)

u = lam * rr * v1
w = float(np.hypot(vp, u))
phi = float(np.degrees(np.arctan2(vp, u)))

if "beta" not in st.session_state:
    st.session_state.beta = round(phi - ALPHA_OPT, 1)
if lc3.button(t(f"Blattwinkel optimal (α = {ALPHA_OPT:.1f}°)",
                f"Optimal blade angle (α = {ALPHA_OPT:.1f}°)"), use_container_width=True):
    st.session_state.beta = float(np.clip(round(phi - ALPHA_OPT, 1), -10.0, 60.0))
beta = lc3.slider(t("Blattwinkel β zur Rotorebene [°]", "Blade angle β to rotor plane [°]"),
                  -10.0, 60.0, key="beta", step=0.5,
                  help=t("Summe aus Verwindung und Pitch an diesem Radius.",
                         "Sum of twist and pitch at this radius."))

alpha = phi - beta
cl, cd = (float(v) for v in polar(alpha))
q_dyn = 0.5 * rho * w**2                    # Staudruck
F_L, F_D = q_dyn * cl, q_dyn * cd           # je m Spannweite bei 1 m Profiltiefe
ph_r = np.radians(phi)
F_t = F_L * np.sin(ph_r) - F_D * np.cos(ph_r)   # Umfangskraft (antreibend)
F_a = F_L * np.cos(ph_r) + F_D * np.sin(ph_r)   # Axialkraft (Schub)

stalled = alpha > CL_MAX_A
lm = st.columns(6)
lm[0].metric(t("Fahrtwind u = λ·(r/R)·v₁", "Head wind u = λ·(r/R)·v₁"), f"{u:.1f} m/s")
lm[1].metric(t("Anströmung w", "Relative wind w"), f"{w:.1f} m/s", f"{w / v1:.1f} × v₁",
             delta_color="off")
lm[2].metric(t("Anströmwinkel φ", "Inflow angle φ"), f"{phi:.1f}°")
lm[3].metric(t("Anstellwinkel α = φ − β", "Angle of attack α = φ − β"), f"{alpha:.1f}°",
             t("Strömungsabriss!", "stall!") if stalled else None,
             delta_color="inverse" if stalled else "off")
lm[4].metric("c_L / c_D", f"{cl / cd:.0f}" if cd > 0 else "–")
lm[5].metric(t("Antriebskraft F_t", "Driving force F_t"), f"{F_t:,.0f} N/m",
             help=t("Je Meter Blattlänge bei 1 m Profiltiefe.", "Per metre span, 1 m chord."))

lift_cfg = dict(v1=v1, vp=vp, u=u, w=w, phi=phi, beta=beta, alpha=alpha, cl=cl, cd=cd,
                lam=lam, rr=rr, Ft=F_t, Fa=F_a, animate=animate,
                L=dict(front=t("Frontansicht Rotor", "Rotor front view"),
                       elem=t("Blattschnitt bei r – mitbewegt", "Blade section at r – moving frame"),
                       wind=t("Wind v₁ (in die Bildebene)", "wind v₁ (into the page)"),
                       head=t("−u (Fahrtwind)", "−u (head wind)"),
                       plane=t("Rotorebene", "rotor plane"),
                       move=t("Blattbewegung", "blade motion"),
                       lift=t("Auftrieb L", "lift L"), drag=t("Widerstand D (×5)", "drag D (×5)"),
                       drive=t("Antrieb F_t", "drive F_t"), thrust=t("Schub F_a", "thrust F_a"),
                       stall=t("STRÖMUNGSABRISS", "STALL")))

LIFT_HTML = """
<div style="display:grid;grid-template-columns:minmax(0,36fr) minmax(0,64fr);gap:10px;width:100%;">
  <canvas id="fv" style="width:100%;height:430px;display:block;border-radius:10px;"></canvas>
  <canvas id="be" style="width:100%;height:430px;display:block;border-radius:10px;"></canvas>
</div>
<script>
const C = __CFG__;
const H = 430;
function setup(id){
  const cv = document.getElementById(id), ctx = cv.getContext('2d');
  const o = {cv, ctx, W: 300};
  o.resize = () => { const d = window.devicePixelRatio||1; o.W = cv.clientWidth;
    cv.width = o.W*d; cv.height = H*d; ctx.setTransform(d,0,0,d,0,0); };
  o.resize(); window.addEventListener('resize', o.resize); return o;
}
const F = setup('fv'), B = setup('be');
const rad = Math.PI/180;
function arrow(ctx, x1,y1,x2,y2, color, width, label, lx, ly, align){
  const ang = Math.atan2(y2-y1, x2-x1), len = Math.hypot(x2-x1,y2-y1);
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = width;
  if (len < 2) return;
  const hl = Math.min(12, len*0.5);
  ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2 - hl*Math.cos(ang)*0.8, y2 - hl*Math.sin(ang)*0.8); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x2,y2);
  ctx.lineTo(x2 - hl*Math.cos(ang-0.4), y2 - hl*Math.sin(ang-0.4));
  ctx.lineTo(x2 - hl*Math.cos(ang+0.4), y2 - hl*Math.sin(ang+0.4)); ctx.fill();
  if (label){ ctx.font='bold 13px sans-serif'; ctx.textAlign = align||'left';
    ctx.fillText(label, lx===undefined?x2+6:lx, ly===undefined?y2:ly); }
}

// ---------- Frontansicht
let theta = 0, last = performance.now();
const omegaVis = 0.35*C.lam;
function drawFront(dt){
  const ctx = F.ctx, W = F.W;
  ctx.fillStyle = '#eef4fa'; ctx.fillRect(0,0,W,H);
  const cx = W/2, cy = H/2 + 10, R = Math.min(W, H)*0.40;
  ctx.fillStyle='#9aa5b1'; ctx.beginPath(); ctx.moveTo(cx-5,cy); ctx.lineTo(cx+5,cy); ctx.lineTo(cx+9,H); ctx.lineTo(cx-9,H); ctx.fill();
  const rr = C.rr*R;
  ctx.setLineDash([4,4]); ctx.strokeStyle='rgba(244,163,0,0.8)'; ctx.lineWidth=1.5;
  ctx.beginPath(); ctx.arc(cx,cy,rr,0,2*Math.PI); ctx.stroke(); ctx.setLineDash([]);
  if (C.animate) theta += omegaVis*dt;
  for (let k=0;k<3;k++){
    const a = theta + k*2*Math.PI/3;
    const ux = Math.cos(a), uy = Math.sin(a), nx = -uy, ny = ux;
    ctx.beginPath();
    ctx.moveTo(cx + nx*6, cy + ny*6);
    ctx.quadraticCurveTo(cx + ux*R*0.25 + nx*13, cy + uy*R*0.25 + ny*13, cx + ux*R, cy + uy*R);
    ctx.quadraticCurveTo(cx + ux*R*0.3 - nx*4, cy + uy*R*0.3 - ny*4, cx - nx*6, cy - ny*6);
    ctx.fillStyle = k===0 ? '#7d8a99' : '#a9b4c0'; ctx.fill();
    ctx.strokeStyle='#4a5563'; ctx.lineWidth=1; ctx.stroke();
  }
  ctx.beginPath(); ctx.arc(cx,cy,10,0,2*Math.PI); ctx.fillStyle='#5d6876'; ctx.fill();
  // Schnitt-Markierung auf Blatt 0 + Umfangsgeschwindigkeit
  const a0 = theta, px = cx + Math.cos(a0)*rr, py = cy + Math.sin(a0)*rr;
  ctx.beginPath(); ctx.arc(px,py,6,0,2*Math.PI); ctx.fillStyle='#f4a300'; ctx.fill();
  const tx = -Math.sin(a0), ty = Math.cos(a0), ul = 18 + 55*Math.min(1, C.u/(12*C.v1));
  arrow(ctx, px,py, px+tx*ul, py+ty*ul, '#333', 2.5, `u = ${C.u.toFixed(0)} m/s`);
  ctx.fillStyle='#223'; ctx.font='bold 13px sans-serif'; ctx.textAlign='left';
  ctx.fillText(C.L.front, 10, 20);
  ctx.font='12px sans-serif'; ctx.fillText('⊗ ' + C.L.wind, 10, 38);
  ctx.fillText(`λ = ${C.lam.toFixed(1)}`, 10, H-12);
}

// ---------- Blattschnitt
const N = 70, parts = [];
for (let i=0;i<N;i++) parts.push({a: Math.random()*900-450, b: (Math.random()*2-1)*190});
function airfoil(t){            // NACA 4415 – Ober-/Unterseite im Profilkoordinatensystem
  const m=0.04, p=0.4, th=0.15;
  const yt = 5*th*(0.2969*Math.sqrt(t)-0.126*t-0.3516*t*t+0.2843*t*t*t-0.1015*t*t*t*t);
  const yc = t<p ? m/(p*p)*(2*p*t-t*t) : m/((1-p)*(1-p))*((1-2*p)+2*p*t-t*t);
  return {up: yc+yt, lo: yc-yt};
}
function drawElem(dt){
  const ctx = B.ctx, W = B.W;
  ctx.fillStyle = '#f7fafc'; ctx.fillRect(0,0,W,H);
  const cx = W*0.58, cy = H*0.45;
  // x = Windrichtung (Bild nach unten), y = Rotorebene (Bild nach rechts); Blatt bewegt sich nach links
  const S = (x,y) => [cx + y, cy + x];
  const ph = C.phi*rad, be = C.beta*rad;
  const wh = [Math.sin(ph), Math.cos(ph)];        // Richtung Anströmung
  const nl = [Math.cos(ph), -Math.sin(ph)];       // Richtung Auftrieb
  // Rotorebene
  ctx.setLineDash([6,5]); ctx.strokeStyle='#99a'; ctx.lineWidth=1.2;
  ctx.beginPath(); ctx.moveTo(10, cy); ctx.lineTo(W-10, cy); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle='#778'; ctx.font='12px sans-serif'; ctx.textAlign='right'; ctx.fillText(C.L.plane, W-12, cy-6);
  arrow(ctx, W-30, 66, W-110, 66, '#555', 2.5, C.L.move, W-30, 84, 'right');

  // Stromlinien (relative Anströmung, Umlenkung hinter dem Profil)
  const spd = Math.min(320, C.w*5.5);
  for (const p of parts){
    if (C.animate) p.a += spd*dt;
    if (p.a > 480){ p.a = -480 - Math.random()*60; p.b = (Math.random()*2-1)*190; }
    const g = Math.exp(-(p.b*p.b)/(90*90));
    const smooth = 0.5*(1+Math.tanh(p.a/60));
    const defl = -45*C.cl*g*smooth;                         // Abwind: Luft wird gegen L umgelenkt
    const bump = Math.sign(p.b||1)*18*Math.exp(-(p.a*p.a)/(70*70))*Math.exp(-(p.b*p.b)/(30*30));
    const bb = p.b + defl + bump, ang = Math.atan2(-45*C.cl*g*(1-Math.tanh(p.a/60)**2)/120, 1);
    const x = p.a*wh[0] + bb*nl[0], y = p.a*wh[1] + bb*nl[1];
    const len = 16;
    const dx = (wh[0]*Math.cos(ang) + nl[0]*Math.sin(ang))*len, dy = (wh[1]*Math.cos(ang) + nl[1]*Math.sin(ang))*len;
    const [X,Y] = S(x,y), [X0,Y0] = S(x-dx, y-dy);
    ctx.strokeStyle='rgba(90,110,140,0.45)'; ctx.lineWidth=1.6;
    ctx.beginPath(); ctx.moveTo(X0,Y0); ctx.lineTo(X,Y); ctx.stroke();
  }

  // Profil
  const c = Math.min(210, W*0.32), d = [Math.sin(be), Math.cos(be)], n = [Math.cos(be), -Math.sin(be)];
  const le = [-d[0]*c*0.3, -d[1]*c*0.3];
  ctx.beginPath();
  const pts = [];
  for (let i=0;i<=40;i++){ const tt = 0.5*(1-Math.cos(Math.PI*i/40)); const f = airfoil(tt);
    pts.push([le[0]+d[0]*tt*c + n[0]*f.up*c, le[1]+d[1]*tt*c + n[1]*f.up*c]); }
  for (let i=40;i>=0;i--){ const tt = 0.5*(1-Math.cos(Math.PI*i/40)); const f = airfoil(tt);
    pts.push([le[0]+d[0]*tt*c + n[0]*f.lo*c, le[1]+d[1]*tt*c + n[1]*f.lo*c]); }
  pts.forEach((q,i)=>{ const [X,Y]=S(q[0],q[1]); i?ctx.lineTo(X,Y):ctx.moveTo(X,Y); });
  ctx.closePath(); ctx.fillStyle = C.alpha>12 ? '#e9b3b0' : '#c9d3dd'; ctx.fill();
  ctx.strokeStyle='#334'; ctx.lineWidth=1.5; ctx.stroke();
  // Sehne
  ctx.setLineDash([3,3]); ctx.strokeStyle='#556';
  const [s1x,s1y]=S(le[0]-d[0]*30, le[1]-d[1]*30), [s2x,s2y]=S(le[0]+d[0]*(c+30), le[1]+d[1]*(c+30));
  ctx.beginPath(); ctx.moveTo(s1x,s1y); ctx.lineTo(s2x,s2y); ctx.stroke(); ctx.setLineDash([]);

  // Geschwindigkeitsdreieck – endet an der Profilnase
  const vs = Math.min(190, W*0.36)/Math.max(C.w, 1e-6);
  const tip = le, O = [tip[0]-C.w*vs*wh[0], tip[1]-C.w*vs*wh[1]], M = [O[0]+C.vp*vs, O[1]];
  let [ax,ay]=S(...O), [bx,by]=S(...M), [tx2,ty2]=S(...tip);
  arrow(ctx, ax,ay,bx,by, '#2171b5', 3, `v' = ${C.vp.toFixed(1)} m/s`, ax-6, (ay+by)/2+4, 'right');
  arrow(ctx, bx,by,tx2,ty2, '#666', 3, `${C.L.head} = ${C.u.toFixed(0)} m/s`, (bx+tx2)/2, by+18, 'center');
  arrow(ctx, ax,ay,tx2,ty2, '#7b3fa0', 3.5, `w = ${C.w.toFixed(1)} m/s`, (ax+tx2)/2, Math.min(ay,ty2)-10, 'center');

  // Kräfte im Druckpunkt (≈ c/4)
  const ac = [le[0]+d[0]*c*0.25, le[1]+d[1]*c*0.25];
  const fs = 120;                     // px je c_L = 1
  const Lv = [nl[0]*C.cl*fs, nl[1]*C.cl*fs], Dv = [wh[0]*C.cd*fs*5, wh[1]*C.cd*fs*5];
  const [px,py] = S(...ac);
  const s = Math.sin(ph), co = Math.cos(ph);
  const ct = C.cl*s - C.cd*co, ca = C.cl*co + C.cd*s;
  // Komponenten
  let [qx,qy] = S(ac[0], ac[1]-ct*fs);
  arrow(ctx, px,py, qx,qy, '#f4a300', 5, `${C.L.drive}`, Math.min(qx,px)-4, qy-24, 'right');
  [qx,qy] = S(ac[0]+ca*fs, ac[1]);
  arrow(ctx, px,py, qx,qy, '#888', 3, `${C.L.thrust}`, qx+8, qy+4);
  // L und D
  [qx,qy] = S(ac[0]+Lv[0], ac[1]+Lv[1]);
  arrow(ctx, px,py, qx,qy, '#2a9d8f', 3.5, C.L.lift, qx-8, qy+16, 'right');
  [qx,qy] = S(ac[0]+Dv[0], ac[1]+Dv[1]);
  arrow(ctx, px,py, qx,qy, '#d6453f', 2.5, C.L.drag, qx+8, qy-6);

  ctx.fillStyle='#223'; ctx.font='bold 13px sans-serif'; ctx.textAlign='left';
  ctx.fillText(C.L.elem, 10, 20);
  ctx.font='12px sans-serif';
  ctx.fillText(`φ = ${C.phi.toFixed(1)}°   β = ${C.beta.toFixed(1)}°   α = ${C.alpha.toFixed(1)}°   c_L = ${C.cl.toFixed(2)}   c_D = ${C.cd.toFixed(3)}`, 10, 38);
  if (C.alpha > 12){ ctx.fillStyle='#c0392b'; ctx.font='bold 15px sans-serif'; ctx.fillText(C.L.stall, 10, 60); }
}
function loop(now){
  const dt = Math.min(0.05,(now-last)/1000); last = now;
  drawFront(dt); drawElem(dt); requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
</script>
"""
components.html(LIFT_HTML.replace("__CFG__", json.dumps(lift_cfg)), height=440)

st.caption(t(
    "Rechts: Sicht eines Beobachters, der mit dem Blatt mitfährt (Blatt läuft nach links, Wind "
    "kommt von oben). Die Luft trifft fast waagrecht auf das Profil (Fahrtwind + Wind) und wird hinter dem Profil umgelenkt – die Gegenkraft ist der Auftrieb. "
    "Gelb = Anteil in Drehrichtung (Drehmoment), grau = Schub auf den Turm. "
    "Die Axialgeschwindigkeit v' stammt aus dem Betz-Teil oben.",
    "Right: view of an observer moving with the blade (blade moves left, wind comes from above). "
    "Air meets the airfoil almost horizontally (head wind + wind) "
    "and is deflected behind the airfoil – the reaction force is lift. Yellow = component in the "
    "direction of rotation (torque), grey = thrust on the tower. The axial speed v' is taken from "
    "the Betz section above."))

pc1, pc2 = st.columns(2)
with pc1:
    st.subheader(t("Profilpolare", "Airfoil polar"))
    fp = go.Figure()
    fp.add_trace(go.Scatter(x=al_grid, y=cl_g, name="c_L", line=dict(color="#2a9d8f", width=3)))
    fp.add_trace(go.Scatter(x=al_grid, y=cl_g / cd_g / 100, name=t("c_L/c_D ÷ 100", "c_L/c_D ÷ 100"),
                            line=dict(color="#555", width=2, dash="dot")))
    fp.add_vrect(x0=CL_MAX_A, x1=30, fillcolor="#d6453f", opacity=0.08, line_width=0,
                 annotation_text=t("Strömungsabriss", "stall"), annotation_position="top left")
    fp.add_trace(go.Scatter(x=[alpha], y=[cl], mode="markers", showlegend=False,
                            marker=dict(size=14, color="#f4a300", line=dict(color="#222", width=2))))
    fp.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), template="plotly_white",
                     xaxis_title=t("Anstellwinkel α [°]", "angle of attack α [°]"),
                     legend=dict(orientation="h", y=-0.2), xaxis_range=[-10, 30])
    st.plotly_chart(fp, use_container_width=True)
    st.caption(t("Vereinfachte Polare eines gewölbten Profils (illustrativ, keine Messdaten).",
                 "Simplified polar of a cambered airfoil (illustrative, not measured data)."))

with pc2:
    st.subheader(t("Auftriebs- vs. Widerstandsläufer", "Lift vs. drag rotors"))
    LD = float(np.clip(cl / cd if cd > 0 and cl > 0 else 5, 5, 200))
    lg = np.linspace(0.5, 14, 300)
    Bn = 3
    cp_lift = (16 / 27) * lg / (lg + 1.32 + ((lg - 8) / 20) ** 2 / Bn ** (2 / 3)) \
        - 0.57 * lg**2 / (LD * (lg + 1 / (2 * Bn)))
    cp_lift = np.clip(cp_lift, 0, None)
    lw = np.linspace(0, 1, 200)
    cp_drag = 1.2 * lw * (1 - lw) ** 2
    fc = go.Figure()
    fc.add_trace(go.Scatter(x=lg, y=cp_lift, name=t(f"Auftriebsläufer, 3 Blätter, c_L/c_D = {LD:.0f}",
                                                    f"lift rotor, 3 blades, c_L/c_D = {LD:.0f}"),
                            line=dict(color="#2a9d8f", width=3)))
    fc.add_trace(go.Scatter(x=lw, y=cp_drag, name=t("Widerstandsläufer (c_D = 1,2)", "drag rotor (c_D = 1.2)"),
                            line=dict(color="#d6453f", width=3)))
    fc.add_hline(y=BETZ, line=dict(color="#888", dash="dash"), annotation_text="Betz 16/27",
                 annotation_position="top right")
    i_l = int(np.argmin(np.abs(lg - lam)))
    fc.add_trace(go.Scatter(x=[lam], y=[cp_lift[i_l]], mode="markers", showlegend=False,
                            marker=dict(size=14, color="#f4a300", line=dict(color="#222", width=2))))
    fc.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), template="plotly_white",
                     xaxis_title=t("Schnelllaufzahl λ", "tip-speed ratio λ"), yaxis_title="c_P",
                     yaxis_range=[0, 0.65], legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fc, use_container_width=True)
    st.caption(t("Auftriebsläufer: Näherung nach Wilson et al. (1976), inkl. Drall-, Spitzen- und "
                 "Profilverlusten. Widerstandsläufer: c_P = c_D·λ(1−λ)², max. 4/27·c_D bei λ = 1/3.",
                 "Lift rotor: approximation after Wilson et al. (1976) incl. wake rotation, tip and "
                 "profile losses. Drag rotor: c_P = c_D·λ(1−λ)², max. 4/27·c_D at λ = 1/3."))

wa, wb = st.columns(2)
wa.markdown(t(
    "**Widerstandsläufer** (z. B. Savonius, Schalenkreuz-Anemometer)  \n"
    "Der Wind *drückt* auf eine Fläche. Die Fläche kann höchstens so schnell werden wie der Wind "
    "(λ < 1), und je schneller sie wird, desto schwächer die Anströmung v − u. "
    "→ c_P ≈ 0,15–0,2, viel Material pro kW.",
    "**Drag rotor** (e.g. Savonius, cup anemometer)  \n"
    "The wind *pushes* on a surface. The surface can never move faster than the wind (λ < 1), "
    "and the faster it moves, the weaker the inflow v − u. → c_P ≈ 0.15–0.2, much material per kW."))
wb.markdown(t(
    "**Auftriebsläufer** (moderne 3-Blatt-Anlage)  \n"
    "Das Blatt bewegt sich *quer* zum Wind und erzeugt sich so seine eigene, viel stärkere "
    "Anströmung w (bei λ = 7 etwa 5–7 × v₁). Weil Kraft ∝ w² ist, genügen schlanke Blätter. "
    "→ c_P ≈ 0,45–0,50, nahe an Betz.",
    "**Lift rotor** (modern three-blade turbine)  \n"
    "The blade moves *across* the wind and thus creates its own, much stronger inflow w "
    "(about 5–7 × v₁ at λ = 7). Since force ∝ w², slender blades are enough. "
    "→ c_P ≈ 0.45–0.50, close to Betz."))

with st.expander(t("🎓 Fragen zum Auftriebsläufer", "🎓 Questions on lift rotors"), expanded=False):
    st.markdown(t(
        "1. Verschiebe r/R von 0,2 auf 1,0 bei festem β. Was passiert mit φ und α? Warum sind Rotorblätter **verwunden**?\n"
        "2. Senke λ bei festem β – das entspricht mehr Wind bei fester Drehzahl. Ab wann reißt die Strömung ab? So regeln Stall-Anlagen.\n"
        "3. Erhöhe β (Pitch) bei Starkwind. Wie ändern sich α, Antriebskraft und Schub? So regeln Pitch-Anlagen.\n"
        "4. Warum liegt die Antriebskraft F_t nur bei einem kleinen Bruchteil des Auftriebs L?",
        "1. Move r/R from 0.2 to 1.0 at fixed β. What happens to φ and α? Why are blades **twisted**?\n"
        "2. Lower λ at fixed β – this corresponds to more wind at fixed rotor speed. When does the flow stall? This is how stall-regulated turbines work.\n"
        "3. Raise β (pitch) in strong wind. How do α, driving force and thrust change? This is how pitch control works.\n"
        "4. Why is the driving force F_t only a small fraction of the lift L?"))
