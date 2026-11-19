# Lehr-Dashboards Energiesysteme

Interaktive Streamlit-Dashboards für die Lehre an der Technischen Hochschule Ingolstadt.
Jeder Unterordner ist eine eigenständige App mit eigener `requirements.txt`.

| Dashboard | Online | Ordner |
|---|---|---|
| Betz-Gesetz (Energieentnahme aus dem Wind) und Auftriebsläufer | https://betz-gesetz.streamlit.app | [`betz/`](betz/) |
| Gebäudeenergietechnik: Jahresbilanz, typische Wochen, Auslegung | https://gebaeudeenergie.streamlit.app | [`gebaeude/`](gebaeude/) |
| Photovoltaik: pn-Übergang, Photon → Strom, Kennlinie & MPP-Tracker, Auslegung mit/ohne Speicher, Energieflüsse | *(noch nicht online)* | [`pv/`](pv/) |
| Gebäudeenergietechnik plus: Kosten, Studie JAZ, flexible Strompreise, optimierte Auslegung | https://gebaeudeenergie-plus.streamlit.app | [`gebaeude-erweitert/`](gebaeude-erweitert/) |

## Lokal starten

```bash
pip install -r betz/requirements.txt
streamlit run betz/app.py
```

## Online (Streamlit Community Cloud)

Jede App wird in Streamlit Cloud aus diesem Repo angelegt, Branch `main`, Datei z. B. `betz/app.py`.
Jeder Push auf `main` aktualisiert alle Apps automatisch.
