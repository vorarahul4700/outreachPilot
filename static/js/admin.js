/**
 * OutreachPilot - Master Admin Panel Client Controller
 * File: static/js/admin.js
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- Theme Management (Exact Match with /app) ---
  const themeBtn = document.getElementById("btn-theme-toggle");
  const themeIcon = document.getElementById("theme-toggle-icon");

  function updateThemeIcon() {
    const isDark = document.documentElement.classList.contains("dark");
    if (themeIcon) {
      themeIcon.textContent = isDark ? "light_mode" : "dark_mode";
    }
  }
  updateThemeIcon();

  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const isDark = document.documentElement.classList.contains("dark");
      if (isDark) {
        document.documentElement.classList.remove("dark");
        document.documentElement.classList.add("light");
        localStorage.setItem("pilot_theme", "light");
      } else {
        document.documentElement.classList.add("dark");
        document.documentElement.classList.remove("light");
        localStorage.setItem("pilot_theme", "dark");
      }
      updateThemeIcon();
    });
  }

  // --- Toast Notifications ---
  const toastContainer = document.getElementById("admin-toast-container");
  function showToast(message, type = "success") {
    if (!toastContainer) return;
    const toast = document.createElement("div");
    const bgClass = type === "error" 
      ? "bg-rose-500 text-white" 
      : type === "warning"
      ? "bg-amber-500 text-white"
      : "bg-surface-container-highest text-on-surface border border-outline-variant/50";

    toast.className = `px-4 py-3 rounded-xl shadow-xl flex items-center gap-3 text-xs font-semibold tracking-wide transition-all transform duration-300 pointer-events-auto ${bgClass}`;
    toast.innerHTML = `
      <span class="material-symbols-outlined text-[18px]">${type === "error" ? "error" : type === "warning" ? "warning" : "check_circle"}</span>
      <span>${message}</span>
    `;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- Tab Navigation ---
  const tabButtons = document.querySelectorAll(".admin-tab-btn");
  const tabPanels = document.querySelectorAll(".admin-tab-panel");
  const currentViewTitle = document.getElementById("current-view-title");
  const headerHeading = document.getElementById("header-heading");

  const tabMeta = {
    overview: { title: "Overview", heading: "Telemetry & System Controls" },
    users: { title: "Users", heading: "User Accounts & Role Governance" },
    companies: { title: "Companies", heading: "Directory Pipeline & Quarantined Leads" },
    subscriptions: { title: "Subscriptions", heading: "Tier Quotas & Monetization Architecture" },
    pitches: { title: "Sent Pitches", heading: "Cold Outreach Pitches & Delivery Telemetry" },
    github: { title: "GitHub Actions", heading: "CI/CD Telemetry & Workflows" }
  };

  function switchTab(tabId) {
    tabButtons.forEach(btn => {
      if (btn.getAttribute("data-tab") === tabId) {
        btn.classList.add("active", "bg-primary-container", "text-on-primary-container");
        btn.classList.remove("text-on-surface-variant");
      } else {
        btn.classList.remove("active", "bg-primary-container", "text-on-primary-container");
        btn.classList.add("text-on-surface-variant");
      }
    });

    tabPanels.forEach(panel => {
      if (panel.id === `tab-content-${tabId}`) {
        panel.classList.remove("hidden");
      } else {
        panel.classList.add("hidden");
      }
    });

    if (tabMeta[tabId]) {
      if (currentViewTitle) currentViewTitle.textContent = tabMeta[tabId].title;
      if (headerHeading) headerHeading.textContent = tabMeta[tabId].heading;
    }

    if (tabId === "users") loadUsers(1);
    if (tabId === "companies") {
      loadActiveCompanies(1);
      loadInvalidCompanies(1);
    }
    if (tabId === "overview") loadKillSwitchStatus();
    if (tabId === "subscriptions") {
      loadTiers();
      loadKillSwitchStatus();
    }
    if (tabId === "pitches") loadAdminPitches(1);
    if (tabId === "github") loadGitHubTelemetry();
  }

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const tabId = btn.getAttribute("data-tab");
      switchTab(tabId);
    });
  });

  // KPI Metric Cards Interactive Routing & Navigation
  document.getElementById("card-kpi-users")?.addEventListener("click", () => switchTab("users"));
  document.getElementById("card-kpi-companies")?.addEventListener("click", () => switchTab("companies"));
  document.getElementById("card-kpi-pitches")?.addEventListener("click", () => {
    activePitchFilter = "today";
    if (typeof updatePitchFilterTabsUI === "function") updatePitchFilterTabsUI();
    switchTab("pitches");
  });
  document.getElementById("card-kpi-subs")?.addEventListener("click", () => switchTab("subscriptions"));

  // Quick action shortcut buttons on Overview
  document.getElementById("btn-quick-add-company")?.addEventListener("click", () => openModal("modal-add-company"));
  document.getElementById("btn-quick-csv-upload")?.addEventListener("click", () => openModal("modal-bulk-csv"));
  document.getElementById("btn-quick-view-invalid")?.addEventListener("click", () => switchTab("companies"));

  // --- Modal Helpers with Non-Scrollable Background Enforcement ---
  function updateBodyScrollLock() {
    const activeModals = document.querySelectorAll(".fixed[id^='modal-']:not(.hidden)");
    if (activeModals.length > 0) {
      document.body.classList.add("overflow-hidden");
      document.documentElement.classList.add("overflow-hidden");
    } else {
      document.body.classList.remove("overflow-hidden");
      document.documentElement.classList.remove("overflow-hidden");
    }
  }

  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.remove("hidden");
      updateBodyScrollLock();
    }
  }

  function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.add("hidden");
    }
    updateBodyScrollLock();
  }

  document.querySelectorAll(".modal-close").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const modal = e.target.closest(".fixed");
      if (modal) modal.classList.add("hidden");
      updateBodyScrollLock();
    });
  });

  // Close modals when clicking outer semi-transparent backdrop
  document.querySelectorAll(".fixed[id^='modal-']").forEach(modal => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        modal.classList.add("hidden");
        updateBodyScrollLock();
      }
    });
  });

  // Close modals on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".fixed[id^='modal-']:not(.hidden)").forEach(m => m.classList.add("hidden"));
      updateBodyScrollLock();
    }
  });

  // Automatic scroll lock observer for all admin modals
  try {
    const adminModalObserver = new MutationObserver(() => updateBodyScrollLock());
    document.querySelectorAll(".fixed[id^='modal-'], #admin-mobile-backdrop").forEach(el => {
      adminModalObserver.observe(el, { attributes: true, attributeFilter: ["class"] });
    });
  } catch (e) {}

  document.getElementById("btn-open-add-company-modal")?.addEventListener("click", () => openModal("modal-add-company"));
  document.getElementById("btn-open-csv-upload-modal")?.addEventListener("click", () => openModal("modal-bulk-csv"));

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

  // Global close custom dropdown on click outside
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".custom-dropdown")) {
      document.querySelectorAll(".custom-dropdown.is-open").forEach(d => {
        d.classList.remove("is-open");
        const b = d.querySelector(".custom-dropdown-btn");
        if (b) b.setAttribute("aria-expanded", "false");
      });
    }
  });

  // Wire up Custom Dropdowns
  initStaticCustomDropdown("dropdown-filter-category", (val) => {
    loadActiveCompanies(1);
  });
  initStaticCustomDropdown("dropdown-filter-tier", (val) => {
    loadUsers(1);
  });
  initStaticCustomDropdown("dropdown-filter-role", (val) => {
    loadUsers(1);
  });

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

  // --- API: Load Overview Metrics ---
  async function loadMetrics() {
    try {
      const res = await fetch("/api/admin/metrics");
      if (!res.ok) throw new Error("Failed to load metrics");
      const data = await res.json();

      // Update KPI cards safely
      const elTotalUsers = document.getElementById("kpi-total-users");
      if (elTotalUsers) elTotalUsers.textContent = (data.users_total || 0).toLocaleString();

      const elActiveUsers = document.getElementById("kpi-active-users");
      if (elActiveUsers) elActiveUsers.textContent = `${(data.users_with_oauth || 0).toLocaleString()} active`;

      const elMasterAdmins = document.getElementById("kpi-master-admins");
      if (elMasterAdmins) elMasterAdmins.textContent = (data.master_admins || 0).toLocaleString();

      const elTotalComps = document.getElementById("kpi-total-companies");
      if (elTotalComps) elTotalComps.textContent = (data.companies_valid || 0).toLocaleString();

      const elVerifiedEmails = document.getElementById("kpi-verified-emails");
      if (elVerifiedEmails) elVerifiedEmails.textContent = (data.verified_emails || 0).toLocaleString();

      const elPitchesToday = document.getElementById("kpi-pitches-today");
      if (elPitchesToday) elPitchesToday.textContent = (data.pitches_sent_today || 0).toLocaleString();

      const badgePitchesCount = document.getElementById("badge-pitches-count");
      if (badgePitchesCount) badgePitchesCount.textContent = `${data.pitches_sent_today || 0} today`;

      const activeSubs = (data.subscribers_pro || 0) + (data.subscribers_premium_plus || 0);
      const elActiveSubs = document.getElementById("kpi-active-subs");
      if (elActiveSubs) elActiveSubs.textContent = activeSubs.toLocaleString();

      const elSubBreakdown = document.getElementById("kpi-sub-breakdown");
      if (elSubBreakdown) elSubBreakdown.textContent = `${data.subscribers_pro || 0} Pro / ${data.subscribers_premium_plus || 0} Prem+`;

      const elFreeUsers = document.getElementById("kpi-free-users");
      if (elFreeUsers) elFreeUsers.textContent = (data.subscribers_free || 0).toLocaleString();

      const invalidCount = data.companies_invalid || 0;
      const elInvalidSummary = document.getElementById("kpi-invalid-summary");
      if (elInvalidSummary) elInvalidSummary.textContent = `${invalidCount.toLocaleString()} entities quarantined`;

      const badgeInvalid = document.getElementById("badge-invalid-count");
      if (badgeInvalid) badgeInvalid.textContent = invalidCount.toLocaleString();

      const badgeActiveComps = document.getElementById("badge-active-comps-count");
      if (badgeActiveComps) badgeActiveComps.textContent = (data.companies_valid || 0).toLocaleString();

      const badgeUsersCount = document.getElementById("badge-users-count");
      if (badgeUsersCount) badgeUsersCount.textContent = (data.users_total || 0).toLocaleString();

      // Update Subscriptions matrix counts if static cards present
      const elPlanFree = document.getElementById("plan-count-free");
      if (elPlanFree) elPlanFree.textContent = (data.subscribers_free || 0).toLocaleString();

      const elPlanPro = document.getElementById("plan-count-pro");
      if (elPlanPro) elPlanPro.textContent = (data.subscribers_pro || 0).toLocaleString();

      const elPlanPrem = document.getElementById("plan-count-premium");
      if (elPlanPrem) elPlanPrem.textContent = (data.subscribers_premium_plus || 0).toLocaleString();

      const elPlanAdmin = document.getElementById("plan-count-admin");
      if (elPlanAdmin) elPlanAdmin.textContent = (data.master_admins || 0).toLocaleString();

    } catch (err) {
      console.error("Error loading metrics:", err);
      showToast("Could not sync latest metrics", "warning");
    }
  }

  document.getElementById("btn-refresh-data")?.addEventListener("click", () => {
    loadMetrics();
    showToast("Synced with Neon PostgreSQL Cloud");
  });

  // --- API: Load Users ---
  let usersCurrentPage = 1;
  const usersTableBody = document.getElementById("users-table-body");
  const usersPageInfo = document.getElementById("users-page-info");
  const usersBtnPrev = document.getElementById("users-btn-prev");
  const usersBtnNext = document.getElementById("users-btn-next");
  const usersSearchInput = document.getElementById("users-search");
  const usersFilterTier = document.getElementById("users-filter-tier");
  const usersFilterRole = document.getElementById("users-filter-role");

  let usersSortBy = "id";
  let usersSortOrder = "desc";

  async function loadUsers(page = 1) {
    usersCurrentPage = page;
    const search = usersSearchInput ? usersSearchInput.value.trim() : "";
    const tier = usersFilterTier ? usersFilterTier.value : "";
    const role = usersFilterRole ? usersFilterRole.value : "";

    usersTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant">Loading user directory...</td></tr>`;

    try {
      const url = `/api/admin/users?page=${page}&page_size=15&search=${encodeURIComponent(search)}&tier=${encodeURIComponent(tier)}&role=${encodeURIComponent(role)}&sort_by=${encodeURIComponent(usersSortBy)}&sort_order=${encodeURIComponent(usersSortOrder)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch users");
      const data = await res.json();
      updateHeaderSortIcons(".sortable-user-header", usersSortBy, usersSortOrder);

      if (!data.users || data.users.length === 0) {
        usersTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant">No matching users found.</td></tr>`;
        usersPageInfo.textContent = `Page ${page} of 1`;
        usersBtnPrev.disabled = true;
        usersBtnNext.disabled = true;
        return;
      }

      usersPageInfo.textContent = `Page ${data.current_page} of ${data.total_pages} (${data.total_count} total)`;
      usersBtnPrev.disabled = data.current_page <= 1;
      usersBtnNext.disabled = data.current_page >= data.total_pages;

      usersTableBody.innerHTML = data.users.map(u => {
        const isAdmin = u.is_admin;
        const isBanned = u.is_banned;
        const tierName = u.subscription_tier || "free";
        const tierBadge = tierName === "premium_plus"
          ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-500/20 text-emerald-400">Premium+ (100)</span>`
          : tierName === "pro"
          ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-blue-500/20 text-blue-400">Pro (50)</span>`
          : `<span class="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-surface-container-highest text-on-surface-variant">Free (10)</span>`;

        const roleBadge = isAdmin
          ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-500/20 text-amber-500 border border-amber-500/40">★ Master Admin</span>`
          : `<span class="px-2 py-0.5 rounded text-[11px] font-mono text-on-surface-variant">User</span>`;

        const quotaDisplay = isAdmin
          ? `<span class="text-amber-500 font-mono font-semibold">∞ Infinite</span>`
          : `<span class="font-mono text-xs">${u.pitches_sent_today || 0} / ${u.daily_pitch_limit || 10}</span>`;

        const statusBadge = isBanned
          ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-rose-500/20 text-rose-400 font-semibold">Suspended</span>`
          : `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-500/10 text-emerald-500">Active</span>`;

        return `
          <tr class="hover:bg-surface-container/50 transition">
            <td class="px-4 py-3">
              <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
                  ${(u.name || u.email)[0].toUpperCase()}
                </div>
                <div class="flex flex-col min-w-0">
                  <span class="font-semibold text-on-surface truncate text-xs">${u.name || "User"}</span>
                  <span class="text-[11px] font-mono text-on-surface-variant truncate">${u.email}</span>
                </div>
              </div>
            </td>
            <td class="px-4 py-3">${roleBadge}</td>
            <td class="px-4 py-3">${tierBadge}</td>
            <td class="px-4 py-3">${quotaDisplay}</td>
            <td class="px-4 py-3">${statusBadge}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-1.5">
                <button onclick="toggleUserAdmin(${u.id}, ${isAdmin})" class="px-2 py-1 rounded text-[11px] font-medium border border-outline-variant/40 hover:bg-surface-container transition" title="${isAdmin ? 'Revoke Admin' : 'Promote to Master Admin'}">
                  ${isAdmin ? 'Demote' : 'Make Admin'}
                </button>
                <button onclick="openEditPlanModal(${u.id}, '${u.email}', '${tierName}')" class="px-2 py-1 rounded text-[11px] font-medium border border-outline-variant/40 hover:bg-surface-container transition">
                  Plan
                </button>
                <button onclick="toggleUserBan(${u.id}, ${isBanned})" class="px-2 py-1 rounded text-[11px] font-medium border ${isBanned ? 'border-emerald-500/40 text-emerald-500' : 'border-rose-500/40 text-rose-500'} hover:bg-surface-container transition">
                  ${isBanned ? 'Unban' : 'Ban'}
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading users:", err);
      usersTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-rose-500">Failed to load users: ${err.message}</td></tr>`;
    }
  }

  // Users Filter Listeners with Debounce
  let searchTimeout = null;
  usersSearchInput?.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => loadUsers(1), 300);
  });
  usersFilterTier?.addEventListener("change", () => loadUsers(1));
  usersFilterRole?.addEventListener("change", () => loadUsers(1));
  usersBtnPrev?.addEventListener("click", () => { if (usersCurrentPage > 1) loadUsers(usersCurrentPage - 1); });
  usersBtnNext?.addEventListener("click", () => { loadUsers(usersCurrentPage + 1); });

  // Users Sortable Headers Listener
  document.querySelectorAll(".sortable-user-header").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.getAttribute("data-sort");
      if (usersSortBy === col) {
        usersSortOrder = usersSortOrder === "asc" ? "desc" : "asc";
      } else {
        usersSortBy = col;
        usersSortOrder = (col === "email" || col === "tier") ? "asc" : "desc";
      }
      updateHeaderSortIcons(".sortable-user-header", usersSortBy, usersSortOrder);
      loadUsers(1);
    });
  });

  // User Action Handlers (Global scope for onclick)
  window.toggleUserAdmin = async function(userId, currentIsAdmin) {
    const action = currentIsAdmin ? "demote this user to Regular User" : "promote this user to Master Admin (granting infinite pitches and full admin controls)";
    if (!confirm(`Are you sure you want to ${action}?`)) return;

    try {
      const res = await fetch(`/api/admin/users/${userId}/toggle-admin`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to toggle admin status");
      showToast(data.message || "User role updated successfully");
      loadUsers(usersCurrentPage);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  window.toggleUserBan = async function(userId, currentIsBanned) {
    const action = currentIsBanned ? "unban and restore access for" : "suspend and ban";
    let reason = "";
    if (!currentIsBanned) {
      reason = prompt("Enter suspension reason (optional):", "Terms of service violation");
      if (reason === null) return;
    } else {
      if (!confirm(`Restore access for this user?`)) return;
    }

    try {
      const res = await fetch(`/api/admin/users/${userId}/ban`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_banned: !currentIsBanned, reason: reason })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update ban status");
      showToast(data.message || "User status updated");
      loadUsers(usersCurrentPage);
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  window.openEditPlanModal = function(userId, email, currentTier) {
    document.getElementById("edit-plan-user-id").value = userId;
    document.getElementById("edit-plan-user-email").textContent = email;
    const radios = document.querySelectorAll("input[name='plan-tier']");
    radios.forEach(r => {
      r.checked = (r.value === currentTier);
    });
    openModal("modal-edit-plan");
  };

  document.getElementById("btn-confirm-save-plan")?.addEventListener("click", async () => {
    const userId = document.getElementById("edit-plan-user-id").value;
    const selectedRadio = document.querySelector("input[name='plan-tier']:checked");
    if (!selectedRadio || !userId) return;

    const tier = selectedRadio.value;
    try {
      const res = await fetch(`/api/admin/users/${userId}/update-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier: tier })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update plan");
      showToast(data.message || "Subscription plan updated successfully");
      closeModal("modal-edit-plan");
      loadUsers(usersCurrentPage);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // --- Companies Sub-Tabs (Active Directory vs Quarantined Leads) ---
  const subtabActiveComps = document.getElementById("btn-subtab-active-companies");
  const subtabQuarantineComps = document.getElementById("btn-subtab-quarantine-companies");
  const viewActiveComps = document.getElementById("view-companies-active");
  const viewQuarantineComps = document.getElementById("view-companies-quarantine");

  function switchCompaniesSubtab(view) {
    if (view === "active") {
      subtabActiveComps?.classList.add("active", "bg-primary-container", "text-on-primary-container");
      subtabActiveComps?.classList.remove("text-on-surface-variant");
      subtabQuarantineComps?.classList.remove("active", "bg-primary-container", "text-on-primary-container");
      subtabQuarantineComps?.classList.add("text-on-surface-variant");
      viewActiveComps?.classList.remove("hidden");
      viewQuarantineComps?.classList.add("hidden");
      loadActiveCompanies(1);
    } else {
      subtabQuarantineComps?.classList.add("active", "bg-primary-container", "text-on-primary-container");
      subtabQuarantineComps?.classList.remove("text-on-surface-variant");
      subtabActiveComps?.classList.remove("active", "bg-primary-container", "text-on-primary-container");
      subtabActiveComps?.classList.add("text-on-surface-variant");
      viewQuarantineComps?.classList.remove("hidden");
      viewActiveComps?.classList.add("hidden");
      loadInvalidCompanies(1);
    }
  }

  subtabActiveComps?.addEventListener("click", () => switchCompaniesSubtab("active"));
  subtabQuarantineComps?.addEventListener("click", () => switchCompaniesSubtab("quarantine"));

  // --- API: Load Active Verified Directory Companies ---
  let activeCompsCurrentPage = 1;
  let activeCompsSortBy = "id";
  let activeCompsSortOrder = "desc";
  const activeCompsTableBody = document.getElementById("active-comps-table-body");
  const activeCompsPageInfo = document.getElementById("active-comps-page-info");
  const activeCompsBtnPrev = document.getElementById("active-comps-btn-prev");
  const activeCompsBtnNext = document.getElementById("active-comps-btn-next");
  const activeCompsSearchInput = document.getElementById("active-comps-search");
  const activeCompsFilterCat = document.getElementById("active-comps-filter-category");
  const badgeActiveCompsCount = document.getElementById("badge-active-comps-count");

  async function loadActiveCompanies(page = 1) {
    activeCompsCurrentPage = page;
    const search = activeCompsSearchInput ? activeCompsSearchInput.value.trim() : "";
    const category = activeCompsFilterCat ? activeCompsFilterCat.value.trim() : "";

    activeCompsTableBody.innerHTML = `<tr><td colspan="5" class="px-4 py-8 text-center text-on-surface-variant">Loading genuine companies...</td></tr>`;

    try {
      const url = `/api/admin/companies?page=${page}&page_size=15&search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}&status=valid&sort_by=${encodeURIComponent(activeCompsSortBy)}&sort_order=${encodeURIComponent(activeCompsSortOrder)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch verified companies");
      const data = await res.json();
      updateHeaderSortIcons(".sortable-comp-header", activeCompsSortBy, activeCompsSortOrder);

      if (badgeActiveCompsCount) badgeActiveCompsCount.textContent = Number(data.total_count).toLocaleString();

      if (!data.companies || data.companies.length === 0) {
        activeCompsTableBody.innerHTML = `<tr><td colspan="5" class="px-4 py-8 text-center text-on-surface-variant">No active companies found matching filters.</td></tr>`;
        activeCompsPageInfo.textContent = `Page 1 of 1`;
        activeCompsBtnPrev.disabled = true;
        activeCompsBtnNext.disabled = true;
        return;
      }

      activeCompsPageInfo.textContent = `Page ${data.current_page} of ${data.total_pages} (${Number(data.total_count).toLocaleString()} total)`;
      activeCompsBtnPrev.disabled = data.current_page <= 1;
      activeCompsBtnNext.disabled = data.current_page >= data.total_pages;

      activeCompsTableBody.innerHTML = data.companies.map(c => {
        const techBadges = (c.tech_stack || []).slice(0, 3).map(t =>
          `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-container border border-outline-variant/30 text-on-surface-variant">${t}</span>`
        ).join(" ") + (c.tech_stack && c.tech_stack.length > 3 ? `<span class="text-[10px] text-on-surface-variant">+${c.tech_stack.length - 3}</span>` : "");

        const emailBadge = c.email
          ? `<span class="font-mono text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>${c.email}</span>`
          : `<span class="text-xs text-on-surface-variant/70 italic">Pending enrichment</span>`;

        return `
          <tr class="hover:bg-surface-container/50 transition">
            <td class="px-4 py-3">
              <div class="flex flex-col">
                <a href="${c.website_url}" target="_blank" class="font-semibold text-xs text-on-surface hover:text-primary transition flex items-center gap-1">
                  <span>${c.name}</span>
                  <span class="material-symbols-outlined text-[13px] opacity-70">open_in_new</span>
                </a>
                <span class="font-mono text-[11px] text-on-surface-variant">${c.domain}</span>
              </div>
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-col text-xs">
                <span class="text-on-surface font-medium">${c.category}</span>
                <span class="text-[11px] text-on-surface-variant">${c.city}</span>
              </div>
            </td>
            <td class="px-4 py-3">${emailBadge}</td>
            <td class="px-4 py-3"><div class="flex flex-wrap items-center gap-1">${techBadges || '<span class="text-[11px] text-on-surface-variant/60">--</span>'}</div></td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-1.5">
                <button onclick="openEditCompanyModal(${c.id})" class="px-2.5 py-1 rounded text-xs font-semibold bg-primary/10 text-primary hover:bg-primary/20 transition cursor-pointer flex items-center gap-1">
                  <span class="material-symbols-outlined text-[14px]">edit</span>
                  <span>Edit</span>
                </button>
                <button onclick="openQuarantineModal(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="px-2 py-1 rounded text-xs font-semibold bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 transition cursor-pointer" title="Quarantine / Exclude Lead">
                  <span class="material-symbols-outlined text-[14px]">block</span>
                </button>
                <button onclick="deleteCompanyPermanently(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="px-2 py-1 rounded text-xs font-semibold bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition cursor-pointer" title="Delete Permanently">
                  <span class="material-symbols-outlined text-[14px]">delete</span>
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading active companies:", err);
      activeCompsTableBody.innerHTML = `<tr><td colspan="5" class="px-4 py-8 text-center text-rose-500">Failed to load: ${err.message}</td></tr>`;
    }
  }

  activeCompsSearchInput?.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => loadActiveCompanies(1), 300);
  });
  activeCompsFilterCat?.addEventListener("change", () => loadActiveCompanies(1));
  document.getElementById("btn-refresh-active-comps")?.addEventListener("click", () => loadActiveCompanies(activeCompsCurrentPage));
  activeCompsBtnPrev?.addEventListener("click", () => { if (activeCompsCurrentPage > 1) loadActiveCompanies(activeCompsCurrentPage - 1); });
  activeCompsBtnNext?.addEventListener("click", () => { loadActiveCompanies(activeCompsCurrentPage + 1); });

  // Active Companies Sortable Headers Listener
  document.querySelectorAll(".sortable-comp-header").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.getAttribute("data-sort");
      if (activeCompsSortBy === col) {
        activeCompsSortOrder = activeCompsSortOrder === "asc" ? "desc" : "asc";
      } else {
        activeCompsSortBy = col;
        activeCompsSortOrder = (col === "name" || col === "city") ? "asc" : "desc";
      }
      updateHeaderSortIcons(".sortable-comp-header", activeCompsSortBy, activeCompsSortOrder);
      loadActiveCompanies(1);
    });
  });

  // --- API: Load Quarantined / Invalid Companies ---
  let invalidCurrentPage = 1;
  let invalidSortBy = "id";
  let invalidSortOrder = "desc";
  const invalidTableBody = document.getElementById("invalid-table-body");
  const invalidPageInfo = document.getElementById("invalid-page-info");
  const invalidBtnPrev = document.getElementById("invalid-btn-prev");
  const invalidBtnNext = document.getElementById("invalid-btn-next");
  const invalidSearchInput = document.getElementById("invalid-search");

  async function loadInvalidCompanies(page = 1) {
    invalidCurrentPage = page;
    const search = invalidSearchInput ? invalidSearchInput.value.trim() : "";

    invalidTableBody.innerHTML = `<tr><td colspan="4" class="px-4 py-8 text-center text-on-surface-variant">Loading quarantined records...</td></tr>`;

    try {
      const url = `/api/admin/companies/invalid?page=${page}&page_size=15&search=${encodeURIComponent(search)}&sort_by=${encodeURIComponent(invalidSortBy)}&sort_order=${encodeURIComponent(invalidSortOrder)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch quarantined companies");
      const data = await res.json();
      updateHeaderSortIcons(".sortable-invalid-header", invalidSortBy, invalidSortOrder);

      const badgeInv = document.getElementById("badge-invalid-count");
      if (badgeInv) badgeInv.textContent = Number(data.total_count).toLocaleString();

      if (!data.companies || data.companies.length === 0) {
        invalidTableBody.innerHTML = `<tr><td colspan="4" class="px-4 py-8 text-center text-on-surface-variant">No quarantined companies found.</td></tr>`;
        invalidPageInfo.textContent = `Page 1 of 1`;
        invalidBtnPrev.disabled = true;
        invalidBtnNext.disabled = true;
        return;
      }

      invalidPageInfo.textContent = `Page ${data.current_page} of ${data.total_pages} (${Number(data.total_count).toLocaleString()} total)`;
      invalidBtnPrev.disabled = data.current_page <= 1;
      invalidBtnNext.disabled = data.current_page >= data.total_pages;

      invalidTableBody.innerHTML = data.companies.map(c => {
        return `
          <tr class="hover:bg-surface-container/50 transition">
            <td class="px-4 py-3 font-semibold text-xs text-on-surface">${c.name}</td>
            <td class="px-4 py-3 font-mono text-xs text-on-surface-variant">${c.domain}</td>
            <td class="px-4 py-3 text-xs text-on-surface-variant max-w-xs truncate">${c.invalid_reason || "Flagged as non-company"}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-2">
                <button onclick="restoreCompany(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="px-2.5 py-1 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 transition cursor-pointer">
                  Restore Lead
                </button>
                <button onclick="deleteCompanyPermanently(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="px-2.5 py-1 rounded text-xs font-semibold bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition cursor-pointer">
                  Delete
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading quarantined companies:", err);
      invalidTableBody.innerHTML = `<tr><td colspan="4" class="px-4 py-8 text-center text-rose-500">Failed to load: ${err.message}</td></tr>`;
    }
  }

  invalidSearchInput?.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => loadInvalidCompanies(1), 300);
  });
  invalidBtnPrev?.addEventListener("click", () => { if (invalidCurrentPage > 1) loadInvalidCompanies(invalidCurrentPage - 1); });
  invalidBtnNext?.addEventListener("click", () => { loadInvalidCompanies(invalidCurrentPage + 1); });

  // Quarantined Leads Sortable Headers Listener
  document.querySelectorAll(".sortable-invalid-header").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.getAttribute("data-sort");
      if (invalidSortBy === col) {
        invalidSortOrder = invalidSortOrder === "asc" ? "desc" : "asc";
      } else {
        invalidSortBy = col;
        invalidSortOrder = "asc";
      }
      updateHeaderSortIcons(".sortable-invalid-header", invalidSortBy, invalidSortOrder);
      loadInvalidCompanies(1);
    });
  });

  // --- Company Edit Modal & Submission ---
  window.openEditCompanyModal = async function(companyId) {
    try {
      const res = await fetch(`/api/admin/companies/${companyId}`);
      if (!res.ok) throw new Error("Could not fetch company details");
      const c = await res.json();

      document.getElementById("edit-company-id").value = c.id;
      document.getElementById("edit-company-name").value = c.name || "";
      document.getElementById("edit-company-domain").value = c.domain || "";
      document.getElementById("edit-company-website").value = c.website_url || "";
      document.getElementById("edit-company-city").value = c.city || "";
      document.getElementById("edit-company-email").value = c.email || "";
      document.getElementById("edit-company-phone").value = c.phone || "";
      document.getElementById("edit-company-tech").value = c.tech_stack_str || "";
      document.getElementById("edit-company-summary").value = c.summary || "";
      if (document.getElementById("edit-company-category") && c.category) {
        document.getElementById("edit-company-category").value = c.category;
      }

      openModal("modal-edit-company");
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  document.getElementById("form-edit-company")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const companyId = document.getElementById("edit-company-id").value;
    const btn = document.getElementById("btn-submit-edit-company");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const payload = {
      name: document.getElementById("edit-company-name").value.trim(),
      domain: document.getElementById("edit-company-domain").value.trim(),
      website_url: document.getElementById("edit-company-website").value.trim(),
      city: document.getElementById("edit-company-city").value.trim(),
      category: document.getElementById("edit-company-category").value,
      email: document.getElementById("edit-company-email").value.trim(),
      phone: document.getElementById("edit-company-phone").value.trim(),
      tech_stack: document.getElementById("edit-company-tech").value.trim(),
      summary: document.getElementById("edit-company-summary").value.trim()
    };

    try {
      const res = await fetch(`/api/admin/companies/${companyId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update company");

      showToast(`Updated '${data.name}' successfully`);
      closeModal("modal-edit-company");
      loadActiveCompanies(activeCompsCurrentPage);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Save Company";
    }
  });

  // --- Quarantine Lead Modal ---
  window.openQuarantineModal = function(id, name) {
    document.getElementById("quarantine-target-id").value = id;
    document.getElementById("quarantine-target-name").textContent = name;
    openModal("modal-quarantine-company");
  };

  document.getElementById("btn-confirm-quarantine")?.addEventListener("click", async () => {
    const id = document.getElementById("quarantine-target-id").value;
    const reason = document.getElementById("quarantine-reason-input").value.trim();
    if (!id) return;

    try {
      const res = await fetch(`/api/admin/companies/${id}/quarantine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason || "Quarantined by Master Admin" })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to quarantine company");

      showToast("Company quarantined and moved to exclusion queue");
      closeModal("modal-quarantine-company");
      loadActiveCompanies(activeCompsCurrentPage);
      loadInvalidCompanies(1);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  window.restoreCompany = async function(id, name) {
    if (!confirm(`Restore '${name}' back to genuine companies directory?`)) return;
    try {
      const res = await fetch(`/api/admin/companies/${id}/restore`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to restore");
      showToast(`'${name}' restored successfully`);
      loadInvalidCompanies(invalidCurrentPage);
      loadActiveCompanies(1);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  window.deleteCompanyPermanently = async function(id, name) {
    if (!confirm(`Permanently delete '${name}' from database? This cannot be undone.`)) return;
    try {
      const res = await fetch(`/api/admin/companies/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to delete");
      showToast(`Company permanently deleted`);
      loadActiveCompanies(activeCompsCurrentPage);
      loadInvalidCompanies(invalidCurrentPage);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  // --- API: Add Single Company ---
  document.getElementById("form-add-company")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-add-company");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const payload = {
      name: document.getElementById("add-cname").value.trim(),
      domain: document.getElementById("add-cdomain").value.trim(),
      city: document.getElementById("add-ccity").value.trim(),
      category: document.getElementById("add-ccat").value,
      email: document.getElementById("add-cemail").value.trim(),
      phone: document.getElementById("add-cphone").value.trim(),
      tech_stack: document.getElementById("add-ctech").value.trim()
    };

    try {
      const res = await fetch("/api/admin/companies/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to add company");

      showToast(`Added '${data.name}' (${data.domain})`);
      closeModal("modal-add-company");
      document.getElementById("form-add-company").reset();
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Save Company";
    }
  });

  // --- API: Bulk CSV Importer ---
  const dropzone = document.getElementById("csv-dropzone");
  const fileInput = document.getElementById("csv-file-input");
  const filenameLabel = document.getElementById("csv-filename-label");
  const btnUploadCsv = document.getElementById("btn-submit-csv-upload");
  const resultBox = document.getElementById("csv-result-box");
  const resultTitle = document.getElementById("csv-result-title");
  const resultDetails = document.getElementById("csv-result-details");
  let selectedCsvFile = null;

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("border-primary");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("border-primary"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("border-primary");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileSelect(e.target.files[0]);
      }
    });
  }

  function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      showToast("Please select a valid .csv file", "error");
      return;
    }
    selectedCsvFile = file;
    if (filenameLabel) filenameLabel.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    if (btnUploadCsv) btnUploadCsv.disabled = false;
    if (resultBox) resultBox.classList.add("hidden");
  }

  btnUploadCsv?.addEventListener("click", async () => {
    if (!selectedCsvFile) return;
    btnUploadCsv.disabled = true;
    btnUploadCsv.textContent = "Importing...";
    if (resultBox) {
      resultBox.classList.remove("hidden");
      resultTitle.textContent = "Processing CSV data...";
      resultDetails.textContent = "Sanitizing company names and checking for existing domain duplicates...";
    }

    const formData = new FormData();
    formData.append("file", selectedCsvFile);

    try {
      const res = await fetch("/api/admin/companies/bulk-upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to process bulk upload");

      resultTitle.textContent = "✓ Import Completed Successfully";
      resultDetails.innerHTML = `
        Total Rows in CSV: <strong>${data.total_rows}</strong><br>
        Newly Registered Leads: <strong class="text-emerald-500">${data.imported}</strong><br>
        Skipped Existing Duplicates: <strong class="text-amber-500">${data.skipped_duplicates}</strong><br>
        Invalid Domains / Entities Filtered: <strong>${data.invalid_domains}</strong>
      `;
      showToast(`Imported ${data.imported} new companies`);
      loadMetrics();
    } catch (err) {
      resultTitle.textContent = "Import Failed";
      resultDetails.textContent = err.message;
      showToast(err.message, "error");
    } finally {
      btnUploadCsv.disabled = false;
      btnUploadCsv.textContent = "Start Import";
    }
  });

  // --- System Maintenance: Name Sanitation & Purging Engines ---
  const btnSanitizePrev = document.getElementById("btn-sanitize-preview");
  const btnSanitizeExec = document.getElementById("btn-sanitize-execute");
  const sanitizeResultBox = document.getElementById("sanitize-result-box");
  const sanitizeStatusHeading = document.getElementById("sanitize-status-heading");
  const sanitizeStatusTime = document.getElementById("sanitize-status-time");
  const sanitizeSamples = document.getElementById("sanitize-samples");

  async function triggerNameSanitation(dryRun = false) {
    const btn = dryRun ? btnSanitizePrev : btnSanitizeExec;
    if (btn) btn.disabled = true;
    if (sanitizeResultBox) {
      sanitizeResultBox.classList.remove("hidden");
      sanitizeStatusHeading.textContent = dryRun ? "Running Dry-Run Preview..." : "Executing Live Sanitation Migration...";
      sanitizeStatusTime.textContent = "";
      sanitizeSamples.innerHTML = `<span class="italic text-on-surface-variant">Scanning primary-key index across Neon PostgreSQL...</span>`;
    }

    try {
      const res = await fetch("/api/admin/maintenance/sanitize-names", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: dryRun, limit: 3000 })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Sanitation failed");

      sanitizeStatusHeading.innerHTML = dryRun
        ? `Preview: <strong class="text-primary">${data.cleaned}</strong> candidates identified out of ${data.scanned} scanned`
        : `✓ Migration Complete: <strong class="text-emerald-500">${data.cleaned}</strong> records cleaned in DB`;
      sanitizeStatusTime.textContent = `${data.elapsed_seconds}s`;

      if (data.samples && data.samples.length > 0) {
        sanitizeSamples.innerHTML = data.samples.map(s => `
          <div class="border-b border-outline-variant/20 pb-1">
            <span class="text-rose-400 line-through">${s.before}</span> → <span class="text-emerald-400 font-semibold">${s.after}</span>
          </div>
        `).join("");
      } else {
        sanitizeSamples.innerHTML = `<span>No companies required name sanitation in this batch.</span>`;
      }

      showToast(data.message);
      if (!dryRun) {
        loadActiveCompanies(activeCompsCurrentPage);
        loadMetrics();
      }
    } catch (err) {
      sanitizeStatusHeading.textContent = "Sanitation Error";
      sanitizeSamples.textContent = err.message;
      showToast(err.message, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  btnSanitizePrev?.addEventListener("click", () => triggerNameSanitation(true));
  btnSanitizeExec?.addEventListener("click", () => {
    if (confirm("Run live company name cleanup on Neon PostgreSQL? Taglines and SEO slogans will be stripped.")) {
      triggerNameSanitation(false);
    }
  });

  const btnPurgePrev = document.getElementById("btn-purge-preview");
  const btnPurgeExec = document.getElementById("btn-purge-execute");
  const purgeResultBox = document.getElementById("purge-result-box");
  const purgeStatusHeading = document.getElementById("purge-status-heading");
  const purgeStatusTime = document.getElementById("purge-status-time");
  const purgeSamples = document.getElementById("purge-samples");

  async function triggerNonCompanyPurge(dryRun = false) {
    const btn = dryRun ? btnPurgePrev : btnPurgeExec;
    if (btn) btn.disabled = true;
    if (purgeResultBox) {
      purgeResultBox.classList.remove("hidden");
      purgeStatusHeading.textContent = dryRun ? "Auditing Directory for Institutes & Portfolios..." : "Executing Quarantine Migration...";
      purgeStatusTime.textContent = "";
      purgeSamples.innerHTML = `<span class="italic text-on-surface-variant">Scanning entity names and TLDs for academic and portfolio terms...</span>`;
    }

    try {
      const res = await fetch("/api/admin/maintenance/purge-non-companies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: dryRun, limit: 5000 })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Purge audit failed");

      purgeStatusHeading.innerHTML = dryRun
        ? `Audit: <strong class="text-amber-500">${data.flagged}</strong> non-company leads flagged out of ${data.scanned} scanned`
        : `✓ Quarantined <strong class="text-rose-500">${data.flagged}</strong> non-company leads in DB`;
      purgeStatusTime.textContent = `${data.elapsed_seconds}s`;

      if (data.samples && data.samples.length > 0) {
        purgeSamples.innerHTML = data.samples.map(s => `
          <div class="border-b border-outline-variant/20 pb-1 flex items-center justify-between">
            <span class="font-semibold text-on-surface">${s.name} (${s.domain})</span>
            <span class="text-amber-400 text-[10px]">${s.reason}</span>
          </div>
        `).join("");
      } else {
        purgeSamples.innerHTML = `<span>Zero non-company entities detected in this batch.</span>`;
      }

      showToast(data.message);
      if (!dryRun) {
        loadActiveCompanies(activeCompsCurrentPage);
        loadInvalidCompanies(1);
        loadMetrics();
      }
    } catch (err) {
      purgeStatusHeading.textContent = "Purge Error";
      purgeSamples.textContent = err.message;
      showToast(err.message, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  btnPurgePrev?.addEventListener("click", () => triggerNonCompanyPurge(true));
  btnPurgeExec?.addEventListener("click", () => {
    if (confirm("Move all detected coaching institutes, academies, and portfolios to the Quarantine queue?")) {
      triggerNonCompanyPurge(false);
    }
  });

  // --- API: Load & Manage Subscription Tiers ---
  let loadedTiers = [];
  const tiersGridContainer = document.getElementById("tiers-grid-container");

  async function loadTiers() {
    if (!tiersGridContainer) return;
    tiersGridContainer.innerHTML = `<div class="p-8 text-center text-on-surface-variant col-span-full">Loading subscription tiers...</div>`;

    try {
      const res = await fetch("/api/admin/tiers");
      if (!res.ok) throw new Error("Failed to load subscription tiers");
      const data = await res.json();
      loadedTiers = data.tiers || [];

      if (loadedTiers.length === 0) {
        tiersGridContainer.innerHTML = `<div class="p-8 text-center text-on-surface-variant col-span-full">No subscription tiers configured.</div>`;
        return;
      }

      tiersGridContainer.innerHTML = loadedTiers.map(t => {
        const isMaster = t.code === "master_admin";
        const isPro = t.code === "pro";
        const borderClass = isMaster
          ? "border-amber-500/40"
          : isPro
          ? "border-2 border-primary/50 shadow-md"
          : "border-outline-variant/30";

        const badgeHtml = t.badge
          ? `<div class="absolute -top-3 left-6 px-2.5 py-0.5 rounded-full ${isMaster ? 'bg-amber-500 text-black' : 'bg-primary text-on-primary'} text-[10px] font-bold tracking-wide">${t.badge}</div>`
          : "";

        const priceDisplay = isMaster ? "∞" : `₹${t.price_inr}`;
        const limitDisplay = isMaster ? "Infinite pitches / day" : `${t.daily_pitch_limit} pitches / day`;

        const featureItems = (t.features || []).map(f =>
          `<li class="flex items-center gap-2"><span class="${isMaster ? 'text-amber-500' : 'text-emerald-500'}">✓</span> <span>${f}</span></li>`
        ).join("");

        return `
          <div class="bg-surface-container-low border ${borderClass} rounded-xl p-6 flex flex-col justify-between relative">
            ${badgeHtml}
            <div class="flex flex-col gap-3">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold ${isMaster ? 'text-amber-500' : isPro ? 'text-primary' : 'text-on-surface-variant'}">${t.subtitle || t.code.toUpperCase()}</span>
                <span class="text-[11px] px-2 py-0.5 rounded-full bg-surface-container font-mono text-on-surface-variant">${t.subscriber_count} active</span>
              </div>
              <div class="flex items-baseline gap-1">
                <span class="text-headline-lg font-headline-lg ${isMaster ? 'text-amber-500' : 'text-on-surface'} font-bold tabular-nums">${priceDisplay}</span>
                <span class="text-xs text-on-surface-variant">${isMaster ? 'Superuser' : '/ month'}</span>
              </div>
              <h3 class="text-sm font-semibold text-on-surface">${t.name}</h3>
              <div class="text-xs font-semibold ${isMaster ? 'text-amber-500' : 'text-emerald-500'}">${limitDisplay}</div>
              <ul class="text-xs text-on-surface-variant flex flex-col gap-2 mt-2">
                ${featureItems}
              </ul>
            </div>
            <div class="mt-6 pt-4 border-t border-outline-variant/20 flex items-center justify-between">
              <span class="text-xs text-on-surface-variant">Code: <code>${t.code}</code></span>
              <button onclick="openEditTierModal(${t.id})" class="px-3 py-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high border border-outline-variant/40 text-xs font-semibold text-on-surface transition cursor-pointer flex items-center gap-1">
                <span class="material-symbols-outlined text-[14px]">edit</span>
                <span>Edit Plan</span>
              </button>
            </div>
          </div>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading tiers:", err);
      tiersGridContainer.innerHTML = `<div class="p-8 text-center text-rose-500 col-span-full">Failed to load tier configurations: ${err.message}</div>`;
    }
  }

  window.openEditTierModal = function(tierId) {
    const tier = loadedTiers.find(t => t.id === tierId);
    if (!tier) return;

    document.getElementById("tier-modal-title").textContent = `Edit Plan: ${tier.name}`;
    document.getElementById("tier-form-id").value = tier.id;
    document.getElementById("tier-form-code").value = tier.code;
    document.getElementById("tier-form-code").disabled = true; // Cannot alter existing code
    document.getElementById("tier-form-name").value = tier.name;
    document.getElementById("tier-form-subtitle").value = tier.subtitle || "";
    document.getElementById("tier-form-price").value = tier.price_inr;
    document.getElementById("tier-form-limit").value = tier.daily_pitch_limit;
    document.getElementById("tier-form-badge").value = tier.badge || "";
    document.getElementById("tier-form-features").value = (tier.features || []).join("\n");
    document.getElementById("tier-form-sync-users").checked = true;

    openModal("modal-tier-form");
  };

  document.getElementById("btn-add-custom-tier")?.addEventListener("click", () => {
    document.getElementById("tier-modal-title").textContent = "Add Custom Tier Plan";
    document.getElementById("tier-form-id").value = "";
    document.getElementById("tier-form-code").value = "";
    document.getElementById("tier-form-code").disabled = false;
    document.getElementById("tier-form-name").value = "";
    document.getElementById("tier-form-subtitle").value = "";
    document.getElementById("tier-form-price").value = "499";
    document.getElementById("tier-form-limit").value = "50";
    document.getElementById("tier-form-badge").value = "";
    document.getElementById("tier-form-features").value = "50 pitches / day\nVerified contact discovery\nAI pitch customization";
    openModal("modal-tier-form");
  });

  document.getElementById("form-tier-config")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const tierId = document.getElementById("tier-form-id").value;
    const isEdit = Boolean(tierId);
    const btn = document.getElementById("btn-submit-tier-form");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const featuresLines = document.getElementById("tier-form-features").value
      .split("\n")
      .map(line => line.trim())
      .filter(line => line.length > 0);

    const payload = {
      code: document.getElementById("tier-form-code").value.trim().toLowerCase(),
      name: document.getElementById("tier-form-name").value.trim(),
      subtitle: document.getElementById("tier-form-subtitle").value.trim(),
      price_inr: parseInt(document.getElementById("tier-form-price").value, 10) || 0,
      daily_pitch_limit: parseInt(document.getElementById("tier-form-limit").value, 10) || 10,
      badge: document.getElementById("tier-form-badge").value.trim() || null,
      features: featuresLines,
      is_active: true,
      sync_users: document.getElementById("tier-form-sync-users")?.checked ?? true
    };

    try {
      const url = isEdit ? `/api/admin/tiers/${tierId}` : `/api/admin/tiers`;
      const method = isEdit ? "PUT" : "POST";
      const res = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to save tier");

      showToast(data.message || "Tier saved successfully");
      closeModal("modal-tier-form");
      loadTiers();
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Save Tier Plan";
    }
  });

  // --- Master Kill Switch: Subscription & RBAC Bypass Controller ---
  async function loadKillSwitchStatus() {
    try {
      const res = await fetch("/api/admin/system/kill-switch");
      if (!res.ok) return;
      const data = await res.json();
      const isActive = !!data.active;

      const toggle = document.getElementById("toggle-subscription-kill-switch");
      if (toggle) toggle.checked = isActive;

      const pill = document.getElementById("kill-switch-status-pill");
      const iconBox = document.getElementById("kill-switch-icon-box");
      const bannerCard = document.getElementById("card-kill-switch-banner");
      const overviewPill = document.getElementById("overview-kill-switch-pill");

      if (isActive) {
        if (pill) {
          pill.className = "px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider bg-amber-500/20 text-amber-500 border border-amber-500/40 flex items-center gap-1.5";
          pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span><span>ACTIVE (OPEN ACCESS &amp; INFINITE PITCHES)</span>`;
        }
        if (iconBox) {
          iconBox.className = "w-11 h-11 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-500 flex items-center justify-center shrink-0 mt-0.5";
        }
        if (bannerCard) {
          bannerCard.classList.add("border-amber-500/40", "bg-amber-500/5");
        }
        if (overviewPill) {
          overviewPill.className = "px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-500 border border-amber-500/40";
          overviewPill.textContent = "OPEN ACCESS (INFINITE)";
        }
      } else {
        if (pill) {
          pill.className = "px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider bg-emerald-500/15 text-emerald-500 border border-emerald-500/30 flex items-center gap-1.5";
          pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span><span>DISABLED (STANDARD RBAC ACTIVE)</span>`;
        }
        if (iconBox) {
          iconBox.className = "w-11 h-11 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-400 flex items-center justify-center shrink-0 mt-0.5";
        }
        if (bannerCard) {
          bannerCard.classList.remove("border-amber-500/40", "bg-amber-500/5");
        }
        if (overviewPill) {
          overviewPill.className = "px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-500 border border-emerald-500/30";
          overviewPill.textContent = "STANDARD RBAC";
        }
      }
    } catch (err) {
      console.warn("Could not load kill switch status:", err);
    }
  }

  document.getElementById("toggle-subscription-kill-switch")?.addEventListener("change", async function () {
    const desiredState = this.checked;
    try {
      const res = await fetch("/api/admin/system/kill-switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: desiredState })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update kill switch");
      showToast(data.message || "Kill switch status updated", desiredState ? "warning" : "info");
      loadKillSwitchStatus();
    } catch (err) {
      this.checked = !desiredState;
      showToast(err.message, "error");
    }
  });

  document.getElementById("btn-overview-toggle-kill-switch")?.addEventListener("click", () => {
    switchTab("subscriptions");
    setTimeout(() => {
      document.getElementById("card-kill-switch-banner")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 100);
  });

  // --- Sent Cold Pitches Telemetry & Delivery Logs ---
  let activePitchFilter = "today";
  let currentPitchesPage = 1;
  let cachedPitchesList = [];
  let pitchSearchDebounceTimer = null;

  function updatePitchFilterTabsUI() {
    document.querySelectorAll(".pitch-filter-btn").forEach(btn => {
      const filterVal = btn.getAttribute("data-pitch-filter");
      if (filterVal === activePitchFilter) {
        btn.classList.add("active", "bg-purple-500/15", "text-purple-400", "border", "border-purple-500/30");
        btn.classList.remove("text-on-surface-variant");
      } else {
        btn.classList.remove("active", "bg-purple-500/15", "text-purple-400", "border", "border-purple-500/30");
        btn.classList.add("text-on-surface-variant");
      }
    });
  }

  async function loadAdminPitches(page = 1) {
    currentPitchesPage = page;
    const tableBody = document.getElementById("pitches-table-body");
    const searchVal = document.getElementById("pitches-search-input")?.value || "";

    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="8" class="px-4 py-8 text-center text-on-surface-variant"><span class="animate-pulse">Loading ${activePitchFilter === 'today' ? "today's" : "all"} pitch records...</span></td></tr>`;
    }

    try {
      const url = `/api/admin/pitches?filter=${encodeURIComponent(activePitchFilter)}&page=${page}&page_size=25&search=${encodeURIComponent(searchVal)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to load sent pitches telemetry");
      const data = await res.json();

      cachedPitchesList = data.pitches || [];

      // Update pills and badges
      const todayPill = document.getElementById("pitches-today-pill-count");
      const allPill = document.getElementById("pitches-all-pill-count");
      const badgePitchesCount = document.getElementById("badge-pitches-count");
      const metricPitches = document.getElementById("metric-pitches");

      if (todayPill) todayPill.textContent = data.today_count ?? 0;
      if (allPill) allPill.textContent = data.total_count_all ?? 0;
      if (badgePitchesCount) badgePitchesCount.textContent = `${data.today_count ?? 0} today`;
      if (metricPitches) metricPitches.textContent = data.today_count ?? 0;

      // Render table rows
      renderPitchesTable(cachedPitchesList);

      // Pagination controls
      const paginationInfo = document.getElementById("pitches-pagination-info");
      const pageIndicator = document.getElementById("pitches-page-indicator");
      const btnPrev = document.getElementById("btn-pitches-prev");
      const btnNext = document.getElementById("btn-pitches-next");

      const total = data.total || 0;
      const totalPages = data.total_pages || 1;
      const startItem = total === 0 ? 0 : (page - 1) * 25 + 1;
      const endItem = Math.min(page * 25, total);

      if (paginationInfo) paginationInfo.textContent = `Showing ${startItem}-${endItem} of ${total} pitches`;
      if (pageIndicator) pageIndicator.textContent = `Page ${page} of ${totalPages}`;
      if (btnPrev) btnPrev.disabled = (page <= 1);
      if (btnNext) btnNext.disabled = (page >= totalPages);

    } catch (err) {
      if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="8" class="px-4 py-8 text-center text-rose-500 font-semibold">Error loading pitches: ${err.message}</td></tr>`;
      }
    }
  }

  function renderPitchesTable(pitches) {
    const tableBody = document.getElementById("pitches-table-body");
    if (!tableBody) return;

    if (!pitches || pitches.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="8" class="px-4 py-12 text-center text-on-surface-variant">
            <div class="flex flex-col items-center gap-2">
              <span class="material-symbols-outlined text-3xl opacity-40">mark_email_read</span>
              <p class="font-medium text-xs">No cold outreach pitch records found for ${activePitchFilter === 'today' ? "today" : "the current filter"}.</p>
              <p class="text-[11px] text-on-surface-variant/70">When users dispatch personalized emails or batch outreach campaigns, they will be logged here in real time.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tableBody.innerHTML = pitches.map(p => {
      const isFailed = (p.status || "").toUpperCase() === "FAILED";
      const statusBadge = isFailed
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/15 text-rose-500 border border-rose-500/30">FAILED</span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">${p.status || "SENT"}</span>`;

      const domainLink = p.company_domain
        ? `<a href="https://${p.company_domain}" target="_blank" class="text-[11px] text-primary hover:underline font-mono truncate max-w-[150px] inline-block">${p.company_domain}</a>`
        : `<span class="text-[11px] text-on-surface-variant/60 font-mono">--</span>`;

      const subjectSnippet = p.subject
        ? (p.subject.length > 36 ? p.subject.slice(0, 36) + "..." : p.subject)
        : "(No Subject)";

      const methodBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-container text-on-surface-variant border border-outline-variant/30">${p.delivery_method || "GMAIL_OAUTH"}</span>`;

      return `
        <tr class="hover:bg-surface-container/50 transition cursor-pointer" onclick="openAdminPitchModal(${p.id})">
          <td class="px-4 py-3 font-mono text-xs text-on-surface-variant font-semibold">#${p.id}</td>
          <td class="px-4 py-3">
            <div class="flex flex-col">
              <span class="font-semibold text-xs text-on-surface">${p.company_name || "Unknown"}</span>
              ${domainLink}
            </div>
          </td>
          <td class="px-4 py-3">
            <div class="flex flex-col font-mono text-xs">
              <span class="text-on-surface font-semibold">${p.recipient_email || "--"}</span>
              <span class="text-[11px] text-on-surface-variant truncate max-w-[160px]">by ${p.sender_email || "System"}</span>
            </div>
          </td>
          <td class="px-4 py-3">
            <div class="flex flex-col max-w-[220px]">
              <span class="font-medium text-xs text-on-surface truncate">${subjectSnippet}</span>
              <span class="text-[11px] text-on-surface-variant truncate">${(p.email_body || "").replace(/\\n/g, " ").slice(0, 45)}...</span>
            </div>
          </td>
          <td class="px-4 py-3">${methodBadge}</td>
          <td class="px-4 py-3">${statusBadge}</td>
          <td class="px-4 py-3 font-mono text-xs text-on-surface-variant whitespace-nowrap">${p.sent_at || "--"}</td>
          <td class="px-4 py-3 text-right">
            <button type="button" onclick="event.stopPropagation(); openAdminPitchModal(${p.id});" class="px-2.5 py-1 rounded-md bg-surface-container hover:bg-surface-container-high border border-outline-variant/40 text-on-surface text-xs font-medium transition cursor-pointer flex items-center gap-1 inline-flex">
              <span class="material-symbols-outlined text-[14px]">visibility</span>
              <span>View</span>
            </button>
          </td>
        </tr>
      `;
    }).join("");
  }

  window.openAdminPitchModal = function(pitchId) {
    const pitch = cachedPitchesList.find(p => p.id === pitchId);
    if (!pitch) return;

    const modalMeta = document.getElementById("view-pitch-meta");
    const modalCompany = document.getElementById("view-pitch-company");
    const modalBadge = document.getElementById("view-pitch-status-badge");
    const modalRecipient = document.getElementById("view-pitch-recipient");
    const modalSender = document.getElementById("view-pitch-sender");
    const modalSubject = document.getElementById("view-pitch-subject");
    const modalBody = document.getElementById("view-pitch-body");

    if (modalMeta) modalMeta.textContent = `Dispatched ${pitch.sent_at || "recently"} via ${pitch.delivery_method || "GMAIL_OAUTH"}`;
    if (modalCompany) modalCompany.textContent = `${pitch.company_name || "Unknown"} (${pitch.company_domain || "no domain"})`;
    if (modalRecipient) modalRecipient.textContent = pitch.recipient_email || "--";
    if (modalSender) modalSender.textContent = `${pitch.sender_name || "Admin"} <${pitch.sender_email || "System"}>`;
    if (modalSubject) modalSubject.textContent = pitch.subject || "(No Subject)";
    if (modalBody) modalBody.textContent = pitch.email_body || "(No message body content recorded)";

    if (modalBadge) {
      const isFailed = (pitch.status || "").toUpperCase() === "FAILED";
      modalBadge.className = isFailed
        ? "px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/20 text-rose-400"
        : "px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400";
      modalBadge.textContent = pitch.status || "SENT";
    }

    openModal("modal-admin-view-pitch");
  };

  // Event Listeners for Pitches Tab
  document.querySelectorAll(".pitch-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const filterVal = btn.getAttribute("data-pitch-filter");
      if (filterVal && filterVal !== activePitchFilter) {
        activePitchFilter = filterVal;
        updatePitchFilterTabsUI();
        loadAdminPitches(1);
      }
    });
  });

  document.getElementById("pitches-search-input")?.addEventListener("input", () => {
    clearTimeout(pitchSearchDebounceTimer);
    pitchSearchDebounceTimer = setTimeout(() => {
      loadAdminPitches(1);
    }, 350);
  });

  document.getElementById("btn-refresh-pitches")?.addEventListener("click", () => {
    loadAdminPitches(currentPitchesPage);
  });

  document.getElementById("btn-pitches-prev")?.addEventListener("click", () => {
    if (currentPitchesPage > 1) {
      loadAdminPitches(currentPitchesPage - 1);
    }
  });

  document.getElementById("btn-pitches-next")?.addEventListener("click", () => {
    loadAdminPitches(currentPitchesPage + 1);
  });

  document.getElementById("btn-copy-view-pitch")?.addEventListener("click", () => {
    const subj = document.getElementById("view-pitch-subject")?.textContent || "";
    const body = document.getElementById("view-pitch-body")?.textContent || "";
    const fullText = `Subject: ${subj}\n\n${body}`;
    navigator.clipboard.writeText(fullText).then(() => {
      showToast("Email text copied to clipboard!");
    }).catch(() => {
      showToast("Failed to copy email text", "error");
    });
  });

  // --- API: GitHub Actions CI/CD Telemetry & Workflows ---
  let currentSelectedWorkflow = "cloud_scout.yml";
  let cachedWorkflows = [
    {
      id: 1,
      name: "Cloud Scout & Autonomous Neon DB Queue Worker",
      file_name: "cloud_scout.yml",
      path: ".github/workflows/cloud_scout.yml",
      state: "active",
      html_url: "https://github.com/vorarahul4700/outreachPilot/actions/workflows/cloud_scout.yml"
    },
    {
      id: 2,
      name: "Cloud Lead Enrichment & Contact Email Discovery",
      file_name: "cloud_enrich.yml",
      path: ".github/workflows/cloud_enrich.yml",
      state: "active",
      html_url: "https://github.com/vorarahul4700/outreachPilot/actions/workflows/cloud_enrich.yml"
    },
    {
      id: 3,
      name: "Render Keep-Alive & Crawl Health Ping",
      file_name: "keep_alive.yml",
      path: ".github/workflows/keep_alive.yml",
      state: "active",
      html_url: "https://github.com/vorarahul4700/outreachPilot/actions/workflows/keep_alive.yml"
    }
  ];

  function getWorkflowDisplayName(wfFile) {
    const clean = (wfFile || "").split("/").pop();
    const found = cachedWorkflows.find(w => w.file_name === clean || w.path.endsWith(clean));
    return found ? found.name : (clean || "Cloud Scout & Autonomous Neon DB Queue Worker");
  }

  function renderWorkflowCards() {
    const wfGrid = document.getElementById("github-workflows-grid");
    if (!wfGrid) return;

    wfGrid.innerHTML = cachedWorkflows.map(w => {
      const isSelected = (w.file_name === currentSelectedWorkflow) || (w.path.endsWith(currentSelectedWorkflow));
      const borderClass = isSelected
        ? "border-2 border-primary bg-primary/10 shadow-md ring-1 ring-primary/40"
        : "border border-outline-variant/30 hover:border-outline hover:bg-surface-container/60";

      const selectionBadge = isSelected
        ? `<span class="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-primary text-on-primary tracking-wider shadow-sm flex items-center gap-1">
             <span class="material-symbols-outlined text-[12px]">check</span>
             <span>SELECTED</span>
           </span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-mono ${w.state === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-surface-container text-on-surface-variant'}">${w.state || 'active'}</span>`;

      const selectAction = isSelected
        ? `<div class="text-xs font-semibold text-primary flex items-center gap-1">
             <span class="material-symbols-outlined text-[15px]">radio_button_checked</span>
             <span>Target Workflow</span>
           </div>`
        : `<button type="button" class="text-xs text-on-surface-variant hover:text-primary transition font-semibold flex items-center gap-1">
             <span class="material-symbols-outlined text-[15px]">radio_button_unchecked</span>
             <span>Click to Select</span>
           </button>`;

      return `
        <div class="p-5 rounded-xl bg-surface-container-low ${borderClass} flex flex-col justify-between gap-3 shadow-sm transition-all duration-150 cursor-pointer group" data-wf-file="${w.file_name}">
          <div class="flex items-start justify-between gap-2">
            <span class="text-xs font-bold text-on-surface leading-snug group-hover:text-primary transition-colors">${w.name}</span>
            <div class="shrink-0">${selectionBadge}</div>
          </div>
          <span class="text-[11px] font-mono text-on-surface-variant truncate">${w.path}</span>
          <div class="pt-2 border-t border-outline-variant/20 flex items-center justify-between">
            <div class="flex items-center gap-1">
              ${selectAction}
            </div>
            <a href="${w.html_url}" target="_blank" onclick="event.stopPropagation()" class="text-xs text-on-surface-variant hover:text-primary font-medium flex items-center gap-1" title="View workflow on GitHub">
              <span>GitHub</span>
              <span class="material-symbols-outlined text-[13px]">open_in_new</span>
            </a>
          </div>
        </div>
      `;
    }).join("");

    // Attach click events on workflow cards to select workflow first
    wfGrid.querySelectorAll("[data-wf-file]").forEach(card => {
      card.addEventListener("click", () => {
        const wfFile = card.getAttribute("data-wf-file");
        if (wfFile && wfFile !== currentSelectedWorkflow) {
          currentSelectedWorkflow = wfFile;
          renderWorkflowCards();
          loadGitHubTelemetry(currentSelectedWorkflow);
        }
      });
    });
  }

  async function loadGitHubTelemetry(workflowFile = null) {
    if (workflowFile) {
      currentSelectedWorkflow = workflowFile.split("/").pop();
    }

    const runsHeading = document.getElementById("github-runs-heading");
    const runsTableBody = document.getElementById("github-runs-table-body");
    const selectedTitle = getWorkflowDisplayName(currentSelectedWorkflow);

    if (runsHeading) {
      runsHeading.textContent = `Latest 10 Executions for: ${selectedTitle}`;
    }

    if (runsTableBody) {
      runsTableBody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-on-surface-variant">Syncing live GitHub Actions runs for <strong>${selectedTitle}</strong>...</td></tr>`;
    }

    try {
      const res = await fetch(`/api/admin/github/telemetry?workflow=${encodeURIComponent(currentSelectedWorkflow)}`);
      if (!res.ok) throw new Error("Failed to fetch GitHub Actions telemetry");
      const data = await res.json();

      if (data.workflows && data.workflows.length > 0) {
        cachedWorkflows = data.workflows;
      }
      renderWorkflowCards();



      // Render Runs for selected workflow
      if (!runsTableBody) return;

      if (!data.runs || data.runs.length === 0) {
        runsTableBody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-on-surface-variant">No execution history recorded for this workflow yet. Click "Run Selected Workflow" to trigger.</td></tr>`;
        return;
      }

      runsTableBody.innerHTML = data.runs.map(r => {
        const isSuccess = r.conclusion === "success";
        const isFailed = r.conclusion === "failure";
        const isRunning = r.status === "in_progress" || r.status === "queued";

        const badgeHtml = isSuccess
          ? `<span class="px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold border border-emerald-500/30">SUCCESS</span>`
          : isFailed
          ? `<span class="px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-rose-500/15 text-rose-600 dark:text-rose-400 font-bold border border-rose-500/30">FAILED</span>`
          : `<span class="px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-amber-500/15 text-amber-500 font-bold animate-pulse border border-amber-500/30">${(r.status || "RUNNING").toUpperCase()}</span>`;

        return `
          <tr class="hover:bg-surface-container/50 transition cursor-pointer" onclick="window.open('${r.html_url}', '_blank')">
            <td class="px-4 py-3 font-mono text-xs text-on-surface-variant font-semibold">#${r.run_number || r.id}</td>
            <td class="px-4 py-3">
              <div class="flex flex-col">
                <span class="font-semibold text-xs text-on-surface">${r.display_title || r.name}</span>
                <span class="text-[11px] text-on-surface-variant">${r.name}</span>
              </div>
            </td>
            <td class="px-4 py-3">${badgeHtml}</td>
            <td class="px-4 py-3 font-mono text-xs text-on-surface-variant">${r.event || "schedule"}</td>
            <td class="px-4 py-3">
              <div class="flex flex-col font-mono text-xs">
                <span class="text-on-surface">${r.branch} (<span class="text-primary">${r.commit_sha}</span>)</span>
                <span class="text-[11px] text-on-surface-variant truncate max-w-xs">${r.commit_msg}</span>
              </div>
            </td>
            <td class="px-4 py-3 font-mono text-xs text-on-surface-variant">${r.duration}</td>
            <td class="px-4 py-3 text-right">
              <a href="${r.html_url}" target="_blank" onclick="event.stopPropagation()" class="px-2.5 py-1 rounded bg-surface-container hover:bg-surface-container-high border border-outline-variant/30 text-xs font-semibold text-primary transition inline-flex items-center gap-1">
                <span>Inspect</span>
                <span class="material-symbols-outlined text-[13px]">open_in_new</span>
              </a>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading GitHub telemetry:", err);
      if (runsTableBody) {
        runsTableBody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-rose-500">Failed to load GitHub telemetry: ${err.message}</td></tr>`;
      }
    }
  }

  // --- Modal: Run GitHub Actions Workflow Directly with Dynamic Parameters ---
  const btnTriggerWorkflow = document.getElementById("btn-trigger-selected-workflow");
  const formRunWorkflow = document.getElementById("form-run-workflow");

  function renderDynamicWorkflowInputs(wf) {
    const wrapper = document.getElementById("wf-dynamic-fields-wrapper");
    const countBadge = document.getElementById("wf-dynamic-inputs-count");
    if (!wrapper) return;

    const inputs = (wf && Array.isArray(wf.inputs)) ? wf.inputs : [];

    if (countBadge) {
      countBadge.textContent = inputs.length > 0 
        ? `${inputs.length} Parameter${inputs.length > 1 ? 's' : ''}`
        : "No Parameters";
    }

    if (inputs.length === 0) {
      wrapper.innerHTML = `
        <div class="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant/30 flex items-start gap-2.5">
          <span class="material-symbols-outlined text-primary text-[18px] mt-0.5">info</span>
          <div class="flex flex-col gap-0.5">
            <span class="font-semibold text-on-surface text-xs">No Custom Parameters Required</span>
            <span class="text-[11px] text-on-surface-variant leading-relaxed">This workflow does not require any input parameters. Click <strong>Trigger Execution</strong> to dispatch directly on the specified branch.</span>
          </div>
        </div>
      `;
      return;
    }

    wrapper.innerHTML = inputs.map(param => {
      const pName = param.name || "";
      const pDesc = param.description || "";
      const pDefault = param.default !== undefined ? String(param.default) : "";
      const pReq = !!param.required;
      const pType = (param.type || "string").toLowerCase();
      const options = Array.isArray(param.options) ? param.options : [];

      let inputControl = "";

      if (pType === "choice" || options.length > 0) {
        const optsHtml = options.map(opt => {
          const optStr = String(opt);
          const isSel = (optStr === pDefault) ? "selected" : "";
          return `<option value="${optStr}" ${isSel}>${optStr}</option>`;
        }).join("");

        inputControl = `
          <select data-wf-param="${pName}" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant/40 rounded-lg text-on-surface text-xs focus:outline-none focus:border-primary">
            ${optsHtml}
          </select>
        `;
      } else if (pType === "boolean") {
        const isChecked = (pDefault.toLowerCase() === "true");
        inputControl = `
          <label class="flex items-center gap-2 cursor-pointer pt-1">
            <input type="checkbox" data-wf-param="${pName}" ${isChecked ? "checked" : ""} class="rounded border-outline-variant/50 text-primary focus:ring-primary w-4 h-4">
            <span class="text-xs text-on-surface font-mono">${pName} (Enable / True)</span>
          </label>
        `;
      } else if (pType === "number") {
        inputControl = `
          <input type="number" data-wf-param="${pName}" value="${pDefault}" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant/40 rounded-lg text-on-surface text-xs font-mono focus:outline-none focus:border-primary">
        `;
      } else {
        inputControl = `
          <input type="text" data-wf-param="${pName}" value="${pDefault}" placeholder="${pDesc ? pDesc.replace(/"/g, '&quot;') : pName}" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant/40 rounded-lg text-on-surface text-xs focus:outline-none focus:border-primary">
        `;
      }

      return `
        <div class="flex flex-col gap-1 p-2.5 rounded-lg bg-surface-container-lowest/80 border border-outline-variant/20 hover:border-outline-variant/40 transition-colors">
          <div class="flex items-center justify-between">
            <label class="text-on-surface font-semibold text-xs flex items-center gap-1 font-mono">
              <span>${pName}</span>
              ${pReq ? '<span class="text-rose-500 font-bold" title="Required">*</span>' : ''}
            </label>
            <span class="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant font-medium">${pType}</span>
          </div>
          ${inputControl}
          ${pDesc ? `<span class="text-[11px] text-on-surface-variant leading-snug">${pDesc}</span>` : ''}
        </div>
      `;
    }).join("");
  }

  btnTriggerWorkflow?.addEventListener("click", () => {
    const selectedTitle = getWorkflowDisplayName(currentSelectedWorkflow);
    const titleEl = document.getElementById("run-wf-modal-title");
    const pathEl = document.getElementById("run-wf-modal-path");
    const fileEl = document.getElementById("run-wf-file");

    const clean = (currentSelectedWorkflow || "").split("/").pop();
    const currentWf = cachedWorkflows.find(w => w.file_name === clean || w.path.endsWith(clean));

    if (titleEl) titleEl.textContent = `Run: ${selectedTitle}`;
    if (pathEl) pathEl.textContent = currentWf?.path || `.github/workflows/${currentSelectedWorkflow}`;
    if (fileEl) fileEl.value = currentSelectedWorkflow;

    renderDynamicWorkflowInputs(currentWf);
    openModal("modal-run-workflow");
  });

  formRunWorkflow?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btnSubmit = document.getElementById("btn-submit-dispatch");
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">sync</span><span>Dispatching...</span>`;
    }

    const workflowFile = document.getElementById("run-wf-file")?.value || currentSelectedWorkflow;
    const branchRef = document.getElementById("run-wf-ref")?.value.trim() || "main";

    const inputs = {};
    const paramEls = document.querySelectorAll("#wf-dynamic-fields-wrapper [data-wf-param]");
    paramEls.forEach(el => {
      const pName = el.getAttribute("data-wf-param");
      if (!pName) return;
      if (el.type === "checkbox") {
        inputs[pName] = el.checked ? "true" : "false";
      } else {
        const val = el.value.trim();
        if (val !== "") {
          inputs[pName] = val;
        }
      }
    });

    try {
      const res = await fetch(`/api/admin/github/workflows/${encodeURIComponent(workflowFile)}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ref: branchRef,
          inputs: inputs
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Workflow dispatch failed");

      showToast(data.message || "Workflow execution triggered successfully!");
      closeModal("modal-run-workflow");

      // Auto-refresh runs after 3 seconds
      setTimeout(() => {
        loadGitHubTelemetry(currentSelectedWorkflow);
      }, 3000);

    } catch (err) {
      showToast(err.message, "error");
    } finally {
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = `<span class="material-symbols-outlined text-[16px]">bolt</span><span>Trigger Execution</span>`;
      }
    }
  });

  document.getElementById("btn-refresh-github")?.addEventListener("click", () => {
    loadGitHubTelemetry(currentSelectedWorkflow);
  });

  // --- Initial Load ---
  loadMetrics();
  loadKillSwitchStatus();
});
