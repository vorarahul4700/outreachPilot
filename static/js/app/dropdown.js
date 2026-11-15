/* OutreachPilot app: The searchable custom dropdown used for every filter.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

// --- Tactile Custom Dropdown Component Controller (Supports Single & Multi-Select) ---
function initCustomDropdown({ containerId, inputId, defaultLabel, searchPlaceholder, isMulti = false, onSelect }) {
  const container = document.getElementById(containerId);
  if (!container) return null;
  const input = document.getElementById(inputId);
  const btn = container.querySelector(".custom-dropdown-btn");
  const label = container.querySelector(".custom-dropdown-label");
  const searchInput = container.querySelector(".custom-dropdown-search");
  const listEl = container.querySelector(".custom-dropdown-list");

  let currentOptions = [];
  let selectedValues = new Set();
  let selectedValue = "";

  // Parse initial input value
  if (input && input.value) {
    if (isMulti) {
      input.value.split(",").map(v => v.trim()).filter(Boolean).forEach(v => selectedValues.add(v));
    } else {
      selectedValue = input.value.trim();
    }
  }

  // Helper to update the trigger button label
  function updateTriggerLabel() {
    if (isMulti) {
      if (selectedValues.size === 0) {
        label.textContent = defaultLabel;
        btn.removeAttribute("title");
      } else if (selectedValues.size === 1) {
        const onlyVal = Array.from(selectedValues)[0];
        const matched = currentOptions.find(o => o.value === onlyVal);
        const text = matched ? (matched.count ? `${matched.label} (${matched.count})` : matched.label) : onlyVal;
        label.textContent = text;
        btn.setAttribute("title", text);
      } else {
        const baseName = defaultLabel.replace(" (All)", "").replace("All ", "");
        label.textContent = `${baseName} (${selectedValues.size})`;
        const names = Array.from(selectedValues).map(v => {
          const m = currentOptions.find(o => o.value === v);
          return m ? m.label : v;
        }).join(", ");
        btn.setAttribute("title", `${baseName}: ${names}`);
      }
    } else {
      const matched = currentOptions.find(o => o.value === selectedValue);
      if (matched && matched.label) {
        label.textContent = matched.count ? `${matched.label} (${matched.count})` : matched.label;
      } else {
        label.textContent = defaultLabel;
      }
    }
  }

  function renderList(filterQuery = "") {
    if (!listEl) return;
    const q = (filterQuery || "").trim().toLowerCase();
    const filtered = currentOptions.filter(opt => 
      !q || opt.label.toLowerCase().includes(q) || (opt.value && opt.value.toLowerCase().includes(q))
    );

    // Multi-select quick toolbar (Selection count + Clear All action)
    let toolbarHtml = "";
    if (isMulti && selectedValues.size > 0) {
      toolbarHtml = `
        <div class="custom-dropdown-toolbar">
          <span class="text-primary font-semibold">${selectedValues.size} selected</span>
          <button type="button" class="btn-dropdown-clear text-[11px] text-on-surface-variant hover:text-error transition cursor-pointer">Clear all</button>
        </div>
      `;
    }

    if (filtered.length === 0) {
      listEl.innerHTML = `${toolbarHtml}<div class="custom-dropdown-empty">No matching options</div>`;
      attachToolbarEvents();
      return;
    }

    listEl.innerHTML = toolbarHtml + filtered.map(opt => {
      const isSelected = isMulti 
        ? (opt.value ? selectedValues.has(opt.value) : (selectedValues.size === 0))
        : (opt.value === selectedValue);
        
      const countHtml = (opt.count !== undefined && opt.count !== null)
        ? `<span class="count-badge">${opt.count}</span>`
        : '';

      if (isMulti) {
        return `
          <div class="custom-dropdown-item ${isSelected ? 'is-selected' : ''}" data-value="${escapeHTML(opt.value)}">
            <div class="flex items-center min-w-0 flex-1 truncate">
              <span class="custom-dropdown-checkbox ${isSelected && opt.value ? 'is-checked' : ''}">
                <span class="material-symbols-outlined check-icon">check</span>
              </span>
              <span class="truncate ${isSelected && opt.value ? 'font-semibold text-primary' : ''}">${escapeHTML(opt.label)}</span>
            </div>
            ${countHtml}
          </div>
        `;
      } else {
        return `
          <div class="custom-dropdown-item ${isSelected ? 'is-selected' : ''}" data-value="${escapeHTML(opt.value)}">
            <div class="flex items-center min-w-0 flex-1 truncate">
              <span class="material-symbols-outlined check-icon">check</span>
              <span class="truncate">${escapeHTML(opt.label)}</span>
            </div>
            ${countHtml}
          </div>
        `;
      }
    }).join("");

    attachToolbarEvents();

    listEl.querySelectorAll(".custom-dropdown-item").forEach(item => {
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        const val = item.dataset.value;
        if (isMulti) {
          toggleMultiValue(val);
        } else {
          selectValue(val);
          closeDropdown();
        }
      });
    });
  }

  function attachToolbarEvents() {
    const clearBtn = listEl.querySelector(".btn-dropdown-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        clearAll();
      });
    }
  }

  function toggleMultiValue(val) {
    if (!val) {
      selectedValues.clear();
    } else {
      if (selectedValues.has(val)) {
        selectedValues.delete(val);
      } else {
        selectedValues.add(val);
      }
    }
    syncMultiState();
  }

  function clearAll() {
    selectedValues.clear();
    syncMultiState();
  }

  function syncMultiState() {
    const serialized = Array.from(selectedValues).join(",");
    if (input) {
      input.value = serialized;
      input.dispatchEvent(new Event("change"));
    }
    updateTriggerLabel();
    renderList(searchInput ? searchInput.value : "");
    if (onSelect) onSelect(serialized);
  }

  function selectValue(val) {
    selectedValue = (val || "");
    if (input) {
      input.value = selectedValue;
      input.dispatchEvent(new Event("change"));
    }
    updateTriggerLabel();
    renderList(searchInput ? searchInput.value : "");
    if (onSelect) onSelect(selectedValue);
  }

  function openDropdown() {
    document.querySelectorAll(".custom-dropdown.is-open").forEach(d => {
      if (d !== container) d.classList.remove("is-open");
    });
    container.classList.add("is-open");
    if (btn) btn.setAttribute("aria-expanded", "true");
    if (searchInput) {
      searchInput.value = "";
      renderList("");
      setTimeout(() => searchInput.focus(), 60);
    } else {
      renderList("");
    }
  }

  function closeDropdown() {
    container.classList.remove("is-open");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  if (btn) {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (container.classList.contains("is-open")) {
        closeDropdown();
      } else {
        openDropdown();
      }
    });
  }

  if (searchInput) {
    let searchDebounce = null;
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        renderList(e.target.value);
      }, 120);
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeDropdown();
      }
    });
  }

  document.addEventListener("click", (e) => {
    if (!container.contains(e.target)) {
      closeDropdown();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && container.classList.contains("is-open")) {
      closeDropdown();
    }
  });

  return {
    setOptions(newOptions) {
      currentOptions = newOptions || [];
      updateTriggerLabel();
      renderList();
    },
    setValue(val) {
      if (isMulti) {
        selectedValues.clear();
        if (Array.isArray(val)) {
          val.forEach(v => selectedValues.add(v.trim()));
        } else if (typeof val === "string" && val.trim()) {
          val.split(",").forEach(v => selectedValues.add(v.trim()));
        }
        syncMultiState();
      } else {
        selectValue(val);
      }
    },
    getValue() {
      return isMulti ? Array.from(selectedValues).join(",") : selectedValue;
    },
    getValues() {
      return isMulti ? Array.from(selectedValues) : (selectedValue ? [selectedValue] : []);
    },
    reset() {
      if (isMulti) {
        clearAll();
      } else {
        selectValue("");
      }
    }
  };
}
