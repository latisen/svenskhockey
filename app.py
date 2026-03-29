"""
app.py – Flask-applikation för Svenska Hockeymatcher.

Exponerar:
  GET /           → Laddar och renderar dagens matcher
  GET /reload     → Rensar cachen och omdirigerar till /
"""

import logging
from datetime import date

from flask import Flask, render_template, redirect, url_for, jsonify, request

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
    """Hämtar matcher för valt datum och renderar startsidan."""
    from datetime import timedelta
    
    # Hämta datumsparameter från URL, annars använd idag
    selected_date = request.args.get("date")
    
    today = date.today()
    if selected_date:
        try:
            # Validera datumsformat
            selected = date.fromisoformat(selected_date)
            today_display = selected.strftime("%A %d %B %Y")
            today_iso = selected.strftime("%Y-%m-%d")
        except ValueError:
            # Ogiltigt datum, använd idag
            today_display = today.strftime("%A %d %B %Y")
            today_iso = today.strftime("%Y-%m-%d")
    else:
        today_display = today.strftime("%A %d %B %Y")
        today_iso = today.strftime("%Y-%m-%d")

    # Beräkna föregående och nästa datum för navigering
    selected_obj = date.fromisoformat(today_iso)
    prev_date = (selected_obj - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (selected_obj + timedelta(days=1)).strftime("%Y-%m-%d")

    matches, fetched_at, error = fetch_todays_matches(target_date=today_iso)
    grouped = group_matches_by_series(matches) if matches else {}

    total_matches = len(matches)
    played = sum(1 for m in matches if m.status == "Färdigspelad")
    upcoming = total_matches - played

    return render_template(
        "index.html",
        grouped=grouped,
        today_display=today_display,
        today_iso=today_iso,
        prev_date=prev_date,
        next_date=next_date,
        fetched_at=fetched_at,
        error=error,
        total_matches=total_matches,
        played=played,
        upcoming=upcoming,
    )


@app.route("/api/matches")
def api_matches():
    """JSON API för live-uppdateringar av matcher. Förbi-cache för att få senaste data."""
    # Hämta datumsparameter
    selected_date = request.args.get("date")
    
    matches, fetched_at, error = fetch_todays_matches(force_refresh=True, target_date=selected_date)
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
    selected_date = request.args.get("date")
    clear_cache()
    if selected_date:
        return redirect(url_for("index", date=selected_date))
    return redirect(url_for("index"))


@app.route("/api/match-details")
def api_match_details():
    """
    Hämtar detaljerad information om en match.
    
    Query-parametrar:
      - home_team: Hemmalag
      - away_team: Bortalag
      - date: Datum (YYYY-MM-DD)
      - time: Tid (HH:MM)
    """
    from match_finder import find_match_id, get_match_details
    
    home_team = request.args.get("home_team", "").strip()
    away_team = request.args.get("away_team", "").strip()
    match_date = request.args.get("date", "").strip()
    match_time = request.args.get("time", "").strip()
    
    if not all([home_team, away_team, match_date, match_time]):
        return jsonify({"error": "Missing required parameters"}), 400
    
    try:
        # Söka efter match-ID
        match_id = find_match_id(home_team, away_team, match_date, match_time)
        if not match_id:
            return jsonify({"error": "Could not find match"}), 404
        
        # Hämta matchdetaljer
        details = get_match_details(match_id)
        if not details:
            return jsonify({"error": "Could not fetch match details"}), 404
        
        return jsonify(details)
    
    except Exception as e:
        logger.error(f"Error in match details API: {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Startpunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
