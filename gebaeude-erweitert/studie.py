"""Studie: Steigerung der Jahresarbeitszahl (JAZ) einer Luft-Wärmepumpe durch
  (1) einen Kachelofen, der gezielt in kalten Stunden Wärme liefert,
  (2) einen Wasser-Pufferspeicher, der in warmen Stunden beladen wird,
  (3) die thermische Masse des Gebäudes (Überheizen innerhalb eines Komfortbands).

Lineares Programm mit perfekter Voraussicht, Stundenauflösung über ein Jahr
(8760 h, zyklisch). Zielfunktion: minimaler Strombedarf der Wärmepumpe.

Gebäude als 1R1C-Modell in der Übertemperatur x = T_Raum − T_Soll:
    C·(x[t+1] − x[t]) = q_dir + q_vor + q_ent + q_ofen − L[t] − H·x[t] − q_lueft
mit L[t] = max(0, H·(T_Heizgrenze − T_außen[t])) (Last bei Solltemperatur, innere/solare
Gewinne stecken in der Heizgrenze), 0 ≤ x ≤ Komfortband.

Wärmepumpe, drei Betriebsarten mit je eigenem COP (alle zeitabhängig bekannt):
    q_dir  direktes Heizen bis höchstens zur aktuellen Last, Vorlauf nach Heizkurve
    q_vor  Vorheizen der Gebäudemasse, Vorlauf + dt_vor
    q_lad  Laden des Pufferspeichers, Vorlauf (48-h-Maximum) + Speicherspreizung
Warmwasser wird als feste Last bei 55 °C mitgeführt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog

import data
import model

N = 8760

# Wirksame Wärmekapazität je m² Nutzfläche [Wh/(m²K)] nach EN ISO 13790, Tab. 12
MASSE = {"sehr leicht": 22.2, "leicht": 30.6, "mittel": 45.8, "schwer": 72.2, "sehr schwer": 102.8}

# Wärmeabgabe eines Kachelofens nach dem Abbrand, Anteil je Stunde (12 h)
OFEN_KERN = np.array([0.5, 1.0, 1.0, 0.95, 0.85, 0.75, 0.65, 0.55, 0.45, 0.35, 0.25, 0.15])
OFEN_KERN = OFEN_KERN / OFEN_KERN.sum()

DEFAULTS = dict(
    flaeche=140.0, personen=3, spez=80.0, heizgrenze=14.0, t_vorlauf=45.0, ww_kwh_person=600.0,
    masse=45.8,            # Wh/(m²K)
    band=0.0,              # zulässige Übertemperatur des Raums [K]
    vorheizen=False,       # darf die WP die Gebäudemasse aktiv vorheizen?
    dt_vor=5.0,            # Vorlaufzuschlag beim Vorheizen [K]
    sp_liter=0.0, sp_dt=10.0, sp_verlust=0.3,      # Puffer: Volumen, Spreizung [K], Verlust [%/h]
    ko_budget=0.0,         # max. Ofenwärme pro Jahr [kWh]
    ko_tag_max=40.0,       # max. Ofenwärme pro Tag [kWh] (ca. 2 Abbrände)
    ko_gezielt=True,       # True: Optimierer wählt die Abbrände; False: jeden Abend 18 Uhr
    ko_t_max=5.0,          # Ofen nur an Tagen mit Tagesmitteltemperatur bis zu diesem Wert [°C]
    ko_von=6, ko_bis=22,   # Abbrand nur in diesen Stunden möglich
    ko_eta=0.80,
    wp_quelle="Luft", wp_guete=0.40, wp_cop_max=6.5, wp_faktor=1.2,
)


def vorbereiten(t_aussen: np.ndarray, p: dict, jahr: int = 2019) -> dict:
    """Zeitreihen und Kenngrößen des Gebäudes und der Wärmepumpe."""
    ta = np.asarray(t_aussen, float)
    gradstunden = np.clip(p["heizgrenze"] - ta, 0, None).sum()
    H = p["spez"] * p["flaeche"] / gradstunden                    # kW/K
    L = H * (p["heizgrenze"] - ta)                                # kW, kann negativ sein
    idx15 = data.time_index(jahr)
    ww = model.warmwasser_profil(idx15, p["ww_kwh_person"] * p["personen"]).reshape(-1, 4).mean(axis=1)
    t_vl = model.vorlauftemperatur(ta, p["t_vorlauf"])
    cop = lambda ts: model.cop_waermepumpe(ta, ts, p["wp_quelle"], p["wp_guete"], p["wp_cop_max"])
    # Speicher muss die höchste Vorlauftemperatur der umliegenden 48 h liefern können
    t_vl_max = pd.Series(t_vl).rolling(48, center=True, min_periods=1).max().values
    return dict(
        ta=ta, H=H, L=L, ww=ww, t_vl=t_vl,
        C=p["masse"] * p["flaeche"] / 1000.0,                     # kWh/K
        cop_dir=cop(t_vl), cop_vor=cop(t_vl + p["dt_vor"]), cop_lad=cop(t_vl_max + p["sp_dt"]),
        cop_ww=cop(model.T_WARMWASSER),
        p_wp=p["wp_faktor"] * float((np.clip(L, 0, None) + ww).max()),
        sp_kap=p["sp_liter"] * 1.163e-3 * p["sp_dt"],             # kWh
    )


def loese(t_aussen: np.ndarray, params: dict | None = None, jahr: int = 2019,
          preis: np.ndarray | None = None, holzpreis: float = 0.0) -> tuple[pd.DataFrame, dict]:
    """Löst das LP. Rückgabe: Stundenzeitreihen und Kennzahlen.

    preis=None (Paper 1): minimaler Strombedarf. Mit preis (8760 Stundenwerte, €/kWh Strom) und
    holzpreis (€/kWh Brennstoff): minimale Betriebskosten (Paper 2).
    """
    p = {**DEFAULTS, **(params or {})}
    v = vorbereiten(t_aussen, p, jahr)
    n = N
    H, C, L, ww = v["H"], v["C"], v["L"], v["ww"]
    Lp = np.clip(L, 0, None)
    stunde = np.arange(n) % 24
    tag = np.arange(n) // 24

    # Variablenblöcke: q_dir, q_vor, q_lad, q_ent, s, x, f (Abbrand), lueft
    DIR, VOR, LAD, ENT, S, X, F, LU = (slice(i * n, (i + 1) * n) for i in range(8))
    nv = 8 * n
    I = sparse.identity(n, format="csr")
    vor = sparse.csr_matrix((np.ones(n), (np.arange(n), (np.arange(n) + 1) % n)), shape=(n, n))  # x[t+1]
    Z = sparse.csr_matrix((n, n))
    # Ofen: Wärmeabgabe = Faltung der Abbrände mit dem Kern (zyklisch)
    zeilen = np.concatenate([(np.arange(n) + k) % n for k in range(len(OFEN_KERN))])
    spalten = np.tile(np.arange(n), len(OFEN_KERN))
    werte = np.repeat(OFEN_KERN, n)
    W = sparse.csr_matrix((werte, (zeilen, spalten)), shape=(n, n))

    # Gleichungen: Raum und Speicher
    raum = sparse.hstack([-I, -I, Z, -I, Z, C * vor - (C - H) * I, -W, I])
    v_sp = p["sp_verlust"] / 100.0
    speicher = sparse.hstack([Z, Z, -I, I, vor - (1 - v_sp) * I, Z, Z, Z])
    A_eq = sparse.vstack([raum, speicher], format="csr")
    # Überschüssige Gewinne (L < 0) werden weggelüftet/verschattet und nicht eingespeichert:
    # so bleibt der Wärmebedarf der Referenz unabhängig von Masse und Komfortband.
    b_eq = np.concatenate([-Lp, np.zeros(n)])

    # Ungleichungen: WP-Leistung, Ofen je Tag, Ofen je Jahr
    leistung = sparse.hstack([I, I, I, Z, Z, Z, Z, Z])
    T = sparse.csr_matrix((np.ones(n), (tag, np.arange(n))), shape=(365, n))
    Z365 = sparse.csr_matrix((365, n))
    ofen_tag = sparse.hstack([Z365, Z365, Z365, Z365, Z365, Z365, T, Z365])
    jahr_zeile = np.zeros((1, nv)); jahr_zeile[0, F] = 1.0
    A_ub = sparse.vstack([leistung, ofen_tag, sparse.csr_matrix(jahr_zeile)], format="csr")
    b_ub = np.concatenate([np.clip(v["p_wp"] - ww, 0, None), np.full(365, p["ko_tag_max"]),
                           [p["ko_budget"]]])

    lb = np.zeros(nv); ub = np.zeros(nv)
    ub[DIR] = Lp + 1e-6      # kleine Toleranz, sonst meldet der Presolve fälschlich Unlösbarkeit
    ub[VOR] = v["p_wp"] if (p["vorheizen"] and p["band"] > 0) else 0.0
    ub[LAD] = v["p_wp"] if v["sp_kap"] > 0 else 0.0
    ub[ENT] = 10 * v["p_wp"] if v["sp_kap"] > 0 else 0.0
    ub[S] = v["sp_kap"]
    ub[X] = p["band"]
    ub[LU] = np.inf
    # Ofen nur an kalten Tagen (Tagesmittel der Außentemperatur <= ko_t_max)
    kalt = np.repeat(v["ta"].reshape(365, 24).mean(axis=1) <= p["ko_t_max"], 24)
    if p["ko_budget"] > 0 and kalt.any():
        if p["ko_gezielt"]:
            ub[F] = np.where(kalt & (stunde >= p["ko_von"]) & (stunde < p["ko_bis"]), p["ko_tag_max"], 0.0)
        else:   # ungezielt: an jedem kalten Tag abends um 18 Uhr gleich viel (höchstens ko_tag_max)
            je_tag = min(p["ko_budget"] / (kalt.sum() / 24), p["ko_tag_max"])
            fest = np.where(kalt & (stunde == 18), je_tag, 0.0)
            lb[F] = fest; ub[F] = fest
            b_ub[-1] = 1e9

    c = np.zeros(nv)
    c[DIR] = 1 / v["cop_dir"]; c[VOR] = 1 / v["cop_vor"]; c[LAD] = 1 / v["cop_lad"]
    c[LU] = 1e-4; c[F] = 1e-6; c[ENT] = 1e-6
    if preis is not None:       # Kostenminimierung: Strom mit Stundenpreis, Holz mit Brennstoffpreis
        pr = np.asarray(preis, float)
        c[DIR] *= pr; c[VOR] *= pr; c[LAD] *= pr
        c[F] += holzpreis / p["ko_eta"]
        # Wärme wird nicht absichtlich weggelüftet, auch nicht bei negativen Preisen
        c[LU] = max(1e-4, 1e-4 - float((pr / v["cop_vor"]).min()), 1e-4 - float((pr / v["cop_lad"]).min()))

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=np.column_stack([lb, ub]),
                  method="highs")
    if res.status != 0:
        raise RuntimeError(f"LP nicht gelöst: {res.message}")
    z = res.x
    q_dir, q_vor, q_lad, q_ent = z[DIR], z[VOR], z[LAD], z[ENT]
    q_ofen = W @ z[F]
    el_heiz = q_dir / v["cop_dir"] + q_vor / v["cop_vor"] + q_lad / v["cop_lad"]
    el_ww = ww / v["cop_ww"]
    idx = pd.date_range(f"{jahr}-01-01", periods=n, freq="h") if jahr % 4 else data.time_index(jahr)[::4]
    ts = pd.DataFrame({
        "t_aussen": v["ta"], "last": Lp, "ww": ww, "q_dir": q_dir, "q_vor": q_vor, "q_lad": q_lad,
        "q_ent": q_ent, "sp_stand": z[S], "x": z[X], "abbrand": z[F], "q_ofen": q_ofen, "lueft": z[LU],
        "el_heiz": el_heiz, "el_ww": el_ww, "cop_dir": v["cop_dir"], "cop_lad": v["cop_lad"],
        "cop_vor": v["cop_vor"], "t_vl": v["t_vl"],
    }, index=idx)

    q_wp_heiz = float((q_dir + q_vor + q_lad).sum())
    k = dict(
        H=H * 1000, C=C, p_wp=v["p_wp"], sp_kap=v["sp_kap"],
        waermebedarf=float(Lp.sum()), ww=float(ww.sum()),
        q_wp_heiz=q_wp_heiz, el_heiz=float(el_heiz.sum()), el_ww=float(el_ww.sum()),
        q_dir=float(q_dir.sum()), q_vor=float(q_vor.sum()), q_lad=float(q_lad.sum()),
        q_ofen=float(q_ofen.sum()), holz=float(z[F].sum()) / p["ko_eta"], lueft=float(z[LU].sum()),
        x_mittel=float(z[X].mean()), el_max=float((el_heiz + el_ww).max()),
        ofentage=int((z[F].reshape(365, 24).sum(axis=1) > 0.01).sum()), kalte_tage=int(kalt.sum() / 24),
    )
    k["el"] = k["el_heiz"] + k["el_ww"]
    k["jaz_heiz"] = k["q_wp_heiz"] / k["el_heiz"] if k["el_heiz"] > 0 else float("nan")
    k["jaz"] = (k["q_wp_heiz"] + k["ww"]) / k["el"] if k["el"] > 0 else float("nan")
    # mittlere Außentemperatur, gewichtet mit der Wärmeabgabe der WP bzw. des Ofens
    wq = q_dir + q_vor + q_lad
    k["t_wp"] = float((v["ta"] * wq).sum() / wq.sum()) if wq.sum() > 0 else float("nan")
    k["t_ofen"] = float((v["ta"] * q_ofen).sum() / q_ofen.sum()) if q_ofen.sum() > 1e-6 else float("nan")
    k["q_ent"] = float(q_ent.sum())
    k["p_el_max"] = float((el_heiz + el_ww).max())
    return ts, k
