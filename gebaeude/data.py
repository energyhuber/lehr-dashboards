"""Wetter- und Ertragsdaten: PVGIS-Abruf (JRC) und synthetischer Fallback.

Alle Zeitreihen werden auf ein Normaljahr mit 365 Tagen gebracht
(Schalttag entfernt), von UTC nach MEZ (UTC+1, ohne Sommerzeit) verschoben
und von Stunden- auf 15-Minuten-Werte linear interpoliert.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests

HOURS = 8760
STEPS = HOURS * 4          # 35 040 Viertelstunden
DT = 0.25                  # h
UTC_OFFSET_H = 1           # MEZ, Sommerzeit wird nicht berücksichtigt

STANDORTE = {
    "Ingolstadt": (48.77, 11.43),
    "München": (48.14, 11.58),
    "Nürnberg": (49.45, 11.08),
    "Berlin": (52.52, 13.40),
    "Hamburg": (53.55, 9.99),
    "Freiburg": (47.99, 7.85),
    "Benutzerdefiniert": (48.77, 11.43),
}

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"


def time_index(year: int) -> pd.DatetimeIndex:
    """15-min-Zeitstempel eines Jahres ohne 29. Februar (35 040 Werte)."""
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:45", freq="15min")
    return idx[~((idx.month == 2) & (idx.day == 29))]


def fetch_pvgis(lat: float, lon: float, tilt: float, aspect: float, year: int,
                loss: float = 14.0) -> pd.DataFrame:
    """Stündliche Daten von PVGIS (seriescalc), in Ortszeit (MEZ).

    aspect: PVGIS-Konvention, 0 = Süd, 90 = West, -90 = Ost.
    Rückgabe: 8760 Zeilen mit
      pv  – PV-Leistung je kWp [kW/kWp] (inkl. Systemverluste `loss`)
      g   – Globalstrahlung in Modulebene G(i) [W/m²]
      t2m – Außentemperatur in 2 m Höhe [°C]
    """
    params = dict(lat=lat, lon=lon, peakpower=1, loss=loss, angle=tilt,
                  aspect=aspect, pvcalculation=1, startyear=year, endyear=year,
                  outputformat="json")
    r = requests.get(PVGIS_URL, params=params, timeout=60)
    r.raise_for_status()
    h = pd.DataFrame(r.json()["outputs"]["hourly"])
    t = pd.to_datetime(h["time"], format="%Y%m%d:%H%M")
    keep = ~((t.dt.month == 2) & (t.dt.day == 29)).values
    out = {}
    for col, src, scale in (("pv", "P", 1 / 1000.0), ("g", "G(i)", 1.0), ("t2m", "T2m", 1.0)):
        v = h[src].values[keep].astype(float) * scale
        if len(v) != HOURS:
            raise ValueError(f"PVGIS lieferte {len(v)} statt {HOURS} Stundenwerte")
        out[col] = np.roll(v, UTC_OFFSET_H)      # UTC -> MEZ
    df = pd.DataFrame(out)
    df["pv"] = df["pv"].clip(lower=0)
    df["g"] = df["g"].clip(lower=0)
    return df


def synthetic_weather(lat: float, tilt: float, aspect: float,
                      annual_irradiation: float = 1250.0, seed: int = 1) -> pd.DataFrame:
    """Fallback ohne Internet: Sonnenstandsgeometrie + zufällige Bewölkung
    (AR(1)-Prozess des Tages-Klarheitsindex) und sinusförmiger Temperaturgang
    mit Tagesgang und Wetterrauschen. Skaliert auf `annual_irradiation`
    kWh/m²a in Modulebene; PV-Ertrag mit Performance Ratio 0,86.
    Nur für die Nordhalbkugel/Mitteleuropa gedacht.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(HOURS)
    doy = t // 24 + 1
    hour = t % 24 + 0.5
    phi, beta, gam = np.radians(lat), np.radians(tilt), np.radians(aspect)
    decl = np.radians(23.45) * np.sin(2 * np.pi * (284 + doy) / 365)
    om = np.radians(15 * (hour - 12))
    cos_z = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(om)
    cos_i = (np.sin(decl) * np.sin(phi) * np.cos(beta)
             - np.sin(decl) * np.cos(phi) * np.sin(beta) * np.cos(gam)
             + np.cos(decl) * np.cos(phi) * np.cos(beta) * np.cos(om)
             + np.cos(decl) * np.sin(phi) * np.sin(beta) * np.cos(gam) * np.cos(om)
             + np.cos(decl) * np.sin(beta) * np.sin(gam) * np.sin(om))
    up = cos_z > 0
    beam = np.where(up, np.clip(cos_i, 0, None), 0.0)
    diffuse = np.where(up, 0.25 * cos_z * (1 + np.cos(beta)) / 2 + 0.05, 0.0)
    days = HOURS // 24
    d = np.arange(days)
    season = 0.45 + 0.15 * np.cos(2 * np.pi * (d - 172) / 365)   # Sommer klarer
    k = np.empty(days)
    k[0] = season[0]
    for i in range(1, days):
        k[i] = season[i] + 0.6 * (k[i - 1] - season[i - 1]) + rng.normal(0, 0.15)
    k = np.clip(k, 0.05, 0.85)
    kh = np.repeat(k, 24)
    g = beam * kh + diffuse * (0.5 + 0.5 * kh)
    g = g / g.sum() * annual_irradiation * 1000.0                # W/m²
    g = np.clip(g, 0, 1100)
    # Temperatur: Jahresgang + Tagesgang + Wetterrauschen, sonnige Tage wärmer
    noise = np.empty(days)
    noise[0] = 0.0
    for i in range(1, days):
        noise[i] = 0.75 * noise[i - 1] + rng.normal(0, 2.2)
    t_day = 9.5 - 10.0 * np.cos(2 * np.pi * (d - 20) / 365) + noise + 4 * (k - season)
    t2m = np.repeat(t_day, 24) + (2 + 5 * kh) * np.cos(2 * np.pi * (hour - 15) / 24)
    return pd.DataFrame({"pv": np.clip(g / 1000.0 * 0.86, 0, 1.0), "g": g, "t2m": t2m})


def to_15min(hourly: pd.DataFrame, year: int) -> pd.DataFrame:
    """Stundenwerte (als Stundenmittel interpretiert) linear auf 15 min."""
    xh = np.arange(HOURS) + 0.5
    xq = (np.arange(STEPS) + 0.5) / 4.0
    out = {c: np.interp(xq, xh, hourly[c].values) for c in hourly.columns}
    df = pd.DataFrame(out, index=time_index(year))
    df["pv"] = df["pv"].clip(lower=0)
    df["g"] = df["g"].clip(lower=0)
    return df
