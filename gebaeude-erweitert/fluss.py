"""Animiertes Energieflussbild eines Hauses als eigenständiges HTML (SVG + JavaScript) für
st.components.v1.html. Die Animation läuft im Browser; Streamlit rechnet dabei nicht neu.

Eingabe ist eine Stundentabelle mit den Spalten (fehlende Spalten zählen als 0), alle in kW:
  pv, netzbezug, einspeisung, bat_laden, bat_entladen, haushalt, el_wp, q_wp, q_solar, q_ofen,
  q_raum, q_ww sowie bat_soc [kWh] und t_aussen [°C]; Kessel über die Liste `kessel`.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

FARBE = {"strom": "#2a78d6", "waerme": "#e34948", "brennstoff": "#9a6b2f", "umwelt": "#1baf7a",
         "solar": "#eda100"}
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
BW, BH = 150, 46                      # Knotengröße
XA, XB, XC, XD = 95, 370, 640, 905    # Spalten: Quellen, Wandler, Speicher/Verteilung, Verbraucher


def html(df: pd.DataFrame, kessel: list[dict] | None = None, bat_kap: float = 0.0,
         jahreswerte: bool = False) -> tuple[str, int]:
    """Liefert (HTML, Höhe in Pixeln). kessel: [{name, brennstoff, q, fuel}] mit Spaltennamen in df.
    jahreswerte=True: ein einziges Bild mit den Summen in kWh (Stundenwerte in kW vorausgesetzt),
    ohne Zeitregler."""
    kessel = kessel or []
    n = len(df)
    sp = lambda name: (df[name].values.astype(float) if name in df else np.zeros(n))
    pos = lambda a: np.clip(a, 0, None)
    hat = lambda a: float(np.max(a)) > 0.02
    el_wp, q_wp = sp("el_wp"), sp("q_wp")
    q_raum, q_ofen = sp("q_raum"), sp("q_ofen")

    knoten, kanten = {}, []

    def K(kid, label, x, y, art):
        knoten[kid] = dict(label=label, x=x, y=y, art=art)

    def E(von, nach, art, werte, modus="h", dy=0):
        if hat(werte) and von in knoten and nach in knoten:
            kanten.append(dict(von=von, nach=nach, art=art, v=np.round(werte, 3).tolist(), modus=modus, dy=dy))

    # Stromseite
    K("bus", "Hausanschluss", XB, 150, "strom")
    K("hh", "Haushaltsstrom", XD, 150, "strom")
    K("netz", "Stromnetz (Bezug)", XA, 150, "strom")
    if hat(sp("pv")):
        K("pv", "Photovoltaik", XA, 50, "solar")
    if hat(sp("einspeisung")):
        K("eins", "Stromnetz (Verkauf)", XD, 50, "strom")
    if hat(sp("bat_laden")) or hat(sp("bat_entladen")):
        K("bat", "Batterie", XB, 50, "strom")
    # Wärmeseite
    y = 290
    if hat(q_wp):
        K("wp", "Wärmepumpe", XB, y, "waerme")
        K("umw", "Umweltwärme", XA, y, "umwelt")
        y += 85
    for j, k in enumerate(kessel):
        if hat(sp(k["q"])):
            K(f"k{j}", k["name"], XB, y, "waerme")
            K(f"b{j}", k["brennstoff"], XA, y, "brennstoff")
            y += 85
    if hat(sp("q_solar")):
        K("st", "Solarthermie", XB, y, "solar")
        y += 85
    y_max = max(y - 85, 290)
    y_mitte = (290 + y_max) / 2
    K("wv", "Wärmeverteilung", XC, y_mitte, "waerme")
    K("raum", "Raumwärme", XD, max(y_mitte - 50, 250), "waerme")
    K("ww", "Warmwasser", XD, max(y_mitte - 50, 250) + 100, "waerme")
    if hat(q_ofen):
        K("ofen", "Kachelofen (Holz)", XC, max(y_max, y_mitte + 85) + 85, "brennstoff")
    oben = int(min(k["y"] for k in knoten.values()) - 40)          # ohne PV/Batterie oben nichts frei lassen
    hoehe = int(max(k["y"] for k in knoten.values()) + 45) - oben

    E("pv", "bus", "solar", sp("pv"))
    E("netz", "bus", "strom", sp("netzbezug"))
    E("bus", "eins", "strom", sp("einspeisung"))
    E("bus", "bat", "strom", sp("bat_laden"), modus="v", dy=-16)      # dy = seitlicher Versatz
    E("bat", "bus", "strom", sp("bat_entladen"), modus="v", dy=16)
    E("bus", "hh", "strom", sp("haushalt"))
    E("bus", "wp", "strom", el_wp, modus="v")
    E("umw", "wp", "umwelt", pos(q_wp - el_wp))
    E("wp", "wv", "waerme", q_wp)
    for j, k in enumerate(kessel):
        E(f"b{j}", f"k{j}", "brennstoff", sp(k["fuel"]))
        E(f"k{j}", "wv", "waerme", sp(k["q"]))
    E("st", "wv", "solar", sp("q_solar"))
    E("wv", "raum", "waerme", pos(q_raum - q_ofen))
    E("wv", "ww", "waerme", sp("q_ww"))
    E("ofen", "raum", "brennstoff", q_ofen)

    if jahreswerte:
        for e in kanten:
            e["v"] = [round(float(sum(e["v"])))]
        n = 1

    # Geometrie der Kanten
    teile = []
    for i, e in enumerate(kanten):
        a, b = knoten[e["von"]], knoten[e["nach"]]
        if e["modus"] == "v":
            s = 1 if b["y"] > a["y"] else -1
            x1, y1, x2, y2 = a["x"] + e["dy"], a["y"] + s * BH / 2, b["x"] + e["dy"], b["y"] - s * BH / 2
            d = f"M{x1},{y1} L{x2},{y2}"
            lx, ly, anker = (x1 - 10, (y1 + y2) / 2 + 4, "end") if e["dy"] < 0 else (x1 + 10, (y1 + y2) / 2 + 4, "start")
        else:
            s = 1 if b["x"] > a["x"] else -1
            x1, y1, x2, y2 = a["x"] + s * BW / 2, a["y"] + e["dy"], b["x"] - s * BW / 2, b["y"] + e["dy"]
            xm = (x1 + x2) / 2
            d = f"M{x1},{y1} C{xm},{y1} {xm},{y2} {x2},{y2}"
            lx, ly, anker = xm, (y1 + y2) / 2 + (-7 if e["dy"] <= 0 else 17), "middle"
        f = FARBE[e["art"]]
        teile.append(f'<path d="{d}" class="spur" stroke="{f}"/>'
                     f'<path id="f{i}" d="{d}" class="fluss" stroke="{f}"/>'
                     f'<text id="l{i}" x="{lx:.0f}" y="{ly:.0f}" text-anchor="{anker}" class="wert"></text>')
    for kid, k in knoten.items():
        f = FARBE[k["art"]]
        x0, y0 = k["x"] - BW / 2, k["y"] - BH / 2
        teile.append(f'<rect x="{x0}" y="{y0}" width="{BW}" height="{BH}" rx="8" class="kasten" stroke="{f}"/>')
        if kid == "bat":
            teile.append(f'<rect id="soc" x="{x0 + 3}" y="{y0 + BH - 9}" width="0" height="6" rx="3" fill="{f}" '
                         f'opacity="0.55"/>')
        teile.append(f'<text x="{k["x"]}" y="{k["y"] - 1}" text-anchor="middle" class="name">{k["label"]}</text>'
                     f'<text id="n_{kid}" x="{k["x"]}" y="{k["y"] + 14}" text-anchor="middle" class="zahl"></text>')

    # Summen je Knoten (Anzeige unter dem Namen)
    def summe(kid):
        rein = sum((np.array(e["v"]) for e in kanten if e["nach"] == kid), np.zeros(n))
        raus = sum((np.array(e["v"]) for e in kanten if e["von"] == kid), np.zeros(n))
        return np.round(np.maximum(rein, raus), 2).tolist()

    idx = df.index
    daten = dict(
        zeit=[""] if jahreswerte else [f"{TAGE[t.dayofweek]} {t:%d.%m.%Y %H}:00" for t in idx],
        ta=[0] if jahreswerte else np.round(sp("t_aussen"), 1).tolist(),
        kanten=[e["v"] for e in kanten],
        knoten={kid: summe(kid) for kid in knoten if kid not in ("bus", "wv", "bat")},
        soc=(np.round(np.clip(sp("bat_soc") / bat_kap, 0, 1), 3).tolist()
             if bat_kap > 0 and not jahreswerte else []),
        vmax=max(max((max(e["v"]) for e in kanten), default=1.0), 0.1), bw=BW - 6,
        jahr=jahreswerte, einheit="kWh" if jahreswerte else "kW",
    )
    leiste_stil = ' style="display:none"' if jahreswerte else ""
    hinweis = "Linienstärke und Zahl: Energie in kWh pro Jahr" if jahreswerte else "Linienstärke und Zahl: Leistung in kW"
    legende = "".join(f'<span><i style="background:{FARBE[a]}"></i>{t}</span>' for a, t in
                      (("strom", "Strom"), ("solar", "Solarenergie"), ("waerme", "Wärme"),
                       ("umwelt", "Umweltwärme"), ("brennstoff", "Brennstoff")))
    seite = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;font-family:"Source Sans Pro",system-ui,sans-serif;color:#31333f;background:transparent}}
.leiste{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:2px 4px 6px}}
button{{border:1px solid #c9c9cf;background:#fff;border-radius:8px;padding:5px 14px;font-size:14px;cursor:pointer;min-width:92px}}
button:hover{{border-color:#2a78d6;color:#2a78d6}}
input[type=range]{{flex:1;min-width:160px;accent-color:#2a78d6}}
select{{border:1px solid #c9c9cf;border-radius:8px;padding:4px 6px;font-size:13px;background:#fff}}
#zeit{{font-weight:600;min-width:205px;font-variant-numeric:tabular-nums}}
#ta{{color:#6b6d76;min-width:70px;font-variant-numeric:tabular-nums}}
.legende{{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:#6b6d76;padding:2px 6px}}
.legende i{{display:inline-block;width:18px;height:4px;border-radius:2px;margin-right:5px;vertical-align:middle}}
.spur{{fill:none;stroke-width:1.2;opacity:.18}}
.fluss{{fill:none;stroke-linecap:round;stroke-dasharray:3 13;opacity:0}}
.kasten{{fill:#fff;stroke-width:1.6}}
.name{{font-size:13.5px;font-weight:600;fill:#31333f}}
.zahl{{font-size:12px;fill:#6b6d76;font-variant-numeric:tabular-nums}}
.wert{{font-size:11.5px;fill:#31333f;paint-order:stroke;stroke:#fff;stroke-width:3.5px;font-variant-numeric:tabular-nums}}
@media (prefers-reduced-motion: reduce){{.fluss{{stroke-dasharray:none}}}}
</style></head><body>
<div class="leiste"{leiste_stil}><button id="play">⏸ Pause</button><span id="zeit"></span><span id="ta"></span>
<input id="regler" type="range" min="0" max="{n - 1}" value="0" step="1" aria-label="Zeitpunkt">
<select id="tempo" aria-label="Geschwindigkeit"><option value="900">langsam</option>
<option value="450" selected>normal</option><option value="180">schnell</option></select></div>
<svg viewBox="0 {oben} 1000 {hoehe}" width="100%" style="max-width:1000px;display:block;margin:0 auto" role="img" aria-label="Animiertes Energieflussbild">{''.join(teile)}</svg>
<div class="legende">{legende}<span>{hinweis}</span></div>
<script>
const D={json.dumps(daten, separators=(",", ":"))};
const n=D.zeit.length, F=D.kanten.map((_,j)=>document.getElementById('f'+j)),
      L=D.kanten.map((_,j)=>document.getElementById('l'+j));
const regler=document.getElementById('regler'), play=document.getElementById('play'),
      tempo=document.getElementById('tempo'), soc=document.getElementById('soc');
let i=0, laeuft=!window.matchMedia('(prefers-reduced-motion: reduce)').matches, zuletzt=0, versatz=0;
const z=v=>D.jahr?Math.round(v).toLocaleString('de-DE')
  :v.toLocaleString('de-DE',{{minimumFractionDigits:v<10?2:1,maximumFractionDigits:v<10?2:1}});
function zeichne(){{
  document.getElementById('zeit').textContent=D.zeit[i];
  document.getElementById('ta').textContent=z(D.ta[i])+' °C';
  D.kanten.forEach((v,j)=>{{const w=v[i];
    if(w<0.02){{F[j].style.opacity=0;L[j].textContent='';}}
    else{{F[j].style.opacity=1;F[j].setAttribute('stroke-width',(2+13*Math.sqrt(w/D.vmax)).toFixed(1));
         L[j].textContent=z(w)+' '+D.einheit;}}}});
  for(const k in D.knoten){{const w=D.knoten[k][i];
    document.getElementById('n_'+k).textContent=w<0.02?'–':z(w)+' '+D.einheit;}}
  if(soc&&D.soc.length){{soc.setAttribute('width',(D.bw*D.soc[i]).toFixed(1));
    document.getElementById('n_bat').textContent=Math.round(100*D.soc[i])+' % geladen';}}
  play.textContent=laeuft?'⏸ Pause':'▶ Abspielen';
}}
function takt(t){{
  if(laeuft){{versatz-=0.7;F.forEach(p=>p.setAttribute('stroke-dashoffset',versatz.toFixed(1)));
    if(t-zuletzt>+tempo.value){{i=(i+1)%n;zuletzt=t;regler.value=i;zeichne();}}}}
  requestAnimationFrame(takt);
}}
play.onclick=()=>{{laeuft=!laeuft;zeichne();}};
regler.oninput=()=>{{i=+regler.value;zeichne();}};
zeichne();requestAnimationFrame(takt);
</script></body></html>"""
    return seite, hoehe


def wochen(t_aussen: np.ndarray) -> dict[str, int]:
    """Startstunde auswählbarer Wochen (Stundenreihe eines Jahres)."""
    kalt = int(pd.Series(t_aussen).rolling(168).mean().idxmin()) - 167
    return {"Kälteste Woche": max(kalt - kalt % 24, 0), "Frühlingswoche (ab 15. April)": 104 * 24,
            "Sommerwoche (ab 15. Juli)": 195 * 24, "Herbstwoche (ab 15. Oktober)": 287 * 24}
