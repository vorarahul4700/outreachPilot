/* OutreachPilot admin: Static filter dropdowns and sortable table headers.
   Moved unchanged out of static/js/admin.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before admin.js. */

// --- Reusable Custom Dropdown Component Controller ---
function initStaticCustomDropdown(containerId, onSelectCallback) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const btn = container.querySelector(".custom-dropdown-btn");
  const label = container.querySelector(".custom-dropdown-label");
  const hiddenInput = container.querySelector("input[type='hidden']");
  const items = container.querySelectorAll(".custom-dropdown-item");

  if (btn) {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = container.classList.contains("is-open");
      document.querySelectorAll(".custom-dropdown.is-open").forEach(d => {
        if (d !== container) d.classList.remove("is-open");
      });
      container.classList.toggle("is-open", !isOpen);
      btn.setAttribute("aria-expanded", String(!isOpen));
    });
  }

  items.forEach(item => {
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      const val = item.getAttribute("data-value") !== null ? item.getAttribute("data-value") : "";
      const itemText = item.querySelector(".truncate")?.textContent?.trim() || item.textContent.trim();

      if (hiddenInput) {
        hiddenInput.value = val;
        hiddenInput.dispatchEvent(new Event("change"));
      }
      if (label) {
        label.textContent = itemText;
      }

      items.forEach(it => it.classList.remove("is-selected"));
      item.classList.add("is-selected");

      container.classList.remove("is-open");
      if (btn) btn.setAttribute("aria-expanded", "false");

      if (onSelectCallback) onSelectCallback(val);
    });
  });
}

// --- Header Sorting Helper ---
function updateHeaderSortIcons(selector, activeSort, activeOrder) {
  document.querySelectorAll(selector).forEach(th => {
    const sortKey = th.getAttribute("data-sort");
    const icon = th.querySelector(".sort-icon");
    if (!icon) return;

    if (sortKey === activeSort) {
      th.classList.add("text-primary");
      th.classList.remove("text-on-surface-variant");
      icon.textContent = activeOrder === "asc" ? "arrow_upward" : "arrow_downward";
      icon.className = "material-symbols-outlined text-[15px] sort-icon text-primary font-bold";
    } else {
      th.classList.remove("text-primary");
      th.classList.add("text-on-surface-variant");
      icon.textContent = "unfold_more";
      icon.className = "material-symbols-outlined text-[15px] sort-icon text-on-surface-variant/40 group-hover:text-on-surface-variant transition-colors";
    }
  });
}
