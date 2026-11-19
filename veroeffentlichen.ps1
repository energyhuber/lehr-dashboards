# Veröffentlicht den aktuellen Stand des Betz-Dashboards auf GitHub.
# Streamlit Community Cloud übernimmt die Änderung danach automatisch (1–2 Minuten).
#
# Aufruf:  .\veroeffentlichen.ps1 "Kurze Beschreibung der Änderung"

param([string]$Nachricht = "Aktualisierung Dashboard")

Set-Location $PSScriptRoot

git add -A
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Keine Änderungen – nichts zu veröffentlichen."
    exit 0
}

git commit -m $Nachricht
if ($LASTEXITCODE -ne 0) { Write-Error "Commit fehlgeschlagen."; exit 1 }

git push
if ($LASTEXITCODE -ne 0) { Write-Error "Push fehlgeschlagen."; exit 1 }

Write-Host "Veröffentlicht. Die App aktualisiert sich in 1–2 Minuten."
