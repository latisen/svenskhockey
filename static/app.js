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

  /**
   * Hämtar uppdateringar från API:t och uppdaterar matchkorten.
   */
  function pollForUpdates() {
    fetch("/api/matches", {
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
        } else {
          badge.classList.add("badge-upcoming");
        }
      }

      // Uppdatera CSS-klass på rad
      row.classList.remove("match-played", "match-upcoming");
      if (updatedMatch.status === "Färdigspelad") {
        row.classList.add("match-played");
      } else {
        row.classList.add("match-upcoming");
      }
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

  /**
   * Starta polling när sidan laddat. Uppdatera var 30:e sekund.
   */
  function startPolling() {
    // Första uppdatering efter 30 sekunder
    pollInterval = setInterval(pollForUpdates, 30000);
  }

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

