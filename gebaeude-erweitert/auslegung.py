"""Optimierte Auslegung: Beispielhaus, Maßnahmen an Hülle und Energietechnik für Neubau und
Sanierung, annuitätische Ausgaben gegen annuitätische Einsparungen, vollständige Enumeration
aller Kombinationen (schnelles Stundenmodell, 8760 h).

Vereinfachungen: Bauteilflächen aus einer Quadergeometrie, U-Werte je Baualtersklasse,
Gradstundenansatz mit Heizgrenze aus den Wärmegewinnen, Wärmepumpe mit Gütegrad-COP,
Batterie nur zur Eigenverbrauchserhöhung, Solarthermie nur für Warmwasser. Beim dynamischen
Tarif wird der Netzbezug stündlich bepreist, aber nicht preisgeführt verschoben (dazu der
Reiter „Flexible Strompreise“).
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

import data
import kosten
import model

# Baualtersklasse -> U-Werte [W/(m²K)] und Auslegungs-Vorlauftemperatur der vorhandenen Heizflächen
ALTER = {
    "vor 1979": dict(wand=1.20, dach=0.80, fenster=2.70, boden=1.00, t_vl=70.0),
    "1979–1994": dict(wand=0.80, dach=0.50, fenster=2.60, boden=0.70, t_vl=60.0),
    "1995–2001": dict(wand=0.50, dach=0.30, fenster=1.80, boden=0.50, t_vl=55.0),
    "2002–2015": dict(wand=0.35, dach=0.25, fenster=1.40, boden=0.40, t_vl=45.0),
}
U_NEU = dict(wand=0.20, dach=0.14, fenster=0.95, boden=0.25)      # nach Sanierung (BEG-Einzelmaßnahme)
MASSNAHMEN = {"dach": "Dachdämmung", "wand": "Fassadendämmung", "fenster": "Fenstertausch",
              "boden": "Kellerdeckendämmung"}
NEUBAU = {"GEG-Neubau": "GEG-Neubau / Effizienzhaus 70", "Effizienzhaus 55": "Effizienzhaus 55",
          "Effizienzhaus 40": "Effizienzhaus 40"}
# Wärmeerzeuger -> (Kostenzeile, Energieträger, Wirkungsgrad bzw. WP-Quelle)
ERZEUGER = {
    "Bestandskessel Gas": (None, "gas", 0.85), "Bestandskessel Öl": (None, "oel", 0.80),
    "Gas-Brennwert neu": ("Gasheizung", "gas", 0.95), "Öl-Brennwert neu": ("Ölheizung", "oel", 0.92),
    "Luft-Wärmepumpe": ("Wärmepumpe Luft", "strom", "Luft"),
    "Erdreich-Wärmepumpe": ("Wärmepumpe Erdreich", "strom", "Erdreich"),
    "Pelletkessel": ("Holzheizung", "holz", 0.85),
}
CO2 = dict(strom=0.380, gas=0.240, oel=0.310, holz=0.020)          # kg/kWh Endenergie
GEWINNE = 7.0            # nutzbare innere und solare Gewinne [W/m² Wohnfläche] in der Heizzeit
WARTUNG_BESTAND = 250.0  # €/a für einen weiterbetriebenen Altkessel
SOWIESO = "Sowieso-Kosten [€/Einheit]"

# Kostenannahmen: Einheit, Fixkosten, spez. Kosten, Förderung %, Nutzungsdauer, Wartung %/a, Sowieso-Kosten
_K = kosten.INVEST
KOSTEN = {
    "Dachdämmung": ("m² Dach", 0.0, 250.0, 0.0, 40, 0.0, 170.0),
    "Fassadendämmung": ("m² Wand", 0.0, 200.0, 0.0, 40, 0.0, 100.0),
    "Fenstertausch": ("m² Fenster", 0.0, 700.0, 0.0, 30, 0.0, 550.0),
    "Kellerdeckendämmung": ("m² Decke", 0.0, 60.0, 0.0, 40, 0.0, 0.0),
    "Hülle Effizienzhaus 55": ("m² Wohnfl.", 0.0, 60.0, 0.0, 50, 0.0, 0.0),
    "Hülle Effizienzhaus 40": ("m² Wohnfl.", 0.0, 130.0, 0.0, 50, 0.0, 0.0),
    **{n: (_K[n][0], _K[n][1], _K[n][2], 0.0, _K[n][4], _K[n][5], 0.0)
       for n in ("Wärmepumpe Luft", "Wärmepumpe Erdreich", "Gasheizung", "Ölheizung", "Holzheizung",
                 "Photovoltaik", "Batteriespeicher", "Solarthermie")},
}


def kosten_df() -> pd.DataFrame:
    df = pd.DataFrame.from_dict(KOSTEN, orient="index", columns=kosten.SP + [SOWIESO])
    df.index.name = "Maßnahme"
    return df


def geometrie(flaeche: float, geschosse: int) -> dict:
    """Bauteilflächen [m²] eines freistehenden Hauses mit quadratischem Grundriss."""
    grund = flaeche / (0.8 * geschosse)                # Bruttogrundfläche je Geschoss
    fenster = 0.18 * flaeche
    wand = 4 * math.sqrt(grund) * 2.8 * geschosse - fenster
    return dict(wand=wand, dach=1.3 * grund, fenster=fenster, boden=grund, volumen=grund * 2.8 * geschosse)


def huelle(haus: dict, modus: str, combo: dict, ta: np.ndarray) -> dict:
    """Wärmeverlustkoeffizient H [kW/K], Heizgrenze [°C] und Auslegungs-Vorlauftemperatur [°C]."""
    if modus == "Neubau":
        spez, hg, vl = model.GEBAEUDESTANDARDS[NEUBAU[combo["huelle"]]]
        H = spez * haus["flaeche"] / np.clip(hg - ta, 0, None).sum()
        return dict(H=H, heizgrenze=hg, t_vl=vl)
    g, u0 = geometrie(haus["flaeche"], haus["geschosse"]), ALTER[haus["baualter"]]

    def h_von(saniert: dict) -> float:
        u = {b: (U_NEU[b] if saniert.get(b) else u0[b]) for b in MASSNAHMEN}
        ht = g["wand"] * u["wand"] + g["dach"] * u["dach"] + g["fenster"] * u["fenster"] + 0.5 * g["boden"] * u["boden"]
        ht += 0.05 * (g["wand"] + g["dach"] + g["fenster"] + g["boden"])           # Wärmebrücken
        return (ht + 0.34 * 0.5 * g["volumen"]) / 1000.0                           # + Lüftung (n = 0,5 1/h)

    H, H0 = h_von(combo), h_von({})
    hg = float(np.clip(20.0 - GEWINNE * haus["flaeche"] / 1000.0 / H, 10.0, 18.0))
    # vorhandene Heizkörper: nötige Übertemperatur sinkt mit der Heizlast (Exponent 1,3)
    t_vl = max(35.0, 25.0 + (u0["t_vl"] - 25.0) * (H / H0) ** (1 / 1.3))
    return dict(H=H, heizgrenze=hg, t_vl=t_vl)


def profile(wetter_h: dict, haus: dict, jahr: int) -> dict:
    """Stundenprofile, die nicht von der Variante abhängen."""
    idx = data.time_index(jahr)
    stunde = lambda x: x.reshape(-1, 4).mean(axis=1)
    ta = np.asarray(wetter_h["ta"], float)
    return dict(
        ta=ta, ta_eff=0.5 * ta + 0.5 * pd.Series(ta).rolling(24, min_periods=1).mean().values,
        pv=np.asarray(wetter_h["pv"], float), g=np.asarray(wetter_h["g"], float),
        strom=stunde(model.strom_profil(idx, haus["strom_kwh"])),
        ww=stunde(model.warmwasser_profil(idx, model.WARMWASSER_KWH_PERSON * haus["personen"])),
    )


def solarthermie(pr: dict, flaeche: float) -> np.ndarray:
    """Warmwasser-Restbedarf [kW] nach Solarthermie mit 300-l-Speicher (12 kWh)."""
    ww = pr["ww"]
    if flaeche <= 0:
        return ww
    dt = 50.0 - pr["ta"]
    ertrag = flaeche * np.clip(0.75 * pr["g"] - 3.5 * dt - 0.015 * dt**2, 0, None) / 1000.0
    rest, s = np.empty(8760), 0.0
    for t in range(8760):
        s = min(s * 0.995 + ertrag[t], 12.0)
        q = min(s, ww[t])
        s -= q
        rest[t] = ww[t] - q
    return rest


def batterie(netto: np.ndarray, kap: np.ndarray) -> np.ndarray:
    """Netzaustausch [kW] nach Batterie (Eigenverbrauch), vektorisiert über alle Varianten."""
    n = netto.shape[0]
    soc, eta, pmax, aus = np.zeros(n), math.sqrt(0.90), 0.5 * kap, np.empty_like(netto)
    for t in range(netto.shape[1]):
        x = netto[:, t]
        laden = np.minimum(np.minimum(np.clip(-x, 0, None), pmax), (kap - soc) / eta)
        entl = np.minimum(np.minimum(np.clip(x, 0, None), pmax), soc * eta)
        soc += laden * eta - entl / eta
        aus[:, t] = x + laden - entl
    return aus


def bewerte(combos: list[dict], haus: dict, modus: str, pr: dict, ann: dict) -> pd.DataFrame:
    """Energiebilanz und Annuitäten für eine Liste von Varianten.

    combo: dach/wand/fenster/boden (bool) bzw. huelle (Neubau), erzeuger, pv [kWp], bat [kWh], st [m²]
    ann: kosten (DataFrame), zins, preis/grund (dict je Energieträger), verguetung, co2_preis [€/t],
         tarif (Stundenpreise €/kWh oder None), ohnehin (Menge von Bauteilen)
    """
    kt, geo = ann["kosten"], geometrie(haus["flaeche"], haus["geschosse"])
    ww_rest = {a: solarthermie(pr, a) for a in {c["st"] for c in combos}}
    huellen, netto, zeilen = {}, np.empty((len(combos), 8760)), []
    for i, c in enumerate(combos):
        hk = tuple(c.get(b, False) for b in MASSNAHMEN) + (c.get("huelle"),)
        if hk not in huellen:
            h = huelle(haus, modus, c, pr["ta"])
            h["last"] = h["H"] * np.clip(h["heizgrenze"] - pr["ta_eff"], 0, None)
            huellen[hk] = h
        h, ww = huellen[hk], ww_rest[c["st"]]
        zeile, traeger, eta = ERZEUGER[c["erzeuger"]]
        end = dict(gas=0.0, oel=0.0, holz=0.0)
        el_wp = 0.0
        if traeger == "strom":
            cop = lambda ts: model.cop_waermepumpe(pr["ta"], ts, eta, 0.40, 6.5)
            el_wp = h["last"] / cop(model.vorlauftemperatur(pr["ta"], h["t_vl"])) + ww / cop(model.T_WARMWASSER)
        else:
            end[traeger] = float((h["last"] + ww).sum()) / eta
        netto[i] = pr["strom"] + el_wp - c["pv"] * pr["pv"]
        kw = math.ceil(float((h["last"] + ww).max()) * 2) / 2
        # Investitionen: (Kostenzeile, Größe, Bauteil für Sowieso-Abzug)
        pos = [(MASSNAHMEN[b], geo[b], b) for b in MASSNAHMEN if c.get(b)]
        if c.get("huelle", "GEG-Neubau") != "GEG-Neubau":
            pos.append((f"Hülle {c['huelle']}", haus["flaeche"], None))
        if zeile:
            pos.append((zeile, kw, None))
        pos += [(n, c[k], None) for n, k in (("Photovoltaik", "pv"), ("Batteriespeicher", "bat"),
                                              ("Solarthermie", "st")) if c[k] > 0]
        inv, foerd, kap, wart = 0.0, 0.0, 0.0, (0.0 if zeile else WARTUNG_BESTAND)
        for name, gr, bauteil in pos:
            a = kt.loc[name]
            spez = kosten._f(a["spez. Kosten [€/Einheit]"])
            if bauteil in ann.get("ohnehin", ()):
                spez = max(spez - kosten._f(a[SOWIESO]), 0.0)
            brutto = kosten._f(a["Fixkosten [€]"]) + spez * gr
            f = brutto * kosten._f(a["Förderung [%]"]) / 100.0
            inv += brutto; foerd += f
            kap += (brutto - f) * kosten.annuitaetenfaktor(ann["zins"], kosten._f(a["Nutzungsdauer [a]"]))
            wart += brutto * kosten._f(a["Wartung [%/a]"]) / 100.0
        zeilen.append(dict(c, H=h["H"] * 1000, t_vl=h["t_vl"], waerme=float(h["last"].sum()), wp_kw=kw,
                           el_wp=float(np.sum(el_wp)), invest=inv, foerderung=foerd, kapital=kap, wartung=wart,
                           **{f"end_{k}": v for k, v in end.items()}))
    df = pd.DataFrame(zeilen)
    kap_bat = df["bat"].values.astype(float)
    mit = kap_bat > 0
    if mit.any():
        netto[mit] = batterie(netto[mit], kap_bat[mit])
    bezug, einsp = np.clip(netto, 0, None), np.clip(-netto, 0, None)
    df["netzbezug"], df["einspeisung"] = bezug.sum(axis=1), einsp.sum(axis=1)
    p, g = ann["preis"], ann["grund"]
    strom = bezug @ ann["tarif"] if ann.get("tarif") is not None else df["netzbezug"] * p["strom"]
    df["energie"] = (strom + g["strom"] + df["end_gas"] * p["gas"] + (df["end_gas"] > 1) * g["gas"]
                     + df["end_oel"] * p["oel"] + df["end_holz"] * p["holz"])
    df["erloes"] = df["einspeisung"] * ann["verguetung"]
    df["co2"] = (df["netzbezug"] * CO2["strom"] + df["end_gas"] * CO2["gas"] + df["end_oel"] * CO2["oel"]
                 + df["end_holz"] * CO2["holz"]) / 1000.0                                   # t/a
    df["co2_kosten"] = df["co2"] * ann["co2_preis"]
    df["ausgaben"] = df["kapital"] + df["wartung"]                     # annuitätische Ausgaben
    df["laufend"] = df["energie"] - df["erloes"] + df["co2_kosten"]    # Energie- und CO2-Kosten
    df["betrieb"] = df["wartung"] + df["laufend"]                      # jährliche Betriebskosten
    df["gesamt"] = df["kapital"] + df["betrieb"]
    return df


def zeitreihen(c: dict, haus: dict, modus: str, pr: dict, jahr: int) -> tuple[pd.DataFrame, list[dict]]:
    """Stundenreihen einer Variante für das Energieflussbild (Spalten wie in fluss.html)
    und die Kesselliste dafür. Gleiche Rechnung wie in bewerte()."""
    h = huelle(haus, modus, c, pr["ta"])
    last = h["H"] * np.clip(h["heizgrenze"] - pr["ta_eff"], 0, None)
    ww = solarthermie(pr, c["st"])
    _, traeger, eta = ERZEUGER[c["erzeuger"]]
    null = np.zeros(8760)
    el_wp = q_wp = q_k = fuel = null
    if traeger == "strom":
        cop = lambda ts: model.cop_waermepumpe(pr["ta"], ts, eta, 0.40, 6.5)
        el_wp = last / cop(model.vorlauftemperatur(pr["ta"], h["t_vl"])) + ww / cop(model.T_WARMWASSER)
        q_wp = last + ww
    else:
        q_k = last + ww
        fuel = q_k / eta
    netto = pr["strom"] + el_wp - c["pv"] * pr["pv"]
    laden, entl, soc = np.zeros(8760), np.zeros(8760), np.zeros(8760)
    if c["bat"] > 0:
        e, wg, pmax = 0.0, math.sqrt(0.90), 0.5 * c["bat"]
        for t in range(8760):
            x = netto[t]
            laden[t] = min(max(-x, 0.0), pmax, (c["bat"] - e) / wg)
            entl[t] = min(max(x, 0.0), pmax, e * wg)
            e += laden[t] * wg - entl[t] / wg
            soc[t] = e
    netz = netto + laden - entl
    df = pd.DataFrame(dict(
        t_aussen=pr["ta"], pv=c["pv"] * pr["pv"], haushalt=pr["strom"], el_wp=el_wp, q_wp=q_wp,
        netzbezug=np.clip(netz, 0, None), einspeisung=np.clip(-netz, 0, None), bat_laden=laden,
        bat_entladen=entl, bat_soc=soc, q_kessel=q_k, brennstoff=fuel, q_solar=pr["ww"] - ww,
        q_raum=last, q_ww=pr["ww"]), index=data.time_index(jahr)[::4])
    stoff = {"gas": "Erdgas", "oel": "Heizöl", "holz": "Pellets"}.get(traeger, "")
    return df, [dict(name=c["erzeuger"], brennstoff=stoff, q="q_kessel", fuel="brennstoff")]


def varianten(modus: str, erzeuger: list[str], pv_max: float, st_flaeche: float) -> list[dict]:
    """Alle Kombinationen für die Optimierung."""
    pv = sorted({0.0, *[x for x in (4.0, 8.0, 12.0, 16.0, 20.0) if x <= pv_max], float(pv_max)})
    bat, st = (0.0, 5.0, 10.0), sorted({0.0, float(st_flaeche)})
    if modus == "Neubau":
        return [dict(huelle=h, erzeuger=e, pv=p, bat=b, st=s)
                for h, e, p, b, s in itertools.product(NEUBAU, erzeuger, pv, bat, st) if not (b > 0 and p == 0)]
    return [dict(zip(MASSNAHMEN, m), erzeuger=e, pv=p, bat=b, st=s)
            for m, e, p, b, s in itertools.product(itertools.product((False, True), repeat=4), erzeuger, pv, bat, st)
            if not (b > 0 and p == 0)]


def beitraege(combo: dict, ref: dict, haus: dict, modus: str, pr: dict, ann: dict) -> pd.DataFrame:
    """Je Maßnahme der Variante: annuitätische Ausgabe und Einsparung, jeweils gegenüber derselben
    Variante ohne diese Maßnahme (übrige Maßnahmen bleiben)."""
    namen = {**MASSNAHMEN, "huelle": "Hüllstandard", "erzeuger": "Wärmeerzeuger", "pv": "Photovoltaik",
             "bat": "Batteriespeicher", "st": "Solarthermie"}
    keys = [k for k in namen if k in combo and combo[k] != ref.get(k)]
    if not keys:
        return pd.DataFrame(columns=["Maßnahme", "Ausgabe", "Einsparung", "Netto"])
    ohne = [dict(combo, **{k: ref[k]}) for k in keys]
    # ohne PV keine Batterie
    ohne = [dict(o, bat=0.0) if o["pv"] == 0 else o for o in ohne]
    e = bewerte([combo] + ohne, haus, modus, pr, ann)
    z = []
    for i, k in enumerate(keys, start=1):
        bez = namen[k] if k not in ("huelle", "erzeuger") else f"{namen[k]}: {combo[k]}"
        aus, ein = e.loc[0, "ausgaben"] - e.loc[i, "ausgaben"], e.loc[i, "laufend"] - e.loc[0, "laufend"]
        z.append([bez, aus, ein, ein - aus])
    return pd.DataFrame(z, columns=["Maßnahme", "Ausgabe", "Einsparung", "Netto"])
