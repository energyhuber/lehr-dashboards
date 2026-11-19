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
import streamlit.components.v1 as components

from pathlib import Path

import auslegung as ausl_mod
import data
import fluss as fluss_mod
import kosten
import model
import preise as tarif_mod
import studie
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
    # Modellstand: Schichtspeicher mit 10 Schichten und Schichttemperaturen (Änderung leert den Zwischenspeicher)
    return model.simulate(wetter, params)


@st.cache_data(show_spinner="Optimiere den Betrieb der Wärmepumpe …")
def studie_rechnen(t_aussen, params, jahr):
    return studie.loese(t_aussen, params, jahr)


@st.cache_data(show_spinner="Optimiere den Betrieb auf minimale Kosten …")
def studie_preis_rechnen(t_aussen, params, jahr, preis, holzpreis):
    return studie.loese(t_aussen, params, jahr, preis=preis, holzpreis=holzpreis)


@st.cache_data(show_spinner="Lade Day-Ahead-Preise von SMARD …")
def spotpreise(jahr):
    return tarif_mod.spotpreis(jahr)


@st.cache_data(show_spinner=False)
def studie_ergebnisse(datei, mtime):
    return pd.read_csv(datei, sep=";", decimal=",", encoding="utf-8-sig")


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
tab_jahr, tab_woche, tab_detail, tab_kosten, tab_studie, tab_preis, tab_opt, tab_annahmen = st.tabs(
    ["📊 Jahresübersicht", "📈 Typische Woche je Jahreszeit", "🔧 Auslegung und Details",
     "💶 Kosten", "🔬 Studie: JAZ steigern", "⚡ Flexible Strompreise", "🎯 Optimierte Auslegung", "📋 Annahmen und Daten"])

wetter, quelle = wetterdaten(float(lat), float(lon), float(neigung), float(azimut), int(jahr), offline)
spez_ertrag = float(wetter["pv"].sum() * DT)

# ---------------------------------------------------------------------------
# Reiter: Auslegung und Details (Eingaben; wird vor der Simulation ausgewertet)
# ---------------------------------------------------------------------------
auslegung = []      # Zeilen für die Kurzübersicht in der Seitenleiste
groessen = {}       # Technologie -> (Größe, Zeitreihe für die Größe bei „0 = unbegrenzt“)
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
                    groessen["Wärmepumpe Luft" if P["wp_quelle"] == "Luft"
                             else "Wärmepumpe Erdreich"] = (kw, "q_wp")
                    P["wp_guete"] = st.number_input(
                        "Gütegrad [–]", 0.2, 0.7, 0.40 if P["wp_quelle"] == "Luft" else 0.50, 0.01,
                        key=f"guete_{P['wp_quelle']}", help="COP = Gütegrad × Carnot-COP.")
                    P["wp_heizstab"] = st.checkbox("Heizstab deckt Restbedarf", value=True,
                                                   help="Nur wirksam, wenn die WP zu klein ist und "
                                                        "kein Kessel den Rest deckt.")
                else:
                    groessen[NAMEN[n]] = (kw, f"q_{n}")
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
                groessen["Kachelofen"] = (P["ko_kw"], None)
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
                P["st_dt_koll"] = st.number_input(
                    "Kollektor über Speichertemperatur [K]", 0.0, 30.0, 10.0, 1.0,
                    help="Die mittlere Kollektortemperatur folgt der Temperatur unten im Speicher: "
                         "Speichertemperatur plus dieser Aufschlag (Wärmetauscher, halbe Kollektorspreizung).")
                P["sp_t_max"] = st.number_input(
                    "Maximale Speichertemperatur [°C]", 60.0, 95.0, 85.0, 5.0,
                    help="Ist der ganze Speicher so warm, steht der Kollektor still (Stagnation).")
                P["sp_schichten"] = st.number_input(
                    "Schichten im Speicher", 1, 20, 10, 1,
                    help="1 = durchmischter Speicher. Mehr Schichten: unten bleibt es kühler, "
                         "der Kollektor arbeitet effizienter, oben steht früher warmes Wasser bereit.")
                auslegung.append(f"Solarthermie: {de(P['st_flaeche'])} m², {de(P['sp_liter'])} l"
                                 + ("" if auto else " (manuell)"))
                groessen["Solarthermie"] = (P["st_flaeche"], None)

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
            groessen["Photovoltaik"] = (P["pv_kwp"], None)
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
                groessen["Batteriespeicher"] = (P["bat_kwh"], None)

    st.subheader("CO₂-Faktoren")
    st.caption("In g/kWh Endenergie. Energiepreise und Investitionskosten stehen im Reiter „💶 Kosten“.")
    c = st.columns(4)
    for j, (kurz, name, co2) in enumerate((("strom", "Strom (Netz)", 380.0), ("gas", "Erdgas", 240.0),
                                           ("oel", "Heizöl", 310.0), ("holz", "Holz", 20.0))):
        P[f"co2_{kurz}"] = c[j].number_input(f"CO₂ {name}", 0.0, 1000.0, co2, 10.0)

# ---------------------------------------------------------------------------
# Reiter: Kosten – Annahmen (Ergebnisse werden nach der Simulation oben eingefügt)
# ---------------------------------------------------------------------------
with tab_kosten:
    kosten_erg = st.container()
    st.divider()
    st.subheader("Annahmen zur Kostenrechnung")
    st.caption("Alle Werte sind Richtwerte (Endkundenpreise inkl. MwSt. und Installation) und editierbar: "
               "Zelle anklicken und überschreiben.")
    c1, c2 = st.columns([1, 2])
    with c1:
        zins = st.number_input("Kalkulationszinssatz [%/a]", 0.0, 15.0, 4.0, 0.25,
                               help="Zinssatz für die Annuität. 0 % = lineare Abschreibung.") / 100
        P["verguetung"] = st.number_input("Einspeisevergütung [€/kWh]", 0.0, 1.0, 0.08, 0.005,
                                          format="%.3f")
    with c2:
        st.markdown("**Energiepreise**")
        preise = st.data_editor(
            kosten.preise_df(), key="ed_preise", width="stretch", num_rows="fixed", disabled=["_index"],
            column_config={
                "Arbeitspreis [€/kWh]": st.column_config.NumberColumn(min_value=0.0, step=0.005, format="%.3f"),
                "Grundpreis [€/a]": st.column_config.NumberColumn(
                    min_value=0.0, step=10.0, format="%.0f",
                    help="Strom: fällt immer an. Übrige: nur, wenn der Energieträger genutzt wird.")})
    for kurz, name in kosten.TRAEGER.items():
        P[f"preis_{kurz}"] = kosten._f(preise.loc[name, "Arbeitspreis [€/kWh]"])
    st.markdown("**Investitionen je Technologie** – Investition = Fixkosten + spezifische Kosten × Größe; "
                "angerechnet werden nur die gewählten Technologien.")
    inv_annahmen = st.data_editor(
        kosten.invest_df(), key="ed_invest", width="stretch", num_rows="fixed", disabled=["Einheit", "_index"],
        column_config={
            "Einheit": st.column_config.TextColumn(help="Bezugsgröße der spezifischen Kosten"),
            "Fixkosten [€]": st.column_config.NumberColumn(min_value=0.0, step=500.0, format="%.0f"),
            "spez. Kosten [€/Einheit]": st.column_config.NumberColumn(min_value=0.0, step=50.0, format="%.0f"),
            "Förderung [%]": st.column_config.NumberColumn(
                min_value=0.0, max_value=100.0, step=5.0, format="%.0f",
                help="Zuschuss in % der Investition (z. B. BEG-Grundförderung 30 %)."),
            "Nutzungsdauer [a]": st.column_config.NumberColumn(min_value=1, max_value=60, step=1, format="%d"),
            "Wartung [%/a]": st.column_config.NumberColumn(
                min_value=0.0, step=0.5, format="%.1f",
                help="Wartung und Instandhaltung in % der Investition pro Jahr.")})

with ausl_box:
    st.divider()
    st.markdown("**Auslegung**\n\n" + "\n".join(f"- {z}" for z in auslegung)
                if auslegung else "Keine Technologie gewählt.")
    st.caption("Ändern im Reiter „🔧 Auslegung und Details“.")

# ---------------------------------------------------------------------------
# Rechnen
# ---------------------------------------------------------------------------
ts, k = rechne(wetter, P)

# Kostenrechnung: Größe „0 = unbegrenzt“ durch die tatsächlich benötigte Leistung ersetzen
gr_real = {tech: (math.ceil(float(ts[col].max()) * 2) / 2 if (gr <= 0 and col) else gr)
           for tech, (gr, col) in groessen.items()}
inv = kosten.investitionen(gr_real, inv_annahmen, zins)
bez = kosten.bezugskosten(k, preise)
K = kosten.zusammenfassung(inv, bez, k["einspeisung"] * P["verguetung"],
                           k["strom_haushalt"] + k["waerme_bedarf"], P["flaeche"])

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
    fig.update_xaxes(range=[lo - (0.4 * spanne if lo < 0 else 0), hi + 0.4 * spanne])
    fig.update_layout(title=titel, xaxis_title=achse, margin=dict(l=10, r=10, t=40, b=10),
                      height=90 + 55 * max(len(werte), 1), yaxis=dict(autorange="reversed"))
    return fig


# ---------------------------------------------------------------------------
# Reiter: Jahresübersicht
# ---------------------------------------------------------------------------
def zeige_fluss(df_h: pd.DataFrame, kessel_: list, bat_kap: float):
    """Energieflussbild mit den Jahreswerten in kWh (aus Stundenwerten eines Jahres)."""
    seite, h_ = fluss_mod.html(df_h, kessel_, bat_kap, jahreswerte=True)
    components.html(seite, height=h_ + 45)


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

    st.subheader("Wärme und Emissionen")
    m = st.columns(3) + st.columns(3)
    m[0].metric("Wärmebedarf", f"{de(k['waerme_bedarf'])} kWh",
                help=f"Raumwärme {de(k['waerme_raum'])} kWh + Warmwasser {de(k['waerme_ww'])} kWh (Nutzwärme)")
    m[1].metric("Max. Wärmelast", f"{de(k['heizlast_max'], 1)} kW")
    m[2].metric("Jahresarbeitszahl WP", "–" if np.isnan(k["jaz"]) else de(k["jaz"], 2))
    m[3].metric("CO₂-Emissionen", f"{de(k['co2_gesamt'])} kg",
                help=f"Ohne Gutschrift. Einspeisung verdrängt rechnerisch {de(k['co2_vermieden'])} kg CO₂ im Netz.")
    m[4].metric("CO₂ je m² Wohnfläche", f"{de(k['co2_gesamt'] / P['flaeche'], 1)} kg/m²")
    m[5].metric("Endenergie Brennstoffe", f"{de(k['end_gas'] + k['end_oel'] + k['end_holz'])} kWh",
                help=f"Erdgas {de(k['end_gas'])} kWh, Heizöl {de(k['end_oel'])} kWh, Holz {de(k['end_holz'])} kWh")

    st.subheader("Kosten pro Jahr")
    m = st.columns(3)
    m[0].metric("Jahresgesamtkosten", f"{de(K['gesamt'])} €",
                help="Brennstoff und Netz + Investition und Wartung. Details im Reiter „Kosten“.")
    m[1].metric("Brennstoff und Netz", f"{de(K['energie'] - K['erloes'])} €",
                help=f"Energiebezug {de(K['energie'])} € (Arbeits- und Grundpreise für Netzstrom und "
                     f"Brennstoffe) abzüglich Einspeiseerlös {de(K['erloes'])} €.")
    m[2].metric("Investition und Wartung", f"{de(K['kapital'] + K['wartung'])} €",
                help=f"Kapitalkosten (Annuität) {de(K['kapital'])} € + Wartung und Instandhaltung "
                     f"{de(K['wartung'])} €.")

    st.subheader("Energieflüsse im Jahr")
    fl_h = pd.DataFrame(ts.values.reshape(-1, 4, ts.shape[1]).mean(axis=1), columns=ts.columns, index=ts.index[::4])
    fl_h["bat_soc"] = ts["bat_soc"].values[3::4]
    fl_h = fl_h.assign(haushalt=fl_h["strom_haushalt"], el_wp=fl_h["strom_wp"] + fl_h["strom_heizstab"],
                       q_wp=fl_h["q_wp"] + fl_h["q_heizstab"], q_ofen=fl_h["q_kachelofen"],
                       q_raum=fl_h["waerme_raum"], q_ww=fl_h["waerme_ww"], f_gas=fl_h["q_gas"] / P["gas_eta"],
                       f_oel=fl_h["q_oel"] / P["oel_eta"], f_holz=fl_h["q_holz"] / P["holz_eta"])
    zeige_fluss(fl_h, [dict(name="Gasheizung", brennstoff="Erdgas", q="q_gas", fuel="f_gas"),
                       dict(name="Ölheizung", brennstoff="Heizöl", q="q_oel", fuel="f_oel"),
                       dict(name="Holzheizung", brennstoff="Holz", q="q_holz", fuel="f_holz")],
                float(P["bat_kwh"]))

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
        st.plotly_chart(balken_h(K["positionen"], "€", "Jahreskosten nach Position", "€ pro Jahr"),
                        width="stretch", key="jahr_kosten")

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

    if P.get("st_flaeche", 0) > 0:
        st.subheader("Solarthermie: Speicher- und Kollektortemperatur")
        tag = ts[["sp_t_oben", "sp_t_unten", "st_tkoll", "t_aussen"]].resample("D").mean()
        fig = go.Figure()
        fig.add_scatter(x=tag.index, y=tag["st_tkoll"], name="Kollektor im Betrieb", mode="lines",
                        line=dict(color=C["solar"], width=2), connectgaps=False,
                        hovertemplate="%{y:.0f} °C")
        fig.add_scatter(x=tag.index, y=tag["sp_t_oben"], name="Speicher oben", mode="lines",
                        line=dict(color=C["oel"], width=2), hovertemplate="%{y:.0f} °C")
        fig.add_scatter(x=tag.index, y=tag["sp_t_unten"], name="Speicher unten", mode="lines",
                        line=dict(color=C["wp"], width=2), hovertemplate="%{y:.0f} °C")
        fig.add_scatter(x=tag.index, y=tag["t_aussen"], name="Außenluft", mode="lines",
                        line=dict(color="#b9b7b0", width=1.5), hovertemplate="%{y:.0f} °C")
        fig.update_layout(title="Tagesmittel der Temperaturen", yaxis_title="°C", **LAYOUT)
        st.plotly_chart(fig, width="stretch")
        st.caption("Die Kollektortemperatur folgt der Temperatur unten im Schichtspeicher. Im Winter bleibt "
                   "der Speicher kühl und der Kollektor arbeitet effizient, im Sommer ist der Speicher oft "
                   "voll und der Kollektor heiß.")

        if k.get("sp_schicht_t") is not None:
            st.markdown("**Speicher im Zeitverlauf (Animation)**")
            a1_, a2_, a3_ = st.columns([2, 2, 3])
            an_start = a1_.date_input("Beginn", value=pd.Timestamp(ts.index[0].year, 6, 1).date(),
                                      min_value=ts.index[0].date(), max_value=ts.index[-1].date(),
                                      format="DD.MM.YYYY", key="an_start")
            an_tage = a2_.selectbox("Dauer", [1, 3, 7, 14], index=1, key="an_tage",
                                    format_func=lambda d: f"{d} Tag" + ("e" if d > 1 else ""))
            an_schritt = a3_.radio("Zeitschritt je Bild", ["15 Minuten", "1 Stunde"], index=1,
                                   horizontal=True, key="an_schritt")
            i0 = int(ts.index.searchsorted(pd.Timestamp(an_start)))
            sw = 1 if an_schritt.startswith("15") else 4
            ii = list(range(i0, min(i0 + an_tage * 96, len(ts)), sw))
            TT = k["sp_schicht_t"]
            ns_ = TT.shape[1]
            ylab = ["oben"] + [f"Schicht {j + 1}" for j in range(1, ns_ - 1)] + (["unten"] if ns_ > 1 else [])
            skala = [[0.0, "#2a78d6"], [0.5, "#f1efe8"], [1.0, "#d64545"]]
            z_max = float(P["sp_t_max"])

            def bild(i):
                z = [[float(v)] for v in TT[i]]
                titel = (f"{ts.index[i]:%d.%m.%Y %H:%M} · Kollektor {de(ts['st_genutzt'].iloc[i], 1)} kW · "
                         f"Entnahme {de(ts['q_solar'].iloc[i], 1)} kW · außen {de(ts['t_aussen'].iloc[i])} °C")
                return z, titel

            z0, t0_ = bild(ii[0])
            hm = dict(x=["Speicher"], y=ylab, zmin=10, zmax=z_max, colorscale=skala, xgap=0, ygap=2,
                      texttemplate="%{z:.0f} °C", textfont=dict(size=16, color="#1f1e1c"),
                      colorbar=dict(title="°C", thickness=14), hovertemplate="%{y}: %{z:.1f} °C<extra></extra>")
            fig = go.Figure(go.Heatmap(z=z0, **hm))
            frames, schritte = [], []
            for i in ii:
                z, titel = bild(i)
                name = f"{ts.index[i]:%d.%m. %H:%M}"
                frames.append(go.Frame(data=[go.Heatmap(z=z)], name=name,
                                       layout=dict(title_text=titel)))
                schritte.append(dict(method="animate", label=name,
                                     args=[[name], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                                        transition=dict(duration=0))]))
            fig.frames = frames
            fig.update_layout(
                title=dict(text=t0_, font=dict(size=14)), height=460,
                margin=dict(l=10, r=10, t=50, b=10),
                yaxis=dict(autorange="reversed"), xaxis=dict(showticklabels=False),
                updatemenus=[dict(type="buttons", direction="left", x=0.0, y=-0.12, xanchor="left",
                                  yanchor="top", showactive=False, buttons=[
                    dict(label="▶ Abspielen", method="animate",
                         args=[None, dict(frame=dict(duration=120, redraw=True), fromcurrent=True,
                                          transition=dict(duration=0))]),
                    dict(label="⏸ Pause", method="animate",
                         args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False),
                                            transition=dict(duration=0))])])],
                sliders=[dict(active=0, x=0.25, len=0.75, y=-0.08, yanchor="top", pad=dict(t=0),
                              currentvalue=dict(visible=False), steps=schritte)])
            st.plotly_chart(fig, width="stretch", key="sp_animation")
            st.caption("Jede Zeile ist eine Schicht des Speichers. Der Kollektor heizt von unten, "
                       "Warmwasser und Heizung entnehmen oben; nachströmendes kaltes Wasser kühlt die "
                       "untere Schicht. „Kollektor“ ist die in den Speicher geladene Leistung, "
                       "„Entnahme“ die an Warmwasser und Raumwärme abgegebene Solarwärme.")

    st.download_button("Zeitreihen (15 min) als CSV herunterladen",
                       ts.round(4).to_csv(sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"gebaeude_{ort}_{jahr}_15min.csv", mime="text/csv")

# ---------------------------------------------------------------------------
# Reiter: Typische Woche je Jahreszeit
# ---------------------------------------------------------------------------
with kosten_erg:
    st.subheader("Jahreskosten")
    m = st.columns(3) + st.columns(3) + st.columns(3)
    m[0].metric("Jahresgesamtkosten", f"{de(K['gesamt'])} €/a",
                help="Kapitalkosten + Wartung + Energiebezug − Einspeiseerlös")
    m[1].metric("Kapitalkosten", f"{de(K['kapital'])} €/a",
                help="Annuität der Investitionen nach Abzug der Förderung")
    m[2].metric("Wartung und Instandhaltung", f"{de(K['wartung'])} €/a")
    m[3].metric("Energiebezug", f"{de(K['energie'])} €/a", help="Arbeits- und Grundpreise")
    m[4].metric("Einspeiseerlös", f"{de(K['erloes'])} €/a")
    m[5].metric("Investition gesamt", f"{de(K['invest'])} €",
                help=f"Vor Förderung. Förderung: {de(K['foerderung'])} €, "
                     f"Eigenanteil: {de(K['invest'] - K['foerderung'])} €.")
    m[6].metric("Kosten je kWh Nutzenergie", f"{de(100 * K['je_kwh'], 1)} ct/kWh",
                help="Jahresgesamtkosten bezogen auf Haushaltsstrom + Wärmebedarf (Nutzenergie).")
    m[7].metric("Kosten je m² Wohnfläche", f"{de(K['je_m2'], 1)} €/m²a")

    c1, c2 = st.columns(2)
    c1.plotly_chart(balken_h(K["positionen"], "€", "Jahreskosten nach Position", "€ pro Jahr"),
                    width="stretch", key="kosten_pos")
    je_tech = {z["Technologie"]: z["Summe [€/a]"] for _, z in inv.iterrows() if z["Summe [€/a]"] > 0.5}
    if je_tech:
        c2.plotly_chart(balken_h(je_tech, "€", "Kapital- und Wartungskosten je Technologie", "€ pro Jahr"),
                        width="stretch", key="kosten_tech")
    else:
        c2.info("Keine Technologie mit Investitionskosten gewählt.")

    euro = st.column_config.NumberColumn(format="%.0f €")
    st.markdown("**Investitionen und Kapitalkosten**")
    st.dataframe(inv, hide_index=True, width="stretch", column_config={
        "Größe": st.column_config.NumberColumn(format="%.1f"),
        "Investition [€]": euro, "Förderung [€]": euro, "Eigenanteil [€]": euro,
        "Nutzungsdauer [a]": st.column_config.NumberColumn(format="%.0f"),
        "Annuitätenfaktor": st.column_config.NumberColumn(format="%.4f"),
        "Kapitalkosten [€/a]": euro, "Wartung [€/a]": euro, "Summe [€/a]": euro})
    st.markdown("**Energiebezug**")
    st.dataframe(bez, hide_index=True, width="stretch", column_config={
        "Menge [kWh/a]": st.column_config.NumberColumn(format="%.0f"),
        "Arbeitspreis [€/kWh]": st.column_config.NumberColumn(format="%.3f"),
        "Arbeitskosten [€/a]": euro, "Grundpreis [€/a]": euro, "Summe [€/a]": euro})
    st.caption(
        f"Annuitätenmethode: Kapitalkosten = (Investition − Förderung) × a mit "
        f"a = i·(1+i)ⁿ / ((1+i)ⁿ − 1), i = {de(100 * zins, 2)} %, n = Nutzungsdauer. Keine "
        "Preissteigerungen, keine Restwerte; Förderhöchstgrenzen und Steuern sind nicht berücksichtigt. "
        "Größen mit „0 kW = unbegrenzt“ werden mit der tatsächlich benötigten Spitzenleistung angesetzt.")

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
with tab_studie:
    ORDNER = Path(__file__).parent
    st.subheader("Wie lässt sich die Jahresarbeitszahl (JAZ) einer Luft-Wärmepumpe steigern?")
    st.markdown(
        "Untersucht werden drei Hebel, die den Betrieb der Wärmepumpe aus den kältesten Stunden heraus "
        "verlagern: ein **Kachelofen**, ein **Wasser-Pufferspeicher** und die **thermische Masse des "
        "Gebäudes**. Der Betrieb wird stündlich über das ganze Jahr optimiert (lineares Programm, perfekte "
        "Voraussicht, Ziel: minimaler Strombedarf). Gebäude, Heizsystem und Wetter kommen aus der "
        "Seitenleiste; betrachtet wird eine Wärmepumpe als alleiniger Wärmeerzeuger – die übrige "
        "Technologiewahl spielt hier keine Rolle.")
    cdl = st.columns(2)
    for spalte_, (datei_, text_) in zip(cdl, (("JAZ_Steigerung_Waermepumpe.pdf", "📄 Paper (IEEE-Format)"),
                                              ("JAZ_Steigerung_Waermepumpe_Elsevier.pdf",
                                               "📄 Paper (Elsevier-Format)"))):
        pdf = ORDNER / "paper" / datei_
        if pdf.exists():
            spalte_.download_button(text_, pdf.read_bytes(), file_name=pdf.name, mime="application/pdf",
                                    key=f"dl_{datei_}")

    c = st.columns(3)
    with c[0], st.container(border=True):
        st.markdown("**Kachelofen**")
        s_budget = st.slider("Maximale Ofenwärme [kWh/a]", 0, 4000, 2000, 250)
        s_gezielt = st.radio("Einsatz", ["gezielt (Optimierer wählt die Abbrände)",
                                         "ungezielt (jeden Abend um 18 Uhr)"]).startswith("gezielt")
        s_tmax = st.number_input("Ofen nur an Tagen mit Tagesmittel bis [°C]", -10.0, 15.0, 5.0, 1.0,
                                 help="Gilt für beide Einsatzarten: an wärmeren Tagen bleibt der Ofen aus.")
        s_tag = st.number_input("Maximale Ofenwärme pro Tag [kWh]", 5.0, 100.0, 40.0, 5.0,
                                help="Etwa zwei Abbrände. Die Wärme wird über 12 Stunden abgegeben.")
    with c[1], st.container(border=True):
        st.markdown("**Pufferspeicher (Wasser)**")
        s_liter = st.slider("Volumen [Liter]", 0, 10000, 0, 100)
        s_spdt = st.number_input("Spreizung über Vorlauf [K]", 2.0, 30.0, 10.0, 1.0,
                                 help="Der Speicher wird um diese Spreizung über die Vorlauftemperatur "
                                      "geladen: mehr Kapazität je Liter, aber schlechterer COP beim Laden.")
        s_verl = st.number_input("Speicherverlust [%/h]", 0.0, 5.0, 0.3, 0.1)
    with c[2], st.container(border=True):
        st.markdown("**Gebäudemasse**")
        s_masse = st.selectbox("Bauweise (EN ISO 13790)", list(studie.MASSE), index=2,
                               format_func=lambda n: f"{n} ({de(studie.MASSE[n], 0)} Wh/m²K)")
        s_band = st.slider("Komfortband über Solltemperatur [K]", 0.0, 4.0, 2.0, 0.5,
                           help="So weit darf die Raumtemperatur über 20 °C steigen (auch durch den Ofen).")
        s_vor = st.checkbox("Wärmepumpe darf das Gebäude vorheizen", value=False)
        s_dtvor = st.number_input("Vorlaufzuschlag beim Vorheizen [K]", 0.0, 15.0, 5.0, 1.0)

    ta_h = wetter["t2m"].values.reshape(-1, 4).mean(axis=1)
    sp_basis = dict(flaeche=P["flaeche"], personen=P["personen"], spez=P["spez_heizwaerme"],
                    heizgrenze=P["heizgrenze"], t_vorlauf=P["t_vorlauf"], ww_kwh_person=P["ww_kwh_person"],
                    wp_quelle=P["wp_quelle"], wp_guete=P["wp_guete"], masse=studie.MASSE[s_masse])
    sp_fall = dict(sp_basis, band=s_band, vorheizen=s_vor, dt_vor=s_dtvor, sp_liter=float(s_liter),
                   sp_dt=s_spdt, sp_verlust=s_verl, ko_budget=float(s_budget), ko_gezielt=s_gezielt,
                   ko_tag_max=s_tag, ko_t_max=s_tmax)
    try:
        ts_r, k_r = studie_rechnen(ta_h, sp_basis, int(jahr))
        ts_f, k_f = studie_rechnen(ta_h, sp_fall, int(jahr))
    except Exception as exc:
        st.error(f"Die Optimierung ist fehlgeschlagen: {exc}")
        ts_r = None
    if ts_r is not None:
        st.markdown(f"**Ergebnis für {std}, {hs}, {de(P['flaeche'])} m²** – Vergleich mit der Referenz "
                    "(nur Wärmepumpe, ohne Speicher und Ofen)")
        m = st.columns(3) + st.columns(3)
        m[0].metric("JAZ (Heizung + Warmwasser)", de(k_f["jaz"], 2),
                    f"{de(100 * (k_f['jaz'] / k_r['jaz'] - 1), 1)} % ggü. {de(k_r['jaz'], 2)}")
        m[1].metric("Strombedarf Wärmepumpe", f"{de(k_f['el'])} kWh",
                    f"{de(100 * (k_f['el'] / k_r['el'] - 1), 1)} % ggü. {de(k_r['el'])} kWh",
                    delta_color="inverse")
        m[2].metric("Max. elektrische Leistung", f"{de(k_f['el_max'], 2)} kW",
                    f"{de(k_f['el_max'] - k_r['el_max'], 2)} kW", delta_color="inverse")
        m[3].metric("Ofenwärme", f"{de(k_f['q_ofen'])} kWh",
                    help=f"Holzeinsatz {de(k_f['holz'])} kWh. Anteil am Raumwärmebedarf: "
                         f"{de(100 * k_f['q_ofen'] / max(k_f['waermebedarf'], 1), 1)} %.")
        je = (k_r["el"] - k_f["el"]) / k_f["q_ofen"] if k_f["q_ofen"] > 1 else float("nan")
        m[4].metric("Ersparter Strom je kWh Ofenwärme", "–" if np.isnan(je) else f"{de(je, 2)} kWh",
                    help="Entspricht dem Kehrwert des COP in den Stunden, die der Ofen ersetzt.")
        m[5].metric("Mittlere Außentemperatur im Betrieb",
                    f"WP {de(k_f['t_wp'], 1)} °C" + ("" if np.isnan(k_f["t_ofen"])
                                                      else f" · Ofen {de(k_f['t_ofen'], 1)} °C"),
                    help=f"Mit der Wärmeabgabe gewichtet. Referenz: WP {de(k_r['t_wp'], 1)} °C.")

        TEILE = [("q_dir", "WP direkt", C["wp"]), ("q_ent", "aus Pufferspeicher", C["oel"]),
                 ("q_ofen", "Kachelofen", C["kachel"]), ("q_vor", "WP Vorheizen", C["einsp"])]
        c1, c2 = st.columns(2)
        # kälteste Woche des Jahres
        i0 = int(pd.Series(ta_h).rolling(168).mean().idxmin()) - 167
        w_ = ts_f.iloc[i0:i0 + 168]
        fig = go.Figure()
        for col, bez, farbe in TEILE:
            if k_f.get(col, ts_f[col].sum()) > 0.5 or ts_f[col].sum() > 0.5:
                fig.add_scatter(x=w_.index, y=w_[col], name=bez, stackgroup="a", mode="lines",
                                line=dict(width=0.5, color=farbe), fillcolor=farbe,
                                hovertemplate="%{y:.2f} kW")
        fig.add_scatter(x=w_.index, y=w_["last"], name="Heizlast bei 20 °C", mode="lines",
                        line=dict(color=C["linie"], width=2), hovertemplate="%{y:.2f} kW")
        fig.update_layout(title=f"Kälteste Woche: Wärmezufuhr in den Raum (Mittel {de(w_['t_aussen'].mean(), 1)} °C)",
                          yaxis_title="kW", height=400, **LAYOUT)
        c1.plotly_chart(fig, width="stretch", key="st_woche")
        # Wärme nach Außentemperatur: in welchen Zeiten läuft was?
        kanten = np.arange(-16, 22, 2)
        mitte = (kanten[:-1] + kanten[1:]) / 2
        klasse = lambda werte: np.histogram(ta_h, bins=kanten, weights=werte)[0]
        fig = go.Figure()
        fig.add_bar(x=mitte, y=klasse((ts_f["q_dir"] + ts_f["q_vor"] + ts_f["q_lad"]).values),
                    name="Wärmepumpe", marker_color=C["wp"], hovertemplate="%{y:,.0f} kWh")
        if k_f["q_ofen"] > 0.5:
            fig.add_bar(x=mitte, y=klasse(ts_f["q_ofen"].values), name="Kachelofen",
                        marker_color=C["kachel"], hovertemplate="%{y:,.0f} kWh")
        fig.add_scatter(x=mitte, y=klasse(ts_r["q_dir"].values), name="Wärmepumpe in der Referenz",
                        mode="lines+markers", line=dict(color=C["linie"], width=2), marker=dict(size=7),
                        hovertemplate="%{y:,.0f} kWh")
        fig.update_layout(barmode="stack", bargap=0.15, title="Wärmeerzeugung nach Außentemperatur",
                          xaxis_title="Außentemperatur [°C] (Klassen von 2 K)", yaxis_title="kWh pro Jahr",
                          height=400, **LAYOUT)
        fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
        c2.plotly_chart(fig, width="stretch", key="st_temp")

        c1, c2 = st.columns(2)
        fig = go.Figure()
        fig.add_scatter(x=w_.index, y=w_["cop_dir"], name="COP direktes Heizen", mode="lines",
                        line=dict(color=C["wp"], width=2), hovertemplate="%{y:.2f}")
        if k_f["q_lad"] > 0.5:
            fig.add_scatter(x=w_.index, y=w_["cop_lad"], name="COP Speicher laden", mode="lines",
                            line=dict(color=C["oel"], width=2, dash="dot"), hovertemplate="%{y:.2f}")
        if k_f["q_vor"] > 0.5:
            fig.add_scatter(x=w_.index, y=w_["cop_vor"], name="COP Vorheizen", mode="lines",
                            line=dict(color=C["einsp"], width=2, dash="dash"), hovertemplate="%{y:.2f}")
        fig.update_layout(title="Kälteste Woche: COP der Betriebsarten", yaxis_title="COP [–]", height=320,
                          **LAYOUT)
        c1.plotly_chart(fig, width="stretch", key="st_cop")
        fig = go.Figure()
        fig.add_scatter(x=w_.index, y=20 + w_["x"], name="Raumtemperatur", mode="lines",
                        line=dict(color=C["linie"], width=2), hovertemplate="%{y:.2f} °C")
        fig.update_layout(title="Kälteste Woche: Raumtemperatur", yaxis_title="°C", height=320,
                          yaxis_range=[19.5, 20.5 + max(s_band, 0.5)], **LAYOUT)
        c2.plotly_chart(fig, width="stretch", key="st_raum")

    # --- vorberechnete Parameterstudie -------------------------------------------
    csv = ORDNER / "studie_ergebnisse" / "ergebnisse.csv"
    st.subheader("Parameterstudie (Ingolstadt, Wetterjahr 2019, 140 m²)")
    if not csv.exists():
        st.info("Noch keine Ergebnisse vorhanden. Erzeugen mit `python studie_lauf.py` im App-Ordner.")
    else:
        erg = studie_ergebnisse(str(csv), csv.stat().st_mtime)
        HAUSFARBE = dict(zip(["Altbau unsaniert", "Altbau teilsaniert", "EnEV 2002–2014", "Effizienzhaus 55"],
                             ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]))
        groesse_y = st.radio("Dargestellte Größe", ["Änderung der JAZ [%]", "Änderung des WP-Stroms [%]"],
                             horizontal=True)
        ycol = "d_jaz_pct" if groesse_y.startswith("Änderung der JAZ") else "d_el_pct"

        def linien(df, xcol, titel, xtitel, gruppen, key, logx=False):
            fig = go.Figure()
            for (h_, var), g in df.groupby(gruppen, sort=False):
                g = g.sort_values(xcol)
                fig.add_scatter(x=g[xcol], y=g[ycol], name=f"{h_} – {var}" if var else h_,
                                mode="lines+markers",
                                line=dict(color=HAUSFARBE.get(h_, C["linie"]), width=2,
                                          dash="dot" if "ungezielt" in str(var) else "solid"),
                                marker=dict(size=7), hovertemplate="%{y:.1f} %")
            fig.add_hline(y=0, line_width=1, line_color="#898781")
            fig.update_layout(title=titel, xaxis_title=xtitel, yaxis_title=groesse_y, height=430, **LAYOUT)
            if logx:
                fig.update_xaxes(type="log")
            st.plotly_chart(fig, width="stretch", key=key)

        c1, c2 = st.columns(2)
        with c1:
            linien(erg[erg["studie"] == "Kachelofen"], "wert",
                   "Kachelofen: gezielt (durchgezogen) und ungezielt (gepunktet)",
                   "Maximale Ofenwärme [kWh/a]", ["haus", "variante"], "ps_ofen")
        with c2:
            d = erg[(erg["studie"] == "Puffer") & (erg["variante"] == "Spreizung 10 K")].assign(variante="")
            linien(d, "wert", "Pufferspeicher (Spreizung 10 K)", "Volumen [Liter]", ["haus", "variante"],
                   "ps_puffer", logx=True)
        c1, c2 = st.columns(2)
        with c1:
            d = erg[(erg["studie"] == "Gebäudemasse") & (erg["variante"] == "Band 2 K")].assign(variante="")
            linien(d, "wert", "Gebäudemasse (Komfortband 2 K, Vorheizen erlaubt)",
                   "Wirksame Wärmekapazität [Wh/m²K]", ["haus", "variante"], "ps_masse")
        with c2:
            d = erg[erg["studie"] == "Kombination"]
            fig = go.Figure()
            for h_, g in d.groupby("haus", sort=False):
                fig.add_bar(x=g["variante"], y=g[ycol], name=h_, marker_color=HAUSFARBE.get(h_),
                            hovertemplate="%{y:.1f} %")
            fig.add_hline(y=0, line_width=1, line_color="#898781")
            fig.update_layout(barmode="group", title="Kombination der Maßnahmen", yaxis_title=groesse_y,
                              height=430, **LAYOUT)
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, width="stretch", key="ps_kombi")
        with st.expander("Alle Ergebnisse als Tabelle"):
            spalten_ = ["studie", "haus", "variante", "wert", "einheit", "jahr", "jaz", "el", "d_jaz_pct",
                        "d_el_pct", "q_ofen", "holz", "el_je_ofen", "d_kosten", "d_co2"]
            st.dataframe(erg[spalten_].round(2), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Reiter: Flexible Strompreise (Paper 2)
# ---------------------------------------------------------------------------
with tab_preis:
    st.subheader("Was bringen Kachelofen, Pufferspeicher und Gebäudemasse bei dynamischen Strompreisen?")
    st.markdown(
        "Gleiches Modell wie im Reiter „Studie“, aber der Betrieb der Luft-Wärmepumpe wird auf **minimale "
        "Kosten** optimiert: Strom zum stündlichen Preis eines dynamischen Tarifs (Day-Ahead-Preis DE-LU von "
        "SMARD plus Netzentgelt, Steuern, Umlagen und Mehrwertsteuer), Holz zum Brennstoffpreis. Verglichen "
        "wird mit der Referenz (nur Wärmepumpe) und mit dem effizienzoptimalen Betrieb derselben Ausstattung. "
        "Gebäude und Heizsystem kommen aus der Seitenleiste, das Wetter aus dem gewählten Preisjahr.")
    pdf2 = ORDNER / "paper" / "Dynamische_Strompreise_Waermepumpe.pdf"
    if pdf2.exists():
        st.download_button("📄 Paper (IEEE-Format)", pdf2.read_bytes(), file_name=pdf2.name,
                           mime="application/pdf", key="dl_paper2")

    c = st.columns(4)
    with c[0], st.container(border=True):
        st.markdown("**Tarif**")
        fp_jahr = st.selectbox("Preis- und Wetterjahr", list(tarif_mod.JAHRE), index=len(tarif_mod.JAHRE) - 1,
                               help="2019/2020: ruhige Preise, 2021/2023: volatil, 2022: Energiekrise.")
        fp_netz = st.number_input("Netzentgelt [ct/kWh netto]", 0.0, 30.0, tarif_mod.NETZENTGELT, 0.5)
        fp_nv = st.checkbox("Zeitvariables Netzentgelt", value=False,
                            help="Angelehnt an §14a EnWG, Modul 3: 0–6 Uhr ein Drittel, 17–21 Uhr das "
                                 "1,67-Fache des Standardentgelts.")
        fp_holz = st.number_input("Holzpreis [ct/kWh Brennstoff]", 0.0, 30.0, 7.0, 0.5)
    with c[1], st.container(border=True):
        st.markdown("**Kachelofen**")
        fp_budget = st.slider("Maximale Ofenwärme [kWh/a]", 0, 4000, 0, 250, key="fp_budget")
        fp_gezielt = st.radio("Einsatz", ["gezielt (Optimierer)", "ungezielt (18 Uhr)"],
                              key="fp_gezielt").startswith("gezielt")
    with c[2], st.container(border=True):
        st.markdown("**Pufferspeicher**")
        fp_liter = st.slider("Volumen [Liter]", 0, 10000, 1000, 100, key="fp_liter")
        fp_spdt = st.number_input("Spreizung über Vorlauf [K]", 2.0, 30.0, 10.0, 1.0, key="fp_spdt")
    with c[3], st.container(border=True):
        st.markdown("**Gebäudemasse**")
        fp_masse = st.selectbox("Bauweise", list(studie.MASSE), index=2, key="fp_masse",
                                format_func=lambda n: f"{n} ({de(studie.MASSE[n], 0)} Wh/m²K)")
        fp_band = st.slider("Komfortband [K]", 0.0, 4.0, 2.0, 0.5, key="fp_band")
        fp_vor = st.checkbox("Wärmepumpe darf vorheizen", value=True, key="fp_vor")

    fp_ok = True
    try:
        spot_j = spotpreise(int(fp_jahr))
        wetter_p, _ = wetterdaten(float(lat), float(lon), float(neigung), float(azimut), int(fp_jahr), offline)
        ta_p = wetter_p["t2m"].values.reshape(-1, 4).mean(axis=1)
        pr = tarif_mod.endpreis(spot_j, fp_nv, fp_netz)
        fp_basis = dict(sp_basis, masse=studie.MASSE[fp_masse])
        fp_fall = dict(fp_basis, band=fp_band, vorheizen=fp_vor, sp_liter=float(fp_liter), sp_dt=fp_spdt,
                       ko_budget=float(fp_budget), ko_gezielt=fp_gezielt)
        holz_eur = fp_holz / 100.0
        ts0, k0 = studie_preis_rechnen(ta_p, fp_basis, int(fp_jahr), pr, holz_eur)
        ts1, k1 = studie_preis_rechnen(ta_p, fp_fall, int(fp_jahr), pr, holz_eur)
        ts2, k2 = studie_rechnen(ta_p, fp_fall, int(fp_jahr))
    except Exception as exc:
        st.error(f"Preisdaten oder Optimierung nicht verfügbar: {exc}")
        fp_ok = False
    if fp_ok:
        def kosten_von(ts_, k_):
            el_ = (ts_["el_heiz"] + ts_["el_ww"]).values
            return float((el_ * pr).sum()) + k_["holz"] * holz_eur, float((el_ * pr).sum()) / max(k_["el"], 1e-9)

        (kost0, bez0), (kost1, bez1), (kost2, _) = kosten_von(ts0, k0), kosten_von(ts1, k1), kosten_von(ts2, k2)
        fix0 = k0["el"] * float(pr.mean())
        tagespreis = pr.reshape(365, 24)
        st.markdown(f"**Ergebnis für {std}, {hs}, {de(P['flaeche'])} m², Preisjahr {fp_jahr}** – mittlerer "
                    f"Strompreis {de(100 * pr.mean(), 1)} ct/kWh, mittlere Tagesspanne "
                    f"{de(100 * (tagespreis.max(1) - tagespreis.min(1)).mean(), 1)} ct/kWh")
        m = st.columns(3) + st.columns(3)
        m[0].metric("Betriebskosten (Strom + Holz)", f"{de(kost1)} €/a",
                    f"{de(kost1 - kost0)} € ({de(100 * (kost1 / kost0 - 1), 1)} %) ggü. Referenz",
                    delta_color="inverse")
        m[1].metric("Strombedarf Wärmepumpe", f"{de(k1['el'])} kWh",
                    f"{de(100 * (k1['el'] / k0['el'] - 1), 1)} % ggü. {de(k0['el'])} kWh", delta_color="inverse")
        m[2].metric("Mittlerer Bezugspreis", f"{de(100 * bez1, 1)} ct/kWh",
                    f"{de(100 * (bez1 - bez0), 1)} ct ggü. Referenz", delta_color="inverse")
        m[3].metric("Referenz: dynamisch statt Festpreis", f"{de(kost0 - fix0)} €/a",
                    f"{de(100 * (kost0 / fix0 - 1), 1)} % ggü. Festpreis gleichen Mittelwerts",
                    delta_color="inverse",
                    help="Mehr- oder Minderkosten der unflexiblen Wärmepumpe im dynamischen Tarif gegenüber "
                         "einem Festpreis in Höhe des Jahresmittels.")
        m[4].metric("Effizienzoptimal betrieben", f"{de(kost2)} €/a",
                    f"{de(kost2 - kost0)} € ggü. Referenz, Strom {de(100 * (k2['el'] / k0['el'] - 1), 1)} %",
                    delta_color="inverse",
                    help="Gleiche Ausstattung, aber Betrieb auf minimalen Strombedarf (Reiter „Studie“), "
                         "bewertet mit dem dynamischen Tarif.")
        m[5].metric("Max. elektrische Leistung", f"{de(k1['el_max'], 2)} kW",
                    f"{de(k1['el_max'] - k0['el_max'], 2)} kW", delta_color="inverse",
                    help=f"Ofenwärme {de(k1['q_ofen'])} kWh, Speicherladung {de(k1['q_lad'])} kWh, "
                         f"Vorheizen {de(k1['q_vor'])} kWh pro Jahr.")

        # Woche mit der größten Preisspanne in der Heizzeit
        sp_ = pd.Series(np.repeat(tagespreis.max(1) - tagespreis.min(1), 24)).rolling(168).mean()
        kalt_ = pd.Series(ta_p).rolling(168).mean() < 5.0
        i0 = int(sp_.where(kalt_).idxmax()) - 167 if kalt_.any() else 0
        i0 -= i0 % 24
        w0, w1 = ts0.iloc[i0:i0 + 168], ts1.iloc[i0:i0 + 168]
        c1, c2 = st.columns(2)
        fig = go.Figure()
        fig.add_scatter(x=w1.index, y=100 * pr[i0:i0 + 168], name="Strompreis", mode="lines",
                        line=dict(color=C["linie"], width=2, shape="hv"), hovertemplate="%{y:.1f} ct/kWh")
        fig.update_layout(title="Kalte Woche mit großer Preisspanne: Strompreis", yaxis_title="ct/kWh",
                          height=320, **LAYOUT)
        c1.plotly_chart(fig, width="stretch", key="fp_preis")
        fig = go.Figure()
        fig.add_scatter(x=w0.index, y=w0["el_heiz"] + w0["el_ww"], name="Referenz", mode="lines",
                        line=dict(color=C["temp"], width=2, shape="hv"), hovertemplate="%{y:.2f} kW")
        fig.add_scatter(x=w1.index, y=w1["el_heiz"] + w1["el_ww"], name="kostenoptimal", mode="lines",
                        line=dict(color=C["wp"], width=2, shape="hv"), hovertemplate="%{y:.2f} kW")
        fig.update_layout(title="Strombezug der Wärmepumpe", yaxis_title="kW", height=320, **LAYOUT)
        c2.plotly_chart(fig, width="stretch", key="fp_strom")
        c1, c2 = st.columns(2)
        fig = go.Figure()
        for col, bez, farbe in (("q_dir", "WP direkt", C["wp"]), ("q_ent", "aus Pufferspeicher", C["oel"]),
                                ("q_ofen", "Kachelofen", C["kachel"]), ("q_vor", "WP Vorheizen", C["einsp"])):
            if ts1[col].sum() > 0.5:
                fig.add_scatter(x=w1.index, y=w1[col], name=bez, stackgroup="a", mode="lines",
                                line=dict(width=0.5, color=farbe), fillcolor=farbe, hovertemplate="%{y:.2f} kW")
        fig.add_scatter(x=w1.index, y=w1["last"], name="Heizlast bei 20 °C", mode="lines",
                        line=dict(color=C["linie"], width=2), hovertemplate="%{y:.2f} kW")
        fig.update_layout(title="Wärmezufuhr in den Raum", yaxis_title="kW", height=320, **LAYOUT)
        c1.plotly_chart(fig, width="stretch", key="fp_waerme")
        fig = go.Figure()
        fig.add_scatter(x=w1.index, y=w1["sp_stand"], name="Pufferspeicher", mode="lines",
                        line=dict(color=C["oel"], width=2), hovertemplate="%{y:.1f} kWh")
        fig.add_scatter(x=w1.index, y=w1["x"] * k1["C"], name="Gebäudemasse", mode="lines",
                        line=dict(color=C["kachel"], width=2), hovertemplate="%{y:.1f} kWh")
        fig.update_layout(title="Gespeicherte Wärme", yaxis_title="kWh", height=320, **LAYOUT)
        c2.plotly_chart(fig, width="stretch", key="fp_speicher")

    # --- vorberechnete Parameterstudie -------------------------------------------
    csv2 = ORDNER / "studie_ergebnisse" / "preis_ergebnisse.csv"
    st.subheader("Parameterstudie (Ingolstadt, 140 m², Tarif mit 9 ct/kWh Netzentgelt)")
    if not csv2.exists():
        st.info("Noch keine Ergebnisse vorhanden. Erzeugen mit `python studie_preis_lauf.py` im App-Ordner.")
    else:
        erg2 = studie_ergebnisse(str(csv2), csv2.stat().st_mtime)
        HAUSFARBE2 = dict(zip(["Altbau unsaniert", "Altbau teilsaniert", "EnEV 2002–2014", "Effizienzhaus 55"],
                              ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]))
        cc = st.columns(3)
        gy = cc[0].radio("Dargestellte Größe", ["Änderung der Kosten [€/a]", "Änderung der Kosten [%]",
                                                "Änderung des WP-Stroms [%]"], key="fp_gy")
        ycol2 = {"Änderung der Kosten [€/a]": "d_kosten", "Änderung der Kosten [%]": "d_kosten_pct",
                 "Änderung des WP-Stroms [%]": "d_el_pct"}[gy]
        ziel2 = cc[1].radio("Betrieb", ["kostenoptimal", "effizienzoptimal"], key="fp_ziel")
        tarif2 = cc[2].radio("Netzentgelt", ["Standard", "Netz variabel"], key="fp_tarif",
                             format_func=lambda t: "konstant" if t == "Standard" else "zeitvariabel (nur 2023)")
        d = erg2[(erg2["studie"] == "Kombination") & (erg2["tarif"] == tarif2)
                 & (erg2["ziel"] == ("kosten" if ziel2 == "kostenoptimal" or tarif2 != "Standard" else "effizienz"))]
        c1, c2 = st.columns(2)
        fig = go.Figure()
        for h_, g in d[d["jahr"] == 2023].groupby("haus", sort=False):
            fig.add_bar(x=g["variante"], y=g[ycol2], name=h_, marker_color=HAUSFARBE2.get(h_),
                        hovertemplate="%{y:.1f}")
        fig.add_hline(y=0, line_width=1, line_color="#898781")
        fig.update_layout(barmode="group", title="Maßnahmen und Kombinationen je Haustyp (Preisjahr 2023)",
                          yaxis_title=gy, height=430, **LAYOUT)
        fig.update_traces(marker_line_width=0)
        c1.plotly_chart(fig, width="stretch", key="fp_kombi")
        fig = go.Figure()
        dj = d[d["haus"] == "EnEV 2002–2014"]
        for var, g in dj.groupby("variante", sort=False):
            g = g.sort_values("jahr")
            fig.add_scatter(x=g["jahr"].astype(str), y=g[ycol2], name=var, mode="lines+markers",
                            marker=dict(size=7), hovertemplate="%{y:.1f}")
        fig.add_hline(y=0, line_width=1, line_color="#898781")
        fig.update_layout(title="Preisjahre 2019–2023 (EnEV 2002–2014)", yaxis_title=gy, height=430, **LAYOUT)
        c2.plotly_chart(fig, width="stretch", key="fp_jahre")
        with st.expander("Alle Ergebnisse als Tabelle"):
            sp2 = ["studie", "haus", "variante", "wert", "einheit", "jahr", "tarif", "ziel", "jaz", "el", "kosten",
                   "kosten_fix", "preis_bezug", "d_kosten", "d_kosten_pct", "d_el_pct", "d_max_pct", "q_ofen",
                   "q_lad", "q_vor"]
            st.dataframe(erg2[sp2].round(3), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Reiter: Optimierte Auslegung (Neubau und Sanierung)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Rechne alle Kombinationen durch …")
def ausl_rechnen(combos, haus_, modus_, wetter_h, jahr_, ann_):
    return ausl_mod.bewerte(combos, haus_, modus_, ausl_mod.profile(wetter_h, haus_, jahr_), ann_)


def ausl_text(c_: dict) -> str:
    """Kurzbeschreibung einer Variante."""
    teile = [c_["huelle"]] if "huelle" in c_ else [n for b, n in ausl_mod.MASSNAHMEN.items() if c_.get(b)]
    teile.append(c_["erzeuger"])
    teile += [f"{t_} {de(c_[k_], 1 if c_[k_] % 1 else 0)} {e_}" for k_, t_, e_ in
              (("pv", "PV", "kWp"), ("bat", "Batterie", "kWh"), ("st", "Solarthermie", "m²")) if c_[k_] > 0]
    return " · ".join(teile)


with tab_opt:
    st.subheader("Welche Maßnahmen rechnen sich? Annuitätische Ausgaben gegen annuitätische Einsparungen")
    st.markdown(
        "Für ein Beispielhaus werden alle Kombinationen aus Maßnahmen an der **Gebäudehülle** und der "
        "**Energietechnik** mit einem schnellen Stundenmodell durchgerechnet. Zielgröße ist die "
        "**Gesamtannuität**: Kapitalkosten und Wartung der Maßnahmen plus Energie- und CO₂-Kosten minus "
        "Einspeiseerlös. Mit den Schaltern und Schiebern stellen Sie eine eigene Variante ein und vergleichen "
        "sie mit der Referenz und dem Kostenoptimum.")
    c = st.columns(3)
    with c[0], st.container(border=True):
        st.markdown("**Beispielhaus**")
        oa_modus = st.radio("Fall", ["Sanierung", "Neubau"], horizontal=True, key="oa_modus")
        oa_fl = st.number_input("Wohnfläche [m²]", 60.0, 400.0, float(P["flaeche"]), 10.0, key="oa_fl")
        cc = st.columns(2)
        oa_gesch = cc[0].number_input("Geschosse", 1, 3, 2, 1, key="oa_gesch")
        oa_pers = cc[1].number_input("Bewohner", 1, 8, int(P["personen"]), 1, key="oa_pers")
        if oa_modus == "Sanierung":
            oa_alter = st.selectbox("Baualtersklasse", list(ausl_mod.ALTER), index=0, key="oa_alter")
            cc = st.columns(2)
            oa_kessel = cc[0].radio("Vorhandener Kessel", ["Gas", "Öl"], key="oa_kessel")
            oa_faellig = cc[1].checkbox("Kessel ohnehin fällig", value=False, key="oa_faellig",
                                        help="Dann enthält die Referenz einen neuen Brennwertkessel.")
        else:
            oa_alter, oa_kessel, oa_faellig = "vor 1979", "Gas", False
    with c[1], st.container(border=True):
        st.markdown("**Rahmenbedingungen**")
        oa_zins = st.number_input("Kalkulationszinssatz [%/a]", 0.0, 15.0, 4.0, 0.25, key="oa_zins") / 100
        oa_co2 = st.slider("CO₂-Preis [€/t]", 0, 400, 0, 10, key="oa_co2",
                           help="Zusätzlich zu den Energiepreisen angesetzt (auf alle Emissionen inkl. Netzstrom).")
        oa_dyn = st.radio("Stromtarif", ["Festpreis", "dynamisch (Day-Ahead)"], horizontal=True,
                          key="oa_dyn").startswith("dyn")
        if oa_dyn:
            oa_jahr = st.selectbox("Preis- und Wetterjahr", list(tarif_mod.JAHRE), key="oa_jahr",
                                   index=list(tarif_mod.JAHRE).index(int(jahr)) if int(jahr) in tarif_mod.JAHRE
                                   else len(tarif_mod.JAHRE) - 1,
                                   help="Der Netzbezug wird stündlich bepreist, aber nicht preisgeführt verschoben.")
        else:
            oa_jahr = int(jahr)
        cc = st.columns(2)
        oa_pvmax = cc[0].number_input("PV maximal [kWp]", 0, 30, 12, 1, key="oa_pvmax", help="Begrenzt durch die Dachfläche.")
        oa_stfl = cc[1].number_input("Solarthermie [m²]", 2.0, 20.0, 6.0, 1.0, key="oa_stfl",
                                     help="Kollektorfläche, falls Solarthermie gewählt wird (nur Warmwasser).")
    with c[2], st.container(border=True):
        st.markdown("**Energiepreise**")
        cc = st.columns(2)
        oa_p = dict(strom=cc[0].number_input("Strom [€/kWh]", 0.0, 1.0, 0.35, 0.01, key="oa_ps", disabled=oa_dyn),
                    gas=cc[1].number_input("Erdgas [€/kWh]", 0.0, 1.0, 0.11, 0.005, format="%.3f", key="oa_pg"),
                    oel=cc[0].number_input("Heizöl [€/kWh]", 0.0, 1.0, 0.10, 0.005, format="%.3f", key="oa_po"),
                    holz=cc[1].number_input("Pellets [€/kWh]", 0.0, 1.0, 0.07, 0.005, format="%.3f", key="oa_ph"))
        oa_verg = cc[0].number_input("Einspeisung [€/kWh]", 0.0, 1.0, 0.08, 0.005, format="%.3f", key="oa_verg")
        oa_grund = dict(strom=150.0, gas=cc[1].number_input("Grundpreis Gas [€/a]", 0.0, 1000.0, 200.0, 10.0,
                                                           key="oa_gg"))
        if oa_modus == "Sanierung":
            oa_ohnehin = tuple(b for b, n in ausl_mod.MASSNAHMEN.items() if b != "boden" and st.checkbox(
                f"{ {'dach': 'Dach', 'wand': 'Fassade', 'fenster': 'Fenster'}[b] } ohnehin fällig", key=f"oa_oh_{b}",
                help="Dann zählen nur die energiebedingten Mehrkosten (Kosten abzüglich Sowieso-Kosten)."))
        else:
            oa_ohnehin = ()
    with st.expander("Kostenannahmen (editierbar): Investition = Fixkosten + spezifische Kosten × Größe"):
        st.caption("Richtwerte inkl. MwSt. und Einbau. Förderung als Zuschuss in % (Vorbelegung 0 %). "
                   "Sowieso-Kosten: Anteil, der bei einer ohnehin fälligen Instandsetzung auch ohne energetische "
                   "Verbesserung anfiele.")
        oa_kosten = st.data_editor(ausl_mod.kosten_df(), key="oa_ed", width="stretch", num_rows="fixed",
                                   disabled=["Einheit", "_index"])

    # Varianten, Referenz und Optimierung
    oa_haus = dict(flaeche=float(oa_fl), geschosse=int(oa_gesch), personen=int(oa_pers), baualter=oa_alter,
                   strom_kwh=float(model.STROMBEDARF_PERSONEN.get(int(oa_pers), 5000)))
    if oa_modus == "Sanierung":
        neu_k = f"{oa_kessel}-Brennwert neu"
        oa_erz = ([] if oa_faellig else [f"Bestandskessel {oa_kessel}"]) + [neu_k, "Luft-Wärmepumpe",
                                                                           "Erdreich-Wärmepumpe", "Pelletkessel"]
        oa_ref = dict(dach=False, wand=False, fenster=False, boden=False, erzeuger=oa_erz[0], pv=0.0, bat=0.0, st=0.0)
    else:
        oa_erz = ["Luft-Wärmepumpe", "Erdreich-Wärmepumpe", "Pelletkessel"]
        oa_ref = dict(huelle="GEG-Neubau", erzeuger=oa_erz[0], pv=0.0, bat=0.0, st=0.0)
    oa_ok = True
    try:
        oa_wetter = wetter if oa_jahr == int(jahr) else wetterdaten(float(lat), float(lon), float(neigung),
                                                                    float(azimut), oa_jahr, offline)[0]
        std_ = lambda sp_: oa_wetter[sp_].values.reshape(-1, 4).mean(axis=1)
        oa_wh = dict(ta=std_("t2m"), pv=std_("pv"), g=std_("g"))
        oa_ann = dict(kosten=oa_kosten, zins=oa_zins, preis=oa_p, grund=oa_grund, verguetung=oa_verg,
                      co2_preis=float(oa_co2), ohnehin=oa_ohnehin,
                      tarif=tarif_mod.endpreis(spotpreise(oa_jahr)) if oa_dyn else None)
        oa_var = ausl_mod.varianten(oa_modus, oa_erz, float(oa_pvmax), float(oa_stfl))
        oa_erg = ausl_rechnen(oa_var, oa_haus, oa_modus, oa_wh, oa_jahr, oa_ann)
        oa_best = oa_var[int(oa_erg["gesamt"].idxmin())]
        st.session_state["oa_best"] = (oa_best, oa_modus, int(oa_pvmax))
    except Exception as exc:
        st.error(f"Die Auslegungsrechnung ist fehlgeschlagen: {exc}")
        oa_ok = False

    def oa_uebernehmen():
        best_, modus_, pvmax_ = st.session_state["oa_best"]
        for b_ in ausl_mod.MASSNAHMEN:
            if b_ in best_:
                st.session_state[f"oa_m_{b_}"] = bool(best_[b_])
        if "huelle" in best_:
            st.session_state["oa_huelle"] = best_["huelle"]
        st.session_state[f"oa_erz_{modus_}"] = best_["erzeuger"]
        st.session_state[f"oa_pv_{pvmax_}"] = int(round(best_["pv"]))
        st.session_state["oa_bat"] = float(best_["bat"])
        st.session_state["oa_st"] = best_["st"] > 0

    if oa_ok:
        st.markdown("#### Eigene Variante")
        c = st.columns([1.2, 1.2, 1.6])
        with c[0], st.container(border=True):
            st.markdown("**Gebäudehülle**")
            if oa_modus == "Sanierung":
                geo_ = ausl_mod.geometrie(oa_haus["flaeche"], oa_haus["geschosse"])
                oa_c = {b: st.checkbox(f"{n} ({de(geo_[b])} m²)", key=f"oa_m_{b}")
                        for b, n in ausl_mod.MASSNAHMEN.items()}
            else:
                oa_c = dict(huelle=st.radio("Hüllstandard", list(ausl_mod.NEUBAU), key="oa_huelle"))
        with c[1], st.container(border=True):
            st.markdown("**Wärmeerzeuger**")
            if st.session_state.get(f"oa_erz_{oa_modus}") not in oa_erz:
                st.session_state.pop(f"oa_erz_{oa_modus}", None)
            oa_c["erzeuger"] = st.radio("Wärmeerzeuger", oa_erz, key=f"oa_erz_{oa_modus}",
                                        label_visibility="collapsed")
        with c[2], st.container(border=True):
            st.markdown("**Strom und Solar**")
            oa_c["pv"] = float(st.slider("Photovoltaik [kWp]", 0, max(int(oa_pvmax), 1), step=1,
                                         key=f"oa_pv_{int(oa_pvmax)}"))
            oa_bat_ = st.slider("Batteriespeicher [kWh]", 0.0, 15.0, step=2.5, key="oa_bat",
                                disabled=oa_c["pv"] == 0, help="Nur zusammen mit Photovoltaik.")
            oa_c["bat"] = float(oa_bat_) if oa_c["pv"] > 0 else 0.0
            oa_c["st"] = float(oa_stfl) if st.checkbox(f"Solarthermie ({de(oa_stfl)} m², Warmwasser)",
                                                        key="oa_st") else 0.0
            st.button("Kostenoptimum in die Schalter übernehmen", on_click=oa_uebernehmen, key="oa_btn")

        oa_pr = ausl_mod.profile(oa_wh, oa_haus, oa_jahr)
        oa_3 = ausl_mod.bewerte([oa_ref, oa_c, oa_best], oa_haus, oa_modus, oa_pr, oa_ann)
        r_, e_, o_ = (oa_3.loc[i] for i in range(3))
        st.markdown(f"**Referenz:** {ausl_text(oa_ref)}  \n**Eigene Variante:** {ausl_text(oa_c)}  \n"
                    f"**Kostenoptimum:** {ausl_text(oa_best)}")
        m = st.columns(3) + st.columns(3)
        m[0].metric("Gesamtannuität", f"{de(e_['gesamt'])} €/a",
                    f"{de(e_['gesamt'] - r_['gesamt'])} € ggü. Referenz", delta_color="inverse",
                    help=f"Kostenoptimum: {de(o_['gesamt'])} €/a.")
        m[1].metric("Annuitätische Ausgaben", f"{de(e_['ausgaben'])} €/a",
                    f"{de(e_['ausgaben'] - r_['ausgaben'])} €", delta_color="inverse",
                    help="Kapitalkosten (Annuität der Investition abzüglich Förderung) plus Wartung.")
        m[2].metric("Annuitätische Einsparung", f"{de(r_['laufend'] - e_['laufend'])} €/a",
                    help="Rückgang der Energie- und CO₂-Kosten (abzüglich Einspeiseerlös) gegenüber der Referenz.")
        m[3].metric("Jährliche Betriebskosten", f"{de(e_['betrieb'])} €/a",
                    f"{de(e_['betrieb'] - r_['betrieb'])} €", delta_color="inverse",
                    help="Energie, CO₂-Kosten und Wartung, abzüglich Einspeiseerlös; ohne Kapitalkosten.")
        m[4].metric("CO₂-Emissionen", f"{de(e_['co2'], 1)} t/a",
                    f"{de(100 * (e_['co2'] / max(r_['co2'], 1e-9) - 1))} %", delta_color="inverse",
                    help=f"Investition {de(e_['invest'])} €, davon Förderung {de(e_['foerderung'])} €.")

        st.markdown("#### Energieflüsse im Jahr")
        oa_wer = st.radio("Variante", ["Eigene Variante", "Referenz", "Kostenoptimum"], horizontal=True,
                          key="oa_fl_wer", label_visibility="collapsed")
        oa_cf = {"Eigene Variante": oa_c, "Referenz": oa_ref, "Kostenoptimum": oa_best}[oa_wer]
        zeige_fluss(*ausl_mod.zeitreihen(oa_cf, oa_haus, oa_modus, oa_pr, oa_jahr), float(oa_cf["bat"]))

        c1, c2 = st.columns(2)
        oa_fuer = c1.radio("Maßnahmen von", ["eigene Variante", "Kostenoptimum"], horizontal=True, key="oa_fuer")
        bt = ausl_mod.beitraege(oa_c if oa_fuer.startswith("eigene") else oa_best, oa_ref, oa_haus, oa_modus,
                                 oa_pr, oa_ann)
        fig = go.Figure()
        if len(bt):
            fig.add_bar(x=bt["Maßnahme"], y=bt["Ausgabe"], name="annuitätische Ausgabe", marker_color=C["oel"],
                        hovertemplate="%{y:,.0f} €/a")
            fig.add_bar(x=bt["Maßnahme"], y=bt["Einsparung"], name="annuitätische Einsparung",
                        marker_color=C["kachel"], hovertemplate="%{y:,.0f} €/a")
            fig.add_scatter(x=bt["Maßnahme"], y=bt["Netto"], name="Nettoertrag", mode="markers",
                            marker=dict(color=C["linie"], size=11, symbol="diamond"), hovertemplate="%{y:,.0f} €/a")
        fig.add_hline(y=0, line_width=1, line_color="#898781")
        fig.update_layout(barmode="group", title="Je Maßnahme: Ausgabe gegen Einsparung", yaxis_title="€/a",
                          height=430, **LAYOUT)
        fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
        c1.plotly_chart(fig, width="stretch", key="oa_beitrag")
        c1.caption("Jede Maßnahme wird gegen dieselbe Variante ohne sie gerechnet; die übrigen Maßnahmen bleiben. "
                   "Die Einzelwerte addieren sich deshalb nicht exakt zur Gesamtwirkung.")

        fig = go.Figure()
        namen3 = ["Referenz", "Eigene Variante", "Kostenoptimum"]
        for sp_, bez_, farbe_, vz in (("kapital", "Kapitalkosten", C["einsp"], 1), ("wartung", "Wartung", C["temp"], 1),
                                      ("energie", "Energiebezug", C["wp"], 1), ("co2_kosten", "CO₂-Kosten", C["oel"], 1),
                                      ("erloes", "Einspeiseerlös", C["pv"], -1)):
            if oa_3[sp_].abs().max() > 0.5:
                fig.add_bar(x=namen3, y=vz * oa_3[sp_], name=bez_, marker_color=farbe_,
                            hovertemplate="%{y:,.0f} €/a")
        fig.add_scatter(x=namen3, y=oa_3["gesamt"], name="Gesamtannuität", mode="markers+text",
                        text=[f"{de(v)} €" for v in oa_3["gesamt"]], textposition="top center",
                        marker=dict(color=C["linie"], size=11, symbol="diamond"), hovertemplate="%{y:,.0f} €/a")
        fig.update_layout(barmode="relative", title="Zusammensetzung der Jahreskosten", yaxis_title="€/a",
                          height=430, **LAYOUT)
        fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
        c2.markdown("&nbsp;")
        c2.plotly_chart(fig, width="stretch", key="oa_kosten")

        c1, c2 = st.columns(2)
        fig = go.Figure()
        fig.add_scatter(x=oa_erg["co2"], y=oa_erg["gesamt"], mode="markers", name="alle Kombinationen",
                        marker=dict(color=C["balken"], size=5), text=[ausl_text(v) for v in oa_var],
                        hovertemplate="%{text}<br>%{y:,.0f} €/a · %{x:.1f} t/a<extra></extra>")
        for z_, bez_, farbe_ in ((r_, "Referenz", C["linie"]), (e_, "Eigene Variante", C["oel"]),
                                 (o_, "Kostenoptimum", C["kachel"])):
            fig.add_scatter(x=[z_["co2"]], y=[z_["gesamt"]], mode="markers", name=bez_,
                            marker=dict(color=farbe_, size=14, symbol="diamond", line=dict(color="white", width=1)),
                            hovertemplate=bez_ + "<br>%{y:,.0f} €/a · %{x:.1f} t/a<extra></extra>")
        fig.update_layout(title=f"Alle {de(len(oa_var))} Kombinationen: Kosten gegen CO₂",
                          xaxis_title="CO₂-Emissionen [t/a]", yaxis_title="Gesamtannuität [€/a]", height=430,
                          **{**LAYOUT, "hovermode": "closest"})
        c1.plotly_chart(fig, width="stretch", key="oa_wolke")
        with c2:
            st.markdown("**Die zehn günstigsten Kombinationen**")
            top = oa_erg.sort_values("gesamt").head(10)
            st.dataframe(pd.DataFrame({
                "Variante": [ausl_text(oa_var[i]) for i in top.index],
                "Gesamt [€/a]": top["gesamt"].round(0), "Ausgaben [€/a]": top["ausgaben"].round(0),
                "Betrieb [€/a]": top["betrieb"].round(0), "Invest [€]": top["invest"].round(0),
                "CO₂ [t/a]": top["co2"].round(1)}), hide_index=True, width="stretch", height=390)
        st.caption(
            f"Wärmebedarf Referenz {de(r_['waerme'])} kWh/a ({de(r_['waerme'] / oa_haus['flaeche'])} kWh/m²a, "
            f"H = {de(r_['H'])} W/K, Vorlauf {de(r_['t_vl'])} °C); eigene Variante {de(e_['waerme'])} kWh/a "
            f"(H = {de(e_['H'])} W/K, Vorlauf {de(e_['t_vl'])} °C). Optimiert wird über PV in 4-kWp-Schritten, "
            "Batterie 0/5/10 kWh und Solarthermie ja/nein. Vereinfachtes Stundenmodell: Bauteilflächen aus einer "
            "Quadergeometrie, U-Werte je Baualtersklasse, Batterie nur für Eigenverbrauch, keine Restwerte, "
            "keine Preissteigerungen.")

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
  a₁ = {de(P['st_a1'], 1)} W/m²K, a₂ = {de(P['st_a2'], 3)} W/m²K². ΔT = mittlere Kollektortemperatur −
  Außentemperatur. Die Kollektortemperatur ist nicht konstant, sondern folgt in jedem Zeitschritt der
  Temperatur unten im Speicher: T_Kollektor = T_unten + {de(P['st_dt_koll'])} K. Gleiche Ausrichtung wie
  die PV.
- **Schichtspeicher:** {de(P['sp_schichten'])} gleich große Schichten (Wärmekapazität = Volumen ×
  1,163 Wh/l·K). Der Kollektor heizt die unterste Schicht; wird sie wärmer als die darüber, mischen sich
  beide (bei Bedarf weiter nach oben, bis keine Schicht mehr wärmer ist als die darüber). Warmwasser wird oben entnommen, Kaltwasser mit {de(P['sp_t_kalt'])} °C strömt unten nach. Ist es
  oben kälter als 55 °C, wärmt der Speicher nur vor und der nächste Wärmeerzeuger heizt nach; ist es
  wärmer, wird Kaltwasser beigemischt. Raumwärme wird ebenfalls oben entnommen, solange es dort wärmer
  ist als der Heizungsrücklauf (Rücklauf = 20 °C + 60 % der Vorlauf-Übertemperatur); der Rücklauf strömt
  unten ein. Verlust {de(P['sp_verlust'], 1)} % je Stunde der Wärme oberhalb von 20 °C. Sind alle
  Schichten {de(P['sp_t_max'])} °C warm, steht der Kollektor still. Der Speicher wird nur solar beladen.
  Vereinfachungen: keine Wärmeleitung zwischen den Schichten, Rücklauf immer ganz unten, Warmwasser
  zuerst.
- **Kachelofen:** deckt nur Raumwärme, im gewählten Zeitfenster an Tagen mit Tagesmitteltemperatur unter dem
  Grenzwert, höchstens mit seiner Wärmeleistung (keine Speichermasse modelliert).
- **Kessel:** Brennstoffeinsatz = Wärme / Jahresnutzungsgrad (heizwertbezogen): Gas-Brennwert 95 %, Öl 88 %,
  Holz 85 %, Kachelofen 75 %. Kein Taktverhalten, keine Teillastabhängigkeit.
""")
    st.subheader("Solarthermie und Schichtspeicher: Formeln")
    st.markdown(rf"""
Gerechnet wird in Zeitschritten von $\Delta t = 0{{,}}25$ h. Der Speicher hat $N$ = {de(P['sp_schichten'])}
Schichten mit den Temperaturen $T_1$ (oben) bis $T_N$ (unten). In jedem Zeitschritt laufen die folgenden
Schritte nacheinander ab.

**Wärmekapazität je Schicht** (Speichervolumen $V$ in Litern):

$$C_s = \frac{{V \cdot 1{{,}}163\ \mathrm{{Wh/(l\,K)}}}}{{N}}$$

**1. Speicherverluste** (Verlustsatz $v$ = {de(P['sp_verlust'], 1)} %/h, Umgebung 20 °C), für jede Schicht
mit $T_j > 20$ °C:

$$T_j \leftarrow T_j - v\,\Delta t\,(T_j - 20\,°\mathrm{{C}})$$

**2. Kollektor.** Mittlere Kollektortemperatur aus der untersten Schicht
($\Delta T_K$ = {de(P['st_dt_koll'])} K), Kollektorleistung aus der Kennlinie mit Einstrahlung $G$ in
Kollektorebene, Außentemperatur $T_a$ und Fläche $A$:

$$T_m = T_N + \Delta T_K$$

$$\dot Q_K = A \cdot \max\!\left(0,\ \eta_0\,G - a_1\,(T_m - T_a) - a_2\,(T_m - T_a)^2\right)$$

mit $\eta_0$ = {de(P['st_eta0'], 2)}, $a_1$ = {de(P['st_a1'], 1)} W/(m²K), $a_2$ = {de(P['st_a2'], 3)} W/(m²K²).
Geladen wird höchstens bis zur Maximaltemperatur $T_{{max}}$ = {de(P['sp_t_max'])} °C (Stagnation), die Wärme
geht in die unterste Schicht:

$$Q_{{lade}} = \min\!\Big(\dot Q_K\,\Delta t,\ C_s \sum_{{j=1}}^{{N}} \max(0,\ T_{{max}} - T_j)\Big)$$

$$T_N \leftarrow T_N + \frac{{Q_{{lade}}}}{{C_s}}$$

**3. Ausgleich (Auftrieb).** Ist eine Schicht wärmer als die darüber, mischen sich beide:

$$T_j > T_{{j-1}} \ \Rightarrow\ T_j,\,T_{{j-1}} \leftarrow \tfrac{{1}}{{2}}\,(T_j + T_{{j-1}})$$

**4. Entnahme.** Eine Last $Q$ mit Solltemperatur $T_{{soll}}$ und Rücklauftemperatur $T_R$ wird oben
entnommen, solange $T_1 > T_R + 0{{,}}5$ K. Bewegte Wärmekapazität $m$ und solar gedeckter Anteil:

$$m = \frac{{Q}}{{\max(T_1,\ T_{{soll}}) - T_R}}, \qquad Q_{{solar}} = m\,(T_1 - T_R)$$

Für $T_1 \ge T_{{soll}}$ deckt der Speicher die Last ganz (Beimischung), sonst nur anteilig; den Rest
$Q - Q_{{solar}}$ liefert der nächste Wärmeerzeuger. Das entnommene Wasser strömt unten mit $T_R$ nach
(Pfropfenströmung, $f = m / C_s \le 1$, sonst in mehreren Teilschritten):

$$T_j \leftarrow T_j + f\,(T_{{j+1}} - T_j)\quad (j = 1 \dots N-1), \qquad T_N \leftarrow T_N + f\,(T_R - T_N)$$

- **Warmwasser** (zuerst): $T_{{soll}}$ = 55 °C, $T_R$ = Kaltwasser {de(P['sp_t_kalt'])} °C.
- **Raumwärme** (danach): $T_{{soll}}$ = Vorlauftemperatur $T_{{VL}}$ nach Heizkurve,
  $T_R = 20\,°\mathrm{{C}} + 0{{,}}6\,(T_{{VL}} - 20\,°\mathrm{{C}})$.

**Heizkurve** (Auslegungs-Vorlauf $T_{{VL,A}}$ bei −14 °C außen):

$$T_{{VL}} = 25\,°\mathrm{{C}} + (T_{{VL,A}} - 25\,°\mathrm{{C}}) \cdot \min\!\left(1,\ \max\!\left(0,\ \frac{{20\,°\mathrm{{C}} - T_a}}{{34\ \mathrm{{K}}}}\right)\right)$$

**Speicherinhalt** (bezogen auf Kaltwasser $T_{{kalt}}$):

$$E = C_s \sum_{{j=1}}^{{N}} (T_j - T_{{kalt}})$$
""")
    st.subheader("Emissionen und Kosten")
    st.markdown(f"""
- **CO₂-Faktoren** (g/kWh Endenergie, editierbar): Erdgas 240, Heizöl 310, Holz 20 (Werte nach GEG
  Anlage 9); Netzstrom 380 als ungefährer deutscher Strommix der letzten Jahre (GEG-Rechenwert: 560).
  Aktuell gerechnet mit Strom {de(P['co2_strom'])}, Gas {de(P['co2_gas'])}, Öl {de(P['co2_oel'])},
  Holz {de(P['co2_holz'])} g/kWh. Für eingespeisten PV-Strom gibt es keine Gutschrift; die rechnerisch
  verdrängte Menge wird nur als Hinweis ausgewiesen.
- **Kosten** (Reiter „Kosten“, dort editierbar): Annuitätenmethode, vereinfacht nach VDI 2067.
  Jahresgesamtkosten = Kapitalkosten + Wartung/Instandhaltung + Energiebezug − Einspeiseerlös.
  Investition je Technologie = Fixkosten + spezifische Kosten × Größe; Kapitalkosten = (Investition −
  Förderung) × Annuitätenfaktor über die Nutzungsdauer; Wartung als Prozentsatz der Investition pro Jahr.
  Energiebezug mit Arbeitspreisen (Strom {de(P['preis_strom'], 3)}, Gas {de(P['preis_gas'], 3)},
  Öl {de(P['preis_oel'], 3)}, Holz {de(P['preis_holz'], 3)} €/kWh) und Grundpreisen, Einspeisevergütung
  {de(P['verguetung'], 3)} €/kWh. Die Investitionswerte sind grobe Richtwerte für Einfamilienhäuser inkl.
  Installation; der Pufferspeicher ist in den Kosten der Solarthermie enthalten. Nicht berücksichtigt:
  Preissteigerungen, Restwerte, Ersatzinvestitionen, Förderhöchstgrenzen, Steuern, eigener
  Wärmepumpen-Stromtarif.
""")
