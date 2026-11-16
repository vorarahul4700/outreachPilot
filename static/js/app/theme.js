/* OutreachPilot app: Light and dark theme toggle for the workspace.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

// --- Dark / Light Theme Mode Toggle (Sun / Moon icon only) ---
function updateThemeIcons(theme) {
  const isLight = theme === "light";
  const iconName = isLight ? "dark_mode" : "light_mode";
  const titleText = isLight ? "Switch to Dark Mode" : "Switch to Light Mode";
  const toggleIcon = document.getElementById("theme-toggle-icon");
  if (toggleIcon) toggleIcon.textContent = iconName;
  document.querySelectorAll(".theme-toggle-icon-mobile").forEach(el => {
    el.textContent = iconName;
  });
  document.querySelectorAll("#btn-theme-toggle, #btn-theme-toggle-mobile").forEach(el => {
    el.setAttribute("title", titleText);
    el.setAttribute("aria-label", titleText);
  });
}

function toggleThemeMode() {
  const isCurrentlyLight = document.documentElement.classList.contains("light");
  const newTheme = isCurrentlyLight ? "dark" : "light";
  if (newTheme === "light") {
    document.documentElement.classList.remove("dark");
    document.documentElement.classList.add("light");
  } else {
    document.documentElement.classList.remove("light");
    document.documentElement.classList.add("dark");
  }
  try {
    localStorage.setItem("pilot_theme", newTheme);
  } catch (_) {}
  updateThemeIcons(newTheme);
  refreshIcons();
}
