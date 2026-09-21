/* Theme handling. Loaded in <head> so the theme is set before first paint. */
(function () {
  "use strict";

  var KEY = "documind-theme";
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function saved() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function syncButtons(theme) {
    var next = theme === "dark" ? "light" : "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-label", "Switch to " + next + " theme");
      btn.setAttribute("title", "Switch to " + next + " theme");
    });
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    syncButtons(theme);
  }

  apply(saved() || (media.matches ? "dark" : "light"));
  document.addEventListener("DOMContentLoaded", function () {
    syncButtons(root.getAttribute("data-theme"));
  });

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    apply(next);
    try { localStorage.setItem(KEY, next); } catch (err) { /* storage unavailable */ }
  });

  // Follow the OS setting until the person picks a theme themselves.
  var onSystemChange = function (e) {
    if (!saved()) apply(e.matches ? "dark" : "light");
  };
  if (media.addEventListener) media.addEventListener("change", onSystemChange);
})();
