@echo off
echo Starting Dashboard Server...
echo The dashboard will automatically open in your web browser.
echo Do NOT close this window while you are viewing the dashboard.
start "" "http://localhost:8000/dashboard.html"
python -m http.server 8000
