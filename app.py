"""
app.py – Flask-applikation för Svenska Hockeymatcher.

Exponerar:
  GET /           → Laddar och renderar dagens matcher
  GET /reload     → Rensar cachen och omdirigerar till /
"""

import logging
from datetime import date

from flask import Flask, render_template, redirect, url_for, jsonify

from scraper import fetch_todays_matches, group_matches_by_series, clear_cache

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Hämtar dagens matcher (med cache) och renderar startsidan."""
    today = date.today()
    today_display = today.strftime("%A %d %B %Y")  # t.ex. "Sunday 29 March 2026"
    today_iso = today.strftime("%Y-%m-%d")

    matches, fetched_at, error = fetch_todays_matches()
    grouped = group_matches_by_series(matches) if matches else {}

    total_matches = len(matches)
    played = sum(1 for m in matches if m.status == "Färdigspelad")
    upcoming = total_matches - played

    return render_template(
        "index.html",
        grouped=grouped,
        today_display=today_display,
        today_iso=today_iso,
        fetched_at=fetched_at,
        error=error,
        total_matches=total_matches,
        played=played,
        upcoming=upcoming,
    )


@app.route("/api/matches")
def api_matches():
    """JSON API för live-uppdateringar av matcher. Förbi-cache för att få senaste data."""
    matches, fetched_at, error = fetch_todays_matches(force_refresh=True)
    grouped = group_matches_by_series(matches) if matches else {}

    # Konvertera Match-dataclass-objekt till dict
    grouped_dict = {}
    for series, match_list in grouped.items():
        grouped_dict[series] = [{
            "series": m.series,
            "date": m.date,
            "time": m.time,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "result": m.result,
            "venue": m.venue,
            "round_info": m.round_info,
            "status": m.status,
        } for m in match_list]

    return jsonify({
        "matches": grouped_dict,
        "fetched_at": fetched_at,
        "error": error,
    })


@app.route("/reload")
def reload_matches():
    """Rensar cachen och tvingar en ny hämtning av matchdata."""
    clear_cache()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Startpunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
