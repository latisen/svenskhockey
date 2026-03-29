# Svenska Hockeymatcher

En webbapp byggd med **Python / Flask** som scrapar och visar alla ishockeymatcher som spelas idag från [stats.swehockey.se](https://stats.swehockey.se).

---

## Funktioner

- Hämtar automatiskt dagens matcher från Swehockey
- Grupperar matcher per serie (SHL, Hockeyettan, U20, U18, m.m.)
- Visar matchstatus: **Spelas idag** eller **Färdigspelad** (med resultat)
- Livesökning på lagnamn – filtrerar matcher och serier direkt
- In-memory-cache (5 min) för att undvika onödiga HTTP-requests
- Manuell "Ladda om"-knapp för att tvinga ny hämtning
- Responsiv design för desktop och mobil

---

## Installation

### Förutsättningar

- Python 3.10 eller senare
- `pip`

### Steg för steg

```bash
# 1. Klona projektet
git clone https://github.com/ditt-repo/svenskhockey.git
cd svenskhockey

# 2. Skapa och aktivera virtuell miljö
python3 -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

# 3. Installera beroenden
pip install -r requirements.txt

# 4. Starta appen
python app.py
```

Öppna sedan [http://localhost:5000](http://localhost:5000) i din webbläsare.

---

## Projektstruktur

```
svenskhockey/
├── app.py               # Flask-app – routes och konfiguration
├── scraper.py           # Scraping-logik och datamodell
├── requirements.txt     # Python-beroenden
├── templates/
│   ├── base.html        # Bas-template (HTML-skelett)
│   └── index.html       # Huvudvy med matcher
└── static/
    ├── style.css        # Stilmall (responsiv design)
    └── app.js           # Livesökning och UI-interaktion
```

---

## Hur scraping och filtrering fungerar

### Scraping (`scraper.py`)

1. Applikationen hämtar `https://stats.swehockey.se/GamesByDate/Index/YYYY-MM-DD` (alltid med dagens datum).
2. BeautifulSoup parsar HTML och söker efter `<table class="tblContent">`.
3. Tabellrader itereras:
   - **Serierader** – en cell med `colspan` → sätter aktuellt serienamn.
   - **Matchrader** – fyra celler: `tid | hemmalag – bortalag | resultat | arena`.
4. Om resultcellen är tom markeras matchen som *Spelas idag*, annars *Färdigspelad*.
5. Matcher grupperas och sorteras per serie via `group_matches_by_series()`.
6. Resultatet cachas i minnet i 5 minuter för att minska belastningen på Swehockey.

### Livesökning (`static/app.js`)

- JavaScript lyssnar på tangenttryckningar i sökrutan (debounce 60 ms).
- Varje matchrad har `data-home` och `data-away`-attribut med lagnamnen i gemener.
- Söktexten jämförs case-insensitivt mot dessa attribut.
- Matchrader som inte matchar döljs med `hidden`-attributet.
- Seriesektioner döljs om inga av deras matcher matchar sökningen.
- Escape-tangenten rensar sökningen.

### Selectors – om HTML-strukturen ändras

Om Swehockey uppdaterar sin sida och scraping slutar fungera, se kommentaren i `scraper.py` under `SELECTORS`-konstanten. Justera:

- `main_table_class` – CSS-klassen på tabellen som innehåller matcherna.
- Cellordningen i `_parse_matches_from_table()`.

---

## Miljövariabler

Inga miljövariabler krävs för grundfunktionaliteten. Flask körs i debug-läge vid `python app.py`. För produktion, starta med en WSGI-server (t.ex. Gunicorn):

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```
