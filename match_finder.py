"""
match_finder.py – Hittar match-IDs från stats.swehockey.se baserat på lag och datum.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging

logger = logging.getLogger(__name__)

_match_id_cache: dict = {}
CACHE_TTL_SECONDS = 3600

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
    """Extraherar hemmalag, bortalag och datum/tid från en Events-sida."""
    soup = BeautifulSoup(html, "html.parser")
    
    h2 = soup.find("h2")
    if not h2:
        return None
    
    full_text = h2.get_text(strip=True)
    teams = re.split(r'\s+-\s+', full_text)
    if len(teams) != 2:
        return None
    
    home_team = teams[0].strip()
    away_team = teams[1].strip()
    
    h3s = soup.find_all("h3")
    datetime_str = None
    for h3 in h3s:
        text = h3.get_text(strip=True)
        if re.search(r'\d{4}-\d{2}-\d{2}', text):
            datetime_str = text
            break
    
    if not datetime_str:
        return None
    
    return home_team, away_team, datetime_str


def find_match_id(home_team: str, away_team: str, date: str, time_str: str, start_id: int = 1081000, max_depth: int = 200) -> str | None:
    """Söker efter ett match-ID baserat på hemmalag, bortalag, datum och tid."""
    home_normalized = home_team.strip().lower()
    away_normalized = away_team.strip().lower()
    
    cached_id = _get_cached_id(home_team, away_team, date, time_str)
    if cached_id:
        logger.info(f"Found cached ID for {home_team} vs {away_team}: {cached_id}")
        return cached_id
    
    logger.info(f"Searching for match: {home_team} vs {away_team} on {date} at {time_str}")
    
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
            
            match_datetime_clean = re.sub(r'[^\d\s:\-]', '', match_datetime).strip()
            
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


def _extract_events_by_period(soup) -> dict:
    """Extrahera alla matchhändelser grupperade per period."""
    events_by_period = {}
    
    main_table = soup.find('table', class_='tblWrapper')
    if not main_table:
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) > 30:
                main_table = table
                break
    
    if not main_table:
        return events_by_period
    
    rows = main_table.find_all('tr')
    current_period = None
    
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        first_cell_text = cells[0].get_text(strip=True).replace("Â", "").strip()
        
        period_match = re.search(r'(\d+)\s*(?:st|nd|rd|th)?\s+period', first_cell_text, re.I)
        if period_match:
            current_period = f"period_{period_match.group(1)}"
            events_by_period[current_period] = []
            continue
        
        if current_period and len(cells) >= 2:
            time_val = first_cell_text
            if re.match(r'\d{1,2}:\d{2}', time_val) or time_val in ['00:00', '60:00']:
                event_type = cells[1].get_text(strip=True).replace("Â", "").strip() if len(cells) > 1 else ""
                team = cells[2].get_text(strip=True).replace("Â", "").strip() if len(cells) > 2 else ""
                
                player_cell = cells[3].get_text(strip=True).replace("Â", "").replace("\n", " ") if len(cells) > 3 else ""
                player_cell = re.sub(r'\s+', ' ', player_cell)
                
                details = cells[4].get_text(strip=True).replace("Â", "").strip() if len(cells) > 4 else ""
                
                event = {
                    "time": time_val,
                    "type": event_type,
                    "team": team,
                    "player": player_cell,
                    "details": details
                }
                
                events_by_period[current_period].append(event)
    
    return events_by_period


def _extract_goalkeeper_info(soup) -> dict:
    """Extrahera målvaktsstatistik från events-tabellen."""
    gk_info = {}
    
    main_table = soup.find('table', class_='tblWrapper')
    if not main_table:
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) > 30:
                main_table = table
                break
    
    if not main_table:
        return gk_info
    
    rows = main_table.find_all('tr')
    gk_section_found = False
    
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        row_text = " ".join([c.get_text(strip=True) for c in cells])
        if "Goalkeeper Summary" in row_text:
            gk_section_found = True
            continue
        
        if gk_section_found and len(cells) >= 5:
            team = cells[2].get_text(strip=True).replace("Â", "").strip() if len(cells) > 2 else ""
            player_info = cells[3].get_text(strip=True).replace("Â", "").strip() if len(cells) > 3 else ""
            stats = cells[4].get_text(strip=True).replace("Â", "").strip() if len(cells) > 4 else ""
            
            if team and player_info and "%" in stats:
                num_match = re.match(r'(\d+)\.\s*(.+)', player_info)
                if num_match:
                    gk_num = num_match.group(1)
                    gk_name = num_match.group(2).replace("\n", " ").replace("\r", "")
                    gk_name = re.sub(r'\s+', ' ', gk_name).strip()
                    
                    gk_info[gk_num] = {
                        "name": gk_name,
                        "team": team,
                        "stats": stats
                    }
            elif not stats and not player_info:
                if gk_section_found:
                    break
    
    return gk_info


def get_match_details(match_id: str) -> dict | None:
    """Hämtar detaljerad matchinformation från Events-sidan."""
    url = f"https://stats.swehockey.se/Game/Events/{match_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        h2 = soup.find("h2")
        if not h2:
            return None
        
        teams_text = h2.get_text(strip=True)
        teams = re.split(r'[Â\s\xa0]*-[Â\s\xa0]*', teams_text)
        if len(teams) != 2:
            logger.error(f"Failed to split teams from: {repr(teams_text)}")
            return None
        
        result_divs = soup.find_all("div", string=re.compile(r'^\d+[Â\s\xa0]*-[Â\s\xa0]*\d+$'))
        score = None
        for div in result_divs:
            score_text = div.get_text(strip=True)
            if '-' in score_text:
                score = score_text
                break
        
        h3s = soup.find_all("h3")
        datetime_str = None
        venue = None
        for h3 in h3s:
            text = h3.get_text(strip=True)
            if re.search(r'\d{4}-\d{2}-\d{2}', text):
                datetime_str = text
            elif len(text) > 5 and ("Arena" in text or "Hall" in text or "Ishall" in text):
                venue = text.replace("<b>", "").replace("</b>", "")
        
        spectators = None
        spec_text = soup.get_text()
        spec_match = re.search(r'Spectators:\s*(\d+(?:\s*\d+)*)', spec_text)
        if spec_match:
            spectators = spec_match.group(1).replace(" ", "")
        
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
                        if len(cells) >= 2:
                            home_shots = cells[1].get_text(strip=True)
                        if len(cells) >= 6:
                            away_shots = cells[5].get_text(strip=True)
                        break
        
        events_by_period = _extract_events_by_period(soup)
        goalkeepers = _extract_goalkeeper_info(soup)
        
        return {
            "home_team": teams[0].strip(),
            "away_team": teams[1].strip(),
            "score": score.replace("Â", "").strip() if score else None,
            "datetime": datetime_str.replace("Â", "").strip() if datetime_str else None,
            "venue": venue,
            "spectators": spectators,
            "home_shots": home_shots,
            "away_shots": away_shots,
            "events_by_period": events_by_period,
            "goalkeepers": goalkeepers,
            "id": match_id,
        }
    
    except Exception as e:
        logger.error(f"Error fetching match details for ID {match_id}: {e}")
        return None
