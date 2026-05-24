// Persist collapse state of highlight and full-list sections.
(function () {
  var ids = ["highlight-section", "full-list"];
  ids.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;

    // Restore saved state
    var saved = localStorage.getItem("brief-" + id);
    if (saved === "closed") {
      el.removeAttribute("open");
    } else if (saved === "open") {
      el.setAttribute("open", "");
    }

    // Save state on toggle
    el.addEventListener("toggle", function () {
      localStorage.setItem("brief-" + id, el.open ? "open" : "closed");
    });
  });
})();
