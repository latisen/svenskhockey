"""
match_finder.py – Hittar match-IDs från stats.swehockey.se baserat på lag och datum.

Eftersom match-IDs inte är tillgängliga direkt på GamesByDate-sidan,
söker vi genom ett intervall av IDs för att hitta rätt match.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging

logger = logging.getLogger(__name__)

# Cache för att undvika upprepade sökningar
_match_id_cache: dict = {}
CACHE_TTL_SECONDS = 3600  # 1 timme

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _get_cached_id(home_team: str, away_team: str, date: str, time_str: str) -> str | None:
    """Returnerar cached match-ID om det finns och inte är för gammalt."""
    cache_key = f"{home_team}|{away_team}|{date}|{time_str}"
    entry = _match_id_cache.get(cache_key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["id"]
    return None


def _set_cached_id(home_team: str, away_team: str, date: str, time_str: str, match_id: str):
    """Sparar match-ID i cache."""
    cache_key = f"{home_team}|{away_team}|{date}|{time_str}"
    _match_id_cache[cache_key] = {"id": match_id, "ts": time.time()}


def _extract_match_info(html: str) -> tuple[str, str, str] | None:
    """
    Extraherar hemmalag, bortalag och datum/tid från en Events-sida.
    Returnerar (home_team, away_team, datetime_str) eller None.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Extrahera lag från <h2>
    h2 = soup.find("h2")
    if not h2:
        return None
    
    full_text = h2.get_text(strip=True)
    teams = re.split(r'\s+-\s+', full_text)
    if len(teams) != 2:
        return None
    
    home_team = teams[0].strip()
    away_team = teams[1].strip()
    
    # Extrahera datum och tid från första <h3> som innehåller ett datum
    h3s = soup.find_all("h3")
    datetime_str = None
    for h3 in h3s:
        text = h3.get_text(strip=True)
        # Söka efter format "YYYY-MM-DD HH:MM"
        if re.search(r'\d{4}-\d{2}-\d{2}', text):
            datetime_str = text
            break
    
    if not datetime_str:
        return None
    
    return home_team, away_team, datetime_str


def find_match_id(home_team: str, away_team: str, date: str, time_str: str, start_id: int = 1081000, max_depth: int = 200) -> str | None:
    """
    Söker efter ett match-ID baserat på hemmalag, bortalag, datum och tid.
    
    Args:
        home_team: Hemmalag (t.ex. "Halmstad Hammers HC")
        away_team: Bortalag
        date: Datum på format YYYY-MM-DD
        time_str: Tid på format HH:MM
        start_id: Startvärde för sökningen (default: i närheten av kända IDs)
        max_depth: Hur många IDs att söka igenom
    
    Returnerar match-ID som string, eller None om inte hittat.
    """
    # Normalisera lagnamn för jämförelse
    home_normalized = home_team.strip().lower()
    away_normalized = away_team.strip().lower()
    
    # Kontrollera cache först
    cached_id = _get_cached_id(home_team, away_team, date, time_str)
    if cached_id:
        logger.info(f"Found cached ID for {home_team} vs {away_team}: {cached_id}")
        return cached_id
    
    logger.info(f"Searching for match: {home_team} vs {away_team} on {date} at {time_str}")
    
    # Söka igenom ett intervall av IDs
    for offset in range(-max_depth // 2, max_depth // 2):
        test_id = start_id + offset
        url = f"https://stats.swehockey.se/Game/Events/{test_id}"
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200:
                continue
            
            match_info = _extract_match_info(response.text)
            if not match_info:
                continue
            
            match_home, match_away, match_datetime = match_info
            match_home_normalized = match_home.strip().lower()
            match_away_normalized = match_away.strip().lower()
            
            # Begränsa datetime till bara datum och tid (ta bort encoding-artefakter)
            match_datetime_clean = re.sub(r'[^\d\s:\-]', '', match_datetime).strip()
            
            # Kontrollera om detta är rätt match
            if (match_home_normalized == home_normalized and
                match_away_normalized == away_normalized and
                match_datetime_clean.startswith(date) and
                time_str in match_datetime_clean):
                
                logger.info(f"Found match ID {test_id} for {home_team} vs {away_team}")
                _set_cached_id(home_team, away_team, date, time_str, str(test_id))
                return str(test_id)
        
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout checking ID {test_id}")
            continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error checking ID {test_id}: {e}")
            continue
    
    logger.warning(f"Could not find match ID for {home_team} vs {away_team}")
    return None


def get_match_details(match_id: str) -> dict | None:
    """
    Hämtar matchdetaljer från Events-sidan.
    
    Returnerar dict med: home_team, away_team, date, time, score, venue, etc.
    eller None om någon fel uppstod.
    """
    url = f"https://stats.swehockey.se/Game/Events/{match_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extrahera lag och datum
        h2 = soup.find("h2")
        if not h2:
            return None
        
        teams_text = h2.get_text(strip=True)
        teams = re.split(r'\s+-\s+', teams_text)
        if len(teams) != 2:
            return None
        
        # Extrahera resultat från mitten av tabellen
        # Format: <div style="..."><div style="...">3 - 5</div>
        result_divs = soup.find_all("div", string=re.compile(r'^\s*\d+\s*-\s*\d+\s*$'))
        score = None
        for div in result_divs:
            score_text = div.get_text(strip=True)
            if '-' in score_text:
                score = score_text
                break
        
        # Extrahera datum, tid och arena från h3-element
        h3s = soup.find_all("h3")
        datetime_str = None
        venue = None
        for h3 in h3s:
            text = h3.get_text(strip=True)
            if re.search(r'\d{4}-\d{2}-\d{2}', text):
                datetime_str = text
            elif len(text) > 5 and "Arena" in text or "Hall" in text or "Ishall" in text:
                venue = text.replace("<b>", "").replace("</b>", "")
        
        # Extrahera spectators
        spectators = None
        spec_text = soup.get_text()
        spec_match = re.search(r'Spectators:\s*(\d+(?:\s*\d+)*)', spec_text)
        if spec_match:
            spectators = spec_match.group(1).replace(" ", "")
        
        # Extrahera shots on goal
        shots_table = soup.find("table", class_="tblContent")
        home_shots = None
        away_shots = None
        if shots_table:
            rows = shots_table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    first_cell = cells[0].get_text(strip=True)
                    if first_cell == "Shots":
                        # Nästa cell är hemmalaget's shots
                        if len(cells) >= 2:
                            home_shots = cells[1].get_text(strip=True)
                        if len(cells) >= 6:
                            away_shots = cells[5].get_text(strip=True)
                        break
        
        return {
            "home_team": teams[0].strip(),
            "away_team": teams[1].strip(),
            "score": score,
            "datetime": datetime_str,
            "venue": venue,
            "spectators": spectators,
            "home_shots": home_shots,
            "away_shots": away_shots,
            "id": match_id,
        }
    
    except Exception as e:
        logger.error(f"Error fetching match details for ID {match_id}: {e}")
        return None
