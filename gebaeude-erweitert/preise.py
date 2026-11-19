"""Stündliche Day-Ahead-Preise (Gebotszone DE-LU) von SMARD (Bundesnetzagentur) und
Aufbau eines dynamischen Endkundentarifs.

Die Preise werden je Jahr als 8760 Stundenwerte in MEZ (UTC+1, ohne Sommerzeit, ohne 29. Februar)
in studie_ergebnisse/spot_<jahr>.npy abgelegt – passend zu den Temperaturreihen t2m_<jahr>.npy.
Liegt die Datei vor, wird nicht erneut im Netz abgerufen.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import requests

AUS = Path(__file__).parent / "studie_ergebnisse"
SMARD = "https://www.smard.de/app/chart_data/4169/DE"      # 4169 = Großhandelspreis DE-LU
JAHRE = (2019, 2020, 2021, 2022, 2023)

# Preisbestandteile neben dem Börsenpreis, netto in ct/kWh (stilisiert, Stand etwa 2024/25)
NETZENTGELT = 9.0
STROMSTEUER = 2.05
UMLAGEN = 2.45          # KWKG-, Offshore-, §19-Umlage und Konzessionsabgabe
VERTRIEB = 1.5
MWST = 0.19
# Zeitvariables Netzentgelt (angelehnt an §14a EnWG, Modul 3), netto in ct/kWh
NETZ_NT, NETZ_HT = 3.0, 15.0       # Niedertarif 0–6 Uhr, Hochtarif 17–21 Uhr, sonst NETZENTGELT


def spotpreis(jahr: int) -> np.ndarray:
    """Day-Ahead-Preis in €/MWh, 8760 Stundenwerte in MEZ."""
    datei = AUS / f"spot_{jahr}.npy"
    if datei.exists():
        return np.load(datei)
    start = pd.Timestamp(f"{jahr}-01-01") - pd.Timedelta(hours=1)          # MEZ -> UTC
    ende = pd.Timestamp(f"{jahr + 1}-01-01") - pd.Timedelta(hours=1)
    wochen = requests.get(f"{SMARD}/index_hour.json", timeout=30).json()["timestamps"]
    ms = lambda t: int(t.value // 10**6)
    teile = []
    for w in wochen:
        if w + 8 * 86400 * 1000 < ms(start) or w > ms(ende):
            continue
        reihe = requests.get(f"{SMARD}/4169_DE_hour_{w}.json", timeout=30).json()["series"]
        teile.append(pd.Series({t: v for t, v in reihe}, dtype=float))
    s = pd.concat(teile)
    s = s[~s.index.duplicated()].sort_index()
    s.index = pd.to_datetime(s.index, unit="ms")                            # UTC
    s = s.reindex(pd.date_range(start, ende, freq="h", inclusive="left")).interpolate(limit_direction="both")
    s.index = s.index + pd.Timedelta(hours=1)                               # MEZ
    s = s[~((s.index.month == 2) & (s.index.day == 29))]
    if len(s) != 8760:
        raise RuntimeError(f"Preisreihe {jahr}: {len(s)} statt 8760 Werte")
    AUS.mkdir(exist_ok=True)
    np.save(datei, s.values)
    return s.values


def netzentgelt(variabel: bool = False, standard: float = NETZENTGELT) -> np.ndarray:
    """Netzentgelt je Stunde in ct/kWh (netto). Nieder- und Hochtarif skalieren mit dem Standardentgelt."""
    h = np.arange(8760) % 24
    if not variabel:
        return np.full(8760, standard)
    f = standard / NETZENTGELT
    return np.where(h < 6, NETZ_NT * f, np.where((h >= 17) & (h < 21), NETZ_HT * f, standard))


def endpreis(spot: np.ndarray, netz_variabel: bool = False, standard: float = NETZENTGELT) -> np.ndarray:
    """Dynamischer Endkundenpreis in €/kWh (brutto)."""
    netto = (np.asarray(spot, float) / 10.0 + netzentgelt(netz_variabel, standard)
             + STROMSTEUER + UMLAGEN + VERTRIEB)
    return netto * (1 + MWST) / 100.0


if __name__ == "__main__":
    for j in JAHRE:
        s = spotpreis(j)
        tag = s.reshape(365, 24)
        print(f"{j}: Mittel {s.mean():6.1f}  Min {s.min():7.1f}  Max {s.max():7.1f}  Std {s.std():6.1f}  "
              f"mittl. Tagesspanne {np.mean(tag.max(1) - tag.min(1)):6.1f} €/MWh  "
              f"negativ {int((s < 0).sum())} h  Endpreis {endpreis(s).mean() * 100:5.1f} ct/kWh")
