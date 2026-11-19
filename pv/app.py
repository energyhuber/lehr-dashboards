"""Photovoltaik interaktiv – vom pn-Übergang bis zur Auslegung fürs Einfamilienhaus.

Reiter:
1. pn-Übergang          – Diffusion, Raumladungszone, E-Feld, Ladungstrennung (Animation)
2. Photon → Strom       – Bandlücke, Thermalisierung, nicht absorbiertes Licht, Grenzwirkungsgrad
3. Kennlinie & MPP      – Eindiodenmodell, Einstrahlung/Temperatur, animierter P&O-Tracker
4. Auslegung Haus       – Jahressimulation PV + Speicher + E-Auto/Wärmepumpe, Varianten
5. Energieflüsse        – Tageszeitraffer der Flüsse und Jahres-Sankey
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import sim

ORDNER = Path(__file__).parent
st.set_page_config(page_title="Photovoltaik interaktiv", page_icon="☀️", layout="wide")

LANG = st.sidebar.radio("Sprache / Language", ["Deutsch", "English"], horizontal=True)
DE = LANG == "Deutsch"


def t(de: str, en: str) -> str:
    return de if DE else en


CSS = """
<style>
 html,body{margin:0;font-family:sans-serif;overflow:hidden}
 #bar{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px 0;align-items:center;font-size:13px}
 #bar button{border:1px solid #ced4da;background:#fff;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:13px}
 #bar button:hover{background:#f1f3f5}
 #bar button.on{background:#ffd43b;border-color:#f59f00;font-weight:bold}
 #cap{font-size:14px;margin:0 0 6px 2px;height:58px;overflow:hidden;color:#222;line-height:1.35}
 canvas{width:100%;display:block;border-radius:10px;border:1px solid #e9ecef}
</style>
"""


def animation(js_datei: str, cfg: dict, hoehe: int, leiste: bool = True, caption: bool = False) -> None:
    js = (ORDNER / js_datei).read_text(encoding="utf-8")
    html = (CSS + ('<div id="bar"></div>' if leiste else "") + ('<div id="cap"></div>' if caption else "")
            + f'<canvas id="cv" style="height:{hoehe}px"></canvas>'
            + f"<script>const C = {json.dumps(cfg)};\n{js}</script>")
    extra = (44 if leiste else 0) + (66 if caption else 0)
    components.html(html, height=hoehe + extra + 12)


st.title(t("☀️ Photovoltaik: vom Photon bis zur Steckdose", "☀️ Photovoltaics: from photon to socket"))
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    t("① pn-Übergang", "① p-n junction"),
    t("② Photon → Strom", "② Photon → electricity"),
    t("③ Kennlinie & MPP-Tracker", "③ I-V curve & MPP tracker"),
    t("④ Auslegung Einfamilienhaus", "④ Sizing a family home"),
    t("⑤ Energieflüsse", "⑤ Energy flows"),
])

# =========================================================================== 1 pn-Übergang
with tab1:
    st.markdown(t(
        "Eine Solarzelle ist eine großflächige **Diode**: zwei unterschiedlich dotierte Siliziumschichten. "
        "Klicke dich durch die vier Schritte (oder ▶ *Automatisch*) und beobachte unten das **Bänderdiagramm**.",
        "A solar cell is a large-area **diode**: two differently doped silicon layers. Step through the four "
        "stages (or ▶ *Auto*) and watch the **band diagram** below."))
    pn_cfg = dict(
        steps=[
            [t("Getrennt", "Separate"),
             t("n-Silizium (z. B. mit Phosphor dotiert) hat freie <b>Elektronen</b>, p-Silizium (Bor) hat freie "
               "<b>Löcher</b>. Beide Schichten sind für sich elektrisch neutral – zu jedem Ladungsträger gehört "
               "ein ortsfestes Ion. Die Fermi-Niveaus liegen unterschiedlich hoch.",
               "n-type silicon (e.g. phosphorus-doped) has free <b>electrons</b>, p-type (boron) has free "
               "<b>holes</b>. Each layer is neutral on its own – every carrier is balanced by a fixed ion. "
               "The Fermi levels differ.")],
            [t("Kontakt: Diffusion", "Contact: diffusion"),
             t("Bringt man beide in Kontakt, <b>diffundieren</b> Elektronen ins p-Gebiet und Löcher ins n-Gebiet "
               "und <b>rekombinieren</b>. Zurück bleiben die ortsfesten Ionen: + im n-Gebiet, − im p-Gebiet.",
               "In contact, electrons <b>diffuse</b> into the p-region and holes into the n-region, where they "
               "<b>recombine</b>. The fixed ions stay behind: + on the n-side, − on the p-side.")],
            [t("Raumladungszone & E-Feld", "Depletion zone & E-field"),
             t("Die freigelegten Ionen bilden die <b>Raumladungszone</b>. Ihr <b>elektrisches Feld</b> zeigt von + "
               "nach − und stoppt die weitere Diffusion – Gleichgewicht. Im Bänderdiagramm: Bänder verbiegen "
               "sich, das Fermi-Niveau ist überall gleich, es entsteht eine <b>Potenzialbarriere</b> (≈ 0,7 V bei Si).",
               "The exposed ions form the <b>depletion zone</b>. Their <b>electric field</b> points from + to − and "
               "stops further diffusion – equilibrium. In the band diagram the bands bend, the Fermi level is "
               "flat and a <b>potential barrier</b> forms (≈ 0.7 V for Si).")],
            [t("Licht: Ladungstrennung", "Light: charge separation"),
             t("Ein <b>Photon</b> mit E ≥ E<sub>g</sub> erzeugt ein Elektron-Loch-Paar. Das E-Feld <b>trennt</b> es: "
               "Elektronen → n-Seite, Löcher → p-Seite. Über einen äußeren Verbraucher fließen die Elektronen "
               "zurück – es fließt <b>Strom</b>, und zwischen den Kontakten liegt eine <b>Spannung</b>.",
               "A <b>photon</b> with E ≥ E<sub>g</sub> creates an electron-hole pair. The E-field <b>separates</b> "
               "it: electrons → n-side, holes → p-side. Electrons return through an external load – "
               "<b>current</b> flows and a <b>voltage</b> appears between the contacts.")],
        ],
        auto=t("⏵ Automatisch", "⏵ Auto"),
        nside=t("n-Gebiet", "n-region"), pside=t("p-Gebiet", "p-region"),
        rlz=t("Raumladungszone", "depletion zone"), load=t("Verbraucher", "load"),
        light=t("Licht", "light"),
        bands=t("Bänderdiagramm (Elektronenenergie ↑)", "Band diagram (electron energy ↑)"),
        barrier=t("Barriere e·U_D", "barrier e·V_bi"),
        e_rolls=t("e⁻ „rollt“ zur n-Seite", "e⁻ 'rolls' to n-side"),
        h_rises=t("Loch „steigt“ zur p-Seite", "hole 'rises' to p-side"),
        leg_e=t("Elektron", "electron"), leg_h=t("Loch", "hole"), leg_ion=t("ortsfeste Ionen (Raumladung)", "fixed ions (space charge)"),
    )
    animation("anim_pn.js", pn_cfg, 560, leiste=True, caption=True)
    c1, c2 = st.columns(2)
    c1.markdown(t(
        "**Merke:**\n"
        "- Das E-Feld entsteht *ohne* Licht – durch die Diffusion der Ladungsträger.\n"
        "- Licht liefert die Energie, um Elektronen ins Leitungsband zu heben; das **Feld sortiert** sie nur.\n"
        "- Ohne Feld würden Elektron und Loch nach kurzer Zeit wieder rekombinieren → nur Wärme.",
        "**Key points:**\n"
        "- The E-field exists *without* light – created by carrier diffusion.\n"
        "- Light supplies the energy to lift electrons into the conduction band; the **field sorts** them.\n"
        "- Without the field electron and hole would soon recombine → only heat."))
    c2.markdown(t(
        "**Spannung und Strom:**\n"
        "- Leerlauf: Ladungen stauen sich, die Barriere wird abgebaut → **U_oc ≈ 0,6–0,7 V** je Si-Zelle.\n"
        "- Kurzschluss: alle getrennten Ladungen fließen ab → **I_sc ∝ Einstrahlung**.\n"
        "- Ein Modul schaltet 60–72 Zellen in Reihe → 35–45 V (siehe Reiter ③).",
        "**Voltage and current:**\n"
        "- Open circuit: charges pile up and lower the barrier → **V_oc ≈ 0.6–0.7 V** per Si cell.\n"
        "- Short circuit: all separated charges flow away → **I_sc ∝ irradiance**.\n"
        "- A module connects 60–72 cells in series → 35–45 V (see tab ③)."))

# =========================================================================== 2 Photon → Strom
with tab2:
    st.markdown(t(
        "Nicht jedes Photon ist gleich nützlich. Entscheidend ist die **Bandlücke E_g** des Halbleiters: "
        "Photonen mit **E < E_g** gehen durch, Photonen mit **E > E_g** werden absorbiert – der Überschuss "
        "**E − E_g geht als Wärme verloren** (Thermalisierung).",
        "Not every photon is equally useful. What matters is the semiconductor's **band gap E_g**: photons "
        "with **E < E_g** pass through, photons with **E > E_g** are absorbed – the excess **E − E_g is lost "
        "as heat** (thermalisation)."))
    MAT = {"Silizium (Si)" if DE else "Silicon (Si)": 1.12, "Galliumarsenid (GaAs)" if DE else "Gallium arsenide (GaAs)": 1.42,
           "Cadmiumtellurid (CdTe)" if DE else "Cadmium telluride (CdTe)": 1.45,
           "Perowskit" if DE else "Perovskite": 1.60, "Germanium (Ge)": 0.67}
    p1, p2 = st.columns([1, 1])
    mat = p1.selectbox(t("Material", "Material"), list(MAT), index=0)
    Eg = MAT[mat]
    lam = p2.slider(t("Wellenlänge des Photons λ [nm]", "Photon wavelength λ [nm]"), 300, 1500, 550, 10)
    Eph = 1239.84 / lam

    animation("anim_band.js", dict(Eph=Eph, Eg=Eg, lam=lam, L=dict(
        cb=t("Leitungsband E_L", "conduction band E_C"), vb=t("Valenzband E_V", "valence band E_V"),
        photon="Photon", transmit=t("E < E_g: nicht absorbiert – das Photon geht hindurch",
                                    "E < E_g: not absorbed – the photon passes through"),
        heat=t("Wärme", "heat"), usable=t("nutzbar", "usable"),
        voc=t("Real nutzbar ist etwas weniger: U_oc ≈ (E_g − 0,4 eV)/e, bei Si ≈ 0,7 V.",
              "In practice slightly less is usable: V_oc ≈ (E_g − 0.4 eV)/e, ≈ 0.7 V for Si."))), 360, leiste=False)

    m = st.columns(4)
    m[0].metric(t("Photonenenergie", "Photon energy"), f"{Eph:.2f} eV")
    m[1].metric(t("Bandlücke", "Band gap"), f"{Eg:.2f} eV", f"λ_g = {1239.84 / Eg:.0f} nm", delta_color="off")
    if Eph >= Eg:
        m[2].metric(t("nutzbarer Anteil", "usable share"), f"{Eg / Eph * 100:.0f} %")
        m[3].metric(t("Thermalisierung", "thermalisation"), f"{(1 - Eg / Eph) * 100:.0f} %")
    else:
        m[2].metric(t("nutzbarer Anteil", "usable share"), "0 %")
        m[3].metric(t("Status", "status"), t("transmittiert", "transmitted"))

    # Sonnenspektrum (Schwarzkörper 5778 K, auf 1000 W/m² skaliert)
    lam_g = np.linspace(280, 2500, 900)
    E_g_arr = 1239.84 / lam_g
    bb = 1 / lam_g**5 / (np.exp(1.4388e7 / (lam_g * 5778)) - 1)
    bb = bb / np.trapezoid(bb, lam_g) * 1000            # W/m²/nm
    absorb = lam_g <= 1239.84 / Eg
    nutz = np.where(absorb, bb * Eg / E_g_arr, 0)
    therm = np.where(absorb, bb - nutz, 0)
    trans = np.where(absorb, 0, bb)
    f_n, f_t, f_tr = (np.trapezoid(a, lam_g) / 1000 for a in (nutz, therm, trans))

    s1, s2 = st.columns([3, 2])
    with s1:
        st.subheader(t("Wohin geht die Sonnenenergie?", "Where does the solar energy go?"))
        fs = go.Figure()
        fs.add_trace(go.Scatter(x=lam_g, y=nutz, fill="tozeroy", mode="none", fillcolor="rgba(43,138,62,0.75)",
                                name=t(f"nutzbar ({f_n * 100:.0f} %)", f"usable ({f_n * 100:.0f} %)")))
        fs.add_trace(go.Scatter(x=lam_g, y=nutz + therm, fill="tonexty", mode="none", fillcolor="rgba(224,49,49,0.55)",
                                name=t(f"Thermalisierung ({f_t * 100:.0f} %)", f"thermalisation ({f_t * 100:.0f} %)")))
        fs.add_trace(go.Scatter(x=lam_g, y=trans, fill="tozeroy", mode="none", fillcolor="rgba(134,142,150,0.5)",
                                name=t(f"nicht absorbiert ({f_tr * 100:.0f} %)", f"not absorbed ({f_tr * 100:.0f} %)")))
        fs.add_trace(go.Scatter(x=lam_g, y=bb, mode="lines", line=dict(color="#222", width=1.5),
                                name=t("Sonnenspektrum (Näherung)", "solar spectrum (approx.)")))
        fs.add_vline(x=lam, line=dict(color="#f59f00", width=2), annotation_text=f"{lam} nm")
        fs.add_vline(x=1239.84 / Eg, line=dict(color="#555", dash="dash"), annotation_text="λ_g",
                     annotation_position="top left")
        fs.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), template="plotly_white",
                         xaxis_title=t("Wellenlänge [nm]", "wavelength [nm]"), yaxis_title="W/(m²·nm)",
                         legend=dict(orientation="h", y=-0.22))
        st.plotly_chart(fs, use_container_width=True)
        st.caption(t("Spektrum als Schwarzkörper mit 5778 K genähert und auf 1000 W/m² skaliert "
                     "(das reale AM1,5-Spektrum hat zusätzlich Absorptionsbanden von Wasser und CO₂).",
                     "Spectrum approximated as a 5778 K black body scaled to 1000 W/m² (the real AM1.5 "
                     "spectrum also has water and CO₂ absorption bands)."))
    with s2:
        st.subheader(t("Welche Bandlücke ist optimal?", "Which band gap is best?"))
        Egs = np.linspace(0.4, 3.0, 131)
        u = []
        for e in Egs:
            a = lam_g <= 1239.84 / e
            u.append(np.trapezoid(np.where(a, bb * e / E_g_arr, 0), lam_g) / 1000)
        fu = go.Figure(go.Scatter(x=Egs, y=np.array(u) * 100, line=dict(color="#2b8a3e", width=3),
                                  name=t("ohne Thermalisierung/Transmission", "after thermalisation/transmission")))
        for name, e in MAT.items():
            fu.add_trace(go.Scatter(x=[e], y=[np.interp(e, Egs, u) * 100], mode="markers+text", text=[name.split(" (")[0]],
                                    textposition="top center", showlegend=False,
                                    marker=dict(size=12 if e == Eg else 8, color="#f59f00" if e == Eg else "#868e96")))
        fu.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), template="plotly_white",
                         xaxis_title="E_g [eV]", yaxis_title=t("Anteil [%]", "share [%]"), showlegend=False)
        st.plotly_chart(fu, use_container_width=True)
        st.caption(t("Kleine Bandlücke: viele Photonen absorbiert, aber viel Thermalisierung. Große Bandlücke: "
                     "wenig Thermalisierung, aber viele Photonen gehen verloren. Das Optimum liegt bei ≈ 1,1–1,4 eV.",
                     "Small gap: many photons absorbed but much thermalisation. Large gap: little thermalisation "
                     "but many photons lost. The optimum is ≈ 1.1–1.4 eV."))

    st.markdown(t(
        f"**Vom Sonnenlicht zum Modul (Silizium):** 100 % → nach Transmission und Thermalisierung ≈ "
        f"{np.interp(1.12, Egs, u) * 100:.0f} % → zusätzlich Spannungsverlust (U_oc < E_g/e), Füllfaktor und "
        f"Strahlungsrekombination: **Shockley-Queisser-Grenze ≈ 33 %** → Rekordzelle 27 % → "
        f"Serienmodul ≈ 21–23 %. Mehr geht nur mit **Tandemzellen** (zwei Bandlücken übereinander).",
        f"**From sunlight to module (silicon):** 100 % → after transmission and thermalisation ≈ "
        f"{np.interp(1.12, Egs, u) * 100:.0f} % → plus voltage loss (V_oc < E_g/e), fill factor and "
        f"radiative recombination: **Shockley-Queisser limit ≈ 33 %** → record cell 27 % → commercial "
        f"module ≈ 21–23 %. Beyond that requires **tandem cells** (two band gaps stacked)."))

# =========================================================================== 3 Kennlinie & MPP
with tab3:
    st.markdown(t(
        "Ein Modul kann bei jeder Spannung zwischen 0 und U_oc betrieben werden – aber nur an **einem Punkt** "
        "liefert es die maximale Leistung (**MPP**, *Maximum Power Point*). Der MPP wandert mit Einstrahlung "
        "und Temperatur. Der **MPP-Tracker** im Wechselrichter sucht ihn ständig: Er verstellt die Spannung "
        "ein Stück und beobachtet die Leistung (*Perturb & Observe*). Steigt sie, geht er weiter in diese "
        "Richtung – sonst kehrt er um.",
        "A module can operate at any voltage between 0 and V_oc – but only **one point** gives maximum power "
        "(**MPP**). The MPP moves with irradiance and temperature. The inverter's **MPP tracker** keeps "
        "searching: it nudges the voltage and watches the power (*perturb & observe*). If power rises it "
        "continues, otherwise it reverses."))
    k1, k2 = st.columns(2)
    G = k1.slider(t("Einstrahlung G [W/m²]", "Irradiance G [W/m²]"), 100, 1200, 1000, 50)
    Tc = k2.slider(t("Zelltemperatur [°C]", "Cell temperature [°C]"), -10, 75, 25, 5)
    animation("anim_mppt.js", dict(G=G, T=Tc, L=dict(
        cloud=t("☁ Wolke", "☁ cloud"), shade=t("🌳 Teilverschattung (1 von 3 Strings)", "🌳 partial shading (1 of 3 strings)"),
        bigstep=t("große Schritte", "large steps"), restart=t("↺ Tracker neu starten", "↺ restart tracker"),
        u=t("Spannung U [V]", "voltage V [V]"), i=t("Strom I [A]", "current I [A]"), p=t("Leistung P [W]", "power P [W]"),
        hist=t("Leistung über die Zeit (letzte 30 s)", "power over time (last 30 s)"),
        pmpp=t("- - mögliche Leistung (MPP)", "- - available power (MPP)"), pop=t("— vom Tracker erreicht", "— achieved by tracker"),
        g_eff=t("Einstrahlung", "irradiance"), eta=t("Tracking-Wirkungsgrad", "tracking efficiency"),
        local=t("⚠ lokales Maximum – Tracker steckt fest!", "⚠ local maximum – tracker is stuck!"))), 430)
    st.markdown(t(
        "**Ausprobieren:**\n"
        "1. **☁ Wolke**: Der Strom (und damit P) bricht ein, die Spannung kaum – der Tracker folgt in wenigen Sekunden.\n"
        "2. **Zelltemperatur** auf 65 °C: U_oc sinkt um ≈ 0,3 %/K → ca. 12 % weniger Leistung im Hochsommer.\n"
        "3. **Teilverschattung**: Die Bypassdiode überbrückt den verschatteten Teilstring → die P-U-Kurve hat **zwei "
        "Maxima**. Startet der Tracker rechts (↺), bleibt er am **lokalen** Maximum hängen. Moderne Wechselrichter "
        "machen deshalb regelmäßig einen *Global-Scan* über die ganze Kennlinie.\n"
        "4. **Große Schritte**: schneller am MPP, aber stärkeres Pendeln um ihn herum.",
        "**Try it:**\n"
        "1. **☁ Cloud**: current (and thus P) drops, voltage hardly – the tracker follows within seconds.\n"
        "2. **Cell temperature** 65 °C: V_oc drops ≈ 0.3 %/K → ≈ 12 % less power in midsummer.\n"
        "3. **Partial shading**: the bypass diode bridges the shaded substring → the P-V curve has **two maxima**. "
        "Starting on the right (↺) the tracker gets stuck at the **local** maximum. Modern inverters therefore "
        "run a periodic *global scan*.\n"
        "4. **Large steps**: reaches the MPP faster but oscillates more around it."))
    st.caption(t("Modell: 60 Zellen (3 Teilstrings à 20 Zellen mit Bypassdiode), Eindiodenmodell ohne Serienwiderstand, "
                 "I_sc = 10 A, U_oc = 40,8 V bei STC.",
                 "Model: 60 cells (3 substrings of 20 cells with bypass diodes), single-diode model without series "
                 "resistance, I_sc = 10 A, V_oc = 40.8 V at STC."))

# =========================================================================== 4 Auslegung
ORIENT = {t("Süd", "South"): [0], t("Südost", "South-east"): [-45], t("Südwest", "South-west"): [45],
          t("Ost", "East"): [-90], t("West", "West"): [90], t("Ost/West (halb/halb)", "East/West (half/half)"): [-90, 90]}


@st.cache_data
def wetter_c():
    return sim.wetter()


@st.cache_data
def lauf(kwp, neigung, orient_deg, kap, hh, ev, ev_mittag, wp):
    w = wetter_c()
    prof = np.mean([sim.pv_profil(w, neigung, a) for a in orient_deg], axis=0)
    L = sim.lastprofil(w, hh, ev, ev_mittag, wp)
    r = sim.simuliere(kwp * prof, L["gesamt"], kap)
    r["haushalt"], r["ev"], r["wp"] = L["haushalt"], L["ev"], L["wp"]
    return r


with tab4:
    st.markdown(t(
        "Jahressimulation in Stundenschritten für ein Einfamilienhaus in Ingolstadt. Wie viel des Solarstroms "
        "nutze ich selbst (**Eigenverbrauch**), wie viel meines Bedarfs decke ich selbst (**Autarkie**) – "
        "und was bringt ein **Speicher**?",
        "Hourly annual simulation for a family home in Ingolstadt. How much of the solar power do I use myself "
        "(**self-consumption**), how much of my demand do I cover (**self-sufficiency**) – and what does a "
        "**battery** add?"))
    a1, a2, a3, a4 = st.columns(4)
    hh = a1.slider(t("Haushaltsstrom [kWh/a]", "Household electricity [kWh/a]"), 1500, 8000, 4000, 250)
    kwp = a2.slider(t("PV-Leistung [kWp]", "PV size [kWp]"), 0.0, 20.0, 8.0, 0.5)
    orient = a3.selectbox(t("Ausrichtung", "Orientation"), list(ORIENT))
    neig = a4.slider(t("Neigung [°]", "Tilt [°]"), 0, 90, 30, 5)
    b1, b2, b3, b4 = st.columns(4)
    kap = b1.slider(t("Speicher [kWh]", "Battery [kWh]"), 0.0, 20.0, 0.0, 0.5)
    ev_an = b2.checkbox(t("E-Auto", "Electric car"), value=False)
    ev_km = b2.number_input(t("km pro Jahr", "km per year"), 0, 40000, 12000, 1000, disabled=not ev_an)
    ev_mit = b3.radio(t("E-Auto laden", "Car charging"), [t("abends (18–22 Uhr)", "evening (6–10 pm)"),
                                                         t("mittags, PV-geführt", "midday, solar-led")],
                      disabled=not ev_an) != t("abends (18–22 Uhr)", "evening (6–10 pm)")
    wp_an = b4.checkbox(t("Wärmepumpe", "Heat pump"), value=False)
    wp_kwh = b4.number_input(t("WP-Strom [kWh/a]", "HP electricity [kWh/a]"), 0, 15000, 3500, 250, disabled=not wp_an)
    with st.expander(t("💶 Preise und Kosten", "💶 Prices and costs")):
        e1, e2, e3, e4 = st.columns(4)
        preis = e1.number_input(t("Strompreis [€/kWh]", "Electricity price [€/kWh]"), 0.10, 0.80, 0.35, 0.01)
        verg = e2.number_input(t("Einspeisevergütung [€/kWh]", "Feed-in tariff [€/kWh]"), 0.0, 0.30, 0.078, 0.002, format="%.3f")
        i_kwp = e3.number_input(t("PV-Investition [€/kWp]", "PV investment [€/kWp]"), 600, 3000, 1400, 50)
        i_kwh = e4.number_input(t("Speicher-Investition [€/kWh]", "Battery investment [€/kWh]"), 200, 1500, 650, 25)

    ev_kwh = ev_km * 0.18 if ev_an else 0.0
    wp_k = float(wp_kwh) if wp_an else 0.0
    odeg = tuple(ORIENT[orient])
    args = (kwp, neig, odeg)
    r = lauf(kwp, neig, odeg, kap, hh, ev_kwh, ev_mit, wp_k)
    k = sim.kennzahlen(r, preis, verg, kwp, kap, i_kwp, i_kwh)

    mm = st.columns(6)
    mm[0].metric(t("PV-Ertrag [MWh/a]", "PV yield [MWh/a]"), f"{k['pv'] / 1000:.1f}", f"{k['pv'] / kwp:,.0f} kWh/kWp" if kwp else None, delta_color="off")
    mm[1].metric(t("Verbrauch [MWh/a]", "Demand [MWh/a]"), f"{k['last'] / 1000:.1f}")
    mm[2].metric(t("Eigenverbrauchsquote", "Self-consumption"), f"{k['eigen'] * 100:.0f} %")
    mm[3].metric(t("Autarkiegrad", "Self-sufficiency"), f"{k['autark'] * 100:.0f} %")
    mm[4].metric(t("Ersparnis pro Jahr", "Savings per year"), f"{k['ersparnis']:,.0f} €")
    mm[5].metric(t("Amortisation [Jahre]", "Payback [years]"),
                 f"{k['amort']:.1f}" if np.isfinite(k["amort"]) else "–",
                 help=t("Einfache Amortisation: Investition ÷ jährliche Ersparnis (ohne Zins, Alterung, Preissteigerung).",
                        "Simple payback: investment ÷ annual savings (no interest, degradation or price changes)."))

    st.subheader(t("Varianten im Vergleich", "Comparing variants"))
    rows = []
    for kp in sorted({0.0, 5.0, 10.0, 15.0, kap}):
        rr = lauf(kwp, neig, odeg, kp, hh, ev_kwh, ev_mit, wp_k)
        kk = sim.kennzahlen(rr, preis, verg, kwp, kp, i_kwp, i_kwh)
        rows.append({
            t("Variante", "Variant"): (t("ohne Speicher", "no battery") if kp == 0 else t(f"Speicher {kp:g} kWh", f"battery {kp:g} kWh"))
                                      + ("  ◀" if kp == kap else ""),
            t("Eigenverbrauch", "Self-cons."): f"{kk['eigen'] * 100:.0f} %",
            t("Autarkie", "Self-suff."): f"{kk['autark'] * 100:.0f} %",
            t("Netzbezug [kWh]", "Grid import [kWh]"): f"{kk['bezug']:,.0f}",
            t("Einspeisung [kWh]", "Feed-in [kWh]"): f"{kk['einsp']:,.0f}",
            t("Ersparnis [€/a]", "Savings [€/a]"): f"{kk['ersparnis']:,.0f}",
            t("Investition [€]", "Investment [€]"): f"{kk['invest']:,.0f}",
            t("Amortisation [a]", "Payback [a]"): f"{kk['amort']:.1f}" if np.isfinite(kk["amort"]) else "–",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    v1, v2 = st.columns(2)
    with v1:
        caps = np.arange(0, 20.5, 1.0)
        ks = [sim.kennzahlen(lauf(kwp, neig, odeg, c, hh, ev_kwh, ev_mit, wp_k), preis, verg, kwp, c, i_kwp, i_kwh) for c in caps]
        f1 = go.Figure()
        f1.add_trace(go.Scatter(x=caps, y=[x["autark"] * 100 for x in ks], name=t("Autarkie", "self-sufficiency"), line=dict(color="#2b8a3e", width=3)))
        f1.add_trace(go.Scatter(x=caps, y=[x["eigen"] * 100 for x in ks], name=t("Eigenverbrauch", "self-consumption"), line=dict(color="#f59f00", width=3)))
        f1.add_vline(x=kap, line=dict(color="#888", dash="dash"))
        f1.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), template="plotly_white",
                         title=t(f"Wirkung der Speichergröße (bei {kwp:g} kWp)", f"Effect of battery size (at {kwp:g} kWp)"),
                         xaxis_title=t("Speicher [kWh]", "battery [kWh]"), yaxis_title="%", yaxis_range=[0, 100],
                         legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(f1, use_container_width=True)
    with v2:
        kwps = np.arange(0, 20.5, 1.0)
        ks2 = [sim.kennzahlen(lauf(p, neig, odeg, kap, hh, ev_kwh, ev_mit, wp_k), preis, verg, max(p, 1e-9), kap, i_kwp, i_kwh) for p in kwps]
        f2 = go.Figure()
        f2.add_trace(go.Scatter(x=kwps, y=[x["autark"] * 100 for x in ks2], name=t("Autarkie", "self-sufficiency"), line=dict(color="#2b8a3e", width=3)))
        f2.add_trace(go.Scatter(x=kwps[1:], y=[x["eigen"] * 100 for x in ks2[1:]], name=t("Eigenverbrauch", "self-consumption"), line=dict(color="#f59f00", width=3)))
        f2.add_vline(x=kwp, line=dict(color="#888", dash="dash"))
        f2.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), template="plotly_white",
                         title=t(f"Wirkung der PV-Größe (Speicher {kap:g} kWh)", f"Effect of PV size (battery {kap:g} kWh)"),
                         xaxis_title="kWp", yaxis_title="%", yaxis_range=[0, 100], legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(f2, use_container_width=True)
    st.caption(t("Typisch: Autarkie steigt mit dem Speicher zunächst stark und flacht dann ab – im Winter fehlt der "
                 "Solarstrom, den man speichern könnte. Eigenverbrauch sinkt mit größerer PV, weil mehr Überschuss entsteht.",
                 "Typical: self-sufficiency rises steeply with the first kWh of storage and then flattens – in winter "
                 "there is no surplus to store. Self-consumption falls with larger PV because surplus grows."))

    # Monatsbilanz
    mon = np.repeat(sim.MONAT_TAG, 24)
    MN = ["Jan", "Feb", "Mär" if DE else "Mar", "Apr", "Mai" if DE else "May", "Jun", "Jul", "Aug", "Sep",
          "Okt" if DE else "Oct", "Nov", "Dez" if DE else "Dec"]
    agg = lambda a: [a[mon == i].sum() for i in range(12)]
    fm = go.Figure()
    fm.add_trace(go.Bar(x=MN, y=agg(r["direkt"]), name=t("PV direkt genutzt", "PV used directly"), marker_color="#f59f00"))
    fm.add_trace(go.Bar(x=MN, y=agg(r["entl"]), name=t("aus Speicher", "from battery"), marker_color="#2b8a3e"))
    fm.add_trace(go.Bar(x=MN, y=agg(r["bezug"]), name=t("Netzbezug", "grid import"), marker_color="#adb5bd"))
    fm.add_trace(go.Scatter(x=MN, y=agg(r["pv"]), name=t("PV-Erzeugung", "PV generation"), mode="lines+markers",
                            line=dict(color="#e8590c", width=3)))
    fm.update_layout(barmode="stack", height=340, margin=dict(l=10, r=10, t=30, b=10), template="plotly_white",
                     title=t("Monatsbilanz: Wodurch wird der Verbrauch gedeckt?", "Monthly balance: what covers the demand?"),
                     yaxis_title="kWh", legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fm, use_container_width=True)
    st.caption(t("Simulation mit synthetischem Wetter für Ingolstadt (kalibriert auf 1000 kWh/kWp bei Süd 30°) und "
                 "synthetischem Lastprofil, Speicher: 90 % Zyklenwirkungsgrad, max. 0,5 C. Stundenwerte überschätzen "
                 "den Eigenverbrauch leicht, weil kurze Lastspitzen ausgemittelt werden.",
                 "Simulation with synthetic weather for Ingolstadt (calibrated to 1000 kWh/kWp at south 30°) and a "
                 "synthetic load profile; battery: 90 % round-trip efficiency, max. 0.5 C. Hourly values slightly "
                 "overestimate self-consumption because short load peaks are averaged out."))

# =========================================================================== 5 Energieflüsse
with tab5:
    st.markdown(t(
        "Die Anlage aus Reiter ④ im **Zeitraffer**: Woher kommt der Strom im Haus, wohin fließt der Solarstrom? "
        "Punkte = Energie, Linienbreite ∝ Leistung.",
        "The system from tab ④ in **time-lapse**: where does the house get its power and where does the solar "
        "power go? Dots = energy, line width ∝ power."))
    d0 = date(2025, 1, 1)
    tag = st.select_slider(t("Tag", "Day"), options=list(range(1, 366)), value=172,
                           format_func=lambda d: (d0 + timedelta(days=d - 1)).strftime("%d.%m."))
    sl = slice((tag - 1) * 24, tag * 24)
    day = {key: [round(float(v), 3) for v in r[key][sl]] for key in ("pv", "last", "direkt", "lade", "entl", "einsp", "bezug", "soc")}
    animation("anim_flow.js", dict(**day, kap=kap, L=dict(
        haus=t("Haus", "House"), bat=t("Speicher", "Battery"), nobat=t("kein Speicher", "no battery"),
        netz=t("Netz", "Grid"), pv_leg=t("■ PV-Erzeugung", "■ PV generation"), last_leg=t("— Verbrauch", "— demand"))), 520)

    dsum = {key: sum(day[key]) for key in day if key != "soc"}
    dm = st.columns(5)
    dm[0].metric(t("PV am Tag", "PV this day"), f"{dsum['pv']:.1f} kWh")
    dm[1].metric(t("Verbrauch am Tag", "Demand this day"), f"{dsum['last']:.1f} kWh")
    dm[2].metric(t("Netzbezug", "Grid import"), f"{dsum['bezug']:.1f} kWh")
    dm[3].metric(t("Einspeisung", "Feed-in"), f"{dsum['einsp']:.1f} kWh")
    dm[4].metric(t("Autarkie am Tag", "Self-sufficiency this day"),
                 f"{(1 - dsum['bezug'] / dsum['last']) * 100:.0f} %" if dsum["last"] > 0 else "–")

    st.subheader(t("Jahresbilanz als Energiefluss", "Annual balance as energy flow"))
    names = ["PV", t("Speicher", "Battery"), t("Netzbezug", "Grid import"), t("Haus", "House"),
             t("Einspeisung", "Feed-in"), t("Speicherverluste", "Battery losses")]
    cols = ["#f59f00", "#2b8a3e", "#868e96", "#495057", "#74c0fc", "#fa5252"]
    S = lambda a: float(np.sum(a))
    src, tgt, val, lc = [], [], [], []
    for s_, t_, v_, c_ in [(0, 3, S(r["direkt"]), "rgba(245,159,0,0.45)"), (0, 1, S(r["lade"]), "rgba(245,159,0,0.45)"),
                           (0, 4, S(r["einsp"]), "rgba(245,159,0,0.45)"), (1, 3, S(r["entl"]), "rgba(43,138,62,0.45)"),
                           (1, 5, r["verlust"], "rgba(250,82,82,0.45)"), (2, 3, S(r["bezug"]), "rgba(134,142,150,0.45)")]:
        if v_ > 1:
            src.append(s_); tgt.append(t_); val.append(round(v_)); lc.append(c_)
    fs_ = go.Figure(go.Sankey(node=dict(label=[f"{n}" for n in names], color=cols, pad=20, thickness=18),
                              link=dict(source=src, target=tgt, value=val, color=lc,
                                        hovertemplate="%{source.label} → %{target.label}: %{value:,.0f} kWh<extra></extra>")))
    fs_.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fs_, use_container_width=True)
    st.caption(t("Werte in kWh pro Jahr, Maus über die Flüsse für Details.", "Values in kWh per year, hover for details."))
