# Lehr-Dashboards Energiesysteme

Interaktive Streamlit-Dashboards für die Lehre an der Technischen Hochschule Ingolstadt.
Jeder Unterordner ist eine eigenständige App mit eigener `requirements.txt`.

| Ordner | Inhalt |
|---|---|
| [`betz/`](betz/) | Betz-Gesetz (Energieentnahme aus dem Wind) und Auftriebsläufer |
| [`gebaeude/`](gebaeude/) | Gebäudeenergietechnik: Jahresbilanz, typische Wochen, Auslegung |
| [`gebaeude-erweitert/`](gebaeude-erweitert/) | Gebäudeenergietechnik erweitert: Kosten, Studie JAZ, flexible Strompreise, optimierte Auslegung |

## Lokal starten

```bash
pip install -r betz/requirements.txt
streamlit run betz/app.py
```

## Online (Streamlit Community Cloud)

Jede App wird in Streamlit Cloud aus diesem Repo angelegt, Branch `main`, Datei z. B. `betz/app.py`.
Jeder Push auf `main` aktualisiert alle Apps automatisch.
