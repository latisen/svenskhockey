"""
match_finder.py – Hittar match-IDs från stats.swehockey.se baserat på lag och datum.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

_match_id_cache: dict = {}
CACHE_TTL_SECONDS = 3600

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _clean_text(value: str | None) -> str:
    """Normaliserar text från swehockey-sidorna."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("Â", "")
        .replace("\xa0", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
        .strip()
    )


def _extract_player_tokens(text: str) -> list[str]:
    """Splittar celltext till en eller flera spelare i formatet 'nr. namn'."""
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    parts = re.split(r'(?=\d+\.\s*)', cleaned)
    tokens = []
    for part in parts:
        part = _clean_text(part)
        if re.match(r'^\d+\.\s*', part):
            tokens.append(re.sub(r'\s+', ' ', part))
    return tokens


def _categorize_event(event_type: str) -> str:
    """Klassificerar en matchhändelse för enklare rendering i frontend."""
    t = _clean_text(event_type).lower()
    if not t:
        return "other"
    if "powerbreak" in t:
        return "powerbreak"
    if "gk in" in t or "gk out" in t:
        return "goalkeeper_change"
    if " min" in t:
        return "penalty"
    if re.search(r'\d+\s*-\s*\d+', t):
        return "goal"
    return "other"


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
        
        first_cell_text = _clean_text(cells[0].get_text(" ", strip=True))
        
        period_match = re.search(r'(\d+)\s*(?:st|nd|rd|th)?\s+period', first_cell_text, re.I)
        if period_match:
            current_period = f"period_{period_match.group(1)}"
            events_by_period[current_period] = []
            continue
        
        if current_period and len(cells) >= 2:
            time_val = first_cell_text
            if re.match(r'\d{1,2}:\d{2}', time_val) or time_val in ['00:00', '60:00']:
                event_type = _clean_text(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else ""
                team = _clean_text(cells[2].get_text(" ", strip=True)) if len(cells) > 2 else ""
                player_cell = _clean_text(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else ""
                details = _clean_text(cells[4].get_text(" ", strip=True)) if len(cells) > 4 else ""
                
                event = {
                    "time": time_val,
                    "type": event_type,
                    "team": team,
                    "player": player_cell,
                    "details": details,
                    "category": _categorize_event(event_type),
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
        
        row_text = " ".join([_clean_text(c.get_text(" ", strip=True)) for c in cells])
        if "Goalkeeper Summary" in row_text:
            gk_section_found = True
            continue
        
        if gk_section_found and len(cells) >= 5:
            team = _clean_text(cells[2].get_text(" ", strip=True)) if len(cells) > 2 else ""
            player_info = _clean_text(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else ""
            stats = _clean_text(cells[4].get_text(" ", strip=True)) if len(cells) > 4 else ""
            
            if team and player_info and "%" in stats:
                num_match = re.match(r'(\d+)\.\s*(.+)', player_info)
                if num_match:
                    gk_num = num_match.group(1)
                    gk_name = _clean_text(num_match.group(2))
                    
                    gk_info[gk_num] = {
                        "name": gk_name,
                        "team": team,
                        "stats": stats
                    }
            elif not stats and not player_info:
                if gk_section_found:
                    break
    
    return gk_info


def _extract_summary_stats(soup) -> dict:
    """Extraherar sammanfattande statistik från resultattabellen."""
    summary = {}
    summary_table = None
    for table in soup.find_all("table", class_="tblContent"):
        rows = table.find_all("tr")
        if len(rows) == 9:
            summary_table = table
            break

    if not summary_table:
        return summary

    rows = summary_table.find_all("tr")
    parsed_rows = []
    for row in rows:
        parsed_rows.append([_clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])])

    # Saves (antal) och save percentage
    if len(parsed_rows) > 5 and len(parsed_rows[4]) >= 6:
        summary["saves"] = {
            "label": "Saves",
            "home": parsed_rows[4][1],
            "away": parsed_rows[4][4],
            "home_periods": parsed_rows[4][2],
            "away_periods": parsed_rows[4][5],
        }

    if len(parsed_rows) > 6 and len(parsed_rows[5]) >= 4:
        summary["save_percentage"] = {
            "label": "Save %",
            "home": parsed_rows[5][1],
            "away": parsed_rows[5][3],
        }

    if len(parsed_rows) > 7 and len(parsed_rows[6]) >= 10:
        summary["pim"] = {
            "label": "PIM",
            "home": parsed_rows[6][1],
            "away": parsed_rows[6][8],
            "home_periods": parsed_rows[6][2],
            "away_periods": parsed_rows[6][9],
        }

    if len(parsed_rows) > 8 and len(parsed_rows[8]) >= 6:
        summary["powerplay"] = {
            "label": "Powerplay",
            "home": parsed_rows[8][1],
            "away": parsed_rows[8][4],
            "home_time": parsed_rows[8][2],
            "away_time": parsed_rows[8][5],
        }

    return summary


def _extract_reports(match_id: str) -> list[dict]:
    """Hämtar rapportlänkar från Reports-sidan."""
    report_url = f"https://stats.swehockey.se/Game/Reports/{match_id}"
    reports = []

    try:
        response = requests.get(report_url, headers=headers, timeout=10)
        response.encoding = "utf-8"
        if response.status_code != 200:
            return reports

        soup = BeautifulSoup(response.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            link = cells[0].find("a", href=True)
            if not link:
                continue

            name = _clean_text(link.get_text(" ", strip=True))
            if not name or name in {"Line Up", "Actions", "Reports"}:
                continue

            reports.append(
                {
                    "name": name,
                    "created_at": _clean_text(cells[1].get_text(" ", strip=True)),
                    "url": urljoin("https://stats.swehockey.se", link["href"]),
                }
            )
    except Exception as e:
        logger.warning(f"Could not extract reports for {match_id}: {e}")

    return reports


def _extract_lineups(match_id: str) -> dict:
    """Hämtar laguppställningar och domare från LineUps-sidan."""
    lineup_url = f"https://stats.swehockey.se/Game/LineUps/{match_id}"
    data = {
        "officials": {"referees": [], "linesmen": []},
        "teams": [],
    }

    try:
        response = requests.get(lineup_url, headers=headers, timeout=10)
        response.encoding = "utf-8"
        if response.status_code != 200:
            return data

        soup = BeautifulSoup(response.text, "html.parser")

        # Domare/linjedomare: läs bara rena label-värde-rader för att undvika
        # den hopslagna "allt i en rad"-texten i vissa tabeller.
        referees = []
        linesmen = []
        for row in soup.find_all("tr"):
            cells = [_clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]
            if len(cells) != 2:
                continue

            label = cells[0].rstrip(":").strip()
            value = cells[1].strip()
            if not value:
                continue

            if label == "Referee(s)":
                referees = [n.strip() for n in value.split(",") if n.strip()]
            elif label == "Linesmen":
                linesmen = [n.strip() for n in value.split(",") if n.strip()]

            if referees and linesmen:
                break

        data["officials"]["referees"] = referees
        data["officials"]["linesmen"] = linesmen

        # Välj tabellen som innehåller själva line up-strukturen
        lineup_table = None
        for table in soup.find_all("table", class_="tblContent"):
            rows = table.find_all("tr")
            if len(rows) >= 30:
                lineup_table = table
                break

        if not lineup_table:
            return data

        team_blocks: dict[str, dict] = {}
        current_team = None
        current_group = None

        def ensure_team(team_name: str):
            if team_name not in team_blocks:
                team_blocks[team_name] = {
                    "team_name": team_name,
                    "coaches": {"head": "", "assistant": ""},
                    "goalies": [],
                    "extra_players": [],
                    "lines": {
                        "1st Line": [],
                        "2nd Line": [],
                        "3rd Line": [],
                        "4th Line": [],
                    },
                }

        for row in lineup_table.find_all("tr"):
            cells = [_clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]
            if not cells:
                continue

            row_text = " | ".join(cells)
            first = cells[0] if cells else ""

            # Teamheader, t.ex. "Halmstad Hammers HC (Blue)"
            if first and "(" in first and ")" in first and "Line" not in first and "Coach" not in first and "Referee" not in first:
                current_team = first
                ensure_team(current_team)
                current_group = None
                continue

            if not current_team:
                continue

            # Coaches
            if "Head Coach" in row_text:
                head_match = re.search(r'Head Coach:\s*([^|]+)', row_text)
                asst_match = re.search(r'Assistant Coach:\s*([^|]+)', row_text)
                if head_match:
                    team_blocks[current_team]["coaches"]["head"] = _clean_text(head_match.group(1))
                if asst_match:
                    team_blocks[current_team]["coaches"]["assistant"] = _clean_text(asst_match.group(1))
                continue

            # Radstart med gruppetikett
            if first in {"Goalies", "Extra Players", "1st Line", "2nd Line", "3rd Line", "4th Line"}:
                current_group = first
                player_candidates = cells[1:]
            else:
                player_candidates = cells

            players = []
            for candidate in player_candidates:
                players.extend(_extract_player_tokens(candidate))

            if not players or not current_group:
                continue

            if current_group == "Goalies":
                team_blocks[current_team]["goalies"].extend(players)
            elif current_group == "Extra Players":
                team_blocks[current_team]["extra_players"].extend(players)
            elif current_group in team_blocks[current_team]["lines"]:
                team_blocks[current_team]["lines"][current_group].extend(players)

        # Deduplicera spelare per lista
        for team_name, block in team_blocks.items():
            block["goalies"] = list(dict.fromkeys(block["goalies"]))
            block["extra_players"] = list(dict.fromkeys(block["extra_players"]))
            for line_name, line_players in block["lines"].items():
                block["lines"][line_name] = list(dict.fromkeys(line_players))

            data["teams"].append(block)

        return data
    except Exception as e:
        logger.warning(f"Could not extract lineups for {match_id}: {e}")
        return data


def get_match_details(match_id: str) -> dict | None:
    """Hämtar detaljerad matchinformation från Events-sidan."""
    url = f"https://stats.swehockey.se/Game/Events/{match_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = "utf-8"
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        h2 = soup.find("h2")
        if not h2:
            return None
        
        teams_text = _clean_text(h2.get_text(" ", strip=True))
        teams = re.split(r'[Â\s\xa0]*-[Â\s\xa0]*', teams_text)
        if len(teams) != 2:
            logger.error(f"Failed to split teams from: {repr(teams_text)}")
            return None
        
        result_divs = soup.find_all("div", string=re.compile(r'^\d+[Â\s\xa0]*-[Â\s\xa0]*\d+$'))
        score = None
        for div in result_divs:
            score_text = _clean_text(div.get_text(" ", strip=True))
            if '-' in score_text:
                score = score_text
                break
        
        h3s = soup.find_all("h3")
        datetime_str = None
        venue = None
        for h3 in h3s:
            text = _clean_text(h3.get_text(" ", strip=True))
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
        summary_stats = _extract_summary_stats(soup)
        lineup_data = _extract_lineups(match_id)
        reports = _extract_reports(match_id)
        
        return {
            "home_team": teams[0].strip(),
            "away_team": teams[1].strip(),
            "score": _clean_text(score) if score else None,
            "datetime": _clean_text(datetime_str) if datetime_str else None,
            "venue": venue,
            "spectators": spectators,
            "home_shots": home_shots,
            "away_shots": away_shots,
            "summary_stats": summary_stats,
            "officials": lineup_data.get("officials", {"referees": [], "linesmen": []}),
            "lineups": lineup_data,
            "events_by_period": events_by_period,
            "goalkeepers": goalkeepers,
            "reports": reports,
            "id": match_id,
        }
    
    except Exception as e:
        logger.error(f"Error fetching match details for ID {match_id}: {e}")
        return None
