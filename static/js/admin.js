/**
 * OutreachPilot - Master Admin Panel Client Controller
 * File: static/js/admin.js
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- Theme Management (Exact Match with /app) ---
  const themeBtn = document.getElementById("btn-theme-toggle");
  const themeIcon = document.getElementById("theme-toggle-icon");

  const themeLabel = document.getElementById("theme-toggle-label");

  // The account menu item names the theme it switches to.
  function updateThemeIcon() {
    const isDark = document.documentElement.classList.contains("dark");
    if (themeIcon) {
      themeIcon.textContent = isDark ? "light_mode" : "dark_mode";
    }
    if (themeLabel) {
      themeLabel.textContent = isDark ? "Light mode" : "Dark mode";
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

  // --- Notifications: same place and look as the workspace (/app) ---
  // Top centre, slide down, coloured border + short label, close button,
  // auto-dismiss after 3.5s (warning 4.5s, error 5.5s).
  const toastContainer = document.getElementById("admin-toast-container");
  const TOAST_STYLES = {
    success: { ring: "border-secondary/60 ring-1 ring-secondary/40", icon: "check_circle", tone: "text-secondary", label: "Success", chip: "bg-secondary/20 text-secondary border-secondary/40" },
    error:   { ring: "border-error/60 ring-1 ring-error/40",         icon: "error",        tone: "text-error",     label: "Error",   chip: "bg-error/20 text-error border-error/40" },
    warning: { ring: "border-tertiary/60 ring-1 ring-tertiary/40",   icon: "warning",      tone: "text-tertiary",  label: "Attention", chip: "bg-tertiary/20 text-tertiary border-tertiary/40" },
    info:    { ring: "border-outline-variant/50",                    icon: "info",         tone: "text-primary",   label: "Info",    chip: "bg-primary/10 text-primary border-primary/30" },
  };

  function showToast(message, type = "success") {
    if (!toastContainer) return;
    const s = TOAST_STYLES[type] || TOAST_STYLES.info;
    const toast = document.createElement("div");
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    const kind = TOAST_STYLES[type] ? type : "info";
    toast.className = `app-toast ${kind} -translate-y-4 opacity-0`;
    toast.innerHTML = `
      <div class="l">
        <span class="ic"><span class="material-symbols-outlined" aria-hidden="true">${s.icon}</span></span>
        <div class="min-w-0"><span class="tag">${s.label}</span><span class="toast-message msg"></span></div>
      </div>
      <button type="button" class="toast-close" aria-label="Dismiss">
        <span class="material-symbols-outlined" aria-hidden="true">close</span>
      </button>
    `;
    // Plain text, so server error messages can never inject markup.
    toast.querySelector(".toast-message").textContent = message;

    const dismiss = () => {
      toast.classList.add("opacity-0", "-translate-y-4");
      setTimeout(() => toast.remove(), 250);
    };
    toast.querySelector(".toast-close")?.addEventListener("click", dismiss);

    toastContainer.appendChild(toast);
    void toast.offsetWidth; // apply the start position so the slide-down animates
    toast.classList.remove("-translate-y-4", "opacity-0");

    const duration = type === "error" ? 5500 : type === "warning" ? 4500 : 3500;
    setTimeout(() => { if (toast.isConnected) dismiss(); }, duration);
  }

  // --- Tab Navigation ---
  const tabButtons = document.querySelectorAll(".admin-tab-btn");
  const tabPanels = document.querySelectorAll(".admin-tab-panel");
  const currentViewTitle = document.getElementById("current-view-title");
  const headerHeading = document.getElementById("header-heading");

  // Lets a long email wrap after the @ (name@ / gmail.com) instead of mid-word.
  const wbrEmail = (e) => String(e).replace("@", "@<wbr>");

  // Phone card layout: tag each cell with its column name so CSS can label it.
  document.querySelectorAll(".a-table").forEach(table => {
    // Screen-reader-only headers (the checkbox column) get no visible label.
    const labels = [...table.querySelectorAll("thead th")].map(th => {
      if (th.querySelector(".sr-only")) return "";
      const c = th.cloneNode(true);
      c.querySelectorAll(".material-symbols-outlined").forEach(i => i.remove());  // sort icons
      return c.textContent.trim();
    });
    const tbody = table.querySelector("tbody");
    const label = () => tbody.querySelectorAll("tr").forEach(tr => {
      let titled = false;
      [...tr.children].forEach((td, i) => {
        if (td.hasAttribute("colspan")) return;
        td.dataset.label = labels[i] || "";
        if (!labels[i]) td.dataset.role = "check";
        else if (labels[i] === "Actions") td.dataset.role = "actions";
        else if (!titled) { td.dataset.role = "title"; titled = true; }
        else td.dataset.role = "field";
      });
    });
    if (tbody) new MutationObserver(label).observe(tbody, { childList: true });
  });

  const tabMeta = {
    overview: { title: "Overview", heading: "Telemetry & System Controls" },
    users: { title: "Users", heading: "User Accounts & Role Governance" },
    companies: { title: "Companies", heading: "Directory Pipeline & Quarantined Leads" },
    categories: { title: "Categories", heading: "Category Visibility" },
    subscriptions: { title: "Subscriptions", heading: "Tier Quotas & Monetization Architecture" },
    pitches: { title: "Sent Pitches", heading: "Cold Outreach Pitches & Delivery Telemetry" },
    scout: { title: "Scout Leads", heading: "Queue Google Maps Scouting Jobs" },
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
    if (tabId === "categories") loadCategoryVisibility(showToast);
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

  // --- Account menu (round profile button at the top of the sidebar) ---
  // One menu, opened from the sidebar button (desktop) or the top-bar button (phones).
  const profileBtns = document.querySelectorAll(".js-profile-btn");
  const profileMenu = document.getElementById("admin-profile-menu");

  function setProfileMenu(open, btn) {
    if (!profileMenu) return;
    if (open && btn) (btn.closest(".sb-brand") || btn.parentElement).appendChild(profileMenu);
    profileMenu.classList.toggle("hidden", !open);
    profileBtns.forEach(b => b.setAttribute("aria-expanded", open && b === btn ? "true" : "false"));
  }

  profileBtns.forEach(btn => btn.addEventListener("click", (e) => {
    e.stopPropagation();
    setProfileMenu(profileMenu?.classList.contains("hidden"), btn);
  }));
  // Close on any click outside the menu, or on Escape.
  document.addEventListener("click", (e) => {
    if (!profileMenu || profileMenu.classList.contains("hidden")) return;
    if (!profileMenu.contains(e.target)) setProfileMenu(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setProfileMenu(false);
  });

  // --- Phone sidebar (below 768px it is off-screen and slides in from the menu button) ---
  const adminSidebar = document.getElementById("admin-sidebar");
  const adminBackdrop = document.getElementById("admin-mobile-backdrop");
  const btnAdminMenu = document.getElementById("btn-admin-mobile-menu");
  const btnAdminMenuClose = document.getElementById("btn-admin-sidebar-close");
  const phoneQuery = window.matchMedia("(max-width: 767px)");

  function setAdminSidebar(open) {
    if (!adminSidebar) return;
    const show = Boolean(open) && phoneQuery.matches;
    if (!show) setProfileMenu(false);
    adminSidebar.classList.toggle("mobile-open", show);
    adminBackdrop?.classList.toggle("hidden", !show);
    btnAdminMenu?.setAttribute("aria-expanded", show ? "true" : "false");
    updateBodyScrollLock();
  }

  btnAdminMenu?.addEventListener("click", () => setAdminSidebar(true));
  btnAdminMenuClose?.addEventListener("click", () => setAdminSidebar(false));
  adminBackdrop?.addEventListener("click", () => setAdminSidebar(false));
  // Picking a section closes the menu so its content is visible straight away.
  tabButtons.forEach(btn => btn.addEventListener("click", () => setAdminSidebar(false)));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && adminSidebar?.classList.contains("mobile-open")) setAdminSidebar(false);
  });
  // Growing past phone width (rotation, resize) puts the sidebar back in place.
  if (phoneQuery.addEventListener) {
    phoneQuery.addEventListener("change", () => setAdminSidebar(false));
  } else if (phoneQuery.addListener) {
    phoneQuery.addListener(() => setAdminSidebar(false));
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

      const activeSubs = data.subscribers_paid || 0;
      const elActiveSubs = document.getElementById("kpi-active-subs");
      if (elActiveSubs) elActiveSubs.textContent = activeSubs.toLocaleString();

      const elSubBreakdown = document.getElementById("kpi-sub-breakdown");
      // One entry per paid plan, named as in admin (e.g. "1 7-Day Pass / 2 Job Seeker Pro").
      if (elSubBreakdown) elSubBreakdown.textContent = (data.subscribers_by_plan || []).map(p => `${p.count} ${p.name}`).join(" / ") || "No paid plans yet";

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

    usersTableBody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-on-surface-variant">Loading user directory...</td></tr>`;

    try {
      const url = `/api/admin/users?page=${page}&page_size=15&search=${encodeURIComponent(search)}&tier=${encodeURIComponent(tier)}&role=${encodeURIComponent(role)}&sort_by=${encodeURIComponent(usersSortBy)}&sort_order=${encodeURIComponent(usersSortOrder)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch users");
      const data = await res.json();
      updateHeaderSortIcons(".sortable-user-header", usersSortBy, usersSortOrder);

      if (!data.users || data.users.length === 0) {
        usersTableBody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-on-surface-variant">No matching users found.</td></tr>`;
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
        // One color per plan so plans stand out at a glance; name and limit come from the DB.
        const planClass = { free: "plan-free", week_pass: "plan-week", pro: "plan-pro" }[tierName] || "plan-top";
        const tierBadge = `<span class="plan-badge ${planClass}">${u.subscription_tier_name}${isAdmin ? "" : ` (${u.daily_pitch_limit})`}</span>`
          + (u.subscription_end && !isAdmin ? `<span class="block text-[11px] text-on-surface-variant mt-1">until ${u.subscription_end}</span>` : "")
          + (u.trial ? `<span class="block text-[11px] mt-1 ${u.trial === "active" ? "text-primary font-semibold" : "text-on-surface-variant"}">${u.trial === "active" ? "Pro trial now" : "Pro trial used"}</span>` : "");

        const roleBadge = isAdmin
          ? `<span class="inline-flex items-center whitespace-nowrap px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-500/20 text-amber-500 border border-amber-500/40">★ Master Admin</span>`
          : `<span class="inline-flex items-center whitespace-nowrap px-2 py-0.5 rounded text-[11px] font-mono text-on-surface-variant">User</span>`;

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
                <div class="flex flex-col min-w-0" style="max-width:150px">
                  <span class="font-semibold text-on-surface truncate text-xs">${u.name || "User"}</span>
                  <span class="text-[11px] font-mono text-on-surface-variant truncate" title="${u.email}">${wbrEmail(u.email)}</span>
                </div>
              </div>
            </td>
            <td class="px-4 py-3">${roleBadge}</td>
            <td class="px-4 py-3">${tierBadge}</td>
            <td class="px-4 py-3">${quotaDisplay}</td>
            <td class="px-4 py-3">${u.pitches_sent_total
              ? `<button type="button" onclick="viewUserPitches(${u.id}, '${u.email.replace(/'/g, "\\'")}')" class="font-mono text-xs font-semibold text-primary underline underline-offset-2 hover:opacity-80 cursor-pointer" title="View pitches sent by ${u.email}">${u.pitches_sent_total.toLocaleString()} sent</button>`
              : `<span class="font-mono text-xs text-on-surface-variant">0</span>`}</td>
            <td class="px-4 py-3">${statusBadge}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-1.5">
                <button onclick="toggleUserAdmin(${u.id}, ${isAdmin})" class="rounded transition cursor-pointer ${isAdmin ? 'bg-amber-500/10 text-amber-500 hover:bg-amber-500/20' : 'bg-primary/10 text-primary hover:bg-primary/20'}" title="${isAdmin ? 'Demote to regular user' : 'Promote to admin'}" aria-label="${isAdmin ? 'Demote to regular user' : 'Promote to admin'}"><span class="material-symbols-outlined text-[16px]">${isAdmin ? 'arrow_downward' : 'arrow_upward'}</span></button>
                <button onclick="openEditPlanModal(${u.id}, '${u.email}', '${tierName}')" class="rounded bg-surface-container text-on-surface-variant hover:bg-surface-container-high transition cursor-pointer" title="Change plan" aria-label="Change plan"><span class="material-symbols-outlined text-[16px]">loyalty</span></button>
                <button onclick="toggleUserBan(${u.id}, ${isBanned})" class="rounded transition cursor-pointer ${isBanned ? 'bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20' : 'bg-rose-500/10 text-rose-500 hover:bg-rose-500/20'}" title="${isBanned ? 'Unban user' : 'Ban user'}" aria-label="${isBanned ? 'Unban user' : 'Ban user'}"><span class="material-symbols-outlined text-[16px]">${isBanned ? 'check_circle' : 'block'}</span></button>
              </div>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading users:", err);
      usersTableBody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-rose-500">Failed to load users: ${err.message}</td></tr>`;
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

  // Plan picker lists the live plans (same names and colors as the users table badges).
  window.openEditPlanModal = async function(userId, email, currentTier) {
    document.getElementById("edit-plan-user-id").value = userId;
    document.getElementById("edit-plan-user-email").textContent = email;
    const box = document.getElementById("edit-plan-options");
    openModal("modal-edit-plan");
    try {
      const res = await fetch("/api/admin/tiers");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not load plans");
      const safe = (v) => String(v ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
      const plans = (data.tiers || [])
        .filter(t => t.code !== "master_admin" && (t.is_active || t.code === currentTier))
        .sort((a, b) => (a.price_inr || 0) - (b.price_inr || 0));
      box.innerHTML = plans.map(t => {
        const cls = { free: "plan-free", week_pass: "plan-week", pro: "plan-pro" }[t.code] || "plan-top";
        const price = t.price_inr ? `₹${t.price_inr} / ${t.period_days === 7 ? "week" : "month"}` : "Free";
        return `<label class="radio-card"><input type="radio" name="plan-tier" value="${safe(t.code)}"${t.code === currentTier ? " checked" : ""}>
          <span class="plan-badge ${cls}">${safe(t.name)}</span>
          <span class="ml-auto text-[12px] font-normal text-on-surface-variant whitespace-nowrap">${price} · ${t.daily_pitch_limit}/day${t.is_active ? "" : " · hidden"}</span></label>`;
      }).join("");
    } catch (err) {
      box.innerHTML = `<span class="app-field-hint">${err.message}</span>`;
    }
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
  const selectedCompIds = new Set();
  let syncBulkBar = () => {};
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

    activeCompsTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant">Loading genuine companies...</td></tr>`;

    try {
      const url = `/api/admin/companies?page=${page}&page_size=15&search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}&status=valid&sort_by=${encodeURIComponent(activeCompsSortBy)}&sort_order=${encodeURIComponent(activeCompsSortOrder)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch verified companies");
      const data = await res.json();
      updateHeaderSortIcons(".sortable-comp-header", activeCompsSortBy, activeCompsSortOrder);

      if (badgeActiveCompsCount) badgeActiveCompsCount.textContent = Number(data.total_count).toLocaleString();
      const matchCount = document.getElementById("active-comps-match-count");
      if (matchCount) matchCount.textContent = Number(data.total_count).toLocaleString();

      // Page went out of range (rows moved by an action on a later page): show the last real page.
      if ((!data.companies || data.companies.length === 0) && page > data.total_pages && data.total_count > 0) return loadActiveCompanies(data.total_pages);
      if (!data.companies || data.companies.length === 0) {
        activeCompsTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant">No active companies found matching filters.</td></tr>`;
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
            <td class="px-4 py-3"><input type="checkbox" class="comp-select" data-id="${c.id}" aria-label="Select ${c.name.replace(/"/g, '&quot;')}" ${selectedCompIds.has(c.id) ? "checked" : ""}></td>
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
                <button onclick="openEditCompanyModal(${c.id})" class="rounded bg-primary/10 text-primary hover:bg-primary/20 transition cursor-pointer" title="Edit company" aria-label="Edit company"><span class="material-symbols-outlined text-[14px]">edit</span></button>
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
      syncBulkBar();

    } catch (err) {
      console.error("Error loading active companies:", err);
      activeCompsTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-rose-500">Failed to load: ${err.message}</td></tr>`;
    }
  }

  // --- Bulk selection (kept across pages and searches until cleared) ---
  // One helper drives both the Active and the Quarantined tables.
  function setupBulkSelection({ ids, tbody, countId, visibleBtnId, allBtnId, clearBtnId, actions, idsUrl }) {
    const countEl = document.getElementById(countId);
    function sync() {
      if (countEl) countEl.textContent = ids.size.toLocaleString();
      tbody.querySelectorAll(".comp-select").forEach(b => { b.checked = ids.has(Number(b.dataset.id)); });
      [...Object.keys(actions), clearBtnId].forEach(btnId => {
        const btn = document.getElementById(btnId);
        if (btn) btn.disabled = ids.size === 0;
      });
    }
    tbody?.addEventListener("change", (e) => {
      const box = e.target.closest(".comp-select");
      if (!box) return;
      const id = Number(box.dataset.id);
      box.checked ? ids.add(id) : ids.delete(id);
      sync();
    });
    document.getElementById(visibleBtnId)?.addEventListener("click", () => {
      tbody.querySelectorAll(".comp-select").forEach(b => ids.add(Number(b.dataset.id)));
      sync();
    });
    document.getElementById(allBtnId)?.addEventListener("click", async () => {
      try {
        const res = await fetch(idsUrl());
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not load matching companies");
        ids.clear();
        data.ids.forEach(id => ids.add(id));
        sync();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    document.getElementById(clearBtnId)?.addEventListener("click", () => { ids.clear(); sync(); });
    Object.entries(actions).forEach(([btnId, action]) => {
      document.getElementById(btnId)?.addEventListener("click", () => runBulkCompanyAction(ids, action));
    });
    return sync;
  }

  async function runBulkCompanyAction(ids, action) {
    const n = ids.size;
    if (!n) return;
    const msg = {
      delete: `Permanently delete ${n.toLocaleString()} companies and their emails, profiles, pitches and outreach logs? This cannot be undone.`,
      quarantine: `Quarantine ${n.toLocaleString()} companies? They move to the exclusion queue and can be restored later.`,
      restore: `Restore ${n.toLocaleString()} companies to the active directory?`,
    }[action];
    if (!confirm(msg)) return;
    try {
      const res = await fetch("/api/admin/companies/bulk-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [...ids], action, reason: "Bulk quarantined by Master Admin" })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Bulk action failed");
      showToast(data.message);
      ids.clear();
      loadActiveCompanies(activeCompsCurrentPage);
      loadInvalidCompanies(invalidCurrentPage);
      loadMetrics();
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  syncBulkBar = setupBulkSelection({
    ids: selectedCompIds,
    tbody: activeCompsTableBody,
    countId: "active-comps-bulk-count",
    visibleBtnId: "btn-select-visible",
    allBtnId: "btn-select-all-matching",
    clearBtnId: "btn-bulk-clear",
    actions: { "btn-bulk-quarantine": "quarantine", "btn-bulk-delete": "delete" },
    idsUrl: () => `/api/admin/companies?ids_only=true&status=valid&search=${encodeURIComponent(activeCompsSearchInput ? activeCompsSearchInput.value.trim() : "")}&category=${encodeURIComponent(activeCompsFilterCat ? activeCompsFilterCat.value.trim() : "")}`,
  });

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
  const selectedInvalidIds = new Set();
  let syncInvalidBulk = () => {};
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
      const invMatch = document.getElementById("invalid-match-count");
      if (invMatch) invMatch.textContent = Number(data.total_count).toLocaleString();

      // Page went out of range (rows moved by an action on a later page): show the last real page.
      if ((!data.companies || data.companies.length === 0) && page > data.total_pages && data.total_count > 0) return loadInvalidCompanies(data.total_pages);
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
            <td class="px-4 py-3"><input type="checkbox" class="comp-select" data-id="${c.id}" aria-label="Select ${c.name.replace(/"/g, '&quot;')}" ${selectedInvalidIds.has(c.id) ? "checked" : ""}></td>
            <td class="px-4 py-3">
              <div class="flex flex-col">
                <span class="font-semibold text-xs text-on-surface">${c.name}</span>
                <span class="font-mono text-[11px] text-on-surface-variant">${c.domain}</span>
              </div>
            </td>
            <td class="px-4 py-3 text-xs text-on-surface-variant max-w-xs truncate">${c.invalid_reason || "Flagged as non-company"}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-2">
                <button onclick="restoreCompany(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="rounded bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 transition cursor-pointer" title="Restore lead" aria-label="Restore lead"><span class="material-symbols-outlined text-[14px]">restore</span></button>
                <button onclick="deleteCompanyPermanently(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="rounded bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition cursor-pointer" title="Delete permanently" aria-label="Delete permanently"><span class="material-symbols-outlined text-[14px]">delete</span></button>
              </div>
            </td>
          </tr>
        `;
      }).join("");
      syncInvalidBulk();

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

  syncInvalidBulk = setupBulkSelection({
    ids: selectedInvalidIds,
    tbody: invalidTableBody,
    countId: "invalid-bulk-count",
    visibleBtnId: "btn-inv-select-visible",
    allBtnId: "btn-inv-select-all",
    clearBtnId: "btn-inv-clear",
    actions: { "btn-inv-restore": "restore", "btn-inv-delete": "delete" },
    idsUrl: () => `/api/admin/companies?ids_only=true&status=invalid&search=${encodeURIComponent(invalidSearchInput ? invalidSearchInput.value.trim() : "")}`,
  });

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

      resultTitle.textContent = "Import completed successfully";
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

  // --- Scout Leads: queue domain keywords x places for the cloud_scout runners ---
  (() => {
    const $ = (id) => document.getElementById(id);
    const btnPreview = $("btn-scout-preview"), btnQueue = $("btn-scout-queue");
    const box = $("scout-result"), heading = $("scout-result-heading"), body = $("scout-result-body");
    if (!btnPreview) return;
    const escHtml = (v) => String(v ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    let lastPreview = null;

    const form = () => ({
      domain: $("scout-domain").value,
      places: $("scout-places").value,
      requeue_done: $("scout-requeue").checked,
      start_now: $("scout-start-now").checked,
    });
    const willQueue = (d) => d.new + ($("scout-requeue").checked ? d.done : 0);
    // Any edit invalidates the preview, so Queue always runs on what was just previewed.
    const resetPreview = () => {
      lastPreview = null;
      btnQueue.disabled = true;
    };
    ["scout-places", "scout-requeue"].forEach(id => $(id).addEventListener("input", resetPreview));
    initStaticCustomDropdown("dropdown-scout-domain", resetPreview);

    async function call(mode) {
      const res = await fetch("/api/admin/scout/queue", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form(), mode }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");
      return data;
    }

    btnPreview.addEventListener("click", async () => {
      btnPreview.disabled = true;
      try {
        const d = await call("preview");
        lastPreview = d;
        box.classList.remove("hidden");
        heading.innerHTML = `<strong>${willQueue(d).toLocaleString()}</strong> jobs will be queued (${d.keywords} keywords x ${d.places} places = ${d.total.toLocaleString()})`;
        body.innerHTML = `<div>${d.new.toLocaleString()} new, ${d.active.toLocaleString()} already queued or running (skipped), ${d.done.toLocaleString()} already scraped (${$("scout-requeue").checked ? "run again" : "skipped"}).</div>` +
          `<div class="pt-2 font-semibold">Keywords</div><div>${d.keyword_list.map(escHtml).join(", ")}</div>`;
        btnQueue.disabled = willQueue(d) === 0;
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btnPreview.disabled = false;
      }
    });

    btnQueue.addEventListener("click", async () => {
      if (!lastPreview || !confirm(`Queue ${willQueue(lastPreview).toLocaleString()} scouting jobs?`)) return;
      btnQueue.disabled = true;
      try {
        const d = await call("queue");
        showToast(d.message);
        heading.textContent = d.message;
        body.innerHTML = `<a class="text-primary underline" href="https://github.com/vorarahul4700/outreachPilot/actions/workflows/cloud_scout.yml" target="_blank" rel="noopener">Watch the cloud_scout runs on GitHub</a>`;
        lastPreview = null;
      } catch (err) {
        showToast(err.message, "error");
        btnQueue.disabled = false;
      }
    });
  })();

  // --- System Maintenance: Name Sanitation & Non-Company Purge ---
  // Preview scans every company and lists each proposed change. Apply sends only the
  // ticked ids (the server re-checks each one).
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  function setupMaintenanceEngine(cfg) {
    const $ = (id) => document.getElementById(id);
    const btnPreview = $(cfg.previewBtn), btnApply = $(cfg.applyBtn), btnCsv = $(cfg.csvBtn);
    const box = $(cfg.box), heading = $(cfg.heading), timeEl = $(cfg.time), list = $(cfg.list);
    let candidates = [];
    const picked = new Set();

    function syncApply() {
      if (btnApply) {
        btnApply.disabled = picked.size === 0;
        const lbl = btnApply.querySelector(".apply-label");
        if (lbl) lbl.textContent = `${cfg.applyVerb} ${picked.size.toLocaleString()} selected`;
      }
      const all = list.querySelector(".mx-all");
      if (all) {
        all.checked = picked.size === candidates.length && candidates.length > 0;
        all.indeterminate = picked.size > 0 && picked.size < candidates.length;
      }
    }

    function render() {
      if (!candidates.length) {
        list.innerHTML = `<span>${esc(cfg.emptyText)}</span>`;
        syncApply();
        return;
      }
      list.innerHTML = `
        <label class="flex items-center gap-2 pb-1 border-b border-outline-variant/20 font-semibold">
          <input type="checkbox" class="mx-all" checked aria-label="Select all rows in this preview"> Select all ${candidates.length.toLocaleString()}
        </label>` +
        candidates.map(c => `
          <label class="flex items-start gap-2 border-b border-outline-variant/20 py-1">
            <input type="checkbox" class="mx-row mt-0.5" data-id="${c.id}" ${picked.has(c.id) ? "checked" : ""}>
            <span class="min-w-0">${cfg.row(c)}</span>
          </label>`).join("");
      syncApply();
    }

    list?.addEventListener("change", (e) => {
      if (e.target.classList.contains("mx-all")) {
        picked.clear();
        if (e.target.checked) candidates.forEach(c => picked.add(c.id));
        list.querySelectorAll(".mx-row").forEach(b => { b.checked = e.target.checked; });
      } else if (e.target.classList.contains("mx-row")) {
        const id = Number(e.target.dataset.id);
        e.target.checked ? picked.add(id) : picked.delete(id);
      }
      syncApply();
    });

    async function call(body) {
      const res = await fetch(cfg.endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");
      return data;
    }

    btnPreview?.addEventListener("click", async () => {
      btnPreview.disabled = true;
      box?.classList.remove("hidden");
      heading.textContent = "Scanning every company...";
      timeEl.textContent = "";
      list.innerHTML = `<span class="italic text-on-surface-variant">${esc(cfg.scanningText)}</span>`;
      try {
        const data = await call({ mode: "preview" });
        candidates = data.candidates || [];
        picked.clear();
        candidates.forEach(c => picked.add(c.id));
        heading.innerHTML = `<strong>${candidates.length.toLocaleString()}</strong> ${esc(cfg.foundText)} (${Number(data.scanned).toLocaleString()} scanned)`;
        timeEl.textContent = `${data.elapsed_seconds}s`;
        if (btnCsv) btnCsv.disabled = candidates.length === 0;
        render();
      } catch (err) {
        heading.textContent = "Preview failed";
        list.textContent = err.message;
        showToast(err.message, "error");
      } finally {
        btnPreview.disabled = false;
      }
    });

    btnApply?.addEventListener("click", async () => {
      if (!picked.size || !confirm(cfg.confirmApply(picked.size))) return;
      btnApply.disabled = true;
      try {
        const data = await call({ mode: "apply", ids: [...picked] });
        showToast(data.message);
        heading.textContent = data.message;
        candidates = candidates.filter(c => !picked.has(c.id));
        picked.clear();
        render();
        cfg.afterChange();
      } catch (err) {
        showToast(err.message, "error");
        syncApply();
      }
    });

    btnCsv?.addEventListener("click", () => {
      const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const csv = [cfg.csvColumns.join(",")]
        .concat(candidates.map(c => cfg.csvColumns.map(k => cell(c[k])).join(",")))
        .join("\r\n");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      a.download = cfg.csvName;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  setupMaintenanceEngine({
    endpoint: "/api/admin/maintenance/sanitize-names",
    previewBtn: "btn-sanitize-preview", applyBtn: "btn-sanitize-execute", csvBtn: "btn-sanitize-csv",
    box: "sanitize-result-box", heading: "sanitize-status-heading", time: "sanitize-status-time", list: "sanitize-samples",
    applyVerb: "Clean",
    scanningText: "Checking every company name for SEO slogans...",
    foundText: "names would change",
    emptyText: "No company names need cleaning.",
    row: (c) => `<span class="text-rose-400 line-through">${esc(c.before)}</span> <span class="text-on-surface-variant" aria-label="becomes">&rarr;</span> <span class="text-emerald-500 font-semibold">${esc(c.after)}</span> <span class="text-on-surface-variant font-mono text-[11px]">${esc(c.domain)}</span>`,
    confirmApply: (n) => `Rename ${n} companies to their cleaned names? This cannot be undone.`,
    csvColumns: ["id", "before", "after", "domain"],
    csvName: "name-cleanup-preview.csv",
    afterChange: () => { loadActiveCompanies(activeCompsCurrentPage); loadMetrics(); },
  });

  setupMaintenanceEngine({
    endpoint: "/api/admin/maintenance/purge-non-companies",
    previewBtn: "btn-purge-preview", applyBtn: "btn-purge-execute", csvBtn: "btn-purge-csv",
    box: "purge-result-box", heading: "purge-status-heading", time: "purge-status-time", list: "purge-samples",
    applyVerb: "Quarantine",
    scanningText: "Checking every active company for institutes, academies and portfolios. This takes about 30 seconds...",
    foundText: "look like non-companies",
    emptyText: "No non-company entities found.",
    row: (c) => `<span class="font-semibold text-on-surface">${esc(c.name)}</span> <span class="font-mono text-[11px] text-on-surface-variant">${esc(c.domain)}</span><br><span class="text-amber-500 text-[11px]">${esc(c.reason)}</span> <span class="text-on-surface-variant text-[11px]">${esc(c.city)}</span>`,
    confirmApply: (n) => `Move ${n} companies to Quarantine? You can restore them from the Quarantined Leads tab.`,
    csvColumns: ["id", "name", "domain", "city", "source_query", "reason"],
    csvName: "non-company-preview.csv",
    afterChange: () => { loadActiveCompanies(activeCompsCurrentPage); loadInvalidCompanies(1); loadMetrics(); },
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

        // Automatic lines from the plan settings first, then the admin's extra bullets.
        const autoLines = isMaster ? [] : [
          { standard: "Standard application emails", tailored: "Company-tailored application emails", tailored_fit: "Tailored application emails + fit summary" }[t.email_style] || "Company-tailored application emails",
          ...(t.has_best_matches ? ["Your best matches"] : []),
          ...(t.has_linkedin ? ["LinkedIn and referral messages"] : []),
          ...((t.resume_slots || 1) > 1 ? [`Up to ${t.resume_slots} resumes`] : []),
          ...(t.has_bulk ? ["Apply in bulk"] : []),
        ];
        const featureItems = [...autoLines, ...(t.features || [])].map(f =>
          `<li class="flex items-center gap-2"><span class="material-symbols-outlined text-[16px] ${isMaster ? 'text-amber-500' : 'text-emerald-500'}">check</span> <span>${f}</span></li>`
        ).join("");

        return `
          <div class="bg-surface-container-low border ${borderClass} rounded-xl p-6 flex flex-col justify-between relative${!t.is_active && !isMaster ? " opacity-70" : ""}">
            ${badgeHtml}
            <div class="flex flex-col gap-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="text-xs font-semibold ${isMaster ? 'text-amber-500' : isPro ? 'text-primary' : 'text-on-surface-variant'}">${t.subtitle || t.code.toUpperCase()}</span>
                <span class="flex items-center gap-1.5">${!t.is_active && !isMaster ? '<span class="plan-badge plan-free">Hidden from users</span>' : ""}<span class="text-[11px] px-2 py-0.5 rounded-full bg-surface-container font-mono text-on-surface-variant whitespace-nowrap">${t.subscriber_count} active</span></span>
              </div>
              <div class="flex items-baseline gap-1">
                <span class="text-headline-lg font-headline-lg ${isMaster ? 'text-amber-500' : 'text-on-surface'} font-bold tabular-nums">${priceDisplay}</span>
                <span class="text-xs text-on-surface-variant">${isMaster ? 'Superuser' : (t.period_days === 7 ? '/ week' : '/ month')}</span>
              </div>
              <h3 class="text-sm font-semibold text-on-surface">${t.name}</h3>
              <div class="text-xs font-semibold ${isMaster ? 'text-amber-500' : 'text-emerald-500'}">${limitDisplay}</div>
              <ul class="text-xs text-on-surface-variant flex flex-col gap-2 mt-2">
                ${featureItems}
              </ul>
            </div>
            <div class="mt-6 pt-4 border-t border-outline-variant/20 flex flex-wrap items-center justify-between gap-2">
              <span class="text-xs text-on-surface-variant min-w-0 break-all">Code: <code>${t.code}</code></span>
              <div class="flex items-center gap-1.5">
                ${isMaster || t.code === "free" ? "" : `<button onclick="toggleTierVisibility(${t.id})" class="px-3 py-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high border border-outline-variant/40 text-xs font-semibold text-on-surface transition cursor-pointer flex items-center gap-1 shrink-0 whitespace-nowrap" title="${t.is_active ? "Hide from pricing and checkout" : "Show on pricing and checkout"}">
                  <span class="material-symbols-outlined text-[14px]">${t.is_active ? "visibility_off" : "visibility"}</span>
                  <span>${t.is_active ? "Hide" : "Show"}</span>
                </button>`}
                <button onclick="openEditTierModal(${t.id})" class="px-3 py-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high border border-outline-variant/40 text-xs font-semibold text-on-surface transition cursor-pointer flex items-center gap-1 shrink-0 whitespace-nowrap">
                  <span class="material-symbols-outlined text-[14px]">edit</span>
                  <span>Edit Plan</span>
                </button>
              </div>
            </div>
          </div>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading tiers:", err);
      tiersGridContainer.innerHTML = `<div class="p-8 text-center text-rose-500 col-span-full">Failed to load tier configurations: ${err.message}</div>`;
    }
  }

  // Hide/show a plan: hidden plans leave pricing and checkout; current subscribers keep theirs until it ends.
  window.toggleTierVisibility = async function(tierId) {
    const t = loadedTiers.find(x => x.id === tierId);
    if (!t) return;
    const hiding = t.is_active;
    const note = hiding
      ? `Hide "${t.name}"? It disappears from pricing and checkout.` + (t.subscriber_count ? ` The ${t.subscriber_count} user(s) on it keep it until their plan ends, then move to Free.` : "")
      : `Show "${t.name}" again on pricing and checkout?`;
    if (!confirm(note)) return;
    try {
      const res = await fetch(`/api/admin/tiers/${t.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: t.name, subtitle: t.subtitle, price_inr: t.price_inr, daily_pitch_limit: t.daily_pitch_limit,
          period_days: t.period_days || 30, email_style: t.email_style, resume_slots: t.resume_slots || 1,
          has_best_matches: t.has_best_matches, has_linkedin: t.has_linkedin, has_bulk: t.has_bulk,
          features: t.features || [], badge: t.badge || null, is_active: !hiding, sync_users: false }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not update the plan");
      showToast(hiding ? `"${t.name}" is hidden.` : `"${t.name}" is visible again.`);
      loadTiers();
    } catch (err) {
      showToast(err.message, "error");
    }
  };

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
    setTierPeriod(tier.period_days);
    setTierFeatures(tier);
    document.getElementById("tier-form-active").checked = tier.is_active !== false;
    document.getElementById("tier-form-badge").value = tier.badge || "";
    document.getElementById("tier-form-features").value = (tier.features || []).join("\n");
    document.getElementById("tier-form-sync-users").checked = true;

    openModal("modal-tier-form");
  };

  // Plan length picker (house dropdown): set value, label and the ticked item together.
  function setTierPeriod(days) {
    const box = document.getElementById("dropdown-tier-period");
    if (!box) return;
    const val = String(days || 30);
    document.getElementById("tier-form-period").value = val;
    box.querySelectorAll(".custom-dropdown-item").forEach(it => {
      const on = it.dataset.value === val;
      it.classList.toggle("is-selected", on);
      if (on) box.querySelector(".custom-dropdown-label").textContent = it.textContent.trim().replace(/check$/, "").trim();
    });
  }
  initStaticCustomDropdown("dropdown-tier-period");

  // Email style picker (house dropdown), same pattern as plan length.
  function setTierStyle(style) {
    const box = document.getElementById("dropdown-tier-style");
    if (!box) return;
    const val = ["standard", "tailored", "tailored_fit"].includes(style) ? style : "tailored";
    document.getElementById("tier-form-style").value = val;
    box.querySelectorAll(".custom-dropdown-item").forEach(it => {
      const on = it.dataset.value === val;
      it.classList.toggle("is-selected", on);
      if (on) box.querySelector(".custom-dropdown-label").textContent = it.querySelector(".truncate").textContent.trim();
    });
  }
  initStaticCustomDropdown("dropdown-tier-style");
  function setTierFeatures(t) {
    setTierStyle(t.email_style);
    document.getElementById("tier-form-resumes").value = t.resume_slots || 1;
    document.getElementById("tier-form-matches").checked = !!t.has_best_matches;
    document.getElementById("tier-form-linkedin").checked = !!t.has_linkedin;
    document.getElementById("tier-form-bulk").checked = !!t.has_bulk;
  }

  document.getElementById("btn-add-custom-tier")?.addEventListener("click", () => {
    document.getElementById("tier-modal-title").textContent = "Add Custom Tier Plan";
    document.getElementById("tier-form-id").value = "";
    document.getElementById("tier-form-code").value = "";
    document.getElementById("tier-form-code").disabled = false;
    document.getElementById("tier-form-name").value = "";
    document.getElementById("tier-form-subtitle").value = "";
    document.getElementById("tier-form-price").value = "199";
    document.getElementById("tier-form-limit").value = "50";
    setTierPeriod(30);
    setTierFeatures({ email_style: "tailored", resume_slots: 1 });
    document.getElementById("tier-form-active").checked = true;
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
      period_days: parseInt(document.getElementById("tier-form-period").value, 10) || 30,
      email_style: document.getElementById("tier-form-style").value,
      resume_slots: parseInt(document.getElementById("tier-form-resumes").value, 10) || 1,
      has_best_matches: document.getElementById("tier-form-matches").checked,
      has_linkedin: document.getElementById("tier-form-linkedin").checked,
      has_bulk: document.getElementById("tier-form-bulk").checked,
      badge: document.getElementById("tier-form-badge").value.trim() || null,
      features: featuresLines,
      is_active: document.getElementById("tier-form-active")?.checked ?? true,
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

  // --- One-day Pro trial settings ---
  async function loadTrialSettings() {
    try {
      const res = await fetch("/api/admin/system/trial");
      if (!res.ok) return;
      const d = await res.json();
      const t = document.getElementById("toggle-pro-trial");
      if (t) t.checked = !!d.enabled;
      const h = document.getElementById("trial-admin-hours");
      if (h) h.value = d.hours;
      const s = document.getElementById("trial-admin-stats");
      if (s) s.textContent = `${d.enabled ? "On" : "Off"} · ${d.active} active · ${d.used} used`;
    } catch (_) {}
  }
  async function saveTrialSettings() {
    const enabled = !!document.getElementById("toggle-pro-trial")?.checked;
    const hours = parseInt(document.getElementById("trial-admin-hours")?.value || "24", 10);
    try {
      const res = await fetch("/api/admin/system/trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, hours })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not save the trial settings");
      showToast(`Pro trial ${data.enabled ? "on" : "off"}, ${data.hours} hours`, "success");
    } catch (err) {
      showToast(err.message, "error");
    }
    loadTrialSettings();
  }
  document.getElementById("toggle-pro-trial")?.addEventListener("change", saveTrialSettings);
  document.getElementById("btn-trial-admin-save")?.addEventListener("click", saveTrialSettings);
  loadTrialSettings();

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
  let pitchUserFilter = null; // { id, email } when opened from a user's "N sent" link

  window.viewUserPitches = function(id, email) {
    pitchUserFilter = { id, email };
    activePitchFilter = "all";
    updatePitchFilterTabsUI();
    switchTab("pitches");
  };

  document.getElementById("btn-clear-pitch-user")?.addEventListener("click", () => {
    pitchUserFilter = null;
    loadAdminPitches(1);
  });

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
      tableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant"><span class="animate-pulse">Loading ${activePitchFilter === 'today' ? "today's" : "all"} pitch records...</span></td></tr>`;
    }

    try {
      const userParam = pitchUserFilter ? `&user_id=${pitchUserFilter.id}` : "";
      const url = `/api/admin/pitches?filter=${encodeURIComponent(activePitchFilter)}&page=${page}&page_size=25&search=${encodeURIComponent(searchVal)}${userParam}`;
      const chip = document.getElementById("pitches-user-filter");
      chip?.classList.toggle("hidden", !pitchUserFilter);
      const chipEmail = document.getElementById("pitches-user-filter-email");
      if (chipEmail) chipEmail.textContent = pitchUserFilter ? pitchUserFilter.email : "";
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
      // Sidebar badge and KPI are global; don't overwrite them with one user's numbers.
      if (!pitchUserFilter) {
        if (badgePitchesCount) badgePitchesCount.textContent = `${data.today_count ?? 0} today`;
        if (metricPitches) metricPitches.textContent = data.today_count ?? 0;
      }

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
        tableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-rose-500 font-semibold">Error loading pitches: ${err.message}</td></tr>`;
      }
    }
  }

  function renderPitchesTable(pitches) {
    const tableBody = document.getElementById("pitches-table-body");
    if (!tableBody) return;

    if (!pitches || pitches.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="6" class="px-4 py-12 text-center text-on-surface-variant">
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

      return `
        <tr class="hover:bg-surface-container/50 transition cursor-pointer" onclick="openAdminPitchModal(${p.id})">
          <td class="px-4 py-3">
            <div class="flex flex-col">
              <span class="font-semibold text-xs text-on-surface">${p.company_name || "Unknown"}</span>
              ${domainLink}
            </div>
          </td>
          <td class="px-4 py-3">
            <div class="flex flex-col font-mono text-xs">
              <span class="text-on-surface font-semibold">${wbrEmail(p.recipient_email || "--")}</span>
              <span class="text-[11px] text-on-surface-variant truncate max-w-[160px]">by ${wbrEmail(p.sender_email || "System")}</span>
            </div>
          </td>
          <td class="px-4 py-3">
            <div class="flex flex-col max-w-[220px]">
              <span class="font-medium text-xs text-on-surface truncate">${subjectSnippet}</span>
              <span class="text-[11px] text-on-surface-variant truncate">${(p.email_body || "").replace(/\\n/g, " ").slice(0, 45)}...</span>
            </div>
          </td>
          <td class="px-4 py-3">${statusBadge}</td>
          <td class="px-4 py-3 font-mono text-xs text-on-surface-variant whitespace-nowrap">${p.sent_at || "--"}</td>
          <td class="px-4 py-3 text-right">
            <button type="button" onclick="event.stopPropagation(); openAdminPitchModal(${p.id});" class="rounded bg-surface-container hover:bg-surface-container-high text-on-surface-variant transition cursor-pointer" title="View pitch" aria-label="View pitch"><span class="material-symbols-outlined text-[14px]">visibility</span></button>
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
      runsTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant">Syncing live GitHub Actions runs for <strong>${selectedTitle}</strong>...</td></tr>`;
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
        runsTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-on-surface-variant">No execution history recorded for this workflow yet. Click "Run Selected Workflow" to trigger.</td></tr>`;
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
              <div class="flex flex-col min-w-[14rem]">
                <span class="font-semibold text-xs text-on-surface">${r.display_title || r.name}</span>
                ${r.display_title && r.display_title !== r.name ? `<span class="text-[11px] text-on-surface-variant">${r.name}</span>` : ""}
              </div>
            </td>
            <td class="px-4 py-3">${badgeHtml}</td>
            <td class="px-4 py-3 font-mono text-xs text-on-surface-variant">${({ workflow_dispatch: "manual", schedule: "schedule", push: "push" })[r.event] || r.event || "schedule"}</td>
            <td class="px-4 py-3">
              <div class="flex flex-col font-mono text-xs">
                <span class="text-on-surface">${r.branch} (<span class="text-primary">${r.commit_sha}</span>)</span>
                <span class="text-[11px] text-on-surface-variant truncate" style="max-width:220px" title="${catvisEscape(r.commit_msg)}">${catvisEscape(r.commit_msg)}</span>
              </div>
            </td>
            <td class="px-4 py-3 font-mono text-xs text-on-surface-variant">${r.duration}</td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading GitHub telemetry:", err);
      if (runsTableBody) {
        runsTableBody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-rose-500">Failed to load GitHub telemetry: ${err.message}</td></tr>`;
      }
    }
  }

  // --- Modal: Run GitHub Actions Workflow Directly with Dynamic Parameters ---
  const btnTriggerWorkflow = document.getElementById("btn-trigger-selected-workflow");
  const formRunWorkflow = document.getElementById("form-run-workflow");

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
