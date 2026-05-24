// Persist collapse state of highlight and full-list sections.
(function () {
  var ids = ["highlight-section", "full-list"];
  ids.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    var saved = localStorage.getItem("brief-" + id);
    if (saved === "closed") {
      el.removeAttribute("open");
    } else if (saved === "open") {
      el.setAttribute("open", "");
    }
    el.addEventListener("toggle", function () {
      localStorage.setItem("brief-" + id, el.open ? "open" : "closed");
    });
  });
})();

// Conference countdown timer.
(function () {
  var data = window.__COUNTDOWN_DATA__;
  if (!data || !data.length) return;

  var grid = document.getElementById("countdown-grid");
  if (!grid) return;

  function render() {
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    // Filter: keep only conferences whose end date hasn't passed
    var upcoming = [];
    data.forEach(function (conf) {
      var end = new Date(conf.end + "T23:59:59");
      if (end >= today) {
        upcoming.push(conf);
      }
    });

    // Sort by start date ascending
    upcoming.sort(function (a, b) {
      return new Date(a.start) - new Date(b.start);
    });

    if (upcoming.length === 0) {
      grid.innerHTML = '<span class="countdown-empty">暂无即将召开的大会。</span>';
      return;
    }

    grid.innerHTML = upcoming.map(function (conf) {
      var start = new Date(conf.start + "T00:00:00");
      var diff = start - now;

      var cardClass = "countdown-card";
      if (diff <= 0) {
        cardClass += " urgent";  // ongoing or starts today
      } else if (diff < 7 * 24 * 3600 * 1000) {
        cardClass += " urgent";
      } else if (diff < 30 * 24 * 3600 * 1000) {
        cardClass += " soon";
      } else {
        cardClass += " distant";
      }

      var timerHtml;
      if (diff <= 0) {
        timerHtml = "进行中";
      } else {
        var days = Math.floor(diff / (24 * 3600 * 1000));
        var hours = Math.floor((diff % (24 * 3600 * 1000)) / (3600 * 1000));
        var mins = Math.floor((diff % (3600 * 1000)) / (60 * 1000));
        var secs = Math.floor((diff % (60 * 1000)) / 1000);
        timerHtml = "还有 " + days + " 天 " +
          (hours < 10 ? "0" : "") + hours + ":" +
          (mins < 10 ? "0" : "") + mins + ":" +
          (secs < 10 ? "0" : "") + secs;
      }

      var nameHtml = conf.url
        ? '<a href="' + conf.url + '" target="_blank" rel="noopener">' + conf.name + "</a>"
        : conf.name;

      var dateStr = conf.start.slice(5) + " — " + conf.end.slice(5);

      return (
        '<div class="' + cardClass + '">' +
        '<div class="countdown-card-name">' + nameHtml + "</div>" +
        '<div class="countdown-card-meta">' + conf.cn + "</div>" +
        '<div class="countdown-card-meta">' + dateStr + " &middot; " + conf.loc + "</div>" +
        '<div class="countdown-card-timer">' + timerHtml + "</div>" +
        "</div>"
      );
    }).join("");
  }

  render();
  setInterval(render, 1000);
})();
