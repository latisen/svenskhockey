/**
 * app.js – Klientsidelogik för Svenska Hockeymatcher
 *
 * Funktioner:
 *  1. Livesökning – filtrera matchrader och sektioner i realtid
 *  2. Rensa-knapp för sökrutan
 *  3. Laddningsindikator på reload-knappen
 *  4. Live-polling för uppdatering av matcher som spelas
 */

(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // Element-referenser
  // ---------------------------------------------------------------------------
  var searchInput   = document.getElementById("searchInput");
  var searchClear   = document.getElementById("searchClear");
  var noResultsMsg  = document.getElementById("noResultsMsg");
  var reloadBtn     = document.getElementById("reloadBtn");
  var seriesList    = document.getElementById("seriesList");

  // Avsluta tyst om nödvändiga element saknas (defensiv programmering)
  if (!searchInput || !seriesList) return;

  // Alla serie-sektioner och matchrader – hämtas en gång för prestanda
  var allSections = Array.prototype.slice.call(
    seriesList.querySelectorAll(".series-card")
  );

  // ---------------------------------------------------------------------------
  // 1. Livesökning
  // ---------------------------------------------------------------------------

  /**
   * Filtrerar matchrader och sektioner baserat på söksträngen.
   * Jämförelse sker case-insensitivt mot data-home och data-away.
   */
  function filterMatches(query) {
    var q = query.trim().toLowerCase();
    var totalVisible = 0;

    allSections.forEach(function (section) {
      var rows = Array.prototype.slice.call(
        section.querySelectorAll(".match-row")
      );
      var visibleInSection = 0;

      rows.forEach(function (row) {
        var home = row.getAttribute("data-home") || "";
        var away = row.getAttribute("data-away") || "";

        if (q === "" || home.indexOf(q) !== -1 || away.indexOf(q) !== -1) {
          row.removeAttribute("hidden");
          visibleInSection++;
        } else {
          row.setAttribute("hidden", "");
        }
      });

      // Dölj hela sektionen om inga matcher matchar
      if (visibleInSection === 0 && q !== "") {
        section.setAttribute("hidden", "");
      } else {
        section.removeAttribute("hidden");
        totalVisible += visibleInSection;
      }
    });

    // Visa "inga resultat"-meddelande om nödvändigt
    if (noResultsMsg) {
      if (q !== "" && totalVisible === 0) {
        noResultsMsg.removeAttribute("hidden");
      } else {
        noResultsMsg.setAttribute("hidden", "");
      }
    }
  }

  // Lyssna på tangentbordsinput med minimalt debounce (60ms)
  var debounceTimer = null;
  searchInput.addEventListener("input", function () {
    var value = searchInput.value;

    // Visa/dölj rensa-knapp
    if (searchClear) {
      if (value.length > 0) {
        searchClear.removeAttribute("hidden");
      } else {
        searchClear.setAttribute("hidden", "");
      }
    }

    // Debounce – vänta 60ms innan filtrering körs (undviker onödig DOM-manipulation)
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      filterMatches(value);
    }, 60);
  });

  // ---------------------------------------------------------------------------
  // 2. Rensa-knapp
  // ---------------------------------------------------------------------------
  if (searchClear) {
    searchClear.addEventListener("click", function () {
      searchInput.value = "";
      searchClear.setAttribute("hidden", "");
      filterMatches("");
      searchInput.focus();
    });
  }

  // ---------------------------------------------------------------------------
  // 3. Reload-knapp – laddningsindikator
  // ---------------------------------------------------------------------------
  if (reloadBtn) {
    reloadBtn.addEventListener("click", function () {
      reloadBtn.classList.add("is-loading");
      // Knappen leds vidare av href – klassen rensas inte aktivt
      // (sidan laddas om, så det är inte nödvändigt)
    });
  }

  // ---------------------------------------------------------------------------
  // 4. Kortkommando: Escape rensar sökning
  // ---------------------------------------------------------------------------
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.activeElement === searchInput) {
      searchInput.value = "";
      if (searchClear) searchClear.setAttribute("hidden", "");
      filterMatches("");
    }
  });

  // ---------------------------------------------------------------------------
  // 5. Live-polling för uppdatering av matcher
  // ---------------------------------------------------------------------------

  var lastFetchedAt = null;
  var pollInterval = null;
  var countdownInterval = null;
  var STOCKHOLM_TIME_ZONE = "Europe/Stockholm";
  var stockholmDateTimeFormatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: STOCKHOLM_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });

  function getStockholmDateTimeParts(date) {
    var parts = stockholmDateTimeFormatter.formatToParts(date);
    var values = {};

    parts.forEach(function (part) {
      if (part.type !== "literal") {
        values[part.type] = part.value;
      }
    });

    return values;
  }

  function getStockholmTodayIso() {
    var nowParts = getStockholmDateTimeParts(new Date());
    return nowParts.year + "-" + nowParts.month + "-" + nowParts.day;
  }

  function getStockholmOffsetMilliseconds(date) {
    var parts = getStockholmDateTimeParts(date);
    var stockholmAsUtc = Date.UTC(
      parseInt(parts.year, 10),
      parseInt(parts.month, 10) - 1,
      parseInt(parts.day, 10),
      parseInt(parts.hour, 10),
      parseInt(parts.minute, 10),
      parseInt(parts.second, 10)
    );

    return stockholmAsUtc - date.getTime();
  }

  function createStockholmDateTime(dateStr, timeStr) {
    var dateParts = (dateStr || getStockholmTodayIso()).split("-");
    var timeParts = (timeStr || "00:00").split(":");
    var year = parseInt(dateParts[0], 10);
    var month = parseInt(dateParts[1], 10);
    var day = parseInt(dateParts[2], 10);
    var hour = parseInt(timeParts[0], 10);
    var minute = parseInt(timeParts[1], 10);
    var second = parseInt(timeParts[2] || "0", 10);

    if (
      isNaN(year) ||
      isNaN(month) ||
      isNaN(day) ||
      isNaN(hour) ||
      isNaN(minute) ||
      isNaN(second)
    ) {
      return null;
    }

    var utcCandidate = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
    var offset = getStockholmOffsetMilliseconds(utcCandidate);
    var adjustedDate = new Date(utcCandidate.getTime() - offset);
    var adjustedOffset = getStockholmOffsetMilliseconds(adjustedDate);

    if (adjustedOffset !== offset) {
      adjustedDate = new Date(utcCandidate.getTime() - adjustedOffset);
    }

    return adjustedDate;
  }

  /**
   * Formaterar återstående tid som HH:MM:ss.
   * t.ex. "00:45:30", "00:00:12"
   */
  function formatTimeRemaining(minutes, seconds) {
    var totalSeconds = minutes * 60 + seconds;
    var hours = Math.floor(totalSeconds / 3600);
    var mins = Math.floor((totalSeconds % 3600) / 60);
    var secs = totalSeconds % 60;
    
    // Pad med nolla för att få HH:MM:ss format
    var h = hours < 10 ? "0" + hours : hours;
    var m = mins < 10 ? "0" + mins : mins;
    var s = secs < 10 ? "0" + secs : secs;
    
    return h + ":" + m + ":" + s;
  }

  /**
   * Uppdaterar countdownen för en enstaka matchrad.
   */
  function updateCountdownForRow(row) {
    var countdownElem = row.querySelector(".match-countdown");
    if (!countdownElem) return;

    var timeStr = countdownElem.getAttribute("data-time");
    var dateStr = row.getAttribute("data-date") || getStockholmTodayIso();
    if (!timeStr) return;

    var status = row.classList.contains("match-played") ? "Färdigspelad" : null;
    if (status === "Färdigspelad") {
      countdownElem.setAttribute("hidden", "");
      return;
    }

    // Beräkna tid kvar
    var now = new Date();
    var matchTime = createStockholmDateTime(dateStr, timeStr);
    if (!matchTime) return;

    var timeRemaining = matchTime.getTime() - now.getTime();

    if (timeRemaining < 0) {
      // Matchen har redan börjat
      countdownElem.setAttribute("hidden", "");
      return;
    }

    var minutesLeft = Math.floor(timeRemaining / 60000);
    var secondsLeft = Math.floor((timeRemaining % 60000) / 1000);

    var formatted = formatTimeRemaining(minutesLeft, secondsLeft);
    countdownElem.textContent = formatted;
    countdownElem.removeAttribute("hidden");

    // Justera styling baserat på tid kvar
    countdownElem.classList.remove("match-soon", "match-live");
    if (minutesLeft === 0 && secondsLeft <= 5) {
      countdownElem.classList.add("match-live");
    } else if (minutesLeft <= 15) {
      countdownElem.classList.add("match-soon");
    }
  }

  /**
   * Uppdaterar alla countdowns på sidan.
   */
  function updateAllCountdowns() {
    var allCountdowns = Array.prototype.slice.call(
      seriesList.querySelectorAll(".match-countdown")
    );
    allCountdowns.forEach(function (elem) {
      var row = elem.closest(".match-row");
      if (row) {
        updateCountdownForRow(row);
      }
    });
  }

  /**
   * Startar countdown-uppdatering var sekund.
   */
  function startCountdownUpdates() {
    // Första uppdatering omedelbar
    updateAllCountdowns();

    // Sedan var sekund
    countdownInterval = setInterval(updateAllCountdowns, 1000);
  }

  /**
   * Hämtar uppdateringar från API:t och uppdaterar matchkorten.
   */
  function pollForUpdates() {
    // Hämta current datum från URL
    var params = new URLSearchParams(window.location.search);
    var currentDate = params.get("date") || "";

    fetch("/api/matches" + (currentDate ? "?date=" + encodeURIComponent(currentDate) : ""), {
      method: "GET",
      headers: { "Accept": "application/json" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("Failed to fetch updates");
        return resp.json();
      })
      .then(function (data) {
        if (data.error) {
          console.warn("API error:", data.error);
          return;
        }

        // Uppdatera tidsangivelsen "senast uppdaterad"
        var statusElem = document.querySelector(".last-updated");
        if (statusElem && data.fetched_at) {
          statusElem.textContent = "Uppdaterad " + data.fetched_at;
          lastFetchedAt = data.fetched_at;
        }

        // Uppdatera matchrader
        updateMatchRows(data.matches);
        
        // Re-checka om det finns live-matcher efter uppdatering
        // (för att kunna stoppa polling om all matcher blev färdigspelade)
        updatePollingStatus();
      })
      .catch(function (err) {
        console.error("Error polling updates:", err);
      });
  }

  /**
   * Uppdaterar matchrader baserat på ny data från API:t.
   * Matchar gamla rader med nya data och uppdaterar resultat/tid.
   */
  function updateMatchRows(groupedMatches) {
    var allRows = Array.prototype.slice.call(
      seriesList.querySelectorAll(".match-row")
    );

    allRows.forEach(function (row) {
      var home = row.getAttribute("data-home");
      var away = row.getAttribute("data-away");
      if (!home || !away) return;

      // Hitta motsvarande match i ny data
      var updatedMatch = findMatchInData(groupedMatches, home, away);
      if (!updatedMatch) return;

      // Uppdatera resultatkolumn
      var resultCol = row.querySelector(".match-result-col");
      if (resultCol) {
        resultCol.innerHTML = "";
        if (updatedMatch.result) {
          var resultSpan = document.createElement("span");
          resultSpan.className = "match-result";
          resultSpan.textContent = updatedMatch.result;
          resultCol.appendChild(resultSpan);
        } else {
          var placeholderSpan = document.createElement("span");
          placeholderSpan.className = "match-result-placeholder";
          placeholderSpan.textContent = "vs";
          resultCol.appendChild(placeholderSpan);
        }
      }

      // Uppdatera badge (status)
      var badge = row.querySelector(".badge");
      if (badge) {
        badge.textContent = updatedMatch.status;
        badge.className = "badge";
        if (updatedMatch.status === "Färdigspelad") {
          badge.classList.add("badge-played");
        } else if (updatedMatch.status === "Live") {
          badge.classList.add("badge-live");
        } else {
          badge.classList.add("badge-upcoming");
        }
      }

      // Uppdatera CSS-klass på rad
      row.classList.remove("match-played", "match-live", "match-upcoming");
      if (updatedMatch.status === "Färdigspelad") {
        row.classList.add("match-played");
      } else if (updatedMatch.status === "Live") {
        row.classList.add("match-live");
      } else {
        row.classList.add("match-upcoming");
      }

      // Uppdatera countdown efter status-ändring
      updateCountdownForRow(row);
    });
  }

  /**
   * Söker efter en match i den nya data-strukturen.
   * data-home och data-away är i gemener.
   */
  function findMatchInData(groupedMatches, homeKey, awayKey) {
    for (var series in groupedMatches) {
      var matches = groupedMatches[series];
      for (var i = 0; i < matches.length; i++) {
        var m = matches[i];
        var mHome = (m.home_team || "").toLowerCase();
        var mAway = (m.away_team || "").toLowerCase();
        if (mHome === homeKey && mAway === awayKey) {
          return m;
        }
      }
    }
    return null;
  }

  function isRowLive(row) {
    if (!row || row.classList.contains("match-played")) {
      return false;
    }

    if (row.classList.contains("match-live")) {
      return true;
    }

    var timeStr = row.getAttribute("data-time");
    var dateStr = row.getAttribute("data-date") || getStockholmTodayIso();
    if (!timeStr) {
      return false;
    }

    var matchTime = createStockholmDateTime(dateStr, timeStr);
    if (!matchTime) {
      return false;
    }

    return matchTime.getTime() <= Date.now();
  }

  /**
   * Checkar om det finns någon match som är "live" (pågår just nu).
   * En match är live om:
   * - Den är NOT "Färdigspelad"
   * - OCH tiden för matchstart har passerat
   */
  function hasLiveMatches() {
    var allRows = Array.prototype.slice.call(
      seriesList.querySelectorAll(".match-row")
    );

    for (var i = 0; i < allRows.length; i++) {
      if (isRowLive(allRows[i])) {
        return true;
      }
    }

    return false;
  }

  /**
   * Starta eller stoppa polling baserat på om det finns live-matcher.
   */
  function updatePollingStatus() {
    var hasLive = hasLiveMatches();
    var reloadBtn = document.getElementById("reloadBtn");
    var autoIndicator = document.getElementById("autoUpdateIndicator");

    if (hasLive && !pollInterval) {
      // Starta polling
      pollInterval = setInterval(pollForUpdates, 60000); // 60 sekunder
      pollForUpdates();
      console.log("Live-polling started");
    } else if (!hasLive && pollInterval) {
      // Stoppa polling
      clearInterval(pollInterval);
      pollInterval = null;
      console.log("Live-polling stopped");
    }

    // Visa/dölj knapp vs. indikator
    if (reloadBtn) reloadBtn.style.display = pollInterval ? "none" : "";
    if (autoIndicator) autoIndicator.style.display = pollInterval ? "" : "none";
  }

  /**
   * Starta polling och countdown när sidan laddat. Uppdatera live-matcher varje minut.
   */
  function startPolling() {
    // Starta countdown-uppdateringar var sekund
    startCountdownUpdates();

    // Checka initialt om det finns live-matcher och starta polling isåfall
    updatePollingStatus();
    
    // Checka status var 10 sekund för att börja/stoppa polling när behövligt
    setInterval(updatePollingStatus, 10000);
  }
  var modal = document.getElementById("matchModal");
  var modalClose = modal ? modal.querySelector("#modalClose") : null;
  var modalOverlay = modal ? modal.querySelector(".modal-overlay") : null;
  var modalLoading = modal ? modal.querySelector("#modalLoading") : null;
  var modalError = modal ? modal.querySelector("#modalError") : null;
  var modalDetails = modal ? modal.querySelector("#modalDetails") : null;

  /**
   * Öppnar modalen för en match.
   */
  function openMatchModal(matchRow) {
    if (!modal) return;

    var homeTeam = matchRow.getAttribute("data-home-team");
    var awayTeam = matchRow.getAttribute("data-away-team");
    var date = matchRow.getAttribute("data-date");
    var time = matchRow.getAttribute("data-time");
    var matchId = matchRow.getAttribute("data-match-id");

    if (!homeTeam || !awayTeam || !date || !time) {
      showModalError("Matchdata saknas");
      return;
    }

    // Visa modal med laddningsindikator
    modal.removeAttribute("aria-hidden");
    modal.classList.add("open");
    document.body.style.overflow = "hidden";

    // Visa laddning, dölj detaljer och fel
    if (modalLoading) modalLoading.removeAttribute("hidden");
    if (modalError) modalError.setAttribute("hidden", "");
    if (modalDetails) modalDetails.setAttribute("hidden", "");

    // Välja first tab och starta tab-systemet
    if (document.querySelector("[data-tab='events']")) {
      switchModalTab("events");
    }

    // Hämta matchdetaljer från API (med match_id om tillgängligt)
    fetchMatchDetails(homeTeam, awayTeam, date, time, matchId);
  }

  /**
   * Stänger modalen.
   */
  function closeMatchModal() {
    if (!modal) return;
    modal.setAttribute("aria-hidden", "true");
    modal.classList.remove("open");
    document.body.style.overflow = "";
  }

  /**
   * Visar felmeddelande i modalen.
   */
  function showModalError(message) {
    if (!modalLoading) return;
    if (!modalError) return;

    modalLoading.setAttribute("hidden", "");
    modalError.removeAttribute("hidden");
    modalDetails.setAttribute("hidden", "");
    document.getElementById("modalErrorText").textContent = message;
  }

  /**
   * Hämtar matchdetaljer från API:t.
   */
  function fetchMatchDetails(homeTeam, awayTeam, date, time, matchId) {
    var params = new URLSearchParams();
    
    // Om match_id finns, använd bara det
    if (matchId) {
      params.append("match_id", matchId);
    } else {
      // Fallback: använd hemmalag, bortalag, datum och tid
      params.append("home_team", homeTeam);
      params.append("away_team", awayTeam);
      params.append("date", date);
      params.append("time", time);
    }

    fetch("/api/match-details?" + params.toString(), {
      method: "GET",
      headers: { "Accept": "application/json" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (details) {
        if (details.error) {
          showModalError("Kunde inte hämta matchdetaljer: " + details.error);
          return;
        }

        displayMatchDetails(details);
      })
      .catch(function (err) {
        console.error("Error fetching match details:", err);
        showModalError("Kunde inte hämta matchdetaljer. Försök igen senare.");
      });
  }

  /**
   * Visar matchdetaljer i modalen.
   */
  function displayMatchDetails(details) {
    if (!modalDetails) return;

    function cleanText(value) {
      return String(value || "")
        .replace(/Â/g, "")
        .replace(/\u00a0/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function sectionToggle(sectionElem, visible) {
      if (!sectionElem) return;
      if (visible) {
        sectionElem.removeAttribute("hidden");
      } else {
        sectionElem.setAttribute("hidden", "");
      }
    }

    // Uppdatera titel
    var title = document.getElementById("modalTitle");
    if (title) {
      title.textContent = cleanText(details.home_team || "?") + " – " + cleanText(details.away_team || "?");
    }

    // Hemmalag
    var homeTeamElem = document.getElementById("modalHomeTeam");
    if (homeTeamElem) homeTeamElem.textContent = cleanText(details.home_team || "–");

    var homeScoreElem = document.getElementById("modalHomeScore");
    if (homeScoreElem) {
      if (details.score) {
        var scores = details.score.split("-");
        homeScoreElem.textContent = scores[0] ? scores[0].trim() : "–";
      } else {
        homeScoreElem.textContent = "–";
      }
    }

    // Bortalag
    var awayTeamElem = document.getElementById("modalAwayTeam");
    if (awayTeamElem) awayTeamElem.textContent = cleanText(details.away_team || "–");

    var awayScoreElem = document.getElementById("modalAwayScore");
    if (awayScoreElem) {
      if (details.score) {
        var scores = details.score.split("-");
        awayScoreElem.textContent = scores[1] ? scores[1].trim() : "–";
      } else {
        awayScoreElem.textContent = "–";
      }
    }

    // Datum & Tid
    var dateTimeElem = document.getElementById("modalDateTime");
    if (dateTimeElem) {
      dateTimeElem.textContent = cleanText(details.datetime || "–");
    }

    // Arena
    var venueElem = document.getElementById("modalVenue");
    if (venueElem) {
      venueElem.textContent = cleanText(details.venue || "–").replace(/<b>|<\/b>/g, "");
    }

    // Publik
    var specElem = document.getElementById("modalSpectators");
    if (specElem) {
      specElem.textContent = details.spectators ? cleanText(details.spectators) + " personer" : "–";
    }

    // Skott på mål
    var homeShotsElem = document.getElementById("modalHomeShots");
    if (homeShotsElem) {
      homeShotsElem.textContent = details.home_shots ? cleanText(details.home_shots).replace(/<strong>|<\/strong>/g, "") : "–";
    }

    var awayShotsElem = document.getElementById("modalAwayShots");
    if (awayShotsElem) {
      awayShotsElem.textContent = details.away_shots ? cleanText(details.away_shots).replace(/<strong>|<\/strong>/g, "") : "–";
    }

    // Link to full details
    var detailsLink = document.getElementById("modalDetailsLink");
    if (detailsLink && details.id) {
      detailsLink.href = "https://stats.swehockey.se/Game/Events/" + details.id;
    }

    // Key stats (PP, PIM, saves) - Render in two boxes
    var keyStatsHomeBox = document.getElementById("modalKeyStatsHome");
    var keyStatsAwayBox = document.getElementById("modalKeyStatsAway");
    var keyStatsBoxes = document.getElementById("modalKeyStatsBoxes");
    
    if ((keyStatsHomeBox || keyStatsAwayBox) && details.summary_stats && keyStatsBoxes) {
      var homeStatRows = [];
      var awayStatRows = [];
      var keys = ["save_percentage", "pim", "powerplay"];
      
      for (var s = 0; s < keys.length; s++) {
        var key = keys[s];
        var stat = details.summary_stats[key];
        if (!stat) continue;
        
        var homeValue = escapeHtml(cleanText(stat.home || "-"));
        var awayValue = escapeHtml(cleanText(stat.away || "-"));
        var label = escapeHtml(cleanText(stat.label || key));
        
        homeStatRows.push(
          "<div class='modal-key-stat-row'>" +
            "<span class='modal-key-stat-row-label'>" + label + "</span>" +
            "<span class='modal-key-stat-row-value'>" + homeValue + "</span>" +
          "</div>"
        );
        
        awayStatRows.push(
          "<div class='modal-key-stat-row'>" +
            "<span class='modal-key-stat-row-label'>" + label + "</span>" +
            "<span class='modal-key-stat-row-value'>" + awayValue + "</span>" +
          "</div>"
        );
      }
      
      if (homeStatRows.length > 0) {
        if (keyStatsHomeBox) keyStatsHomeBox.innerHTML = homeStatRows.join("");
        if (keyStatsAwayBox) keyStatsAwayBox.innerHTML = awayStatRows.join("");
        keyStatsBoxes.style.display = "grid";
      } else {
        keyStatsBoxes.style.display = "none";
      }
    } else if (keyStatsBoxes) {
      keyStatsBoxes.style.display = "none";
    }

    // Officials
    var officialsSection = document.getElementById("modalOfficialsSection");
    var officialsElem = document.getElementById("modalOfficials");
    if (officialsElem && details.officials) {
      var refereeList = (details.officials.referees || []).map(cleanText).filter(Boolean);
      var linesmenList = (details.officials.linesmen || []).map(cleanText).filter(Boolean);
      var officialsHtml = [];
      if (refereeList.length > 0) {
        officialsHtml.push("<div><strong>Domare:</strong> " + escapeHtml(refereeList.join(", ")) + "</div>");
      }
      if (linesmenList.length > 0) {
        officialsHtml.push("<div><strong>Linjedomare:</strong> " + escapeHtml(linesmenList.join(", ")) + "</div>");
      }
      officialsElem.innerHTML = officialsHtml.join("");
      sectionToggle(officialsSection, officialsHtml.length > 0);
    } else {
      sectionToggle(officialsSection, false);
    }

    // Lineups
    var lineupsSection = document.getElementById("modalLineupsSection");
    var lineupsContainer = document.getElementById("modalLineups");
    if (lineupsContainer && details.lineups && details.lineups.teams) {
      var lineupHtml = [];
      for (var t = 0; t < details.lineups.teams.length; t++) {
        var team = details.lineups.teams[t];
        var lines = team.lines || {};
        var lineKeys = ["1st Line", "2nd Line", "3rd Line", "4th Line"];
        var parts = [];

        for (var li = 0; li < lineKeys.length; li++) {
          var lk = lineKeys[li];
          var players = (lines[lk] || []).map(cleanText).filter(Boolean);
          if (players.length === 0) continue;
          parts.push(
            "<div class='modal-line-group'>" +
              "<h5>" + escapeHtml(lk) + "</h5>" +
              "<p>" + escapeHtml(players.join(" | ")) + "</p>" +
            "</div>"
          );
        }

        var gks = (team.goalies || []).map(cleanText).filter(Boolean);
        var extras = (team.extra_players || []).map(cleanText).filter(Boolean);
        var headCoach = cleanText(team.coaches && team.coaches.head ? team.coaches.head : "");
        var assistantCoach = cleanText(team.coaches && team.coaches.assistant ? team.coaches.assistant : "");

        if (gks.length > 0) {
          parts.push(
            "<div class='modal-line-group'>" +
              "<h5>Maalvakter</h5>" +
              "<p>" + escapeHtml(gks.join(" | ")) + "</p>" +
            "</div>"
          );
        }

        if (extras.length > 0) {
          parts.push(
            "<div class='modal-line-group'>" +
              "<h5>Extra players</h5>" +
              "<p>" + escapeHtml(extras.join(" | ")) + "</p>" +
            "</div>"
          );
        }

        if (headCoach || assistantCoach) {
          parts.push(
            "<div class='modal-line-group'>" +
              "<h5>Traenare</h5>" +
              "<p>Head coach: " + escapeHtml(headCoach || "-") + "<br>Assistant coach: " + escapeHtml(assistantCoach || "-") + "</p>" +
            "</div>"
          );
        }

        lineupHtml.push(
          "<article class='modal-lineup-team-card'>" +
            "<h4 class='modal-lineup-team-title'>" + escapeHtml(cleanText(team.team_name || "Lag")) + "</h4>" +
            parts.join("") +
          "</article>"
        );
      }

      lineupsContainer.innerHTML = lineupHtml.join("");
      sectionToggle(lineupsSection, lineupHtml.length > 0);
    } else {
      sectionToggle(lineupsSection, false);
    }

    // Goalkeepers
    var gkSection = document.getElementById("modalGoalkeepersSection");
    var gkContainer = document.getElementById("modalGoalkeepers");
    if (gkContainer && details.goalkeepers) {
      var gkCards = [];
      for (var gkNum in details.goalkeepers) {
        if (!details.goalkeepers.hasOwnProperty(gkNum)) continue;
        var gk = details.goalkeepers[gkNum];
        gkCards.push(
          "<div class='modal-gk-row'>" +
            "<div class='gk-name'>#" + escapeHtml(cleanText(gkNum)) + " " + escapeHtml(cleanText(gk.name || "?")) + " (" + escapeHtml(cleanText(gk.team || "?")) + ")</div>" +
            "<div class='gk-stats'>" + escapeHtml(cleanText(gk.stats || "-")) + "</div>" +
          "</div>"
        );
      }
      gkContainer.innerHTML = gkCards.join("");
      sectionToggle(gkSection, gkCards.length > 0);
    } else {
      sectionToggle(gkSection, false);
    }

    // Events (all events by period)
    var eventsSection = document.getElementById("modalEventsSection");
    var periodsContainer = document.getElementById("modalPeriods");
    if (periodsContainer && details.events_by_period) {
      var periodHtml = [];
      for (var p = 1; p <= 5; p++) {
        var periodKey = "period_" + p;
        var periodEvents = details.events_by_period[periodKey] || [];
        if (periodEvents.length === 0) continue;

        var eventRows = [];
        for (var e = 0; e < periodEvents.length; e++) {
          var evt = periodEvents[e];
          var eventClass = "modal-event";
          var category = cleanText(evt.category || "").toLowerCase();
          if (category === "goal") eventClass += " modal-event-goal";
          if (category === "penalty") eventClass += " modal-event-penalty";
          if (category === "powerbreak") eventClass += " modal-event-break";

          eventRows.push(
            "<div class='" + eventClass + "'>" +
              "<div class='event-time'>" + escapeHtml(cleanText(evt.time || "-")) + "</div>" +
              "<div class='event-main'>" +
                "<div class='event-line'><span class='event-type'>" + escapeHtml(cleanText(evt.type || "-")) + "</span> <span class='event-team'>" + escapeHtml(cleanText(evt.team || "")) + "</span></div>" +
                "<div class='event-player'>" + escapeHtml(cleanText(evt.player || "")) + "</div>" +
                "<div class='event-details'>" + escapeHtml(cleanText(evt.details || "")) + "</div>" +
              "</div>" +
            "</div>"
          );
        }

        periodHtml.push(
          "<section class='modal-period'>" +
            "<h4 class='modal-period-title'>Period " + p + "</h4>" +
            "<div class='modal-events-list'>" + eventRows.join("") + "</div>" +
          "</section>"
        );
      }

      periodsContainer.innerHTML = periodHtml.join("");
      sectionToggle(eventsSection, periodHtml.length > 0);
    } else {
      sectionToggle(eventsSection, false);
    }

    // Reports
    var reportsSection = document.getElementById("modalReportsSection");
    var reportsContainer = document.getElementById("modalReports");
    if (reportsContainer && details.reports && details.reports.length > 0) {
      var reportHtml = [];
      for (var r = 0; r < details.reports.length; r++) {
        var report = details.reports[r];
        reportHtml.push(
          "<a class='modal-report-link' href='" + escapeHtml(cleanText(report.url || "#")) + "' target='_blank' rel='noopener noreferrer'>" +
            "<span class='report-name'>" + escapeHtml(cleanText(report.name || "Rapport")) + "</span>" +
            "<span class='report-time'>" + escapeHtml(cleanText(report.created_at || "")) + "</span>" +
          "</a>"
        );
      }
      reportsContainer.innerHTML = reportHtml.join("");
      sectionToggle(reportsSection, true);
    } else {
      sectionToggle(reportsSection, false);
    }

    // Visa detaljer, dölj laddning
    if (modalLoading) modalLoading.setAttribute("hidden", "");
    if (modalError) modalError.setAttribute("hidden", "");
    modalDetails.removeAttribute("hidden");

    // Initialisera flikar
    initializeModalTabs();
  }

  /**
   * Initialiserar flikväxlings-systemet i modalen.
   */
  function initializeModalTabs() {
    var tabButtons = Array.prototype.slice.call(
      document.querySelectorAll(".modal-tab-btn")
    );
    
    tabButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tabName = btn.getAttribute("data-tab");
        switchModalTab(tabName);
      });
    });
  }

  /**
   * Byter till en specifik flik i modalen.
   */
  function switchModalTab(tabName) {
    // Dölj alla tabs
    var allTabs = Array.prototype.slice.call(
      document.querySelectorAll(".modal-tab-content")
    );
    allTabs.forEach(function (tab) {
      tab.classList.remove("modal-tab-active");
    });

    // Deaktivera alla knappor
    var allButtons = Array.prototype.slice.call(
      document.querySelectorAll(".modal-tab-btn")
    );
    allButtons.forEach(function (btn) {
      btn.classList.remove("modal-tab-active");
    });

    // Aktivera vald tab och knapp
    var activeTab = document.getElementById("tab-" + tabName);
    var activeBtn = document.querySelector("[data-tab='" + tabName + "']");

    if (activeTab) {
      activeTab.classList.add("modal-tab-active");
    }
    if (activeBtn) {
      activeBtn.classList.add("modal-tab-active");
    }
  }

  // Lägg till click-handler på alla matchrader
  if (seriesList) {
    seriesList.addEventListener("click", function (e) {
      var matchRow = e.target.closest(".match-row");
      if (matchRow && !matchRow.disabled) {
        e.preventDefault();
        openMatchModal(matchRow);
      }
    });
  }

  // Stäng modal när close-knapp klickas
  if (modalClose) {
    modalClose.addEventListener("click", closeMatchModal);
  }

  // Stäng modal när overlay klickas
  if (modalOverlay) {
    modalOverlay.addEventListener("click", closeMatchModal);
  }

  // Stäng modal med Escape
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal) {
      closeMatchModal();
    }
  });

  // Starta polling när DOM är redo
  if (
    document.readyState === "complete" ||
    document.readyState === "interactive"
  ) {
    startPolling();
  } else {
    document.addEventListener("DOMContentLoaded", startPolling);
  }
})();

