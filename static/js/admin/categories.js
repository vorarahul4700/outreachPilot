/* OutreachPilot admin: Categories tab.
   Switch a category (and every company in it) on or off for users. Hidden
   categories disappear from the workspace, the public directory, company
   profiles and sitemaps; nothing is deleted. Load before admin.js, which calls
   loadCategoryVisibility(showToast) when the tab opens. */

const catvisState = { data: null, filter: "all", query: "", toast: null, bound: false, busy: false };

function catvisEscape(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function catvisFormat(n) {
  return Number(n || 0).toLocaleString("en-IN");
}

function catvisNotify(message, type) {
  if (typeof catvisState.toast === "function") catvisState.toast(message, type);
}

async function loadCategoryVisibility(toast) {
  if (typeof toast === "function") catvisState.toast = toast;
  bindCategoryVisibilityControls();
  const groups = document.getElementById("catvis-groups");
  if (!catvisState.data && groups) {
    groups.innerHTML = `<div class="a-card catvis-empty">Loading categories...</div>`;
  }
  try {
    const res = await fetch("/api/admin/categories");
    if (!res.ok) throw new Error(`The server answered ${res.status}`);
    catvisState.data = await res.json();
    renderCategoryVisibility();
  } catch (err) {
    if (groups) {
      groups.innerHTML = `<div class="a-card catvis-empty">Could not load categories. ${catvisEscape(err.message)}</div>`;
    }
  }
}

function bindCategoryVisibilityControls() {
  if (catvisState.bound) return;
  catvisState.bound = true;

  document.getElementById("catvis-search")?.addEventListener("input", (e) => {
    catvisState.query = (e.target.value || "").trim().toLowerCase();
    renderCategoryVisibility();
  });

  document.querySelectorAll(".catvis-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      catvisState.filter = btn.getAttribute("data-filter") || "all";
      document.querySelectorAll(".catvis-filter").forEach((b) => {
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
      renderCategoryVisibility();
    });
  });

  document.getElementById("btn-refresh-catvis")?.addEventListener("click", () => loadCategoryVisibility());

  const groups = document.getElementById("catvis-groups");
  if (!groups) return;

  // One switch: apply straight away (it is reversible).
  groups.addEventListener("change", (e) => {
    const input = e.target.closest(".catvis-toggle");
    if (!input) return;
    const slug = input.getAttribute("data-slug");
    const shown = input.checked;
    setCategoryVisibility([slug], !shown, input);
  });

  // Whole industry: confirm first, because it can hide thousands of companies.
  groups.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-catvis-group]");
    if (!btn || !catvisState.data) return;
    const domain = btn.getAttribute("data-domain");
    const hide = btn.getAttribute("data-catvis-group") === "hide";
    const members = catvisState.data.categories.filter((c) => c.domain === domain && c.hidden !== hide);
    if (!members.length) return;
    const companies = members.reduce((sum, c) => sum + (c.count || 0), 0);
    const question = hide
      ? `Hide ${members.length} categories in ${domain}? ${catvisFormat(companies)} companies will disappear from the workspace and the public directory. You can switch them back on at any time.`
      : `Show ${members.length} hidden categories in ${domain} again? ${catvisFormat(companies)} companies will be visible to users.`;
    if (!window.confirm(question)) return;
    setCategoryVisibility(members.map((c) => c.slug), hide, null);
  });
}

async function setCategoryVisibility(slugs, hidden, input) {
  if (catvisState.busy) {
    if (input) input.checked = !input.checked; // undo the click; one change at a time
    return;
  }
  catvisState.busy = true;
  if (input) input.disabled = true;
  try {
    const res = await fetch("/api/admin/categories/visibility", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slugs, hidden }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `The server answered ${res.status}`);
    catvisState.data = data;
    renderCategoryVisibility();
    catvisNotify(data.message || "Saved", hidden ? "warning" : "success");
  } catch (err) {
    if (input) input.checked = !input.checked; // put the switch back
    catvisNotify(`Could not save: ${err.message}`, "error");
  } finally {
    catvisState.busy = false;
    if (input) input.disabled = false;
  }
}

function renderCategoryVisibility() {
  const data = catvisState.data;
  const groups = document.getElementById("catvis-groups");
  if (!data || !groups) return;

  // Summary pill and sidebar badge
  const summary = document.getElementById("catvis-summary");
  if (summary) {
    if (data.hidden_categories) {
      summary.textContent = `${data.hidden_categories} hidden, ${catvisFormat(data.hidden_companies)} companies hidden`;
      summary.classList.add("is-warn");
    } else {
      summary.textContent = `All ${data.total_categories} categories shown`;
      summary.classList.remove("is-warn");
    }
  }
  const badge = document.getElementById("badge-hidden-categories");
  if (badge) {
    badge.textContent = `${data.hidden_categories} hidden`;
    badge.classList.toggle("hidden", !data.hidden_categories);
  }

  // Filter, then group by industry (biggest industry first)
  const q = catvisState.query;
  const rows = data.categories.filter((c) => {
    if (catvisState.filter === "shown" && c.hidden) return false;
    if (catvisState.filter === "hidden" && !c.hidden) return false;
    if (!q) return true;
    return c.name.toLowerCase().includes(q) || (c.domain || "").toLowerCase().includes(q);
  });

  if (!rows.length) {
    const msg = catvisState.filter === "hidden" && !q
      ? "No hidden categories. Every category is shown to users."
      : "No categories match.";
    groups.innerHTML = `<div class="a-card catvis-empty">${msg}</div>`;
    return;
  }

  const byDomain = new Map();
  rows.forEach((c) => {
    const key = c.domain || "Other";
    if (!byDomain.has(key)) byDomain.set(key, []);
    byDomain.get(key).push(c);
  });
  const allByDomain = new Map();
  data.categories.forEach((c) => {
    const key = c.domain || "Other";
    if (!allByDomain.has(key)) allByDomain.set(key, []);
    allByDomain.get(key).push(c);
  });

  const ordered = [...byDomain.entries()].sort((a, b) => {
    const total = (list) => list.reduce((s, c) => s + (c.count || 0), 0);
    return total(allByDomain.get(b[0]) || []) - total(allByDomain.get(a[0]) || []);
  });

  groups.innerHTML = ordered.map(([domain, list]) => {
    const all = allByDomain.get(domain) || list;
    const shownCount = all.filter((c) => !c.hidden).length;
    const companies = all.reduce((s, c) => s + (c.count || 0), 0);
    const anyShown = all.some((c) => !c.hidden);
    const anyHidden = all.some((c) => c.hidden);
    const d = catvisEscape(domain);
    const body = list.map((c) => {
      const label = catvisEscape(c.name);
      return `
        <tr class="${c.hidden ? "is-hidden" : ""}">
          <td>
            <span class="catvis-name">${label}</span>
            ${c.hidden ? `<span class="chip chip-sm chip-soft">Hidden</span>` : ""}
          </td>
          <td class="num tnum">${catvisFormat(c.count)}</td>
          <td class="num">
            <label class="switch" title="${c.hidden ? "Hidden from users. Switch on to show" : "Shown to users. Switch off to hide"}">
              <input type="checkbox" class="catvis-toggle" data-slug="${catvisEscape(c.slug)}" ${c.hidden ? "" : "checked"} aria-label="Show ${label} to users">
              <span class="track"></span>
            </label>
          </td>
        </tr>`;
    }).join("");
    return `
      <div class="a-table-wrap catvis-group">
        <div class="catvis-head">
          <div>
            <b>${d}</b>
            <span class="meta">${shownCount} of ${all.length} shown, ${catvisFormat(companies)} companies</span>
          </div>
          <div class="acts">
            ${anyShown ? `<button type="button" class="btn btn-secondary btn-sm" data-catvis-group="hide" data-domain="${d}">Hide all</button>` : ""}
            ${anyHidden ? `<button type="button" class="btn btn-secondary btn-sm" data-catvis-group="show" data-domain="${d}">Show all</button>` : ""}
          </div>
        </div>
        <div class="scroll">
          <table class="a-table catvis-table">
            <thead><tr><th>Category</th><th class="num">Companies</th><th class="num">Shown to users</th></tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>`;
  }).join("");
}
