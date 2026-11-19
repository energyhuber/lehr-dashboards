"""Dashboard Gebäudeenergietechnik – Strom- und Wärmebedarf eines Gebäudes
und deren Bereitstellung, Jahressimulation in 15-Minuten-Auflösung.

Start:  python -m streamlit run app.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import model
from data import DT

st.set_page_config(page_title="Gebäudeenergietechnik", page_icon="🏠", layout="wide")

# Feste Farbe je Größe (Farbe folgt der Größe, nicht der Reihenfolge)
C = {
    "netz": "#2a78d6", "bat": "#1baf7a", "pv": "#eda100", "einsp": "#6250d6",
    "wp": "#2a78d6", "oel": "#eb6834", "kachel": "#1baf7a", "solar": "#eda100",
    "gas": "#e87ba4", "holz": "#008300", "heizstab": "#6250d6", "ungedeckt": "#e34948",
    "linie": "#52514e", "temp": "#898781", "balken": "#9ec5f4",
}
WAERME = [  # Spalte, Bezeichnung, Farbe – in fester Stapelreihenfolge
    ("q_wp", "Wärmepumpe", C["wp"]), ("q_oel", "Ölheizung", C["oel"]),
    ("q_kachelofen", "Kachelofen", C["kachel"]), ("q_solar", "Solarthermie", C["solar"]),
    ("q_gas", "Gasheizung", C["gas"]), ("q_holz", "Holzheizung", C["holz"]),
    ("q_heizstab", "Heizstab", C["heizstab"]), ("q_ungedeckt", "ungedeckt", C["ungedeckt"]),
]
STROM = [
    ("netzbezug", "Netzbezug", C["netz"]), ("bat_entladen", "Batterie", C["bat"]),
    ("pv_direkt", "PV direkt", C["pv"]),
]
MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def de(x: float, n: int = 0) -> str:
    """Zahl mit deutschem Tausender-/Dezimaltrennzeichen."""
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def halb(x: float) -> float:
    """Auf 0,5 runden."""
    return round(x * 2) / 2


# ---------------------------------------------------------------------------
# Gecachte Rechenschritte
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Lade Wetter- und Ertragsdaten von PVGIS …")
def lade_pvgis(lat, lon, tilt, aspect, year):
    return data.fetch_pvgis(lat, lon, tilt, aspect, year)


@st.cache_data(show_spinner=False)
def synth(lat, tilt, aspect):
    return data.synthetic_weather(lat, tilt, aspect)


@st.cache_data(show_spinner="Simuliere Jahr in 15-min-Schritten …")
def rechne(wetter, params):
    return model.simulate(wetter, params)


def wetterdaten(lat, lon, tilt, aspect, year, offline):
    """Liefert (15-min-Wetter, Quelle). Fällt bei Fehlern auf synthetische Daten zurück."""
    key = (lat, lon, tilt, aspect, year)
    fehler = st.session_state.setdefault("pvgis_fehler", {})
    if not offline and key not in fehler:
        try:
            return data.to_15min(lade_pvgis(*key), year), "PVGIS"
        except Exception as exc:                      # Netzwerk, Timeout, API-Fehler
            fehler[key] = str(exc)
    return data.to_15min(synth(lat, tilt, aspect), year), "synthetisch"


def groesse(label, auto_wert, key, lo, hi, step, auto, fmt="%.1f", hilfe=None):
    """Auslegungsgröße: bei `auto` gesperrtes Feld mit dem automatischen Wert,
    sonst frei editierbar (Startwert = automatischer Wert)."""
    if auto:
        st.number_input(label, value=float(auto_wert), disabled=True, format=fmt,
                        key=f"{key}_auto_{auto_wert}", help=hilfe)
        return float(auto_wert)
    return st.number_input(label, lo, hi, float(min(max(auto_wert, lo), hi)), step, format=fmt,
                           key=f"{key}_man", help=hilfe)


# ---------------------------------------------------------------------------
# Seitenleiste: die wichtigsten Eingaben (Details im Reiter „Auslegung“)
# ---------------------------------------------------------------------------
sb = st.sidebar
sb.title("Eingaben")
P = dict(model.DEFAULTS)

with sb.expander("📍 Standort und Wetter", expanded=False):
    ort = st.selectbox("Standort", list(data.STANDORTE), index=0)
    lat0, lon0 = data.STANDORTE[ort]
    c1, c2 = st.columns(2)
    lat = c1.number_input("Breite [°N]", 35.0, 70.0, lat0, 0.01, format="%.2f", key=f"lat_{ort}")
    lon = c2.number_input("Länge [°O]", -10.0, 30.0, lon0, 0.01, format="%.2f", key=f"lon_{ort}")
    jahr = st.selectbox("Wetterjahr", list(range(2023, 2004, -1)), index=4)
    c1, c2 = st.columns(2)
    neigung = c1.number_input("Neigung [°]", 0, 90, 35, 5,
                              help="Gilt für PV-Module und Solarthermie-Kollektoren.")
    azimut = c2.number_input("Azimut [°]", -180, 180, 0, 15,
                             help="0 = Süd, −90 = Ost, 90 = West. Gilt für PV und Solarthermie.")
    offline = st.checkbox("Synthetische Wetterdaten (offline)", value=False,
                          help="Ohne Internetabruf rechnen (Sonnenstandsmodell + Zufallswetter).")

sb.subheader("🏠 Gebäude")
P["flaeche"] = sb.number_input("Wohnfläche [m²]", 20.0, 1000.0, 140.0, 10.0)
P["personen"] = sb.number_input("Bewohner", 1, 12, 3, 1)
std = sb.selectbox("Gebäudestandard", list(model.GEBAEUDESTANDARDS), index=2)
spez0, hg0, vl0 = model.GEBAEUDESTANDARDS[std]
hs_namen = list(model.HEIZSYSTEME)
hs = sb.selectbox("Heizsystem (Vorlauftemperatur)", hs_namen,
                  index=list(model.HEIZSYSTEME.values()).index(vl0), key=f"hs_{std}",
                  help="Auslegungs-Vorlauftemperatur am kältesten Tag (−14 °C). Sie bestimmt über die "
                       "Heizkurve den COP der Wärmepumpe. Vorbelegt nach Gebäudestandard.")
P["t_vorlauf"] = model.HEIZSYSTEME[hs]

sb.subheader("⚡ Strom")
t_pv = sb.checkbox("Photovoltaik", value=True)
t_bat = sb.checkbox("Batteriespeicher", value=False, disabled=not t_pv) and t_pv
sb.subheader("🔥 Wärme")
t_wp = sb.checkbox("Wärmepumpe", value=False)
t_gas = sb.checkbox("Gasheizung", value=True)
t_oel = sb.checkbox("Ölheizung", value=False)
t_holz = sb.checkbox("Holzheizung", value=False, help="Pellet- oder Scheitholzkessel")
t_ko = sb.checkbox("Kachelofen", value=False)
t_st = sb.checkbox("Solarthermie", value=False)
ausl_box = sb.container()

# ---------------------------------------------------------------------------
# Seitenkopf und Reiter
# ---------------------------------------------------------------------------
st.title("🏠 Gebäudeenergietechnik")
kopf = st.container()
tab_jahr, tab_woche, tab_detail, tab_annahmen = st.tabs(
    ["📊 Jahresübersicht", "📈 Typische Woche je Jahreszeit", "🔧 Auslegung und Details",
     "📋 Annahmen und Daten"])

wetter, quelle = wetterdaten(float(lat), float(lon), float(neigung), float(azimut), int(jahr), offline)
spez_ertrag = float(wetter["pv"].sum() * DT)

# ---------------------------------------------------------------------------
# Reiter: Auslegung und Details (Eingaben; wird vor der Simulation ausgewertet)
# ---------------------------------------------------------------------------
auslegung = []      # Zeilen für die Kurzübersicht in der Seitenleiste
with tab_detail:
    st.caption("Alle Größen sind automatisch vorbelegt. Zum Ändern das Häkchen „automatisch auslegen“ "
               "der jeweiligen Technologie entfernen. Gezeigt werden nur die gewählten Technologien.")

    st.subheader("Gebäude und Bedarf")
    c = st.columns(4)
    strom0 = float(model.STROMBEDARF_PERSONEN.get(P["personen"], 5000 + 500 * (P["personen"] - 6)))
    with c[0]:
        P["spez_heizwaerme"] = st.number_input("Heizwärmebedarf [kWh/m²a]", 5.0, 400.0, spez0, 5.0,
                                               key=f"spez_{std}", help="Vorbelegt nach Gebäudestandard.")
    with c[1]:
        P["heizgrenze"] = st.number_input("Heizgrenztemperatur [°C]", 5.0, 20.0, hg0, 0.5, key=f"hg_{std}")
    with c[2]:
        P["strom_kwh"] = st.number_input("Haushaltsstrom [kWh/a]", 500.0, 30000.0, strom0, 100.0,
                                         key=f"strom_{P['personen']}", help="Vorbelegt nach Personenzahl.")
    with c[3]:
        P["ww_kwh_person"] = st.number_input("Warmwasser [kWh/Person·a]", 0.0, 2000.0,
                                             model.WARMWASSER_KWH_PERSON, 50.0)

    # Spitzenlast Wärme (Raumwärme + Warmwasser) als Basis der Auslegung
    _, k0 = rechne(wetter, {x: P[x] for x in ("flaeche", "personen", "spez_heizwaerme", "heizgrenze",
                                               "strom_kwh", "ww_kwh_person")})
    spitze = k0["heizlast_max"]
    st.info(f"Spitzenlast Wärme (Raumwärme + Warmwasser, 15-min-Wert): **{de(spitze, 1)} kW** · "
            f"Wärmebedarf **{de(k0['waerme_bedarf'])} kWh/a** · spezifischer PV-Ertrag am Standort "
            f"**{de(spez_ertrag)} kWh/kWp**")

    # --- Wärmeerzeuger -------------------------------------------------------
    st.subheader("Wärmeerzeuger")
    haupt = [n for n, an in (("wp", t_wp), ("holz", t_holz), ("gas", t_gas), ("oel", t_oel)) if an]
    auto_kw, rest = {}, spitze
    for i, n in enumerate(haupt):               # vorrangige Erzeuger: 60 % der Restlast
        letzter = i == len(haupt) - 1
        auto_kw[n] = math.ceil(rest * 2) / 2 if letzter else max(halb(0.6 * rest), 0.5)
        rest = max(rest - auto_kw[n], 0.0)
    NAMEN = {"wp": "Wärmepumpe", "holz": "Holzheizung", "gas": "Gasheizung", "oel": "Ölheizung"}
    ETA0 = {"holz": 85.0, "gas": 95.0, "oel": 88.0}

    aktive = haupt + (["ko"] if t_ko else []) + (["st"] if t_st else [])
    if not aktive:
        st.warning("Kein Wärmeerzeuger gewählt – der Wärmebedarf bleibt ungedeckt.")
    spalten = st.columns(max(min(len(aktive), 3), 1))
    for j, n in enumerate(aktive):
        with spalten[j % len(spalten)], st.container(border=True):
            if n in NAMEN:
                letzter = n == haupt[-1]
                st.markdown(f"**{NAMEN[n]}**")
                auto = st.checkbox("automatisch auslegen", value=True, key=f"auto_{n}")
                regel = ("deckt die verbleibende Spitzenlast" if letzter
                         else "60 % der Spitzenlast als Grundlast, der nachrangige Erzeuger deckt die Spitze")
                kw = groesse("Heizleistung [kW]", auto_kw[n], f"kw_{n}", 0.0, 200.0, 0.5, auto,
                             hilfe=f"Automatik: {regel}. Manuell: 0 kW = unbegrenzt.")
                # automatisch ausgelegter letzter Erzeuger darf nie zu klein sein -> unbegrenzt
                P[f"{n}_kw"] = 0.0 if (auto and letzter) else kw
                P[n] = True
                auslegung.append(f"{NAMEN[n]}: {de(kw, 1)} kW" + ("" if auto else " (manuell)"))
                if n == "wp":
                    P["wp_quelle"] = st.radio("Wärmequelle", ["Luft", "Erdreich (Sole)"], horizontal=True)
                    P["wp_guete"] = st.number_input(
                        "Gütegrad [–]", 0.2, 0.7, 0.40 if P["wp_quelle"] == "Luft" else 0.50, 0.01,
                        key=f"guete_{P['wp_quelle']}", help="COP = Gütegrad × Carnot-COP.")
                    P["wp_heizstab"] = st.checkbox("Heizstab deckt Restbedarf", value=True,
                                                   help="Nur wirksam, wenn die WP zu klein ist und "
                                                        "kein Kessel den Rest deckt.")
                else:
                    P[f"{n}_eta"] = st.number_input("Nutzungsgrad [%]", 50.0, 105.0, ETA0[n], 1.0,
                                                    key=f"eta_{n}") / 100
            elif n == "ko":
                st.markdown("**Kachelofen**")
                auto = st.checkbox("automatisch auslegen", value=True, key="auto_ko")
                P["ko_kw"] = groesse("Wärmeleistung [kW]", min(6.0, max(2.0, halb(0.5 * spitze))), "kw_ko",
                                     1.0, 20.0, 0.5, auto, hilfe="Automatik: halbe Spitzenlast, 2 bis 6 kW.")
                c1, c2 = st.columns(2)
                P["ko_start"] = c1.number_input("Betrieb von [h]", 0, 23, 17)
                P["ko_ende"] = c2.number_input("bis [h]", 1, 24, 22)
                P["ko_tgrenz"] = st.number_input("nur bei Tagesmittel unter [°C]", -10.0, 20.0, 8.0, 1.0)
                P["ko_eta"] = st.number_input("Wirkungsgrad [%]", 40.0, 95.0, 75.0, 1.0) / 100
                auslegung.append(f"Kachelofen: {de(P['ko_kw'], 1)} kW" + ("" if auto else " (manuell)"))
            else:
                st.markdown("**Solarthermie**")
                auto = st.checkbox("automatisch auslegen", value=True, key="auto_st")
                a0 = max(4.0, round(1.5 * P["personen"]))
                P["st_flaeche"] = groesse("Kollektorfläche [m²]", a0, "st_a", 1.0, 100.0, 1.0, auto,
                                          hilfe="Automatik: 1,5 m² je Person, mindestens 4 m².")
                P["sp_liter"] = groesse("Pufferspeicher [Liter]",
                                        max(300.0, round(75 * P["st_flaeche"] / 50) * 50), "st_l",
                                        0.0, 5000.0, 50.0, auto, fmt="%.0f",
                                        hilfe="Automatik: 75 Liter je m² Kollektor, mindestens 300 Liter.")
                P["st_tm"] = st.number_input("Mittlere Kollektortemperatur [°C]", 30.0, 90.0, 50.0, 5.0)
                auslegung.append(f"Solarthermie: {de(P['st_flaeche'])} m², {de(P['sp_liter'])} l"
                                 + ("" if auto else " (manuell)"))

    # --- PV und Batterie (brauchen den Stromverbrauch inkl. Wärmepumpe) ----------
    st.subheader("Photovoltaik und Batterie")
    _, k1 = rechne(wetter, {**P, "pv_kwp": 0.0, "bat_kwh": 0.0})
    verbrauch = k1["strom_gesamt"]
    if not t_pv:
        st.caption("Photovoltaik ist nicht gewählt.")
    else:
        spalten = st.columns(3)
        with spalten[0], st.container(border=True):
            st.markdown("**Photovoltaik**")
            auto = st.checkbox("automatisch auslegen", value=True, key="auto_pv")
            kwp0 = min(30.0, max(5.0, halb(verbrauch / max(spez_ertrag, 1.0))))
            P["pv_kwp"] = groesse("PV-Leistung [kWp]", kwp0, "pv", 0.5, 100.0, 0.5, auto,
                                  hilfe="Automatik: PV-Jahresertrag ≈ Jahresstromverbrauch inkl. "
                                        "Wärmepumpe (bilanziell ausgeglichen), 5 bis 30 kWp.")
            auslegung.insert(0, f"PV: {de(P['pv_kwp'], 1)} kWp" + ("" if auto else " (manuell)"))
        if t_bat:
            with spalten[1], st.container(border=True):
                st.markdown("**Batteriespeicher**")
                auto = st.checkbox("automatisch auslegen", value=True, key="auto_bat")
                kwh0 = max(2.0, float(round(min(P["pv_kwp"], verbrauch / 1000.0))))
                P["bat_kwh"] = groesse("Kapazität [kWh]", kwh0, "bat_kwh", 1.0, 100.0, 1.0, auto,
                                       hilfe="Automatik: 1 kWh je kWp PV, höchstens 1 kWh je "
                                             "1.000 kWh Jahresverbrauch.")
                P["bat_kw"] = groesse("Lade-/Entladeleistung [kW]", max(halb(0.5 * P["bat_kwh"]), 0.5),
                                      "bat_kw", 0.5, 50.0, 0.5, auto, hilfe="Automatik: 0,5 C.")
                P["bat_eta"] = st.number_input("Zykluswirkungsgrad [%]", 60.0, 100.0, 90.0, 1.0) / 100
                auslegung.insert(1, f"Batterie: {de(P['bat_kwh'])} kWh / {de(P['bat_kw'], 1)} kW"
                                 + ("" if auto else " (manuell)"))

    st.subheader("CO₂-Faktoren und Preise")
    st.caption("CO₂ in g/kWh Endenergie, Preise in €/kWh")
    c = st.columns(4)
    for j, (kurz, name, co2, preis) in enumerate((("strom", "Strom (Netz)", 380.0, 0.35),
                                                  ("gas", "Erdgas", 240.0, 0.11),
                                                  ("oel", "Heizöl", 310.0, 0.10),
                                                  ("holz", "Holz", 20.0, 0.07))):
        with c[j]:
            P[f"co2_{kurz}"] = st.number_input(f"CO₂ {name}", 0.0, 1000.0, co2, 10.0)
            P[f"preis_{kurz}"] = st.number_input(f"Preis {name}", 0.0, 2.0, preis, 0.01)
    P["verguetung"] = c[0].number_input("Einspeisevergütung [€/kWh]", 0.0, 1.0, 0.08, 0.01)

with ausl_box:
    st.divider()
    st.markdown("**Auslegung**\n\n" + "\n".join(f"- {z}" for z in auslegung)
                if auslegung else "Keine Technologie gewählt.")
    st.caption("Ändern im Reiter „🔧 Auslegung und Details“.")

# ---------------------------------------------------------------------------
# Rechnen
# ---------------------------------------------------------------------------
ts, k = rechne(wetter, P)

with kopf:
    st.caption(f"Jahressimulation in 15-Minuten-Auflösung · {ort} ({de(lat, 2)}° N, {de(lon, 2)}° O) · "
               f"Wetterjahr {jahr} · Wetterdaten: {quelle}")
    if quelle == "synthetisch" and not offline:
        c1, c2 = st.columns([5, 1])
        c1.warning("PVGIS war nicht erreichbar – es wird mit **synthetischen Wetterdaten** gerechnet "
                   "(Sonnenstandsmodell + Zufallswetter, Temperatur als Sinusgang mit Rauschen).")
        if c2.button("Erneut versuchen"):
            st.session_state["pvgis_fehler"] = {}
            st.rerun()
    if k["q_ungedeckt"] > 1.0:
        st.error(f"**{de(k['q_ungedeckt'])} kWh Wärme bleiben ungedeckt** "
                 f"({de(100 * k['q_ungedeckt'] / k['waerme_bedarf'], 1)} % des Bedarfs). "
                 "Wärmeerzeuger hinzufügen oder im Reiter „Auslegung und Details“ die Leistung erhöhen.")

LAYOUT = dict(margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified",
              legend=dict(orientation="h", yanchor="top", y=-0.22, x=0))   # Legende unter dem Diagramm


def balken_h(werte: dict, einheit: str, titel: str, achse: str) -> go.Figure:
    """Dezentes horizontales Balkendiagramm mit Wertbeschriftung."""
    fig = go.Figure(go.Bar(
        x=list(werte.values()), y=list(werte.keys()), orientation="h", marker_color=C["balken"],
        marker_line_width=0, width=0.5, text=[f"{de(v)} {einheit}" for v in werte.values()],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{x:,.0f} " + einheit + "<extra></extra>"))
    lo, hi = min(min(werte.values(), default=0), 0), max(max(werte.values(), default=1), 0)
    spanne = (hi - lo) or 1.0
    fig.update_xaxes(range=[lo - (0.22 * spanne if lo < 0 else 0), hi + 0.22 * spanne])
    fig.update_layout(title=titel, xaxis_title=achse, margin=dict(l=10, r=10, t=40, b=10),
                      height=90 + 55 * max(len(werte), 1), yaxis=dict(autorange="reversed"))
    return fig


# ---------------------------------------------------------------------------
# Reiter: Jahresübersicht
# ---------------------------------------------------------------------------
with tab_jahr:
    st.subheader("Strom")
    m = st.columns(3) + st.columns(3)
    m[0].metric("Stromverbrauch", f"{de(k['strom_gesamt'])} kWh",
                help="Haushaltsstrom + Wärmepumpe + Heizstab")
    m[1].metric("PV-Erzeugung", f"{de(k['pv'])} kWh")
    m[2].metric("Netzbezug", f"{de(k['netzbezug'])} kWh")
    m[3].metric("Einspeisung", f"{de(k['einspeisung'])} kWh")
    m[4].metric("Autarkiegrad", f"{de(100 * k['autarkie'], 1)} %",
                help="Anteil des Stromverbrauchs, der nicht aus dem Netz stammt.")
    m[5].metric("Eigenverbrauchsquote", f"{de(100 * k['eigenverbrauchsquote'], 1)} %",
                help="Anteil der PV-Erzeugung, der im Gebäude genutzt wird (inkl. Batterieverluste).")

    st.subheader("Wärme, Emissionen und Kosten")
    m = st.columns(3) + st.columns(3)
    m[0].metric("Wärmebedarf", f"{de(k['waerme_bedarf'])} kWh",
                help=f"Raumwärme {de(k['waerme_raum'])} kWh + Warmwasser {de(k['waerme_ww'])} kWh (Nutzwärme)")
    m[1].metric("Max. Wärmelast", f"{de(k['heizlast_max'], 1)} kW")
    m[2].metric("Jahresarbeitszahl WP", "–" if np.isnan(k["jaz"]) else de(k["jaz"], 2))
    m[3].metric("CO₂-Emissionen", f"{de(k['co2_gesamt'])} kg",
                help=f"Ohne Gutschrift. Einspeisung verdrängt rechnerisch {de(k['co2_vermieden'])} kg CO₂ im Netz.")
    m[4].metric("CO₂ je m² Wohnfläche", f"{de(k['co2_gesamt'] / P['flaeche'], 1)} kg/m²")
    m[5].metric("Energiekosten (netto)", f"{de(k['kosten_netto'])} €",
                help=f"Brennstoff- und Strombezugskosten abzüglich {de(k['erloes'])} € Einspeiseerlös. "
                     "Ohne Investition, Wartung und Grundpreise.")

    mon = ts.groupby(ts.index.month).sum() * DT
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for col, name, farbe in STROM:
            if k[col] > 0.5 or col == "netzbezug":
                fig.add_bar(x=MONATE, y=mon[col], name=name, marker_color=farbe,
                            hovertemplate="%{y:,.0f} kWh")
        if k["einspeisung"] > 0.5:
            fig.add_bar(x=MONATE, y=-mon["einspeisung"], name="Einspeisung", marker_color=C["einsp"],
                        hovertemplate="%{y:,.0f} kWh")
        fig.update_layout(barmode="relative", bargap=0.25, yaxis_title="kWh",
                          title="Strom je Monat: Verbrauch nach Herkunft (oben), Einspeisung (unten)",
                          **LAYOUT)
        fig.update_traces(marker_line_width=0)
        fig.add_hline(y=0, line_width=1, line_color="#898781")
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = go.Figure()
        for col, name, farbe in WAERME:
            if k[col] > 0.5:
                fig.add_bar(x=MONATE, y=mon[col], name=name, marker_color=farbe,
                            hovertemplate="%{y:,.0f} kWh")
        fig.update_layout(barmode="stack", bargap=0.25, title="Wärmebereitstellung je Monat",
                          yaxis_title="kWh (Nutzwärme)", **LAYOUT)
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        co2 = {n: v for n, v in k["co2"].items() if v > 0.5}
        st.plotly_chart(balken_h(co2, "kg", "CO₂-Emissionen nach Energieträger", "kg CO₂ pro Jahr"),
                        width="stretch")
    with c2:
        kos = {n: v for n, v in k["kosten"].items() if v > 0.5}
        if k["erloes"] > 0.5:
            kos["Einspeiseerlös"] = -k["erloes"]
        st.plotly_chart(balken_h(kos, "€", "Energiekosten nach Energieträger", "€ pro Jahr"),
                        width="stretch")

    st.subheader("Jahresbilanz")
    c1, c2 = st.columns(2)
    strom_tab = pd.DataFrame({
        "Position": ["Haushaltsstrom", "Wärmepumpe", "Heizstab", "Verbrauch gesamt", "PV-Erzeugung",
                     "davon direkt verbraucht", "in Batterie geladen", "aus Batterie entladen",
                     "Netzbezug", "Einspeisung"],
        "kWh/a": [k["strom_haushalt"], k["strom_wp"], k["strom_heizstab"], k["strom_gesamt"], k["pv"],
                  k["pv_direkt"], k["bat_laden"], k["bat_entladen"], k["netzbezug"], k["einspeisung"]],
    })
    strom_tab["kWh/a"] = strom_tab["kWh/a"].clip(lower=0)
    c1.markdown("**Strom**")
    c1.dataframe(strom_tab, hide_index=True, width="stretch",
                 column_config={"kWh/a": st.column_config.NumberColumn(format="%.0f")})
    waerme_tab = pd.DataFrame({
        "Position": ["Raumwärme", "Warmwasser", "Bedarf gesamt"] + [n for _, n, _ in WAERME]
                    + ["Endenergie Erdgas", "Endenergie Heizöl", "Endenergie Holz",
                       "Solarthermie: Kollektorertrag möglich", "Solarthermie: genutzt/gespeichert"],
        "kWh/a": [k["waerme_raum"], k["waerme_ww"], k["waerme_bedarf"]] + [k[c] for c, _, _ in WAERME]
                 + [k["end_gas"], k["end_oel"], k["end_holz"], k["st_ertrag"], k["st_genutzt"]],
    })
    c2.markdown("**Wärme**")
    c2.dataframe(waerme_tab, hide_index=True, width="stretch",
                 column_config={"kWh/a": st.column_config.NumberColumn(format="%.0f")})

    st.download_button("Zeitreihen (15 min) als CSV herunterladen",
                       ts.round(4).to_csv(sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"gebaeude_{ort}_{jahr}_15min.csv", mime="text/csv")

# ---------------------------------------------------------------------------
# Reiter: Typische Woche je Jahreszeit
# ---------------------------------------------------------------------------
JAHRESZEITEN = {  # Name -> (Monate, Stichtag der Beispielwoche)
    "Winter": ([12, 1, 2], (1, 15)), "Frühling": ([3, 4, 5], (4, 15)),
    "Sommer": ([6, 7, 8], (7, 15)), "Herbst": ([9, 10, 11], (10, 15)),
}


def woche(ts_: pd.DataFrame, monate, stichtag, art: str, stunde: bool):
    """Wochenausschnitt (Mo–So) und Achsenbeschriftung."""
    if art.startswith("Beispiel"):
        start = pd.Timestamp(ts_.index[0].year, *stichtag)
        start += pd.Timedelta(days=(7 - start.dayofweek) % 7)          # nächster Montag
        w = ts_.loc[start:start + pd.Timedelta(days=7) - pd.Timedelta(minutes=15)]
        labels = [f"{TAGE[i]} {(start + pd.Timedelta(days=i)):%d.%m.}" for i in range(7)]
    else:
        s = ts_[ts_.index.month.isin(monate)]
        w = s.groupby([s.index.dayofweek, s.index.hour, s.index.minute]).mean()
        start = pd.Timestamp("2024-01-01")                              # ein Montag (Hilfsdatum)
        w.index = pd.date_range(start, periods=len(w), freq="15min")
        labels = TAGE
    if stunde:
        w = w.resample("h").mean()
    ticks = [start + pd.Timedelta(days=i, hours=12) for i in range(7)]
    return w, ticks, labels


def wochen_fig(w, ticks, labels, titel, flaechen, linien, ymax, hoehe=380):
    """Gestapelte Flächen (Deckung) plus Linien (Bedarf/Erzeugung) über eine Woche."""
    fig = go.Figure()
    for col, bez, farbe in flaechen:
        fig.add_scatter(x=w.index, y=w[col], name=bez, stackgroup="a", mode="lines",
                        line=dict(width=0.5, color=farbe), fillcolor=farbe,
                        hovertemplate="%{y:.2f} kW")
    for col, bez, stil in linien:
        fig.add_scatter(x=w.index, y=w[col], name=bez, mode="lines", line=stil,
                        hovertemplate="%{y:.2f} kW")
    fig.update_xaxes(tickmode="array", tickvals=ticks, ticktext=labels, showgrid=False)
    for i in range(1, 7):       # Tagesgrenzen
        fig.add_vline(x=ticks[0] + pd.Timedelta(days=i, hours=-12), line_width=1,
                      line_color="rgba(137,135,129,0.35)")
    fig.update_layout(title=titel, height=hoehe, yaxis_title="kW", yaxis_range=[0, ymax], **LAYOUT)
    return fig


with tab_woche:
    c1, c2, c3 = st.columns([3, 2, 2])
    art = c1.radio("Darstellung", ["Beispielwoche (Mitte der Jahreszeit)", "Mittlere Woche der Jahreszeit"],
                   horizontal=True,
                   help="Beispielwoche: reale Kalenderwoche ab dem ersten Montag nach dem 15. des "
                        "mittleren Monats. Mittlere Woche: Mittelwert aller Wochen der Jahreszeit je "
                        "Wochentag und Uhrzeit (glättet das Wetter).")
    stunde = c2.radio("Auflösung", ["1 Stunde", "15 Minuten"], horizontal=True) == "1 Stunde"
    gleich = c3.checkbox("Gleiche Achsen für alle Jahreszeiten", value=True,
                         help="Erleichtert den Vergleich zwischen den Jahreszeiten.")

    wochen = {n: woche(ts, mo, tag, art, stunde) for n, (mo, tag) in JAHRESZEITEN.items()}
    f_strom = [x for x in STROM if k[x[0]] > 0.5 or x[0] == "netzbezug"]
    l_strom = [("strom_last", "Stromverbrauch", dict(color=C["linie"], width=2))]
    if k["pv"] > 0.5:
        l_strom.append(("pv", "PV-Erzeugung", dict(color=C["pv"], width=2, dash="dot")))
    f_waerme = [x for x in WAERME if k[x[0]] > 0.5]
    l_waerme = [("waerme_bedarf", "Wärmebedarf", dict(color=C["linie"], width=2))]
    max_s = 1.08 * max(max(w["strom_last"].max(), w["pv"].max()) for w, _, _ in wochen.values())
    max_w = 1.08 * max(w["waerme_bedarf"].max() for w, _, _ in wochen.values())

    for name, (w, ticks, labels) in wochen.items():
        st.subheader(name)
        e = lambda col: float(w[col].sum() * (1.0 if stunde else DT))
        st.markdown(
            f"Wochensummen: Stromverbrauch **{de(e('strom_last'))} kWh** · PV-Erzeugung "
            f"**{de(e('pv'))} kWh** · Netzbezug **{de(e('netzbezug'))} kWh** · Einspeisung "
            f"**{de(e('einspeisung'))} kWh** · Wärmebedarf **{de(e('waerme_bedarf'))} kWh** · "
            f"Außentemperatur im Mittel **{de(w['t_aussen'].mean(), 1)} °C** "
            f"({de(w['t_aussen'].min(), 1)} bis {de(w['t_aussen'].max(), 1)} °C)")
        c1, c2 = st.columns(2)
        ys = max_s if gleich else 1.08 * max(w["strom_last"].max(), w["pv"].max())
        yw = max_w if gleich else 1.08 * max(w["waerme_bedarf"].max(), 0.1)
        c1.plotly_chart(wochen_fig(w, ticks, labels, f"Strom – {name}", f_strom, l_strom, ys),
                        width="stretch", key=f"ws_{name}")
        c2.plotly_chart(wochen_fig(w, ticks, labels, f"Wärme – {name}", f_waerme, l_waerme, yw),
                        width="stretch", key=f"ww_{name}")

# ---------------------------------------------------------------------------
# Reiter: Annahmen und Daten
# ---------------------------------------------------------------------------
with tab_annahmen:
    st.subheader("Wetter- und Ertragsdaten")
    if quelle == "PVGIS":
        st.markdown(
            f"Quelle: **PVGIS 5.3** (JRC, `seriescalc`), Stundenwerte {jahr} für {de(lat, 2)}° N / "
            f"{de(lon, 2)}° O: PV-Leistung je kWp (kristallines Silizium, 14 % Systemverluste), "
            "Globalstrahlung in Modulebene G(i), Außentemperatur T2m. Die Werte werden von UTC nach "
            "MEZ verschoben (keine Sommerzeit), der 29. Februar entfällt, und sie werden linear auf "
            "15 Minuten interpoliert.")
    else:
        st.markdown(
            "Quelle: **synthetische Daten** (Fallback): Sonnenstandsgeometrie für die geneigte Fläche, "
            "Tages-Klarheitsindex als AR(1)-Zufallsprozess, skaliert auf 1 250 kWh/m²a in Modulebene; "
            "PV mit Performance Ratio 0,86; Temperatur als Jahres- und Tagesgang mit Wetterrauschen "
            "(Jahresmittel ca. 9,5 °C). Nicht standortgenau – nur zur Demonstration.")
    m = st.columns(4)
    m[0].metric("Einstrahlung Modulebene", f"{de(wetter['g'].sum() * DT / 1000)} kWh/m²a")
    m[1].metric("Spez. PV-Ertrag", f"{de(spez_ertrag)} kWh/kWp")
    m[2].metric("Jahresmitteltemperatur", f"{de(wetter['t2m'].mean(), 1)} °C")
    m[3].metric("Minimum / Maximum", f"{de(wetter['t2m'].min(), 1)} / {de(wetter['t2m'].max(), 1)} °C")
    tag = wetter.resample("D").mean().dropna()
    c1, c2 = st.columns(2)
    fig = go.Figure(go.Scatter(x=tag.index, y=tag["t2m"], mode="lines",
                               line=dict(color=C["linie"], width=2), hovertemplate="%{y:.1f} °C<extra></extra>"))
    fig.update_layout(title="Tagesmittel der Außentemperatur", yaxis_title="°C", height=300,
                      margin=dict(l=10, r=10, t=40, b=10))
    c1.plotly_chart(fig, width="stretch")
    gm = wetter["g"].groupby(wetter.index.month).sum() * DT / 1000
    fig = go.Figure(go.Bar(x=MONATE, y=gm.values, marker_color=C["pv"],
                           hovertemplate="%{y:.0f} kWh/m²<extra></extra>"))
    fig.update_layout(title="Einstrahlung in Modulebene je Monat", yaxis_title="kWh/m²", height=300,
                      margin=dict(l=10, r=10, t=40, b=10))
    c2.plotly_chart(fig, width="stretch")

    st.subheader("Bedarf")
    st.markdown(f"""
- **Raumwärme:** Jahresbedarf = spezifischer Heizwärmebedarf × Wohnfläche (Nutzwärme, Richtwerte je
  Gebäudestandard, siehe Tabelle). Zeitliche Verteilung nach **Gradstunden**: Last ∝ max(0, Heizgrenze −
  wirksame Außentemperatur); wirksame Temperatur = Mittel aus aktuellem Wert und gleitendem 24-h-Mittel
  (Gebäudeträgheit). Nachtabsenkung 23–5 Uhr (Faktor 0,75), Aufheizen 6–8 Uhr (1,15). Der Jahresbedarf wird
  unabhängig vom Wetterjahr auf den Richtwert skaliert – ein kaltes Jahr verschiebt also nur die Verteilung.
- **Warmwasser:** {de(P['ww_kwh_person'])} kWh Nutzwärme je Person und Jahr (≈ 40 l/Tag bei ΔT = 35 K),
  Tagesprofil mit Morgen-, Mittags- und Abendspitze, ±10 % Jahresgang.
- **Haushaltsstrom:** Jahresbedarf nach Personenzahl (Größenordnung Stromspiegel, Einfamilienhaus ohne
  elektrische Warmwasserbereitung). Das Profil ist **synthetisch in Anlehnung an BDEW H0**: eigene Typtage
  (Werktag, Samstag, Sonntag) aus Grundlast und drei Verbrauchsspitzen, Jahresgang mit der originalen
  H0-Dynamisierungsfunktion. Es ist ein geglättetes Mittel vieler Haushalte – ein einzelner Haushalt hat
  höhere Spitzen, Eigenverbrauch und Autarkie werden daher eher **überschätzt**. Feiertage werden nicht
  berücksichtigt.
""")
    c1, c2 = st.columns([3, 2])
    c1.dataframe(pd.DataFrame(
        [(n, a, b, c) for n, (a, b, c) in model.GEBAEUDESTANDARDS.items()],
        columns=["Gebäudestandard", "Heizwärme [kWh/m²a]", "Heizgrenze [°C]", "Vorlauf bei −14 °C [°C]"]),
        hide_index=True, width="stretch")
    c2.dataframe(pd.DataFrame(list(model.STROMBEDARF_PERSONEN.items()),
                              columns=["Personen", "Haushaltsstrom [kWh/a]"]),
                 hide_index=True, width="stretch")

    st.subheader("Wärmepumpe: COP in Abhängigkeit von der Außentemperatur")
    st.markdown(f"""
COP = Gütegrad × Carnot-COP = Gütegrad · T_Senke / (T_Senke − T_Quelle), begrenzt auf
1 … {de(P['wp_cop_max'], 1)}, Mindest-Temperaturhub 8 K. Der COP wird in **jedem Viertelstundenschritt** aus der
aktuellen Außentemperatur berechnet:
- **Quelle:** Luft = Außentemperatur (Gütegrad 0,40); Erdreich = konstant 3 °C Soletemperatur (Gütegrad 0,50).
- **Senke Heizung:** lineare Heizkurve von 25 °C Vorlauf (bei 20 °C außen) bis zur Auslegungs-Vorlauftemperatur
  des gewählten Heizsystems bei −14 °C. Aktuell: **{hs}**, Quelle **{P['wp_quelle']}**,
  Gütegrad {de(P['wp_guete'], 2)}.
- **Senke Warmwasser:** konstant 55 °C.
- Die Heizleistung ist temperaturunabhängig; ein Heizstab (η = 1) deckt optional den Rest.
""")
    ta_ = np.linspace(-15, 20, 71)
    fig = go.Figure()
    for i, (name_, vl_) in enumerate(model.HEIZSYSTEME.items()):
        aktiv = name_ == hs
        fig.add_scatter(x=ta_, y=model.cop_waermepumpe(ta_, model.vorlauftemperatur(ta_, vl_),
                                                       P["wp_quelle"], P["wp_guete"], P["wp_cop_max"]),
                        name=name_ + (" – gewählt" if aktiv else ""), mode="lines",
                        line=dict(color=C["netz"] if aktiv else "#b7d3f6", width=3 if aktiv else 1.5),
                        hovertemplate="%{y:.2f}")
    fig.add_scatter(x=ta_, y=model.cop_waermepumpe(ta_, model.T_WARMWASSER, P["wp_quelle"], P["wp_guete"],
                                                   P["wp_cop_max"]),
                    name="Warmwasser (55 °C)", mode="lines", line=dict(color=C["oel"], width=2, dash="dot"),
                    hovertemplate="%{y:.2f}")
    fig.update_layout(height=420, xaxis_title="Außentemperatur [°C]", yaxis_title="COP [–]",
                      yaxis_rangemode="tozero", **LAYOUT)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Bereitstellung und automatische Auslegung")
    st.markdown(f"""
- **Einsatzreihenfolge Wärme:** Solarthermie/Speicher → Kachelofen → Wärmepumpe → Holz → Gas → Öl →
  Heizstab. Jeder Erzeuger deckt den verbleibenden Bedarf bis zu seiner Leistung.
- **Automatische Auslegung Wärme:** Basis ist die Spitzenlast aus Raumwärme und Warmwasser. Ein einzelner
  Hauptwärmeerzeuger (Wärmepumpe, Holz, Gas, Öl) deckt sie vollständig. Bei mehreren erhält jeder vorrangige
  Erzeuger 60 % der verbleibenden Spitzenlast (Grundlast, z. B. Wärmepumpe im Hybridsystem), der letzte
  deckt den Rest. Kachelofen: halbe Spitzenlast (2–6 kW). Solarthermie: 1,5 m² Kollektor je Person
  (mind. 4 m²), 75 l Speicher je m² (mind. 300 l).
- **Automatische Auslegung Strom:** PV so, dass der Jahresertrag etwa dem Jahresstromverbrauch inkl.
  Wärmepumpe entspricht (5–30 kWp). Batterie: 1 kWh je kWp, höchstens 1 kWh je 1.000 kWh Jahresverbrauch,
  Leistung 0,5 C.
- **Photovoltaik:** PVGIS-Leistung je kWp × installierte Leistung. PV deckt zuerst die Last, lädt dann die
  Batterie, der Rest wird eingespeist.
- **Batterie:** Laden nur aus PV-Überschuss, Entladen nur zur Lastdeckung; Zykluswirkungsgrad
  {de(100 * P['bat_eta'])} % (je zur Hälfte beim Laden und Entladen), keine Selbstentladung, nutzbare
  Kapazität = Nennkapazität.
- **Solarthermie:** Kollektorkennlinie η = η₀ − a₁·ΔT/G − a₂·ΔT²/G mit η₀ = {de(P['st_eta0'], 2)},
  a₁ = {de(P['st_a1'], 1)} W/m²K, a₂ = {de(P['st_a2'], 3)} W/m²K², konstante mittlere Kollektortemperatur
  {de(P['st_tm'])} °C. Gleiche Ausrichtung wie die PV. Der Ertrag deckt erst Warmwasser, dann Raumwärme und
  lädt einen Pufferspeicher (Kapazität = Volumen × 1,163 Wh/l·K × {de(P['sp_dt'])} K, Verlust
  {de(P['sp_verlust'], 1)} % des Inhalts je Stunde). Der Speicher wird nur solar beladen.
- **Kachelofen:** deckt nur Raumwärme, im gewählten Zeitfenster an Tagen mit Tagesmitteltemperatur unter dem
  Grenzwert, höchstens mit seiner Wärmeleistung (keine Speichermasse modelliert).
- **Kessel:** Brennstoffeinsatz = Wärme / Jahresnutzungsgrad (heizwertbezogen): Gas-Brennwert 95 %, Öl 88 %,
  Holz 85 %, Kachelofen 75 %. Kein Taktverhalten, keine Teillastabhängigkeit.
""")
    st.subheader("Emissionen und Kosten")
    st.markdown(f"""
- **CO₂-Faktoren** (g/kWh Endenergie, editierbar): Erdgas 240, Heizöl 310, Holz 20 (Werte nach GEG
  Anlage 9); Netzstrom 380 als ungefährer deutscher Strommix der letzten Jahre (GEG-Rechenwert: 560).
  Aktuell gerechnet mit Strom {de(P['co2_strom'])}, Gas {de(P['co2_gas'])}, Öl {de(P['co2_oel'])},
  Holz {de(P['co2_holz'])} g/kWh. Für eingespeisten PV-Strom gibt es keine Gutschrift; die rechnerisch
  verdrängte Menge wird nur als Hinweis ausgewiesen.
- **Kosten:** nur Arbeitspreise (Strom {de(P['preis_strom'], 2)}, Gas {de(P['preis_gas'], 2)},
  Öl {de(P['preis_oel'], 2)}, Holz {de(P['preis_holz'], 2)} €/kWh) abzüglich Einspeisevergütung
  {de(P['verguetung'], 2)} €/kWh. Keine Investitions-, Wartungs- und Grundkosten.
""")
