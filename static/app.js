/**
 * app.js – Klientsidelogik för Svenska Hockeymatcher
 *
 * Funktioner:
 *  1. Livesökning – filtrera matchrader och sektioner i realtid
 *  2. Rensa-knapp för sökrutan
 *  3. Laddningsindikator på reload-knappen
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

})();
