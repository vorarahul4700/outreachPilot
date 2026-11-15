/* Theme toggle for public pages.
   Same behavior as the previous inline scripts: html.light / html.dark classes,
   localStorage key "pilot_theme", light by default, follows the system only
   while the user has not picked a theme. The pre-paint boot lives in
   templates/partials/theme_boot.html. */

function updateThemeIcon(theme) {
  var isLight = theme === "light";
  var icon = document.getElementById("theme-toggle-icon");
  if (icon) icon.textContent = isLight ? "dark_mode" : "light_mode";
  var btn = document.getElementById("btn-theme-toggle");
  if (btn) {
    var label = isLight ? "Switch to dark mode" : "Switch to light mode";
    btn.setAttribute("title", label);
    btn.setAttribute("aria-label", label);
  }
}

function applyTheme(theme) {
  var root = document.documentElement;
  if (theme === "light") {
    root.classList.remove("dark");
    root.classList.add("light");
  } else {
    root.classList.remove("light");
    root.classList.add("dark");
  }
  updateThemeIcon(theme);
}

function toggleTheme() {
  var next = document.documentElement.classList.contains("light") ? "dark" : "light";
  applyTheme(next);
  try { localStorage.setItem("pilot_theme", next); } catch (_) {}
}

(function () {
  var btn = document.getElementById("btn-theme-toggle");
  if (btn) btn.addEventListener("click", toggleTheme);
  updateThemeIcon(document.documentElement.classList.contains("light") ? "light" : "dark");

  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function (e) {
      var saved = null;
      try { saved = localStorage.getItem("pilot_theme"); } catch (_) {}
      if (!saved) applyTheme(e.matches ? "dark" : "light");
    });
  }
})();
