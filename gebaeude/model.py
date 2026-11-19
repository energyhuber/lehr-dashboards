"""Gebäudemodell: Lastprofile (Strom, Raumwärme, Warmwasser) und
Bereitstellung durch PV, Batterie, Solarthermie, Kachelofen, Wärmepumpe,
Holz-, Gas- und Ölkessel in 15-Minuten-Auflösung.

Alle Leistungen in kW, Energien in kWh, Zeitschritt DT = 0,25 h.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data import DT, STEPS

# ---------------------------------------------------------------------------
# Annahmen (Richtwerte, in der App editierbar)
# ---------------------------------------------------------------------------
# Gebäudestandard -> (spez. Heizwärmebedarf [kWh/m²a, Nutzwärme],
#                     Heizgrenztemperatur [°C], Auslegungs-Vorlauftemperatur [°C])
GEBAEUDESTANDARDS = {
    "Altbau unsaniert (vor 1979)": (220.0, 17.0, 70.0),
    "Altbau teilsaniert (WSchV 1984/95)": (140.0, 15.0, 55.0),
    "EnEV 2002–2014": (80.0, 14.0, 45.0),
    "GEG-Neubau / Effizienzhaus 70": (50.0, 12.0, 35.0),
    "Effizienzhaus 55": (35.0, 12.0, 35.0),
    "Effizienzhaus 40": (25.0, 10.0, 35.0),
    "Passivhaus": (15.0, 10.0, 35.0),
}

# Heizsystem -> Auslegungs-Vorlauftemperatur [°C] bei Norm-Außentemperatur
HEIZSYSTEME = {
    "Fußbodenheizung (35 °C)": 35.0,
    "Niedertemperatur-Heizkörper (45 °C)": 45.0,
    "Heizkörper (55 °C)": 55.0,
    "Alte Heizkörper (70 °C)": 70.0,
}

# Haushaltsstrom [kWh/a] nach Personenzahl (Einfamilienhaus, ohne elektrische
# Warmwasserbereitung und ohne Wärmepumpe; Größenordnung nach Stromspiegel)
STROMBEDARF_PERSONEN = {1: 2300, 2: 3000, 3: 3600, 4: 4000, 5: 4500, 6: 5000}

WARMWASSER_KWH_PERSON = 600.0   # Nutzwärme, ca. 40 l/d bei ΔT = 35 K
T_AUSLEGUNG = -14.0             # Norm-Außentemperatur Ingolstadt (ca.)
T_RAUM = 20.0
T_WARMWASSER = 55.0             # Senkentemperatur WP für Warmwasser

# Energieträger -> (CO2-Faktor [g/kWh Endenergie], Preis [€/kWh])
ENERGIETRAEGER = {
    "Strom (Netz)": (380.0, 0.35),
    "Erdgas": (240.0, 0.11),
    "Heizöl": (310.0, 0.10),
    "Holz (Pellets/Scheitholz)": (20.0, 0.07),
}
EINSPEISEVERGUETUNG = 0.08      # €/kWh

DEFAULTS = dict(
    # Gebäude
    flaeche=140.0, personen=3, spez_heizwaerme=80.0, heizgrenze=14.0,
    t_vorlauf=50.0, strom_kwh=3600.0, ww_kwh_person=WARMWASSER_KWH_PERSON,
    # PV / Batterie
    pv_kwp=0.0, bat_kwh=0.0, bat_kw=0.0, bat_eta=0.90,
    # Solarthermie + Pufferspeicher
    st_flaeche=0.0, st_eta0=0.75, st_a1=3.5, st_a2=0.015, st_tm=50.0,
    sp_liter=500.0, sp_dt=35.0, sp_verlust=0.5,
    # Kachelofen (nur Raumwärme)
    ko_kw=0.0, ko_eta=0.75, ko_start=17, ko_ende=22, ko_tgrenz=8.0,
    # Wärmepumpe
    wp=False, wp_kw=0.0, wp_quelle="Luft", wp_guete=0.40, wp_cop_max=6.5,
    wp_heizstab=True,
    # Kessel (kW = 0: unbegrenzt)
    holz=False, holz_kw=0.0, holz_eta=0.85,
    gas=False, gas_kw=0.0, gas_eta=0.95,
    oel=False, oel_kw=0.0, oel_eta=0.88,
    # CO2 [g/kWh] und Preise [€/kWh]
    co2_strom=380.0, co2_gas=240.0, co2_oel=310.0, co2_holz=20.0,
    preis_strom=0.35, preis_gas=0.11, preis_oel=0.10, preis_holz=0.07,
    verguetung=EINSPEISEVERGUETUNG,
)


# ---------------------------------------------------------------------------
# Lastprofile
# ---------------------------------------------------------------------------
def _gauss(h, mu, sd):
    return np.exp(-0.5 * ((h - mu) / sd) ** 2)


def strom_profil(index: pd.DatetimeIndex, jahres_kwh: float) -> np.ndarray:
    """Synthetisches Haushaltsprofil in Anlehnung an BDEW H0 [kW].

    Tagesform je Typtag (Werktag/Samstag/Sonntag) aus Grundlast + Morgen-,
    Mittags- und Abendspitze (synthetisch, NICHT die Original-H0-Tabelle);
    Jahresgang über die originale H0-Dynamisierungsfunktion
    F(d) = -3,92e-10 d⁴ + 3,2e-7 d³ - 7,02e-5 d² + 2,1e-3 d + 1,24.
    """
    h = (np.arange(96) + 0.5) / 4.0
    werktag = 0.35 + 0.50 * _gauss(h, 7.0, 1.2) + 0.45 * _gauss(h, 12.5, 1.5) + 1.00 * _gauss(h, 19.0, 2.0)
    samstag = 0.35 + 0.40 * _gauss(h, 9.0, 1.8) + 0.60 * _gauss(h, 12.5, 1.8) + 0.90 * _gauss(h, 18.5, 2.2)
    sonntag = 0.35 + 0.35 * _gauss(h, 9.5, 1.8) + 0.90 * _gauss(h, 12.0, 1.5) + 0.75 * _gauss(h, 18.5, 2.2)
    shapes = np.vstack([werktag, samstag, sonntag])
    dow = index.dayofweek.values
    typ = np.where(dow < 5, 0, np.where(dow == 5, 1, 2))
    qh = index.hour.values * 4 + index.minute.values // 15
    d = np.arange(STEPS) // 96 + 1.0
    dyn = -3.92e-10 * d**4 + 3.2e-7 * d**3 - 7.02e-5 * d**2 + 2.1e-3 * d + 1.24
    p = shapes[typ, qh] * dyn
    return p / (p.sum() * DT) * jahres_kwh


def warmwasser_profil(index: pd.DatetimeIndex, jahres_kwh: float) -> np.ndarray:
    """Warmwasser-Nutzwärme [kW]: Morgen-, Mittags- und Abendspitze,
    ±10 % Jahresgang (im Winter höher)."""
    h = index.hour.values + index.minute.values / 60.0 + 0.125
    tag = 0.10 + 1.0 * _gauss(h, 7.0, 1.0) + 0.3 * _gauss(h, 12.5, 1.0) + 0.8 * _gauss(h, 19.5, 1.5)
    d = np.arange(STEPS) // 96
    p = tag * (1 + 0.10 * np.cos(2 * np.pi * (d - 15) / 365))
    return p / (p.sum() * DT) * jahres_kwh


def heiz_profil(index: pd.DatetimeIndex, t_aussen: np.ndarray, jahres_kwh: float,
                heizgrenze: float) -> np.ndarray:
    """Raumwärme-Nutzwärme [kW] nach Gradstunden-Ansatz.

    Wirksame Außentemperatur = Mittel aus aktuellem Wert und gleitendem
    24-h-Mittel (Gebäudeträgheit). Last ∝ max(0, Heizgrenze − T_wirksam),
    multipliziert mit einem Tagesfaktor (Nachtabsenkung 23–5 Uhr: 0,75;
    Aufheizen 6–8 Uhr: 1,15). Skaliert auf den Jahres-Heizwärmebedarf.
    """
    t24 = pd.Series(t_aussen).rolling(96, min_periods=1).mean().values
    t_eff = 0.5 * t_aussen + 0.5 * t24
    hr = index.hour.values
    f = np.where((hr >= 23) | (hr < 5), 0.75, np.where((hr >= 6) & (hr < 8), 1.15, 1.0))
    p = np.clip(heizgrenze - t_eff, 0, None) * f
    if p.sum() <= 0:
        return np.zeros(STEPS)
    return p / (p.sum() * DT) * jahres_kwh


def cop_waermepumpe(t_aussen: np.ndarray, t_senke: np.ndarray | float, quelle: str,
                    guete: float, cop_max: float) -> np.ndarray:
    """COP = Gütegrad × Carnot-COP, begrenzt auf [1, cop_max].
    Quelle Luft: Außentemperatur; Erdreich (Sole): konstant 3 °C."""
    t_q = t_aussen if quelle == "Luft" else np.full_like(t_aussen, 3.0)
    hub = np.clip(t_senke - t_q, 8.0, None)
    return np.clip(guete * (np.asarray(t_senke) + 273.15) / hub, 1.0, cop_max)


def vorlauftemperatur(t_aussen: np.ndarray, t_vl_auslegung: float) -> np.ndarray:
    """Lineare Heizkurve: T_RAUM+5 bei 20 °C außen bis Auslegungswert bei −14 °C."""
    x = np.clip((T_RAUM - t_aussen) / (T_RAUM - T_AUSLEGUNG), 0, 1)
    return (T_RAUM + 5.0) + (max(t_vl_auslegung, T_RAUM + 5.0) - (T_RAUM + 5.0)) * x


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
def simulate(wetter: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, dict]:
    """Jahressimulation. `wetter`: 15-min-DataFrame mit pv [kW/kWp], g [W/m²],
    t2m [°C]. Rückgabe: Zeitreihen [kW bzw. kWh für Speicherstände] und Kennzahlen."""
    p = {**DEFAULTS, **params}
    idx = wetter.index
    ta = wetter["t2m"].values
    g = wetter["g"].values
    n = len(idx)

    # --- Bedarf -----------------------------------------------------------
    el_hh = strom_profil(idx, p["strom_kwh"])
    q_rw = heiz_profil(idx, ta, p["spez_heizwaerme"] * p["flaeche"], p["heizgrenze"])
    q_ww = warmwasser_profil(idx, p["ww_kwh_person"] * p["personen"])

    # --- Solarthermie + Pufferspeicher (Schleife) ---------------------------
    st_gen = np.zeros(n)
    if p["st_flaeche"] > 0:
        dT = p["st_tm"] - ta
        with np.errstate(divide="ignore", invalid="ignore"):
            spez = p["st_eta0"] * g - p["st_a1"] * dT - p["st_a2"] * dT**2   # W/m²
        st_gen = np.clip(spez, 0, None) * p["st_flaeche"] / 1000.0
    sp_kap = p["sp_liter"] * 1.163e-3 * p["sp_dt"] if p["st_flaeche"] > 0 else 0.0
    st_rw = np.zeros(n); st_ww = np.zeros(n); sp_soc = np.zeros(n)
    st_nutz = np.zeros(n); sp_verl = np.zeros(n)
    if p["st_flaeche"] > 0:
        e = 0.0
        vf = p["sp_verlust"] / 100.0 * DT
        gl, rl, wl = st_gen.tolist(), q_rw.tolist(), q_ww.tolist()
        for i in range(n):
            v = e * vf
            e -= v
            ww, rw, gen = wl[i], rl[i], gl[i]
            # direkt nutzen, Warmwasser zuerst
            d_ww = min(gen, ww); rest = gen - d_ww
            d_rw = min(rest, rw); rest -= d_rw
            lade = min(rest, (sp_kap - e) / DT)
            e += lade * DT
            # Speicher entladen
            s_ww = min(ww - d_ww, e / DT); e -= s_ww * DT
            s_rw = min(rw - d_rw, e / DT); e -= s_rw * DT
            st_ww[i] = d_ww + s_ww; st_rw[i] = d_rw + s_rw
            st_nutz[i] = d_ww + d_rw + lade
            sp_soc[i] = e; sp_verl[i] = v / DT

    rest_rw = q_rw - st_rw
    rest_ww = q_ww - st_ww

    # --- Kachelofen (nur Raumwärme, Betrieb abends an kalten Tagen) ---------
    ko = np.zeros(n)
    if p["ko_kw"] > 0:
        t_tag = np.repeat(ta.reshape(-1, 96).mean(axis=1), 96)
        hr = idx.hour.values
        an = (hr >= p["ko_start"]) & (hr < p["ko_ende"]) & (t_tag < p["ko_tgrenz"])
        ko = np.where(an, np.minimum(rest_rw, p["ko_kw"]), 0.0)
        rest_rw = rest_rw - ko

    # --- Kaskade der Wärmeerzeuger: WP -> Holz -> Gas -> Öl -----------------
    def decke(rw, ww, aktiv, kw):
        if not aktiv:
            return np.zeros(n), np.zeros(n)
        tot = rw + ww
        lim = tot if kw <= 0 else np.minimum(tot, kw)
        f = np.divide(lim, tot, out=np.zeros(n), where=tot > 1e-12)
        return rw * f, ww * f

    wp_rw, wp_ww = decke(rest_rw, rest_ww, p["wp"], p["wp_kw"])
    rest_rw, rest_ww = rest_rw - wp_rw, rest_ww - wp_ww
    hz_rw, hz_ww = decke(rest_rw, rest_ww, p["holz"], p["holz_kw"])
    rest_rw, rest_ww = rest_rw - hz_rw, rest_ww - hz_ww
    gs_rw, gs_ww = decke(rest_rw, rest_ww, p["gas"], p["gas_kw"])
    rest_rw, rest_ww = rest_rw - gs_rw, rest_ww - gs_ww
    ol_rw, ol_ww = decke(rest_rw, rest_ww, p["oel"], p["oel_kw"])
    rest_rw, rest_ww = rest_rw - ol_rw, rest_ww - ol_ww
    # Heizstab der WP deckt den Rest (η = 1)
    hs = (rest_rw + rest_ww) if (p["wp"] and p["wp_heizstab"]) else np.zeros(n)
    ungedeckt = np.clip(rest_rw + rest_ww - hs, 0, None)
    ungedeckt[ungedeckt < 1e-9] = 0.0

    cop_rw = cop_waermepumpe(ta, vorlauftemperatur(ta, p["t_vorlauf"]), p["wp_quelle"],
                             p["wp_guete"], p["wp_cop_max"])
    cop_ww = cop_waermepumpe(ta, T_WARMWASSER, p["wp_quelle"], p["wp_guete"], p["wp_cop_max"])
    el_wp = wp_rw / cop_rw + wp_ww / cop_ww
    q_wp = wp_rw + wp_ww
    q_holz, q_gas, q_oel = hz_rw + hz_ww, gs_rw + gs_ww, ol_rw + ol_ww

    # --- Strom: PV -> Last -> Batterie -> Netz ------------------------------
    pv = wetter["pv"].values * p["pv_kwp"]
    last = el_hh + el_wp + hs
    direkt = np.minimum(pv, last)
    ueber = pv - direkt
    defizit = last - direkt
    bat_lad = np.zeros(n); bat_entl = np.zeros(n); bat_soc = np.zeros(n)
    if p["bat_kwh"] > 0 and p["pv_kwp"] > 0:
        eta = float(np.sqrt(p["bat_eta"]))
        kap = p["bat_kwh"]
        pmax = p["bat_kw"] if p["bat_kw"] > 0 else kap      # Standard 1C
        e = 0.0
        ul, dl = ueber.tolist(), defizit.tolist()
        for i in range(n):
            if ul[i] > 0:
                c = min(ul[i], pmax, (kap - e) / (eta * DT))
                e += c * eta * DT
                bat_lad[i] = c
            elif dl[i] > 0:
                c = min(dl[i], pmax, e * eta / DT)
                e -= c / eta * DT
                bat_entl[i] = c
            bat_soc[i] = e
    einspeisung = ueber - bat_lad
    netz = defizit - bat_entl

    ts = pd.DataFrame({
        "t_aussen": ta, "einstrahlung": g,
        "strom_haushalt": el_hh, "strom_wp": el_wp, "strom_heizstab": hs,
        "strom_last": last, "pv": pv, "pv_direkt": direkt,
        "bat_laden": bat_lad, "bat_entladen": bat_entl, "bat_soc": bat_soc,
        "netzbezug": netz, "einspeisung": einspeisung,
        "waerme_raum": q_rw, "waerme_ww": q_ww, "waerme_bedarf": q_rw + q_ww,
        "q_solar": st_rw + st_ww, "q_kachelofen": ko, "q_wp": q_wp,
        "q_holz": q_holz, "q_gas": q_gas, "q_oel": q_oel, "q_heizstab": hs,
        "q_ungedeckt": ungedeckt, "st_ertrag": st_gen, "st_genutzt": st_nutz,
        "sp_soc": sp_soc, "cop": np.where(q_wp > 1e-9, q_wp / np.maximum(el_wp, 1e-12), np.nan),
    }, index=idx)

    # --- Kennzahlen -----------------------------------------------------------
    E = lambda a: float(np.sum(a) * DT)
    end_holz = E(q_holz) / p["holz_eta"] + E(ko) / p["ko_eta"]
    end_gas = E(q_gas) / p["gas_eta"]
    end_oel = E(q_oel) / p["oel_eta"]
    k = dict(
        strom_haushalt=E(el_hh), strom_wp=E(el_wp), strom_heizstab=E(hs),
        strom_gesamt=E(last), pv=E(pv), pv_direkt=E(direkt),
        bat_laden=E(bat_lad), bat_entladen=E(bat_entl),
        netzbezug=E(netz), einspeisung=E(einspeisung),
        waerme_raum=E(q_rw), waerme_ww=E(q_ww), waerme_bedarf=E(q_rw + q_ww),
        q_solar=E(st_rw + st_ww), q_kachelofen=E(ko), q_wp=E(q_wp), q_holz=E(q_holz),
        q_gas=E(q_gas), q_oel=E(q_oel), q_heizstab=E(hs), q_ungedeckt=E(ungedeckt),
        st_ertrag=E(st_gen), st_genutzt=E(st_nutz),
        end_holz=end_holz, end_gas=end_gas, end_oel=end_oel,
        heizlast_max=float((q_rw + q_ww).max()),
    )
    k["eigenverbrauch"] = k["pv"] - k["einspeisung"]
    k["eigenverbrauchsquote"] = k["eigenverbrauch"] / k["pv"] if k["pv"] > 0 else 0.0
    k["autarkie"] = 1 - k["netzbezug"] / k["strom_gesamt"] if k["strom_gesamt"] > 0 else 0.0
    k["jaz"] = k["q_wp"] / k["strom_wp"] if k["strom_wp"] > 0 else float("nan")
    k["co2"] = {
        "Strom (Netz)": k["netzbezug"] * p["co2_strom"] / 1000.0,
        "Erdgas": end_gas * p["co2_gas"] / 1000.0,
        "Heizöl": end_oel * p["co2_oel"] / 1000.0,
        "Holz": end_holz * p["co2_holz"] / 1000.0,
    }
    k["co2_gesamt"] = sum(k["co2"].values())
    k["co2_vermieden"] = k["einspeisung"] * p["co2_strom"] / 1000.0
    k["kosten"] = {
        "Strom (Netz)": k["netzbezug"] * p["preis_strom"],
        "Erdgas": end_gas * p["preis_gas"],
        "Heizöl": end_oel * p["preis_oel"],
        "Holz": end_holz * p["preis_holz"],
    }
    k["erloes"] = k["einspeisung"] * p["verguetung"]
    k["kosten_netto"] = sum(k["kosten"].values()) - k["erloes"]
    return ts, k
