"""Kostenrechnung nach der Annuitätenmethode (vereinfacht nach VDI 2067):
Kapitalkosten (Annuität des Eigenanteils), Wartung/Instandhaltung,
Energiebezug (Arbeits- und Grundpreise) und Einspeiseerlös.

Alle Kostenannahmen sind grobe Richtwerte für Einfamilienhäuser in
Deutschland (Endkundenpreise inkl. MwSt., inkl. Installation) und in der
App editierbar.
"""
from __future__ import annotations

import pandas as pd

TRAEGER = {"strom": "Strom (Netz)", "gas": "Erdgas", "oel": "Heizöl", "holz": "Holz"}

# Energieträger -> (Arbeitspreis [€/kWh], Grundpreis [€/a])
PREISE = {
    "Strom (Netz)": (0.35, 150.0),
    "Erdgas": (0.11, 200.0),
    "Heizöl": (0.10, 0.0),
    "Holz": (0.07, 0.0),
}

# Technologie -> (Einheit, Fixkosten [€], spez. Kosten [€/Einheit], Förderung [%],
#                 Nutzungsdauer [a], Wartung und Instandhaltung [% der Investition pro Jahr])
INVEST = {
    "Photovoltaik": ("kWp", 2000.0, 1100.0, 0.0, 25, 1.0),
    "Batteriespeicher": ("kWh", 1500.0, 550.0, 0.0, 15, 1.0),
    "Wärmepumpe Luft": ("kW", 16000.0, 1500.0, 30.0, 20, 1.5),
    "Wärmepumpe Erdreich": ("kW", 24000.0, 2500.0, 30.0, 20, 1.5),
    "Gasheizung": ("kW", 8000.0, 150.0, 0.0, 20, 2.5),
    "Ölheizung": ("kW", 11000.0, 200.0, 0.0, 20, 2.5),
    "Holzheizung": ("kW", 16000.0, 700.0, 30.0, 20, 3.0),
    "Kachelofen": ("kW", 7000.0, 1000.0, 0.0, 30, 1.0),
    "Solarthermie": ("m²", 3000.0, 600.0, 30.0, 20, 1.5),
}

SP = ["Einheit", "Fixkosten [€]", "spez. Kosten [€/Einheit]", "Förderung [%]",
      "Nutzungsdauer [a]", "Wartung [%/a]"]
SP_PREIS = ["Arbeitspreis [€/kWh]", "Grundpreis [€/a]"]
SP_INV = ["Technologie", "Größe", "Einheit", "Investition [€]", "Förderung [€]", "Eigenanteil [€]",
          "Nutzungsdauer [a]", "Annuitätenfaktor", "Kapitalkosten [€/a]", "Wartung [€/a]", "Summe [€/a]"]
SP_BEZ = ["Energieträger", "Menge [kWh/a]", "Arbeitspreis [€/kWh]", "Arbeitskosten [€/a]",
          "Grundpreis [€/a]", "Summe [€/a]"]


def _f(x) -> float:
    """Zahl aus einer Editor-Zelle (leere Zelle = 0)."""
    return 0.0 if x is None or pd.isna(x) else float(x)


def preise_df() -> pd.DataFrame:
    df = pd.DataFrame.from_dict(PREISE, orient="index", columns=SP_PREIS)
    df.index.name = "Energieträger"
    return df


def invest_df() -> pd.DataFrame:
    df = pd.DataFrame.from_dict(INVEST, orient="index", columns=SP)
    df.index.name = "Technologie"
    return df


def annuitaetenfaktor(zins: float, n: float) -> float:
    """a = i·(1+i)^n / ((1+i)^n − 1); bei i = 0: 1/n."""
    if n <= 0:
        return 0.0
    if abs(zins) < 1e-12:
        return 1.0 / n
    q = (1.0 + zins) ** n
    return zins * q / (q - 1.0)


def investitionen(groessen: dict[str, float], annahmen: pd.DataFrame, zins: float) -> pd.DataFrame:
    """Investition, Förderung, Annuität und Wartung je gewählter Technologie."""
    zeilen = []
    for tech, gr in groessen.items():
        a = annahmen.loc[tech]
        brutto = _f(a["Fixkosten [€]"]) + _f(a["spez. Kosten [€/Einheit]"]) * gr if gr > 0 else 0.0
        foerd = brutto * _f(a["Förderung [%]"]) / 100.0
        n = _f(a["Nutzungsdauer [a]"])
        af = annuitaetenfaktor(zins, n)
        kap = (brutto - foerd) * af
        wart = brutto * _f(a["Wartung [%/a]"]) / 100.0
        zeilen.append([tech, gr, a["Einheit"], brutto, foerd, brutto - foerd, n, af, kap, wart, kap + wart])
    return pd.DataFrame(zeilen, columns=SP_INV)


def bezugskosten(k: dict, preise: pd.DataFrame) -> pd.DataFrame:
    """Arbeits- und Grundpreise je Energieträger. Strom-Grundpreis fällt immer an,
    die übrigen Grundpreise nur, wenn der Energieträger genutzt wird."""
    mengen = {"Strom (Netz)": k["netzbezug"], "Erdgas": k["end_gas"],
              "Heizöl": k["end_oel"], "Holz": k["end_holz"]}
    zeilen = []
    for name, menge in mengen.items():
        ap = _f(preise.loc[name, SP_PREIS[0]])
        genutzt = menge > 0.5 or name == "Strom (Netz)"
        if not genutzt:
            continue
        gp = _f(preise.loc[name, SP_PREIS[1]])
        zeilen.append([name, menge, ap, menge * ap, gp, menge * ap + gp])
    return pd.DataFrame(zeilen, columns=SP_BEZ)


def zusammenfassung(inv: pd.DataFrame, bez: pd.DataFrame, erloes: float,
                    nutzenergie: float, flaeche: float) -> dict:
    K = dict(
        invest=float(inv["Investition [€]"].sum()), foerderung=float(inv["Förderung [€]"].sum()),
        kapital=float(inv["Kapitalkosten [€/a]"].sum()), wartung=float(inv["Wartung [€/a]"].sum()),
        energie=float(bez["Summe [€/a]"].sum()), erloes=float(erloes),
    )
    K["gesamt"] = K["kapital"] + K["wartung"] + K["energie"] - K["erloes"]
    K["je_kwh"] = K["gesamt"] / nutzenergie if nutzenergie > 0 else float("nan")
    K["je_m2"] = K["gesamt"] / flaeche if flaeche > 0 else float("nan")
    pos = {"Kapitalkosten": K["kapital"], "Wartung und Instandhaltung": K["wartung"]}
    for _, z in bez.iterrows():
        pos[f"Bezug {z['Energieträger']}"] = float(z["Summe [€/a]"])
    if K["erloes"] > 0.5:
        pos["Einspeiseerlös"] = -K["erloes"]
    K["positionen"] = {n: v for n, v in pos.items() if abs(v) > 0.5}
    return K
