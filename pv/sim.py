"""Vereinfachte Jahressimulation PV + Haushalt + Batterie (stündlich, 8760 h).

Wetter: synthetisch für Ingolstadt (48,8° N) – Sonnenstand exakt, klarer Himmel nach Haurwitz,
Bewölkung als zufälliger Tages-Klarheitsindex mit typischen Monatsmitteln für Süddeutschland.
Der Ertrag wird auf 1000 kWh/kWp bei Süd-Ausrichtung und 30° Neigung kalibriert.
Last: synthetisches Haushaltsprofil (Werktag/Wochenende, Winter höher), optional E-Auto und
Wärmepumpe. Alles bewusst einfach und reproduzierbar (fester Zufalls-Seed).
"""

from __future__ import annotations

import numpy as np

LAT, LON = 48.77, 11.42
HOURS = 8760
K_MONAT = [0.33, 0.43, 0.50, 0.57, 0.59, 0.62, 0.63, 0.61, 0.56, 0.46, 0.34, 0.29]
MONAT_TAG = np.repeat(np.arange(12), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def wetter(seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    t = np.arange(HOURS)
    doy = t // 24 + 1
    hour = t % 24 + 0.5                                   # Stundenmitte, MEZ (UTC+1)
    decl = np.radians(23.45) * np.sin(2 * np.pi * (284 + doy) / 365)
    B = 2 * np.pi * (doy - 81) / 364
    eot = 9.87 * np.sin(2 * B) - 7.53 * np.cos(B) - 1.5 * np.sin(B)
    st_ = hour + (4 * (LON - 15) + eot) / 60
    ha = np.radians(15 * (st_ - 12))
    phi = np.radians(LAT)
    cosz = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(ha)
    cosz = np.clip(cosz, -1, 1)
    az = np.arctan2(np.sin(ha), np.cos(ha) * np.sin(phi) - np.tan(decl) * np.cos(phi))  # 0 = Süd, W positiv
    clear = np.where(cosz > 0.01, 1098 * cosz * np.exp(-0.057 / np.maximum(cosz, 0.01)), 0.0)

    k_tag = np.clip(rng.normal(np.array(K_MONAT)[MONAT_TAG], 0.22), 0.08, 1.0)
    k = np.clip(np.repeat(k_tag, 24) + rng.normal(0, 0.07, HOURS), 0.05, 1.0)
    ghi = clear * k
    fd = np.clip(1.0 - 1.13 * (k - 0.22), 0.12, 1.0)
    dhi = ghi * fd
    dni = np.where(cosz > 0.087, (ghi - dhi) / np.maximum(cosz, 0.087), 0.0)

    t_tag = rng.normal(0, 2.5, 365)
    temp = 9 - 10 * np.cos(2 * np.pi * (doy - 20) / 365) + 4 * np.sin(2 * np.pi * (hour - 9) / 24) + np.repeat(t_tag, 24)
    return dict(cosz=cosz, az=az, ghi=ghi, dhi=dhi, dni=dni, temp=temp, doy=doy, hour=t % 24)


def pv_profil(w: dict, neigung: float, azimut: float) -> np.ndarray:
    """kW je kWp (Wechselstrom), azimut 0 = Süd, −90 = Ost, +90 = West."""
    def roh(beta_deg, gamma_deg):
        b, g = np.radians(beta_deg), np.radians(gamma_deg)
        sinz = np.sqrt(np.clip(1 - w["cosz"] ** 2, 0, 1))
        cos_t = w["cosz"] * np.cos(b) + sinz * np.sin(b) * np.cos(w["az"] - g)
        poa = (np.maximum(cos_t, 0) * w["dni"] + w["dhi"] * (1 + np.cos(b)) / 2
               + w["ghi"] * 0.2 * (1 - np.cos(b)) / 2)
        poa = np.where(w["cosz"] > 0, poa, 0)
        tz = w["temp"] + 0.03 * poa
        return poa / 1000 * 0.88 * (1 - 0.004 * (tz - 25))
    kal = 1000 / roh(30, 0).sum()
    return np.clip(roh(neigung, azimut) * kal, 0, None)


H0_WERKTAG = np.array([0.55, 0.45, 0.40, 0.40, 0.42, 0.55, 0.95, 1.15, 0.85, 0.65, 0.60, 0.70,
                       0.85, 0.75, 0.65, 0.65, 0.80, 1.20, 1.65, 1.75, 1.60, 1.35, 1.05, 0.75])
H0_WOCHENENDE = np.array([0.65, 0.50, 0.42, 0.40, 0.40, 0.45, 0.55, 0.75, 1.00, 1.05, 1.05, 1.20,
                          1.25, 1.00, 0.85, 0.85, 0.95, 1.20, 1.55, 1.65, 1.50, 1.30, 1.05, 0.80])


def lastprofil(w: dict, haushalt_kwh: float, ev_kwh: float, ev_mittag: bool, wp_kwh: float,
               seed: int = 11) -> dict:
    rng = np.random.default_rng(seed)
    doy, hour = w["doy"], w["hour"]
    wochentag = (doy - 1 + 2) % 7                          # 1.1.2025 = Mittwoch
    form = np.where(wochentag >= 5, H0_WOCHENENDE[hour], H0_WERKTAG[hour])
    saison = 1 + 0.2 * np.cos(2 * np.pi * (doy - 15) / 365)
    hh = form * saison * np.clip(rng.normal(1, 0.15, HOURS), 0.6, 1.5)
    hh = hh / hh.sum() * haushalt_kwh

    ev = np.zeros(HOURS)
    if ev_kwh > 0:
        if ev_mittag:                                       # PV-geführt: 10–16 Uhr, an 5 von 7 Tagen
            maske = (hour >= 10) & (hour < 16) & (wochentag % 7 != 1) & (wochentag % 7 != 3)
        else:                                               # abends nach der Arbeit: 18–22 Uhr
            maske = (hour >= 18) & (hour < 22)
        ev[maske] = 1.0
        ev = ev / ev.sum() * ev_kwh

    wp = np.zeros(HOURS)
    if wp_kwh > 0:
        bedarf = np.maximum(0, 15 - w["temp"]) + 0.15     # Heizgradstunden + Warmwasser
        wp = bedarf / bedarf.sum() * wp_kwh
    return dict(haushalt=hh, ev=ev, wp=wp, gesamt=hh + ev + wp)


def simuliere(pv: np.ndarray, last: np.ndarray, kap: float, wirk: float = 0.90, c_rate: float = 0.5) -> dict:
    eta = np.sqrt(wirk)
    pmax = kap * c_rate
    direkt = np.minimum(pv, last)
    ueber = pv - direkt
    defizit = last - direkt
    lade = np.zeros(HOURS); entl = np.zeros(HOURS); soc = np.zeros(HOURS)
    s = 0.0
    if kap > 0:
        for h in range(HOURS):
            u, d = ueber[h], defizit[h]
            if u > 0:
                c = min(u, pmax, (kap - s) / eta)
                lade[h] = c; s += c * eta
            elif d > 0:
                e = min(d, pmax, s * eta)
                entl[h] = e; s -= e / eta
            soc[h] = s
    einsp = ueber - lade
    bezug = defizit - entl
    verlust = lade.sum() - entl.sum() - s
    return dict(direkt=direkt, lade=lade, entl=entl, einsp=einsp, bezug=bezug, soc=soc,
                verlust=max(verlust, 0.0), pv=pv, last=last)


def kennzahlen(r: dict, preis: float, verguetung: float, kwp: float, kap: float,
               invest_kwp: float, invest_kwh: float) -> dict:
    pv_sum, last_sum = r["pv"].sum(), r["last"].sum()
    ev_ = r["direkt"].sum() + r["lade"].sum()
    eigen = ev_ / pv_sum if pv_sum > 0 else 0.0
    autark = 1 - r["bezug"].sum() / last_sum if last_sum > 0 else 0.0
    kosten_ohne = last_sum * preis
    kosten_mit = r["bezug"].sum() * preis - r["einsp"].sum() * verguetung
    ersparnis = kosten_ohne - kosten_mit
    invest = kwp * invest_kwp + kap * invest_kwh
    amort = invest / ersparnis if ersparnis > 0 else float("inf")
    return dict(pv=pv_sum, last=last_sum, eigen=eigen, autark=autark, bezug=r["bezug"].sum(),
                einsp=r["einsp"].sum(), ersparnis=ersparnis, invest=invest, amort=amort)
