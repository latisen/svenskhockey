"""
scraper.py – Hämtar och parsar dagens ishockeymatcher från stats.swehockey.se.

Swehockey-sidan (GamesByDate) returnerar alltid dagens datum. Strukturen är:
  <table class="tblContent">
    <tr>  ← rubrikrad med datum
    <tr>  ← kolumnrubriker (Group/Time, Game, Result, Venue)
    <tr>  ← serienamnsrad: <td colspan="5"><a href="...">Serienamn</a></td>
    <tr>  ← matchrad: 4 celler (tid, "Hemmalag - Bortalag\nOmgånginfo", resultat, arena)
    ...
  </table>

Om HTML-strukturen ändras: justera SELECTORS-konstanten nedan.
"""

import re
import time
import logging
from datetime import date
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# SELECTORS – Justera dessa om swehockey ändrar sin HTML-struktur
# ---------------------------------------------------------------------------
SELECTORS = {
    "base_url": "https://stats.swehockey.se",
    "games_by_date_url": "https://stats.swehockey.se/GamesByDate/Index/{date}",
    "main_table_class": "tblContent",   # Tabellen som innehåller alla matcher
    "series_row_class": None,           # Serierader identifieras via cell-antal (1 cell)
    "match_row_classes": ("tdOdd", "tdNormal"),  # CSS-klasser på matchrader
}

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Datamodell
# ---------------------------------------------------------------------------

@dataclass
class Match:
    series: str
    date: str
    time: str
    home_team: str
    away_team: str
    result: str
    venue: str
    round_info: str        # Omgångsinformation, t.ex. "Kvartsfinal 1"
    status: str            # "Färdigspelad" | "Spelas idag" | "Kommande"


# ---------------------------------------------------------------------------
# In-memory cache – sparar resultatet i CACHE_TTL_SECONDS sekunder
# ---------------------------------------------------------------------------
_cache: dict = {}
CACHE_TTL_SECONDS = 300  # 5 minuter


def _get_cached(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _set_cache(key: str, data):
    _cache[key] = {"ts": time.time(), "data": data}


def clear_cache():
    """Rensa cachen manuellt (används av reload-knappen i UI)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Scraping-funktioner
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> str:
    """Hämtar HTML från angiven URL med lämpliga headers och timeout."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def _parse_game_cell(cell) -> tuple[str, str, str]:
    """
    Parsar 'Game'-cellen och returnerar (home_team, away_team, round_info).

    Cellen ser typiskt ut som:
        Hemmalag - Bortalag
        <br>
        Kvartsfinal 1
    """
    # Ersätt <br> med pipe-tecken för enkel uppdelning
    for br in cell.find_all("br"):
        br.replace_with("|")

    raw = cell.get_text(separator=" ").strip()
    parts = [p.strip() for p in raw.split("|")]

    game_text = parts[0] if parts else ""
    round_info = parts[1] if len(parts) > 1 else ""

    # Dela upp på " - " för hem/borta
    # Notera: vissa lagnamn kan innehålla bindestreck, t.ex. "Visby/Roma HK"
    # Vi delar på " - " (mellanslag runt bindestrecket)
    match = re.split(r"\s+-\s+", game_text, maxsplit=1)
    if len(match) == 2:
        home_team = match[0].strip()
        away_team = match[1].strip()
    else:
        # Fallback om formatet inte matchar
        home_team = game_text
        away_team = ""

    return home_team, away_team, round_info


def _determine_status(result: str, match_time: str) -> str:
    """Avgör matchstatus baserat på om resultat finns och klockslag."""
    if result:
        return "Färdigspelad"
    # Om ingen tid anges, räkna som kommande
    return "Spelas idag"


def _parse_matches_from_table(table, today_str: str) -> list[Match]:
    """
    Itererar tabellrader och bygger en lista av Match-objekt.

    Logik:
    - Rader med 1 cell (colspan=5) → serienamnsrad
    - Rader med 4 celler och klass tdOdd/tdNormal → matchrad
    - Övriga rader → ignoreras (rubrikrader etc.)
    """
    matches: list[Match] = []
    current_series = "Okänd serie"

    rows = table.find_all("tr")

    for row in rows:
        cells = row.find_all(["td", "th"])

        # --- Serienamnsrad (1 cell med colspan) ---
        if len(cells) == 1:
            cell = cells[0]
            # Skippa om det är th-element (rubrikrad)
            if cell.name == "th":
                continue
            series_text = cell.get_text(strip=True)
            if series_text:
                current_series = series_text
            continue

        # --- Matchrad (4 celler) ---
        if len(cells) == 4:
            # Skippa om första cellen är <th> (kolumnrubrik)
            if cells[0].name == "th":
                continue

            match_time = cells[0].get_text(strip=True)
            home_team, away_team, round_info = _parse_game_cell(cells[1])
            result = cells[2].get_text(strip=True)
            venue = cells[3].get_text(strip=True)

            # Skippa tomma rader
            if not home_team:
                continue

            status = _determine_status(result, match_time)

            matches.append(Match(
                series=current_series,
                date=today_str,
                time=match_time,
                home_team=home_team,
                away_team=away_team,
                result=result,
                venue=venue,
                round_info=round_info,
                status=status,
            ))

    return matches


def fetch_todays_matches(force_refresh: bool = False, target_date: Optional[str] = None) -> tuple[list[Match], str, Optional[str]]:
    """
    Hämtar och returnerar matcher för ett givet datum.

    Args:
        force_refresh: Tvinga ny hämtning, ignorera cache
        target_date: Datum på format YYYY-MM-DD. Om None används idag.

    Returnerar:
        (matches, fetched_at_str, error_message)
        - matches: lista av Match-objekt
        - fetched_at_str: tidsstämpel för senaste hämtning
        - error_message: felmeddelande-sträng om något gick fel, annars None
    """
    if target_date is None:
        today = date.today()
        today_str = today.strftime("%Y-%m-%d")
    else:
        today_str = target_date
    
    cache_key = f"matches_{today_str}"

    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached:
            return cached["matches"], cached["fetched_at"], None

    url = SELECTORS["games_by_date_url"].format(date=today_str)
    logger.info(f"Hämtar matcher från {url}")

    try:
        html = _fetch_html(url)
    except requests.exceptions.Timeout:
        logger.error("Timeout vid hämtning från swehockey.se")
        return [], "", "Timeout: Kunde inte nå stats.swehockey.se inom 15 sekunder."
    except requests.exceptions.ConnectionError:
        logger.error("Anslutningsfel mot swehockey.se")
        return [], "", "Anslutningsfel: Kunde inte ansluta till stats.swehockey.se."
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP-fel: {e}")
        return [], "", f"HTTP-fel: Servern svarade med felkod {e.response.status_code}."
    except Exception as e:
        logger.exception("Oväntat fel vid hämtning")
        return [], "", f"Oväntat fel: {str(e)}"

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Hitta huvudtabellen – justera main_table_class om HTML förändras
        table = soup.find("table", class_=SELECTORS["main_table_class"])
        if not table:
            logger.error("Kunde inte hitta tblContent-tabellen")
            return [], "", "Kunde inte hitta matchdatastrukturen på sidan. HTML-strukturen kan ha förändrats."

        matches = _parse_matches_from_table(table, today_str)

        fetched_at = time.strftime("%H:%M:%S")
        result_data = {"matches": matches, "fetched_at": fetched_at}
        _set_cache(cache_key, result_data)

        logger.info(f"Hittade {len(matches)} matcher för {today_str}")
        return matches, fetched_at, None

    except Exception as e:
        logger.exception("Oväntat fel vid parsning av HTML")
        return [], "", f"Parsningsfel: Kunde inte tolka sidan. {str(e)}"


def group_matches_by_series(matches: list[Match]) -> dict[str, list[Match]]:
    """
    Grupperar matcher per serie och sorterar varje serie efter tid.

    Returnerar en ordnad dict: { serienamn: [Match, ...] }
    """
    grouped: dict[str, list[Match]] = {}
    for match in matches:
        grouped.setdefault(match.series, []).append(match)

    # Sortera matcher inom varje serie efter tid
    for series_matches in grouped.values():
        series_matches.sort(key=lambda m: m.time or "99:99")

    return grouped
