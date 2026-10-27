// OutreachPilot Frontend Application Controller
document.addEventListener("DOMContentLoaded", () => {
  
  // State
  let companies = [];
  let pollInterval = null;
  let activeTab = "companies";
  let currentUser = (window.__INITIAL_AUTH__ && typeof window.__INITIAL_AUTH__.is_logged_in === "boolean")
    ? { ...window.__INITIAL_AUTH__ }
    : { is_logged_in: false, email: null, is_master_admin: false, dev_mode: false };
  let isMasterAdmin = Boolean(currentUser && currentUser.is_master_admin);
  let isDevMode = Boolean(currentUser && currentUser.dev_mode);
  let adminViewMode = "admin"; // "admin" or "preview"
  let filterInvalidOnly = false;
  let invalidCount = 0;

  // Tab Navigation Elements
  const tabScout = document.getElementById("tab-scout");
  const tabCompanies = document.getElementById("tab-companies");
  const tabResume = document.getElementById("tab-resume");
  const tabOutreach = document.getElementById("tab-outreach");

  const secScout = document.getElementById("section-scout");
  const secCompanies = document.getElementById("section-companies");
  const secResume = document.getElementById("section-resume");
  const secOutreach = document.getElementById("section-outreach");

  const pageTitle = document.getElementById("page-current-title");
  const pageSubtitle = document.getElementById("page-current-subtitle");

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function escapeHTML(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function stripMarkdownForCopy(text) {
    if (!text) return "";
    return text
      .replace(/^###\s*(.*$)/gm, "\n$1\n" + "-".repeat(30))
      .replace(/^##\s*(.*$)/gm, "\n$1\n" + "=".repeat(30))
      .replace(/^#\s*(.*$)/gm, "\n$1\n" + "=".repeat(40))
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/\*(.*?)\*/g, "$1")
      .replace(/^\s*[\-\*]\s+/gm, "• ")
      .replace(/^\s*\-\-\s*/gm, "• ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function formatMarkdown(text) {
    if (!text) return "";
    if (typeof marked !== "undefined" && marked.parse) {
      try {
        return marked.parse(text, { breaks: true, gfm: true });
      } catch (e) {
        console.warn("marked.parse error:", e);
      }
    }
    let html = escapeHTML(text);
    html = html.replace(/^### (.*$)/gim, '<h4 class="text-primary font-bold text-xs mt-3 mb-1 uppercase tracking-wider">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 class="text-on-surface font-bold text-sm mt-3 mb-1.5">$1</h3>');
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong class="text-on-surface font-semibold">$1</strong>');
    html = html.replace(/^\- (.*$)/gim, '<div class="flex items-start space-x-1.5 my-1 ml-2"><span class="text-primary font-bold">•</span><span class="text-on-surface-variant">$1</span></div>');
    html = html.replace(/\n\n/gim, '<div class="h-2"></div>');
    html = html.replace(/\n/gim, '<br>');
    return html;
  }

  function getCompanyMonogram(name) {
    if (!name) return "CO";
    const clean = String(name).trim().replace(/[^a-zA-Z0-9\s]/g, "");
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return clean.slice(0, 2).toUpperCase() || "CO";
  }

  function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "fixed top-6 left-1/2 -translate-x-1/2 z-[9999] flex flex-col items-center space-y-2.5 pointer-events-none w-[94vw] max-w-2xl";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    
    let bgClass = "bg-surface-container-low/95 border-outline-variant/50 text-on-surface shadow-[0_12px_40px_rgba(0,0,0,0.6)]";
    let icon = "info";
    let badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-primary-container/20 text-primary border border-primary-container/40 uppercase tracking-wider shrink-0">Info</span>`;

    if (type === "error") {
      bgClass = "bg-surface-container-low/95 border-error/60 text-on-surface shadow-[0_14px_45px_rgba(255,84,73,0.25)] ring-1 ring-error/40";
      icon = "alert-octagon";
      badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-error/20 text-error border border-error/40 uppercase tracking-wider shrink-0">Error</span>`;
    } else if (type === "warning") {
      bgClass = "bg-surface-container-low/95 border-tertiary/60 text-on-surface shadow-[0_14px_45px_rgba(255,185,95,0.25)] ring-1 ring-tertiary/40";
      const isAuthPrompt = message.toLowerCase().includes("sign in") || message.toLowerCase().includes("login") || message.toLowerCase().includes("auth");
      icon = isAuthPrompt ? "lock" : "alert-triangle";
      const badgeText = isAuthPrompt ? "Sign In Required" : "Attention";
      badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-tertiary/20 text-tertiary border border-tertiary/40 uppercase tracking-wider shrink-0">${badgeText}</span>`;
    } else if (type === "success") {
      bgClass = "bg-surface-container-low/95 border-secondary/60 text-on-surface shadow-[0_14px_45px_rgba(78,222,163,0.25)] ring-1 ring-secondary/40";
      icon = "check-circle-2";
      badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-secondary/20 text-secondary border border-secondary/40 uppercase tracking-wider shrink-0">Success</span>`;
    }

    toast.className = `${bgClass} border rounded-2xl px-5 py-3.5 flex items-center justify-between space-x-4 text-body-sm font-medium pointer-events-auto backdrop-blur-md transition-all duration-300 transform -translate-y-4 opacity-0 scale-95 w-auto min-w-[340px] sm:min-w-[500px] max-w-2xl shadow-xl`;
    toast.innerHTML = `
      <div class="flex items-center space-x-3.5 min-w-0 flex-1">
        <i data-lucide="${icon}" class="w-5 h-5 shrink-0 text-on-surface"></i>
        ${badge}
        <span class="leading-relaxed text-sm">${message}</span>
      </div>
      <button type="button" class="toast-close p-1.5 hover:bg-surface-container-highest rounded-lg text-outline hover:text-on-surface transition shrink-0 cursor-pointer ml-2" title="Dismiss">
        <i data-lucide="x" class="w-4 h-4"></i>
      </button>
    `;

    const closeBtn = toast.querySelector(".toast-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        toast.classList.add("opacity-0", "-translate-y-4", "scale-95");
        setTimeout(() => toast.remove(), 250);
      });
    }

    container.appendChild(toast);
    refreshIcons();

    requestAnimationFrame(() => {
      toast.classList.remove("-translate-y-4", "opacity-0", "scale-95");
      toast.classList.add("translate-y-0", "opacity-100", "scale-100");
    });

    const displayDuration = type === "error" ? 5500 : (type === "warning" ? 4500 : 3500);
    setTimeout(() => {
      if (toast.isConnected) {
        toast.classList.add("opacity-0", "-translate-y-4", "scale-95");
        setTimeout(() => toast.remove(), 250);
      }
    }, displayDuration);
  }

  // Centralized HTTP error prompt handler for 4xx/5xx status codes
  async function handleHttpError(response, defaultMsg = "Request failed") {
    let errorDetail = "";
    try {
      const clone = response.clone();
      const contentType = clone.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await clone.json();
        errorDetail = data.detail || data.error || data.message || "";
      } else {
        const text = await clone.text();
        if (text && text.length < 200 && !text.includes("<html")) {
          errorDetail = text;
        }
      }
    } catch (_) {}

    const status = response ? response.status : 0;
    if (status === 401) {
      showToast(errorDetail || "Authentication required. Please sign in to continue.", "warning");
    } else if (status === 403) {
      showToast(errorDetail || "Access restricted. Master Admin privileges required.", "error");
    } else if (status === 404) {
      showToast(errorDetail || "Requested resource or endpoint was not found.", "warning");
    } else if (status === 422) {
      showToast(errorDetail || "Invalid request payload. Please verify your input parameters.", "warning");
    } else if (status === 429) {
      showToast(errorDetail || "Rate limit reached. Please wait a moment before retrying.", "warning");
    } else if (status >= 500) {
      showToast(errorDetail || "Server telemetry error. Please try again in a few moments.", "error");
    } else {
      showToast(errorDetail || defaultMsg || `Request failed with HTTP ${status}`, "error");
    }
  }

  // Expose globally for modular usage
  window.showToast = showToast;
  window.handleHttpError = handleHttpError;

  function highlightFieldWarning(element, message = null) {
    if (!element) return;
    element.classList.add("input-warning-highlight");
    try {
      if (typeof element.focus === "function") {
        element.focus();
      }
      if (typeof element.scrollIntoView === "function") {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    } catch (_) {}

    if (message) {
      showToast(message, "warning");
    }

    const cleanup = () => {
      element.classList.remove("input-warning-highlight");
      element.removeEventListener("input", cleanup);
      element.removeEventListener("change", cleanup);
    };
    element.addEventListener("input", cleanup);
    element.addEventListener("change", cleanup);

    setTimeout(() => {
      element.classList.remove("input-warning-highlight");
    }, 3200);
  }

  function switchTab(tabId) {
    const navItems = [
      { id: "companies", btn: tabCompanies, sec: secCompanies },
      { id: "scout", btn: tabScout, sec: secScout },
      { id: "outreach", btn: tabOutreach, sec: secOutreach },
      { id: "resume", btn: tabResume, sec: secResume }
    ];

    navItems.forEach(({ id, btn, sec }) => {
      const dot = btn?.querySelector(".active-dot");
      if (id === tabId) {
        btn?.classList.add("active", "bg-surface-container-highest/60", "text-primary");
        btn?.classList.remove("text-on-surface-variant");
        dot?.classList.remove("hidden");
        sec?.classList.remove("hidden");
      } else {
        btn?.classList.remove("active", "bg-surface-container-highest/60", "text-primary");
        btn?.classList.add("text-on-surface-variant");
        dot?.classList.add("hidden");
        sec?.classList.add("hidden");
      }
    });

    if (tabId === "scout") {
      updateScoutViewFromInputs();
    } else if (tabId === "companies") {
      applyCompanyFiltersAndRender();
    } else if (tabId === "outreach") {
      if (!outreachLoaded || allOutreachCompanies.length === 0) {
        fetchOutreachCompanies(false);
      } else {
        renderPitchesList();
      }
      fetchAuditLogs();
    }
    activeTab = tabId;
    refreshIcons();
  }

  if (tabScout) tabScout.addEventListener("click", () => switchTab("scout"));
  if (tabCompanies) tabCompanies.addEventListener("click", () => switchTab("companies"));
  if (tabResume) tabResume.addEventListener("click", () => switchTab("resume"));
  if (tabOutreach) tabOutreach.addEventListener("click", () => switchTab("outreach"));

  // Quick action buttons redirecting to Scout Leads or All Companies
  const btnGotoScout = document.getElementById("btn-goto-scout");
  const btnHeaderScout = document.getElementById("btn-header-scout");
  const btnSwitchToCompanies = document.getElementById("btn-switch-to-companies");
  const btnJumpCompanies = document.getElementById("btn-jump-companies");

  if (btnGotoScout) btnGotoScout.addEventListener("click", () => switchTab("scout"));
  if (btnHeaderScout) btnHeaderScout.addEventListener("click", () => switchTab("scout"));
  if (btnSwitchToCompanies) btnSwitchToCompanies.addEventListener("click", () => switchTab("companies"));
  if (btnJumpCompanies) btnJumpCompanies.addEventListener("click", () => switchTab("companies"));

  // Sidebar Expand / Collapse Controller
  const appSidebar = document.getElementById("app-sidebar");
  const mainContentWrap = document.getElementById("main-content-wrap");
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  const btnExpandSidebarMini = document.getElementById("btn-expand-sidebar-mini");
  const sidebarBrandBtn = document.getElementById("sidebar-brand-btn");

  function toggleSidebar() {
    if (!appSidebar || !mainContentWrap) return;
    const isCollapsed = appSidebar.classList.toggle("collapsed");
    mainContentWrap.classList.toggle("sidebar-collapsed", isCollapsed);
    try {
      localStorage.setItem("sidebar_collapsed", isCollapsed ? "1" : "0");
    } catch (_) {}
    refreshIcons();
  }

  if (btnToggleSidebar) btnToggleSidebar.addEventListener("click", toggleSidebar);
  if (btnExpandSidebarMini) btnExpandSidebarMini.addEventListener("click", toggleSidebar);
  if (sidebarBrandBtn) {
    sidebarBrandBtn.addEventListener("click", () => {
      if (appSidebar?.classList.contains("collapsed")) {
        toggleSidebar();
      }
    });
  }

  // Restore saved collapse state preference
  try {
    if (localStorage.getItem("sidebar_collapsed") === "1" && window.innerWidth >= 1024) {
      appSidebar?.classList.add("collapsed");
      mainContentWrap?.classList.add("sidebar-collapsed");
    }
  } catch (_) {}

  // Mobile Off-Canvas Drawer Controller (< 768px)
  const btnMobileSidebar = document.getElementById("btn-mobile-sidebar");
  const btnCloseSidebarMobile = document.getElementById("btn-close-sidebar-mobile");
  const mobileSidebarOverlay = document.getElementById("mobile-sidebar-overlay");

  function toggleMobileSidebar(open) {
    const shouldOpen = typeof open === "boolean" ? open : !appSidebar?.classList.contains("mobile-open");
    if (shouldOpen) {
      appSidebar?.classList.add("mobile-open");
      mobileSidebarOverlay?.classList.add("active");
      document.body.style.overflow = "hidden";
    } else {
      appSidebar?.classList.remove("mobile-open");
      mobileSidebarOverlay?.classList.remove("active");
      document.body.style.overflow = "";
    }
    refreshIcons();
  }

  if (btnMobileSidebar) btnMobileSidebar.addEventListener("click", () => toggleMobileSidebar(true));
  if (btnCloseSidebarMobile) btnCloseSidebarMobile.addEventListener("click", () => toggleMobileSidebar(false));
  if (mobileSidebarOverlay) mobileSidebarOverlay.addEventListener("click", () => toggleMobileSidebar(false));

  // Auto-close mobile sidebar when switching tabs on mobile
  [tabScout, tabCompanies, tabResume, tabOutreach].forEach(tab => {
    tab?.addEventListener("click", () => {
      if (window.innerWidth < 768) {
        toggleMobileSidebar(false);
      }
    });
  });

  // Navigation & Refresh shortcuts
  const btnQuickRefresh = document.getElementById("btn-quick-refresh");
  if (btnQuickRefresh) btnQuickRefresh.addEventListener("click", () => fetchCompanies());

  // Multi-Selection State for Bulk Lead Actions
  const selectedCompanyIds = new Set();
  const checkboxSelectAll = document.getElementById("checkbox-select-all");
  const labelSelectAll = document.getElementById("label-select-all");
  const bulkActionBar = document.getElementById("bulk-action-bar");
  const bulkSelectedCount = document.getElementById("bulk-selected-count");
  const btnBulkExclude = document.getElementById("btn-bulk-exclude");
  const btnBulkRestore = document.getElementById("btn-bulk-restore");
  const btnBulkClear = document.getElementById("btn-bulk-clear");
  const companiesContainer = document.getElementById("companies-container");

  function updateBulkActionBar() {
    const canManageLeads = Boolean((isMasterAdmin && currentUser && currentUser.is_logged_in) || isDevMode);
    if (!canManageLeads) {
      if (bulkActionBar) {
        bulkActionBar.classList.add("hidden");
        bulkActionBar.classList.remove("flex");
      }
      return;
    }
    const count = selectedCompanyIds.size;
    if (!bulkActionBar) return;

    if (count === 0) {
      bulkActionBar.classList.add("hidden");
      bulkActionBar.classList.remove("flex");
      if (checkboxSelectAll) {
        checkboxSelectAll.checked = false;
        checkboxSelectAll.indeterminate = false;
        if (labelSelectAll) labelSelectAll.textContent = "Select All";
      }
      return;
    }

    bulkActionBar.classList.remove("hidden");
    bulkActionBar.classList.add("flex");

    if (bulkSelectedCount) bulkSelectedCount.textContent = count;
    document.querySelectorAll(".bulk-count-num").forEach(el => {
      el.textContent = count;
    });

    if (activeMetricFilter === "invalid") {
      btnBulkRestore?.classList.remove("hidden");
      btnBulkExclude?.classList.add("hidden");
    } else {
      btnBulkExclude?.classList.remove("hidden");
      btnBulkRestore?.classList.add("hidden");
    }
    refreshIcons();
  }

  function updateSelectAllCheckboxState(pageItems) {
    if (!checkboxSelectAll || !pageItems || pageItems.length === 0) {
      if (checkboxSelectAll) {
        checkboxSelectAll.checked = false;
        checkboxSelectAll.indeterminate = false;
        if (labelSelectAll) labelSelectAll.textContent = "Select All";
      }
      return;
    }
    const pageIds = pageItems.map(c => c.id);
    const selectedOnPage = pageIds.filter(id => selectedCompanyIds.has(id)).length;

    if (selectedOnPage === 0) {
      checkboxSelectAll.checked = false;
      checkboxSelectAll.indeterminate = false;
      if (labelSelectAll) labelSelectAll.textContent = "Select All";
    } else if (selectedOnPage === pageIds.length) {
      checkboxSelectAll.checked = true;
      checkboxSelectAll.indeterminate = false;
      if (labelSelectAll) labelSelectAll.textContent = `All (${pageIds.length}) Selected`;
    } else {
      checkboxSelectAll.checked = false;
      checkboxSelectAll.indeterminate = true;
      if (labelSelectAll) labelSelectAll.textContent = `${selectedOnPage}/${pageIds.length} Selected`;
    }
  }

  if (checkboxSelectAll) {
    checkboxSelectAll.addEventListener("change", () => {
      const pageCards = companiesContainer ? Array.from(companiesContainer.querySelectorAll(".company-checkbox")) : [];
      if (checkboxSelectAll.checked) {
        pageCards.forEach(chk => {
          const id = parseInt(chk.dataset.id, 10);
          if (id) {
            selectedCompanyIds.add(id);
            chk.checked = true;
            const parentCard = chk.closest(".company-card") || chk.closest(".company-card-invalid") || chk.closest("div[data-id]");
            if (parentCard) {
              parentCard.classList.add("border-primary", "ring-1", "ring-primary");
              parentCard.classList.remove("border-outline-variant/30");
            }
          }
        });
      } else {
        pageCards.forEach(chk => {
          const id = parseInt(chk.dataset.id, 10);
          if (id) {
            selectedCompanyIds.delete(id);
            chk.checked = false;
            const parentCard = chk.closest(".company-card") || chk.closest(".company-card-invalid") || chk.closest("div[data-id]");
            if (parentCard) {
              parentCard.classList.remove("border-primary", "ring-1", "ring-primary", "ring-2", "ring-primary/60", "border-primary", "bg-slate-800/80", "bg-slate-800/90", "border-primary-container", "ring-primary-container");
              parentCard.classList.add("border-outline-variant/30");
            }
          }
        });
      }
      updateBulkActionBar();
      if (labelSelectAll) {
        labelSelectAll.textContent = checkboxSelectAll.checked ? `All (${pageCards.length}) Selected` : "Select All";
      }
    });
  }

  if (btnBulkClear) {
    btnBulkClear.addEventListener("click", () => {
      selectedCompanyIds.clear();
      document.querySelectorAll(".company-checkbox").forEach(chk => {
        chk.checked = false;
      });
      document.querySelectorAll(".company-card, .company-card-invalid").forEach(card => {
        card.classList.remove(
          "border-primary", "ring-1", "ring-primary", "ring-2", 
          "ring-primary/60", "border-primary", "bg-slate-800/80", 
          "bg-slate-800/90", "border-primary-container", "ring-primary-container", 
          "ring-rose-500/80", "border-rose-500", "bg-rose-500/10"
        );
        card.classList.add("border-outline-variant/30");
      });
      if (checkboxSelectAll) {
        checkboxSelectAll.checked = false;
        checkboxSelectAll.indeterminate = false;
      }
      if (labelSelectAll) labelSelectAll.textContent = "Select All";
      updateBulkActionBar();
    });
  }

  if (btnBulkExclude) {
    btnBulkExclude.addEventListener("click", async () => {
      const ids = Array.from(selectedCompanyIds);
      if (ids.length === 0) return;

      const oldHtml = btnBulkExclude.innerHTML;
      btnBulkExclude.disabled = true;
      btnBulkExclude.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Excluding ${ids.length} Leads...</span>`;
      refreshIcons();

      try {
        const res = await fetch("/api/companies/bulk-invalidate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_ids: ids, reason: "Excluded by Master Admin" })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          // Optimistically update in-memory
          ids.forEach(id => {
            const found = companies.find(c => c.id === id);
            if (found) {
              found.is_invalid = true;
              found.invalid_reason = "Excluded by Master Admin";
            }
          });
          selectedCompanyIds.clear();
          updateBulkActionBar();
          await fetchCompanies(true);
          showToast(`Successfully marked ${ids.length} leads as excluded.`, "error");
        } else {
          showToast("Bulk exclude failed: " + (data.detail || data.message || "Unauthorized"), "error");
        }
      } catch (err) {
        showToast("Bulk exclude error: " + err.message, "error");
      } finally {
        btnBulkExclude.disabled = false;
        btnBulkExclude.innerHTML = oldHtml;
        refreshIcons();
      }
    });
  }

  if (btnBulkRestore) {
    btnBulkRestore.addEventListener("click", async () => {
      const ids = Array.from(selectedCompanyIds);
      if (ids.length === 0) return;

      const oldHtml = btnBulkRestore.innerHTML;
      btnBulkRestore.disabled = true;
      btnBulkRestore.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Restoring ${ids.length} Leads...</span>`;
      refreshIcons();

      try {
        const res = await fetch("/api/companies/bulk-restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_ids: ids })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          // Optimistically update in-memory
          ids.forEach(id => {
            const found = companies.find(c => c.id === id);
            if (found) {
              found.is_invalid = false;
              found.invalid_reason = null;
            }
          });
          selectedCompanyIds.clear();
          updateBulkActionBar();
          await fetchCompanies(true);
          showToast(`Successfully restored ${ids.length} leads to active directory.`, "success");
        } else {
          showToast("Bulk restore failed: " + (data.detail || data.message || "Unauthorized"), "error");
        }
      } catch (err) {
        showToast("Bulk restore error: " + err.message, "error");
      } finally {
        btnBulkRestore.disabled = false;
        btnBulkRestore.innerHTML = oldHtml;
        refreshIcons();
      }
    });
  }

  // ==========================================
  // STAGE 1: LEAD SCOUT CONTROLS & REAL-TIME RESULTS
  // ==========================================
  const scoutForm = document.getElementById("scout-form");
  const btnStartScout = document.getElementById("btn-start-scout");
  const btnLoadCompanies = document.getElementById("btn-load-companies");
  const scoutMonitor = document.getElementById("scout-monitor");
  const monitorStatus = document.getElementById("monitor-status");
  const monitorCount = document.getElementById("monitor-count");
  const monitorProgressBar = document.getElementById("monitor-progress-bar");
  const scoutTerminalLogs = document.getElementById("scout-terminal-logs");
  const scoutTerminalContainer = document.getElementById("scout-terminal-container");
  const btnToggleLogs = document.getElementById("btn-toggle-logs");

  // Scout Results Elements
  const scoutCardsContainer = document.getElementById("scout-cards-container");
  const scoutLeadsCount = document.getElementById("scout-leads-count");
  const scoutQueryLabel = document.getElementById("scout-query-label");
  const inputKeyword = document.getElementById("input-keyword");
  const inputCity = document.getElementById("input-city");

  const filterInput = document.getElementById("filter-search");
  const filterKeywordSelect = document.getElementById("filter-keyword-select");
  const filterTechSelect = document.getElementById("filter-tech-select");
  const filterCitySelect = document.getElementById("filter-city-select");
  const sortSelect = document.getElementById("sort-select");
  const btnFilterEmails = document.getElementById("btn-filter-emails");
  const filterTabExcluded = document.getElementById("filter-tab-excluded");

  // Companies Directory Pagination State & Elements
  const companiesPagination = document.getElementById("companies-pagination");
  const companiesPageRange = document.getElementById("companies-page-range");
  const companiesPageTotal = document.getElementById("companies-page-total");
  const companiesPerPageSelect = document.getElementById("companies-per-page");
  const companiesPageButtons = document.getElementById("companies-page-buttons");
  const companiesPaginationBottom = document.getElementById("companies-pagination-bottom");
  const companiesPageRangeBottom = document.getElementById("companies-page-range-bottom");
  const companiesPageTotalBottom = document.getElementById("companies-page-total-bottom");
  const companiesPageButtonsBottom = document.getElementById("companies-page-buttons-bottom");
  let companiesCurrentPage = 1;
  let companiesPerPage = 20;
  let currentFilteredCompanies = [];
  const companyDetailCache = new Map();

  // Scout Leads Pagination State & Elements
  const scoutPagination = document.getElementById("scout-pagination");
  const scoutPageRange = document.getElementById("scout-page-range");
  const scoutPageTotal = document.getElementById("scout-page-total");
  const scoutPerPageSelect = document.getElementById("scout-per-page");
  const scoutPageButtons = document.getElementById("scout-page-buttons");
  let scoutCurrentPage = 1;
  let scoutPerPage = 20;
  let currentScoutList = [];
  let currentScoutQueryLabel = "";
  let liveScrapedResults = [];

  // Outreach Hub Pagination & Pipeline State
  let outreachLoaded = false;
  let allOutreachCompanies = [];
  let isOutreachLoading = false;
  let outreachCurrentPage = 1;
  let outreachPerPage = 20;

  function renderPaginationControls({
    paginationEl,
    rangeEl,
    totalEl,
    buttonsEl,
    totalItems,
    currentPage,
    pageSize,
    onPageChange
  }) {
    if (!paginationEl) return;
    if (!totalItems || totalItems === 0) {
      paginationEl.classList.add("hidden");
      return;
    }
    paginationEl.classList.remove("hidden");

    const totalPages = pageSize > 0 ? Math.ceil(totalItems / pageSize) : 1;
    const safeCurrentPage = Math.min(Math.max(1, currentPage), totalPages);

    const startIdx = pageSize > 0 ? (safeCurrentPage - 1) * pageSize + 1 : 1;
    const endIdx = pageSize > 0 ? Math.min(safeCurrentPage * pageSize, totalItems) : totalItems;

    if (rangeEl) rangeEl.textContent = `${startIdx}-${endIdx}`;
    if (totalEl) totalEl.textContent = totalItems.toLocaleString();

    if (!buttonsEl) return;
    buttonsEl.innerHTML = "";

    // Mobile View (< 640px): Prev, Page X of Y, Next
    const mobileWrapper = document.createElement("div");
    mobileWrapper.className = "flex sm:hidden items-center space-x-1.5";

    const prevBtnMobile = document.createElement("button");
    prevBtnMobile.type = "button";
    prevBtnMobile.className = `p-1.5 rounded-lg text-xs font-medium border ${safeCurrentPage <= 1 ? 'opacity-40 cursor-not-allowed text-on-surface-variant/40 border-outline-variant/30 bg-surface-container' : 'btn-tactile-slate text-on-surface hover:bg-surface-container-high cursor-pointer'}`;
    prevBtnMobile.innerHTML = `<i data-lucide="chevron-left" class="w-3.5 h-3.5"></i>`;
    prevBtnMobile.disabled = safeCurrentPage <= 1;
    prevBtnMobile.addEventListener("click", () => {
      if (safeCurrentPage > 1) onPageChange(safeCurrentPage - 1);
    });

    const pageInfoMobile = document.createElement("span");
    pageInfoMobile.className = "text-xs font-mono text-on-surface font-semibold px-2";
    pageInfoMobile.textContent = `${safeCurrentPage} / ${totalPages}`;

    const nextBtnMobile = document.createElement("button");
    nextBtnMobile.type = "button";
    nextBtnMobile.className = `p-1.5 rounded-lg text-xs font-medium border ${safeCurrentPage >= totalPages ? 'opacity-40 cursor-not-allowed text-on-surface-variant/40 border-outline-variant/30 bg-surface-container' : 'btn-tactile-slate text-on-surface hover:bg-surface-container-high cursor-pointer'}`;
    nextBtnMobile.innerHTML = `<i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>`;
    nextBtnMobile.disabled = safeCurrentPage >= totalPages;
    nextBtnMobile.addEventListener("click", () => {
      if (safeCurrentPage < totalPages) onPageChange(safeCurrentPage + 1);
    });

    mobileWrapper.appendChild(prevBtnMobile);
    mobileWrapper.appendChild(pageInfoMobile);
    mobileWrapper.appendChild(nextBtnMobile);
    buttonsEl.appendChild(mobileWrapper);

    // Desktop/Tablet View (>= 640px): Full numbered sequence with ellipses
    const desktopWrapper = document.createElement("div");
    desktopWrapper.className = "hidden sm:flex items-center space-x-1";

    const prevBtnDesktop = document.createElement("button");
    prevBtnDesktop.type = "button";
    prevBtnDesktop.className = `px-2.5 py-1 rounded-lg text-xs font-medium border flex items-center space-x-1 ${safeCurrentPage <= 1 ? 'opacity-40 cursor-not-allowed text-on-surface-variant/40 border-outline-variant/30 bg-surface-container' : 'btn-tactile-slate text-on-surface hover:bg-surface-container-high cursor-pointer'}`;
    prevBtnDesktop.innerHTML = `<i data-lucide="chevron-left" class="w-3.5 h-3.5"></i><span>Prev</span>`;
    prevBtnDesktop.disabled = safeCurrentPage <= 1;
    prevBtnDesktop.addEventListener("click", () => {
      if (safeCurrentPage > 1) onPageChange(safeCurrentPage - 1);
    });
    desktopWrapper.appendChild(prevBtnDesktop);

    const pageNumbers = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= Math.max(1, totalPages); i++) pageNumbers.push(i);
    } else {
      pageNumbers.push(1);
      if (safeCurrentPage > 3) pageNumbers.push("...");
      const start = Math.max(2, safeCurrentPage - 1);
      const end = Math.min(totalPages - 1, safeCurrentPage + 1);
      for (let i = start; i <= end; i++) {
        if (!pageNumbers.includes(i)) pageNumbers.push(i);
      }
      if (safeCurrentPage < totalPages - 2) pageNumbers.push("...");
      if (!pageNumbers.includes(totalPages)) pageNumbers.push(totalPages);
    }

    pageNumbers.forEach(p => {
      if (p === "...") {
        const dots = document.createElement("span");
        dots.className = "px-2 py-1 text-xs text-on-surface-variant/60 font-mono";
        dots.textContent = "...";
        desktopWrapper.appendChild(dots);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        const isActive = (p === safeCurrentPage);
        btn.className = `min-w-[32px] px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition ${isActive ? 'bg-primary text-on-primary font-bold shadow-sm cursor-default' : 'btn-tactile-slate text-on-surface-variant hover:text-on-surface cursor-pointer'}`;
        btn.textContent = p;
        btn.disabled = isActive;
        btn.addEventListener("click", () => {
          if (p !== safeCurrentPage) onPageChange(p);
        });
        desktopWrapper.appendChild(btn);
      }
    });

    const nextBtnDesktop = document.createElement("button");
    nextBtnDesktop.type = "button";
    nextBtnDesktop.className = `px-2.5 py-1 rounded-lg text-xs font-medium border flex items-center space-x-1 ${safeCurrentPage >= totalPages ? 'opacity-40 cursor-not-allowed text-on-surface-variant/40 border-outline-variant/30 bg-surface-container' : 'btn-tactile-slate text-on-surface hover:bg-surface-container-high cursor-pointer'}`;
    nextBtnDesktop.innerHTML = `<span>Next</span><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>`;
    nextBtnDesktop.disabled = safeCurrentPage >= totalPages;
    nextBtnDesktop.addEventListener("click", () => {
      if (safeCurrentPage < totalPages) onPageChange(safeCurrentPage + 1);
    });
    desktopWrapper.appendChild(nextBtnDesktop);

    buttonsEl.appendChild(desktopWrapper);
    refreshIcons();
  }

  function cleanAddressText(address) {
    if (!address) return "";
    const trimmed = address.trim();
    const lower = trimmed.toLowerCase();
    if (
      lower.startsWith("open") ||
      lower.startsWith("closed") ||
      lower.includes("on-site") ||
      lower.includes("online appointments") ||
      /^\d\.\d\s*\(\d+\)/.test(trimmed)
    ) {
      return "";
    }
    return trimmed;
  }

  function buildMapsUrl(name, address, city) {
    const clean = cleanAddressText(address);
    const query = [name, clean, city].filter(Boolean).join(", ");
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query || name || 'Google Maps')}`;
  }


  if (btnToggleLogs) {
    btnToggleLogs.addEventListener("click", () => {
      if (scoutTerminalContainer) {
        const isHidden = scoutTerminalContainer.classList.toggle("hidden");
        btnToggleLogs.textContent = isHidden ? "Show Console" : "Hide Console";
      }
    });
  }

  function renderScoutResults(list, queryLabel) {
    currentScoutList = list || [];
    currentScoutQueryLabel = queryLabel;

    if (scoutLeadsCount) scoutLeadsCount.textContent = `${(list || []).length} Leads`;
    if (scoutQueryLabel) scoutQueryLabel.textContent = queryLabel || '—';

    if (scoutCardsContainer) scoutCardsContainer.innerHTML = "";
    if (scoutPagination) scoutPagination.classList.add("hidden");

    if (!list || list.length === 0) {
      if (scoutCardsContainer) {
        scoutCardsContainer.innerHTML = `
          <div class="col-span-full py-12 px-4 text-center bg-surface-container-low border border-outline-variant/30 rounded-2xl space-y-3 shadow-sm">
            <div class="inline-flex p-3 rounded-full bg-primary/10 text-primary border border-primary/20 shadow-sm">
              <i data-lucide="radar" class="w-6 h-6"></i>
            </div>
            <p class="text-sm font-semibold text-on-surface">Ready to Discover Leads</p>
            <p class="text-xs text-on-surface-variant max-w-md mx-auto leading-relaxed">
              Enter your Target Keyword and Location above, then click <strong class="text-primary">"Find Leads"</strong>. Real-time scraped leads from your search session will appear here instantly.
            </p>
          </div>
        `;
      }
      refreshIcons();
      return;
    }

    const totalItems = list.length;
    const totalPages = scoutPerPage > 0 ? Math.ceil(totalItems / scoutPerPage) : 1;
    scoutCurrentPage = Math.min(Math.max(1, scoutCurrentPage), totalPages);

    const pagedList = scoutPerPage > 0
      ? list.slice((scoutCurrentPage - 1) * scoutPerPage, scoutCurrentPage * scoutPerPage)
      : list;

    pagedList.forEach(c => {
      const cleanAddr = cleanAddressText(c.address);
      const mapsUrl = c.location_url || buildMapsUrl(c.name, cleanAddr, c.city);
      const siteUrl = c.website_url || (c.domain ? `https://${c.domain}` : "#");

      const badge = c.already_contacted 
        ? `<span class="px-2 py-0.5 rounded text-caption font-mono bg-primary/10 text-primary border border-primary/30 text-[10px] font-semibold flex items-center space-x-1 shrink-0"><span class="material-symbols-outlined text-[12px]">check</span><span>Contacted</span></span>`
        : (c.is_enriched 
            ? `<span class="px-2 py-0.5 rounded text-caption font-mono bg-secondary/15 text-secondary border border-secondary/30 text-[10px] font-semibold flex items-center space-x-1 shrink-0"><span class="material-symbols-outlined text-[12px]">auto_awesome</span><span>Enriched</span></span>`
            : `<span class="px-2 py-0.5 rounded text-caption font-mono bg-surface-container text-on-surface-variant border border-outline-variant/60 text-[10px] shrink-0">Verified</span>`);

      const ratingDisplay = (c.rating && c.rating > 0)
        ? `<span class="text-tertiary font-semibold flex items-center space-x-1 font-mono text-[11px]">
             <span class="material-symbols-outlined text-[13px] text-tertiary">star</span><span>${Number(c.rating).toFixed(1)}</span>
             <span class="text-on-surface-variant font-normal text-[10px]">(${c.reviews_count || 0})</span>
           </span>`
        : `<span class="text-on-surface-variant text-[10px] font-mono">No ratings</span>`;

      // 1. Scout Lead Card (Artisanal Bento Workshop UI)
      if (scoutCardsContainer) {
        const card = document.createElement("div");
        const monogram = getCompanyMonogram(c.name);
        const monoThemes = [
          { bg: "bg-surface-container-high text-on-surface border-outline-variant/60" },
          { bg: "bg-secondary/15 text-secondary border-secondary/30" },
          { bg: "bg-tertiary/15 text-tertiary border-tertiary/30" },
          { bg: "bg-surface-container-highest text-on-surface-variant border-outline-variant/60" }
        ];
        const monoTheme = monoThemes[(c.id || 0) % monoThemes.length];
        const ratingVal = (c.rating && c.rating > 0) ? Number(c.rating).toFixed(1) : null;

        card.className = "scout-lead-card group bg-surface-container-low border border-outline-variant/50 hover:border-outline hover:bg-surface-container rounded-xl p-5 flex flex-col justify-between transition-all duration-200 shadow-sm hover:shadow-lg cursor-pointer relative min-w-0";
        card.innerHTML = `
          <div>
            <!-- Top Row: Monogram + Name + Domain + Badge -->
            <div class="flex items-start justify-between gap-3 mb-3">
              <div class="flex items-start gap-2.5 min-w-0 flex-1">
                <div class="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-label-md ${monoTheme.bg} border shrink-0 font-mono shadow-sm">
                  ${monogram}
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-1.5">
                    <h3 class="text-headline-sm font-headline-sm text-on-surface font-semibold break-words line-clamp-2 leading-snug hover:text-primary" title="${escapeHTML(c.name)}">${escapeHTML(c.name)}</h3>
                    <a class="text-on-surface-variant hover:text-primary transition-colors shrink-0 mt-0.5" href="${siteUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" title="Visit website">
                      <span class="material-symbols-outlined text-[14px]">open_in_new</span>
                    </a>
                  </div>
                  <span class="text-caption font-mono text-on-surface-variant truncate block mt-0.5">${escapeHTML(c.domain || '')}</span>
                </div>
              </div>
              <div class="shrink-0 pt-0.5">
                ${badge}
              </div>
            </div>

            <!-- Meta: Rating & Phone -->
            <div class="flex items-center justify-between text-caption font-caption py-2 border-y border-outline-variant/40 mb-3 gap-2">
              <div class="flex items-center gap-1 text-on-surface shrink-0 font-mono text-[11px]">
                ${ratingVal ? `
                  <span class="material-symbols-outlined text-[14px] text-tertiary">star</span>
                  <span class="font-semibold text-tertiary">${ratingVal}</span>
                  <span class="text-on-surface-variant">(${c.reviews_count || 0})</span>
                ` : `<span class="text-on-surface-variant">No ratings</span>`}
              </div>
              ${c.phone ? `
                <a href="tel:${escapeHTML(c.phone)}" class="text-on-surface-variant hover:text-on-surface flex items-center gap-1 font-mono truncate text-[11px]" onclick="event.stopPropagation();" title="Call ${escapeHTML(c.phone)}">
                  <span class="material-symbols-outlined text-[13px]">phone</span>
                  <span class="truncate">${escapeHTML(c.phone)}</span>
                </a>
              ` : ''}
            </div>

            <!-- Address & Location -->
            <div class="text-caption font-caption text-on-surface-variant flex items-center gap-1.5 mb-4 truncate font-mono text-[11px]">
              <span class="material-symbols-outlined text-[14px] text-on-surface-variant shrink-0">location_on</span>
              <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="hover:text-on-surface truncate" onclick="event.stopPropagation();" title="${escapeHTML(cleanAddr || c.city || 'Google Maps')}">
                ${escapeHTML(cleanAddr || (c.city ? c.city + ', Location' : 'Location'))}
              </a>
            </div>
          </div>

          <!-- Bottom Tactile Action Buttons -->
          <div class="grid grid-cols-2 gap-2 mt-auto pt-3 border-t border-outline-variant/40">
            <a href="${siteUrl}" target="_blank" rel="noopener noreferrer" class="btn-tactile-slate px-3 py-1.5 rounded text-label-sm font-label-sm font-medium transition-colors text-center flex items-center justify-center gap-1" onclick="event.stopPropagation();">
              <span>Visit Site</span>
              <span class="material-symbols-outlined text-[13px]">open_in_new</span>
            </a>
            <button type="button" class="btn-scout-card-enrich btn-tactile-ecru px-3 py-1.5 rounded text-label-sm font-label-sm font-semibold transition-colors text-center cursor-pointer flex items-center justify-center gap-1">
              <span class="material-symbols-outlined text-[14px]">auto_awesome</span>
              <span>Enrich</span>
            </button>
          </div>
        `;

        card.addEventListener("click", () => openCompanyDetailsModal(c));
        const btnEnrich = card.querySelector(".btn-scout-card-enrich");
        if (btnEnrich) {
          btnEnrich.addEventListener("click", (e) => {
            e.stopPropagation();
            openCompanyDetailsModal(c);
          });
        }

        scoutCardsContainer.appendChild(card);
      }
    });

    renderPaginationControls({
      paginationEl: scoutPagination,
      rangeEl: scoutPageRange,
      totalEl: scoutPageTotal,
      buttonsEl: scoutPageButtons,
      totalItems: totalItems,
      currentPage: scoutCurrentPage,
      pageSize: scoutPerPage,
      onPageChange: (newPage) => {
        scoutCurrentPage = newPage;
        renderScoutResults(currentScoutList, currentScoutQueryLabel);
        if (scoutCardsContainer) {
          scoutCardsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });

    refreshIcons();
  }

  if (scoutPerPageSelect) {
    scoutPerPageSelect.addEventListener("change", (e) => {
      scoutPerPage = parseInt(e.target.value, 10);
      scoutCurrentPage = 1;
      renderScoutResults(currentScoutList, currentScoutQueryLabel);
    });
  }

  function updateScoutViewFromInputs(resetPage = true) {
    if (resetPage) {
      scoutCurrentPage = 1;
    }
    const kwDisplay = inputKeyword?.value?.trim() || "";
    const cityDisplay = inputCity?.value?.trim() || "";
    const queryTag = (kwDisplay && cityDisplay)
      ? `"${kwDisplay}" in "${cityDisplay}"`
      : (kwDisplay ? `"${kwDisplay}"` : (cityDisplay ? `in "${cityDisplay}"` : ""));

    // Find Leads tab ONLY shows live real-time scraped leads from current session
    if (liveScrapedResults && liveScrapedResults.length > 0) {
      renderScoutResults(liveScrapedResults, queryTag ? `Discovered Leads: ${queryTag}` : "Discovered Leads");
    } else {
      renderScoutResults([], queryTag ? `Ready to Search: ${queryTag}` : "—");
    }
  }

  let scoutInputTimer = null;
  if (inputKeyword) {
    inputKeyword.addEventListener("input", () => {
      clearTimeout(scoutInputTimer);
      scoutInputTimer = setTimeout(updateScoutViewFromInputs, 200);
    });
  }
  if (inputCity) {
    inputCity.addEventListener("input", () => {
      clearTimeout(scoutInputTimer);
      scoutInputTimer = setTimeout(updateScoutViewFromInputs, 200);
    });
  }

  // Close modals on Escape key press
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      cmodal?.classList.add("hidden");
      modal?.classList.add("hidden");
      loginModal?.classList.add("hidden");
    }
  });

  function sortCompaniesList(list) {
    if (!list || list.length === 0) return [];
    const sortVal = sortSelect ? sortSelect.value : "rating_desc";
    const copy = [...list];

    copy.sort((a, b) => {
      const rA = parseFloat(a.rating) || 0.0;
      const rB = parseFloat(b.rating) || 0.0;
      const cA = parseInt(a.reviews_count) || 0;
      const cB = parseInt(b.reviews_count) || 0;

      if (sortVal === "enriched_desc") {
        const eA = a.is_enriched ? 1 : 0;
        const eB = b.is_enriched ? 1 : 0;
        if (eB !== eA) return eB - eA; // Enriched (Yes) first, Unenriched (No) second
        if (rB !== rA) return rB - rA; // Secondary sort: rating desc
        return cB - cA;
      } else if (sortVal === "rating_desc") {
        if (rB !== rA) return rB - rA; // Primary: rating descending
        return cB - cA; // Secondary: reviews count descending
      } else if (sortVal === "reviews_desc") {
        if (cB !== cA) return cB - cA;
        return rB - rA;
      } else if (sortVal === "rating_asc") {
        if (rA !== rB) return rA - rB;
        return cA - cB;
      } else if (sortVal === "name_asc") {
        return (a.name || "").localeCompare(b.name || "");
      } else if (sortVal === "newest") {
        return (b.id || 0) - (a.id || 0);
      }
      return 0;
    });

    return copy;
  }

  // Metric Card Filter Elements & State
  let activeMetricFilter = null; // null (or "all"), "enriched", "emails", "contacted", "invalid"
  const statCardAll = document.getElementById("stat-card-all");
  const statCardEnriched = document.getElementById("stat-card-enriched");
  const statCardEmails = document.getElementById("stat-card-emails");
  const statCardContacted = document.getElementById("stat-card-contacted");
  const statCardInvalid = document.getElementById("stat-card-invalid");
  const statInvalidCount = document.getElementById("stat-invalid-count");
  const statInvalidHint = document.getElementById("stat-invalid-hint");

  const adminModeToggleGroup = document.getElementById("admin-mode-toggle-group");
  const btnModeAdmin = document.getElementById("btn-mode-admin");
  const btnModePreview = document.getElementById("btn-mode-preview");
  const adminPreviewBanner = document.getElementById("admin-preview-banner");
  const btnBannerExitPreview = document.getElementById("btn-banner-exit-preview");

  function updateMetricCardStyles() {
    const current = (!activeMetricFilter || activeMetricFilter === "all") ? "all" : activeMetricFilter;
    const cards = [
      { id: "all", el: statCardAll, activeRing: "ring-[#EFECE6]/80", activeBorder: "border-[#EFECE6]" },
      { id: "emails", el: statCardEmails, activeRing: "ring-[#86B29B]/80", activeBorder: "border-[#86B29B]" },
      { id: "enriched", el: statCardEnriched, activeRing: "ring-[#A48464]/80", activeBorder: "border-[#A48464]" },
      { id: "contacted", el: statCardContacted, activeRing: "ring-[#EFECE6]/80", activeBorder: "border-[#EFECE6]" },
      { id: "invalid", el: statCardInvalid, activeRing: "ring-[#E06C75]/80", activeBorder: "border-[#E06C75]" }
    ];

    cards.forEach(c => {
      if (!c.el) return;
      const isActive = (c.id === current);
      if (isActive) {
        c.el.classList.add("ring-2", "ring-primary/25", "border-primary", "bg-surface-container-high", "shadow-sm");
        c.el.classList.remove("border-outline-variant/30", "bg-surface-container-low", "opacity-80");
      } else {
        c.el.classList.remove("ring-2", "ring-primary/25", "border-primary", "bg-surface-container-high", "shadow-sm");
        c.el.classList.add("border-outline-variant/30", "bg-surface-container-low", "opacity-80");
      }
    });
  }

  function setActiveMetricFilter(filterName) {
    if (filterName === null || filterName === "all") {
      activeMetricFilter = null;
      filterInvalidOnly = false;
    } else if (activeMetricFilter === filterName) {
      // Toggle off if already active
      activeMetricFilter = null;
      filterInvalidOnly = false;
    } else {
      activeMetricFilter = filterName;
      filterInvalidOnly = (filterName === "invalid");
    }

    updateMetricCardStyles();
    applyCompanyFiltersAndRender();
  }

  function setAdminViewMode(mode) {
    adminViewMode = mode;
    if (mode === "admin") {
      btnModeAdmin?.classList.add("bg-primary-container", "text-on-primary-container");
      btnModeAdmin?.classList.remove("text-on-surface-variant");
      btnModePreview?.classList.remove("bg-amber-600", "text-white");
      btnModePreview?.classList.add("text-on-surface-variant");
      adminPreviewBanner?.classList.add("hidden");
      statCardInvalid?.classList.remove("hidden");
    } else {
      btnModePreview?.classList.add("bg-amber-600", "text-white");
      btnModePreview?.classList.remove("text-on-surface-variant");
      btnModeAdmin?.classList.remove("bg-primary-container", "text-on-primary-container");
      btnModeAdmin?.classList.add("text-on-surface-variant");
      adminPreviewBanner?.classList.remove("hidden");
      statCardInvalid?.classList.add("hidden");
      if (activeMetricFilter === "invalid") {
        activeMetricFilter = null;
        filterInvalidOnly = false;
      }
    }
    updateMetricCardStyles();
    applyCompanyFiltersAndRender();
    refreshIcons();
  }

  if (btnModeAdmin) btnModeAdmin.addEventListener("click", () => setAdminViewMode("admin"));
  if (btnModePreview) btnModePreview.addEventListener("click", () => setAdminViewMode("preview"));
  if (btnBannerExitPreview) btnBannerExitPreview.addEventListener("click", () => setAdminViewMode("admin"));

  // Metric Cards Click Handlers
  if (statCardAll) statCardAll.addEventListener("click", () => setActiveMetricFilter(null));
  if (statCardEnriched) statCardEnriched.addEventListener("click", () => setActiveMetricFilter("enriched"));
  if (statCardEmails) statCardEmails.addEventListener("click", () => setActiveMetricFilter("emails"));
  if (statCardContacted) {
    statCardContacted.addEventListener("click", () => {
      requireLogin(() => {
        setActiveMetricFilter("contacted");
      }, "Please sign in with Google to view and track your sent pitches.");
    });
  }
  if (statCardInvalid) statCardInvalid.addEventListener("click", () => setActiveMetricFilter("invalid"));

  async function handleInvalidateCompany(id, companyName) {
    selectedCompanyIds.delete(id);
    updateBulkActionBar();
    try {
      const res = await fetch(`/api/companies/${id}/invalidate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Excluded by Master Admin" })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        // Optimistically update in-memory model
        const target = companies.find(c => c.id === id);
        if (target) {
          target.is_invalid = true;
          target.invalid_reason = "Excluded by Master Admin";
        }
        selectedCompanyIds.delete(id);
        updateBulkActionBar();
        await fetchCompanies(true);
        if (activeModalCompany && activeModalCompany.id === id) {
          cmodal?.classList.add("hidden");
        }
        showToast(`'${companyName || 'Company'}' marked as invalid lead.`, "error");
      } else {
        showToast("Action failed: " + (data.detail || data.message || "Unauthorized"), "error");
      }
    } catch (err) {
      showToast("Invalidate error: " + err.message, "error");
    }
  }

  async function handleRestoreCompany(id, companyName) {
    selectedCompanyIds.delete(id);
    updateBulkActionBar();
    try {
      const res = await fetch(`/api/companies/${id}/restore`, {
        method: "POST"
      });
      const data = await res.json();
      if (res.ok && data.success) {
        // Optimistically update in-memory model
        const target = companies.find(c => c.id === id);
        if (target) {
          target.is_invalid = false;
          target.invalid_reason = null;
        }
        selectedCompanyIds.delete(id);
        updateBulkActionBar();
        await fetchCompanies(true);
        if (activeModalCompany && activeModalCompany.id === id) {
          cmodal?.classList.add("hidden");
        }
        showToast(`'${companyName || 'Company'}' restored to active leads.`, "success");
      } else {
        showToast("Restore failed: " + (data.detail || data.message || "Unauthorized"), "error");
      }
    } catch (err) {
      showToast("Restore error: " + err.message, "error");
    }
  }

  function updateCompanyMetrics(statsOrList) {
    const isLoggedIn = Boolean(
      (currentUser && currentUser.is_logged_in) ||
      (statsOrList && statsOrList.is_logged_in)
    );

    if (statsOrList && typeof statsOrList.total === "number") {
      const total = statsOrList.total || 0;
      const enriched = statsOrList.enriched || 0;
      const withEmails = statsOrList.emails || 0;
      const contacted = (isLoggedIn && typeof statsOrList.contacted === "number") ? statsOrList.contacted : null;
      const invalid = statsOrList.invalid || 0;

      const totalCountEl = document.getElementById("companies-total-count");
      if (totalCountEl) totalCountEl.textContent = total;

      const navBadgeEl = document.getElementById("nav-companies-badge");
      if (navBadgeEl) navBadgeEl.textContent = total;

      const headerCounter = document.getElementById("header-leads-counter");
      if (headerCounter) headerCounter.textContent = total;

      document.querySelectorAll(".badge-total-count").forEach(el => el.textContent = total);

      const statEnriched = document.getElementById("stat-enriched-count");
      if (statEnriched) statEnriched.textContent = enriched;

      const statEmails = document.getElementById("stat-emails-count");
      if (statEmails) statEmails.textContent = withEmails;

      const badgeEmails = document.getElementById("badge-emails-count");
      if (badgeEmails) badgeEmails.textContent = withEmails;

      // Contacted / Pitched Stat Card (STRICT: only visible if user is logged in and only for this user)
      const statContacted = document.getElementById("stat-contacted-count");
      const statContactedBadge = document.getElementById("stat-contacted-badge");
      const statContactedText = document.getElementById("stat-contacted-text");

      if (statContacted && statContactedBadge && statContactedText) {
        if (!isLoggedIn) {
          statContacted.textContent = "0";
          statContactedBadge.textContent = "Sign in";
          statContactedBadge.className = "text-caption font-caption text-outline px-1.5 py-0.5 rounded bg-surface-container font-mono text-[11px]";
          statContactedText.textContent = "Sign in to track your pitches";
        } else {
          const userContacted = contacted !== null ? contacted : 0;
          statContacted.textContent = userContacted;
          if (userContacted === 0) {
            statContactedBadge.textContent = "0% outreach";
            statContactedBadge.className = "text-caption font-caption text-outline px-1.5 py-0.5 rounded bg-surface-container-highest font-mono text-[11px]";
            statContactedText.textContent = "No campaigns sent yet";
          } else {
            const responseRatePct = total > 0 ? Math.round((userContacted / total) * 100) : 0;
            statContactedBadge.textContent = `${responseRatePct}% outreach`;
            statContactedBadge.className = "text-caption font-caption text-secondary px-1.5 py-0.5 rounded bg-secondary/10 font-mono text-[11px]";
            statContactedText.textContent = `${userContacted} of ${total} contacted`;
          }
        }
      }

      const statEmailsTotal = document.getElementById("stat-emails-total");
      if (statEmailsTotal) statEmailsTotal.textContent = total;

      const statYield = document.getElementById("stat-yield-text");
      if (statYield) {
        const yieldPct = total > 0 ? Math.round((withEmails / total) * 100) : 0;
        statYield.textContent = `${yieldPct}% contact yield`;
      }

      const pillAll = document.getElementById("pill-count-all");
      if (pillAll) pillAll.textContent = total;
      const pillResearched = document.getElementById("pill-count-researched");
      if (pillResearched) pillResearched.textContent = enriched;
      const pillPitched = document.getElementById("pill-count-pitched");
      if (pillPitched) {
        pillPitched.textContent = (isLoggedIn && contacted !== null) ? contacted : "0";
      }
      const pillExcluded = document.getElementById("pill-count-excluded");
      if (pillExcluded) pillExcluded.textContent = invalid;

      if (statInvalidCount) statInvalidCount.textContent = invalid;

      // Outreach Hub Quick Metric Strip & Badges (Globally synchronized from server stats)
      const outreachTotalEl = document.getElementById("outreach-count-total");
      if (outreachTotalEl) outreachTotalEl.textContent = total.toLocaleString();

      const outreachEmailsEl = document.getElementById("outreach-count-emails");
      if (outreachEmailsEl) outreachEmailsEl.textContent = withEmails.toLocaleString();

      const userContactedCount = (isLoggedIn && contacted !== null) ? contacted : 0;
      const outreachReadyEl = document.getElementById("outreach-count-ready");
      if (outreachReadyEl) outreachReadyEl.textContent = Math.max(0, total - userContactedCount).toLocaleString();

      const outreachSentEl = document.getElementById("outreach-count-sent");
      if (outreachSentEl) outreachSentEl.textContent = isLoggedIn ? userContactedCount.toLocaleString() : "0";

      document.querySelectorAll(".outreach-badge-all").forEach(el => el.textContent = total);
      document.querySelectorAll(".outreach-badge-emails").forEach(el => el.textContent = withEmails);
      document.querySelectorAll(".outreach-badge-ready").forEach(el => el.textContent = Math.max(0, total - userContactedCount));
      document.querySelectorAll(".outreach-badge-sent").forEach(el => {
        el.textContent = isLoggedIn ? userContactedCount : "—";
      });
    } else if (Array.isArray(statsOrList)) {
      const validList = statsOrList.filter(c => !c.is_invalid);
      const total = validList.length;
      const enriched = validList.filter(c => c.is_enriched).length;
      const withEmails = validList.filter(c => c.emails && c.emails.length > 0).length;
      const contacted = isLoggedIn ? validList.filter(c => c.already_contacted).length : null;

      const totalCountEl = document.getElementById("companies-total-count");
      if (totalCountEl) totalCountEl.textContent = total;
      const statEnriched = document.getElementById("stat-enriched-count");
      if (statEnriched) statEnriched.textContent = enriched;
      const statEmails = document.getElementById("stat-emails-count");
      if (statEmails) statEmails.textContent = withEmails;
      const statContacted = document.getElementById("stat-contacted-count");
      if (statContacted) {
        statContacted.textContent = isLoggedIn ? (contacted ?? 0) : "0";
      }
    }

    // Visibility of Master Admin controls based on login & mode
    if (isMasterAdmin && adminViewMode === "admin") {
      statCardInvalid?.classList.remove("hidden");
      adminModeToggleGroup?.classList.remove("hidden");
      adminModeToggleGroup?.classList.add("flex");
      adminPreviewBanner?.classList.add("hidden");
    } else if (isMasterAdmin && adminViewMode === "preview") {
      statCardInvalid?.classList.add("hidden");
      adminModeToggleGroup?.classList.remove("hidden");
      adminModeToggleGroup?.classList.add("flex");
      adminPreviewBanner?.classList.remove("hidden");
    } else {
      statCardInvalid?.classList.add("hidden");
      adminModeToggleGroup?.classList.add("hidden");
      adminModeToggleGroup?.classList.remove("flex");
      adminPreviewBanner?.classList.add("hidden");
    }
  }

  function renderSkeletonCompanies(count = 6) {
    if (!companiesContainer) return;
    companiesContainer.innerHTML = Array.from({ length: count }).map(() => `
      <div class="skeleton-shimmer bg-surface-container-low border border-outline-variant/30 rounded-xl p-5 flex flex-col justify-between min-h-[220px]">
        <div class="space-y-3.5">
          <div class="flex items-start gap-3">
            <div class="w-9 h-9 rounded-md bg-surface-container-highest shrink-0"></div>
            <div class="space-y-2 flex-1 min-w-0">
              <div class="h-4 bg-surface-container-highest rounded w-3/4"></div>
              <div class="h-3 bg-surface-container rounded w-1/2"></div>
            </div>
          </div>
          <div class="space-y-1.5 pt-1">
            <div class="h-3 bg-surface-container rounded w-full"></div>
            <div class="h-3 bg-surface-container rounded w-4/5"></div>
          </div>
          <div class="flex gap-1.5 pt-2">
            <div class="h-5 bg-surface-container-highest rounded w-16"></div>
            <div class="h-5 bg-surface-container-highest rounded w-20"></div>
            <div class="h-5 bg-surface-container-highest rounded w-14"></div>
          </div>
        </div>
        <div class="pt-3.5 border-t border-outline-variant/30 flex gap-2 mt-4">
          <div class="h-8 bg-surface-container-highest rounded w-1/2"></div>
          <div class="h-8 bg-surface-container-highest rounded w-1/2"></div>
        </div>
      </div>
    `).join('');
  }

  let filterDebounceTimer = null;
  function applyCompanyFiltersAndRender(resetPage = false) {
    if (resetPage) {
      companiesCurrentPage = 1;
    }
    clearTimeout(filterDebounceTimer);
    filterDebounceTimer = setTimeout(() => {
      fetchCompanies(!resetPage);
    }, 150);
  }

  const btnResetFilters = document.getElementById("btn-reset-filters");
  if (btnResetFilters) {
    btnResetFilters.addEventListener("click", () => {
      if (filterInput) filterInput.value = "";
      if (filterTechSelect) filterTechSelect.value = "";
      if (filterCitySelect) filterCitySelect.value = "";
      if (ddFilterTech) ddFilterTech.reset();
      if (ddFilterCity) ddFilterCity.reset();
      activeMetricFilter = null;
      document.querySelectorAll(".filter-tab-btn").forEach(btn => {
        if (btn.id === "filter-tab-all") {
          btn.classList.add("active", "bg-surface-container-highest", "text-on-surface");
          btn.classList.remove("text-on-surface-variant");
        } else {
          btn.classList.remove("active", "bg-surface-container-highest", "text-on-surface");
          btn.classList.add("text-on-surface-variant");
        }
      });
      updateMetricCardStyles();
      applyCompanyFiltersAndRender(true);
      showToast("Filters reset to default", "info");
    });
  }

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
      searchInput.addEventListener("input", (e) => {
        renderList(e.target.value);
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

  // Initialize tactile dropdown instances (Tech stack & City are both multi-selectable)
  const ddFilterTech = initCustomDropdown({
    containerId: "dropdown-filter-tech",
    inputId: "filter-tech-select",
    defaultLabel: "Tech Stack (All)",
    searchPlaceholder: "Search stack...",
    isMulti: true,
    onSelect: () => applyCompanyFiltersAndRender(true)
  });

  const ddFilterCity = initCustomDropdown({
    containerId: "dropdown-filter-city",
    inputId: "filter-city-select",
    defaultLabel: "All Cities",
    searchPlaceholder: "Search city...",
    isMulti: true,
    onSelect: () => applyCompanyFiltersAndRender(true)
  });

  const ddOutreachTech = initCustomDropdown({
    containerId: "dropdown-outreach-tech",
    inputId: "outreach-tech-select",
    defaultLabel: "Tech Stack (All)",
    searchPlaceholder: "Search stack...",
    isMulti: true,
    onSelect: (val) => {
      outreachSelectedTech = (val || "").trim().toLowerCase();
      outreachCurrentPage = 1;
      renderPitchesList();
    }
  });

  const ddOutreachCity = initCustomDropdown({
    containerId: "dropdown-outreach-city",
    inputId: "outreach-city-select",
    defaultLabel: "All Cities",
    searchPlaceholder: "Search city...",
    isMulti: true,
    onSelect: (val) => {
      outreachSelectedCity = (val || "").trim().toLowerCase();
      outreachCurrentPage = 1;
      renderPitchesList();
    }
  });

  // Initialize Scout Leads Tactile Dropdowns
  const ddScoutPages = initCustomDropdown({
    containerId: "dropdown-scout-pages",
    inputId: "input-pages",
    defaultLabel: "2 Pages (~40 leads)"
  });
  if (ddScoutPages) {
    ddScoutPages.setOptions([
      { value: "1", label: "1 Page (~20 leads)" },
      { value: "2", label: "2 Pages (~40 leads)" },
      { value: "3", label: "3 Pages (~60 leads)" },
      { value: "5", label: "5 Pages (~100 leads)" },
      { value: "10", label: "10 Pages (~200 leads)" },
      { value: "15", label: "15 Pages (~300 leads)" },
      { value: "20", label: "20 Pages (~400 leads)" },
      { value: "30", label: "30 Pages (~600 leads)" },
      { value: "0", label: "⚡ All Available Pages" }
    ]);
  }

  const ddScoutGl = initCustomDropdown({
    containerId: "dropdown-scout-gl",
    inputId: "input-gl",
    defaultLabel: "IN (India)",
    searchPlaceholder: "Search country..."
  });
  if (ddScoutGl) {
    ddScoutGl.setOptions([
      { value: "in", label: "IN (India)" },
      { value: "us", label: "US (USA)" },
      { value: "uk", label: "UK" },
      { value: "ca", label: "CA (Canada)" },
      { value: "ae", label: "AE (UAE)" },
      { value: "de", label: "DE (Germany)" },
      { value: "au", label: "AU (Australia)" }
    ]);
  }

  // Initialize Compact Per-Page Pagination Dropdowns
  const ddCompaniesPerPage = initCustomDropdown({
    containerId: "dropdown-companies-per-page",
    inputId: "companies-per-page",
    defaultLabel: "20",
    onSelect: (val) => {
      companiesPerPage = parseInt(val, 10);
      companiesCurrentPage = 1;
      fetchCompanies();
    }
  });
  if (ddCompaniesPerPage) {
    ddCompaniesPerPage.setOptions([
      { value: "10", label: "10" },
      { value: "20", label: "20" },
      { value: "50", label: "50" },
      { value: "100", label: "100" },
      { value: "200", label: "200" }
    ]);
  }

  const ddOutreachPerPage = initCustomDropdown({
    containerId: "dropdown-outreach-per-page",
    inputId: "outreach-per-page",
    defaultLabel: "20",
    onSelect: (val) => {
      outreachPerPage = parseInt(val, 10);
      outreachCurrentPage = 1;
      fetchOutreachCompanies(false);
    }
  });
  if (ddOutreachPerPage) {
    ddOutreachPerPage.setOptions([
      { value: "10", label: "10" },
      { value: "20", label: "20" },
      { value: "50", label: "50" },
      { value: "100", label: "100" },
      { value: "200", label: "200" }
    ]);
  }

  const ddScoutPerPage = initCustomDropdown({
    containerId: "dropdown-scout-per-page",
    inputId: "scout-per-page",
    defaultLabel: "20",
    onSelect: (val) => {
      scoutPerPage = parseInt(val, 10);
      scoutCurrentPage = 1;
      renderScoutResults(currentScoutList, currentScoutQueryLabel);
    }
  });
  if (ddScoutPerPage) {
    ddScoutPerPage.setOptions([
      { value: "10", label: "10" },
      { value: "20", label: "20" },
      { value: "50", label: "50" },
      { value: "100", label: "100" },
      { value: "200", label: "200" }
    ]);
  }

  if (filterTechSelect) {
    filterTechSelect.addEventListener("change", () => applyCompanyFiltersAndRender(true));
  }

  if (filterCitySelect) {
    filterCitySelect.addEventListener("change", () => applyCompanyFiltersAndRender(true));
  }

  if (btnFilterEmails) {
    btnFilterEmails.addEventListener("click", () => {
      setActiveMetricFilter("emails");
    });
  }

  let totalServerCount = 0;
  let totalServerPages = 1;

  let filterOptionsLoaded = false;

  // Fetch cached filter options (Tech Stacks & Cities with counts) from backend
  async function fetchCompaniesFilters() {
    try {
      const res = await fetch("/api/companies/filters");
      if (!res.ok) return;
      const data = await res.json();
      filterOptionsLoaded = true;

      // Build tech options
      const techOpts = [{ value: "", label: "Tech Stack (All)", count: null }];
      (data.tech_stacks || []).forEach(t => {
        techOpts.push({ value: t.name.toLowerCase(), label: t.name, count: t.count });
      });
      if (ddFilterTech) ddFilterTech.setOptions(techOpts);
      if (ddOutreachTech) ddOutreachTech.setOptions(techOpts);

      // Build city options
      const cityOpts = [{ value: "", label: "All Cities", count: null }];
      (data.cities || []).forEach(c => {
        cityOpts.push({ value: c.name.toLowerCase(), label: c.name, count: c.count });
      });
      if (ddFilterCity) ddFilterCity.setOptions(cityOpts);
      if (ddOutreachCity) ddOutreachCity.setOptions(cityOpts);

      if (data.stats) {
        updateCompanyMetrics(data.stats);
      }
    } catch (e) {
      console.warn("Failed to fetch company filters:", e);
    }
  }

  async function fetchCompanies(preservePage = true) {
    try {
      if (!companies || companies.length === 0) {
        renderSkeletonCompanies(6);
      }

      if (!preservePage) {
        companiesCurrentPage = 1;
      }

      const q = (filterInput?.value || "").trim();
      const selectedTech = (filterTechSelect?.value || "").trim();
      const selectedCity = (filterCitySelect?.value || "").trim();
      const selectedSort = (sortSelect?.value || "newest").trim();
      const statusParam = activeMetricFilter || "all";
      const pageSize = (companiesPerPage !== undefined && companiesPerPage !== null) ? companiesPerPage : 20;

      const params = new URLSearchParams({
        page: companiesCurrentPage,
        page_size: pageSize,
        search: q,
        tech: selectedTech,
        city: selectedCity,
        status: statusParam,
        sort: selectedSort
      });

      const res = await fetch(`/api/companies?${params.toString()}`);
      if (!res.ok) {
        console.warn(`[Directory] API responded with HTTP ${res.status}. Retrying in 1.5s...`);
        setTimeout(() => fetchCompanies(preservePage), 1500);
        return;
      }
      const data = await res.json();
      companies = data.companies || [];
      totalServerCount = data.total_count || 0;
      totalServerPages = data.total_pages || 1;
      companiesCurrentPage = data.current_page || 1;
      invalidCount = data.invalid_count || 0;
      if (typeof data.is_master_admin === "boolean") {
        isMasterAdmin = data.is_master_admin;
      }
      if (typeof data.dev_mode === "boolean") {
        isDevMode = data.dev_mode;
      }

      // Populate filter dropdowns on initial load
      if (!filterOptionsLoaded) {
        fetchCompaniesFilters();
      }

      updateMetricCardStyles();
      // Purge any invalid company IDs from multi-selection if viewing active leads
      if (activeMetricFilter !== "invalid") {
        companies.forEach(c => {
          if (c.is_invalid) selectedCompanyIds.delete(c.id);
        });
      }
      renderCompanies(companies);
      updateScoutViewFromInputs();
    } catch (err) {
      console.error("Failed to load companies:", err);
    }
  }

  function renderCompanies(list) {
    currentFilteredCompanies = list || [];

    if (companiesContainer) companiesContainer.innerHTML = "";

    if (!list || list.length === 0) {
      if (companiesPagination) companiesPagination.classList.add("hidden");
      if (companiesPaginationBottom) companiesPaginationBottom.classList.add("hidden");
      let emptyTitle = "No leads saved yet";
      let emptyMsg = "No leads available. Scout companies in Step 1 first.";
      if (activeMetricFilter === "invalid") {
        emptyTitle = "No Invalid Leads Found";
        emptyMsg = "No invalid / excluded leads recorded. Active companies can be marked invalid by Master Admin.";
      } else if (activeMetricFilter === "enriched") {
        emptyTitle = "No Deep Enriched Leads Found";
        emptyMsg = "None of the companies have been enriched yet. Click 'Deep Enrich All' or enrich individually.";
      } else if (activeMetricFilter === "emails") {
        emptyTitle = "No Leads with Discovered Emails";
        emptyMsg = "No direct emails discovered under this filter. Try enriching companies to discover contacts.";
      } else if (activeMetricFilter === "contacted") {
        emptyTitle = "No Outreach Sent Yet";
        emptyMsg = "You haven't contacted any companies yet under this filter. Generate a pitch and reach out!";
      }

      if (companiesContainer) {
        companiesContainer.innerHTML = `
          <div class="col-span-full py-12 px-4 text-center bg-surface-container-low border border-outline-variant/30 rounded-2xl space-y-3 shadow-sm transition-colors">
            <div class="inline-flex p-3 rounded-full bg-primary/10 text-primary border border-primary/20 shadow-sm">
              <i data-lucide="layers" class="w-6 h-6"></i>
            </div>
            <p class="text-sm font-semibold text-on-surface">${emptyTitle}</p>
            <p class="text-xs text-on-surface-variant max-w-md mx-auto leading-relaxed">${emptyMsg}</p>
          </div>
        `;
        refreshIcons();
      }
      updateBulkActionBar();
      updateSelectAllCheckboxState([]);
      return;
    }

    const pagedList = list;
    const totalItems = totalServerCount;

    pagedList.forEach(c => {
      // 1. Grid Card
      if (companiesContainer) {
        const card = document.createElement("div");
        const isSelected = selectedCompanyIds.has(c.id);
        const canManageLeads = Boolean((isMasterAdmin && currentUser && currentUser.is_logged_in) || isDevMode);

        if (c.is_invalid) {
          // If viewing general leads, invalid companies should never be selected
          if (activeMetricFilter !== "invalid") {
            selectedCompanyIds.delete(c.id);
          }
          // Invalid Lead Grid Card Styling
          card.className = `company-card-invalid bg-surface-container-low border ${isSelected && activeMetricFilter === "invalid" ? 'border-rose-500 ring-2 ring-rose-500/80 bg-rose-500/10' : 'border-rose-500/30 hover:border-rose-500/50'} rounded-2xl p-4 sm:p-5 flex flex-col justify-between transition-all duration-200 group shadow-sm cursor-pointer relative min-w-0`;
          card.innerHTML = `
            <div class="space-y-2 pointer-events-none">
              <div class="flex items-start justify-between gap-1.5 pointer-events-auto">
                <div class="flex items-center space-x-2 flex-1 min-w-0">
                  ${(canManageLeads && activeMetricFilter === "invalid") ? `<input type="checkbox" class="company-checkbox w-4 h-4 rounded bg-surface-container-lowest border-rose-600 text-rose-600 focus:ring-rose-500 cursor-pointer shrink-0 transition" data-id="${c.id}" ${isSelected ? 'checked' : ''} title="Select lead">` : ''}
                  <h4 class="font-bold text-xs sm:text-sm text-on-surface group-hover:text-rose-500 transition flex items-center space-x-1.5 break-words flex-1">
                    <span>${escapeHTML(c.name)}</span>
                  </h4>
                </div>
                <span class="px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30 text-[9px] sm:text-[10px] font-bold flex items-center space-x-1 shrink-0">
                  <i data-lucide="shield-alert" class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-rose-500"></i>
                  <span>INVALID</span>
                </span>
              </div>
              <div class="text-[10px] sm:text-[11px] text-rose-800 dark:text-rose-200 bg-rose-500/10 p-2.5 rounded-xl border border-rose-500/25 space-y-0.5">
                <div class="flex items-center space-x-1 font-semibold text-rose-700 dark:text-rose-400 text-[9px] sm:text-[10px] uppercase tracking-wider">
                  <i data-lucide="alert-circle" class="w-3 h-3"></i>
                  <span>Excluded</span>
                </div>
                <p class="break-words leading-tight">${escapeHTML(c.invalid_reason || 'Excluded by Admin')}</p>
                ${c.invalid_at ? `<p class="text-[9px] sm:text-[10px] text-on-surface-variant font-mono">Date: ${escapeHTML(c.invalid_at)}</p>` : ''}
              </div>
              <div class="text-[10px] sm:text-[11px] font-mono text-on-surface-variant flex items-center space-x-1 break-all">
                <i data-lucide="globe" class="w-3 h-3 text-outline shrink-0"></i>
                <span>${escapeHTML(c.domain)}</span>
              </div>
            </div>

            ${canManageLeads ? `
            <div class="pt-2.5 sm:pt-3 mt-2.5 sm:mt-3 border-t border-rose-500/20 flex items-center justify-end">
              <button class="btn-single-restore w-full text-center justify-center text-[11px] sm:text-xs px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center space-x-1 shadow-sm cursor-pointer" data-id="${c.id}" title="Restore company to active directory">
                <i data-lucide="rotate-ccw" class="w-3 h-3"></i>
                <span>Restore Lead</span>
              </button>
            </div>
            ` : ''}
          `;

          const btnRestore = card.querySelector(".btn-single-restore");
          if (btnRestore) {
            btnRestore.addEventListener("click", (e) => {
              e.stopPropagation();
              handleRestoreCompany(c.id, c.name);
            });
          }

        } else {
          // Genuine Active Company Grid Card
          const monogram = getCompanyMonogram(c.name);
          const monoThemes = [
            { bg: "bg-surface-container-high text-on-surface border-outline-variant/60" },
            { bg: "bg-secondary/15 text-secondary border-secondary/30" },
            { bg: "bg-tertiary/15 text-tertiary border-tertiary/30" },
            { bg: "bg-surface-container-highest text-on-surface-variant border-outline-variant/60" }
          ];
          const monoTheme = monoThemes[(c.id || 0) % monoThemes.length];

          // Rating & Reviews display
          const ratingVal = (c.rating && c.rating > 0) ? Number(c.rating).toFixed(1) : null;
          const ratingDisplay = ratingVal
            ? `<div class="flex items-center gap-1 text-tertiary text-caption font-semibold shrink-0">
                 <span class="material-symbols-outlined text-[14px] text-tertiary">star</span>
                 <span>${ratingVal}</span>
                 <span class="text-on-surface-variant font-normal">(${c.reviews_count || 0})</span>
               </div>`
            : '';

          // Status Badge: Pitched, Researched, Uncontacted
          let statusBadge = "";
          if (c.already_contacted) {
            statusBadge = `<span onclick="event.stopPropagation(); window.viewSentEmailForCompany && window.viewSentEmailForCompany(${c.id})" class="px-2.5 py-0.5 rounded text-caption font-mono bg-primary/10 text-primary border border-primary/30 shrink-0 cursor-pointer flex items-center gap-1 font-semibold hover:brightness-110" title="Click to view outreach sent"><span class="material-symbols-outlined text-[13px]">check_circle</span><span>Pitched</span></span>`;
          } else if (c.is_enriched) {
            statusBadge = `<span class="px-2.5 py-0.5 rounded text-caption font-mono bg-secondary/15 text-secondary border border-secondary/30 shrink-0 flex items-center gap-1 font-semibold"><span class="material-symbols-outlined text-[13px]">auto_awesome</span><span>Researched</span></span>`;
          } else {
            statusBadge = `<span class="px-2.5 py-0.5 rounded text-caption font-mono bg-surface-container text-on-surface-variant border border-outline-variant/60 shrink-0">Uncontacted</span>`;
          }

          // Description (2-line clamp with JSON cleanup)
          const rawKeyword = c.normalized_keyword || c.search_keyword || '';
          const cleanKeyword = rawKeyword.replace(/\s+(companies|firms|agencies)$/i, '').trim();
          let rawDesc = (c.profile && c.profile.summary)
            ? c.profile.summary
            : (c.description || (cleanKeyword ? `${cleanKeyword} engineering and enterprise solutions.` : 'Technology solutions and services provider.'));
          if (typeof rawDesc === 'string') {
            const trimmed = rawDesc.trim();
            if (trimmed.startsWith('{') || trimmed.includes('"summary"')) {
              try {
                const parsed = JSON.parse(trimmed);
                rawDesc = parsed.summary || parsed.description || rawDesc;
              } catch (_) {
                rawDesc = rawDesc.replace(/^[{\s(]*"?summary"?\s*:\s*"?/i, '').replace(/["}\s)]+$/, '');
              }
            }
          }
          const descText = rawDesc;

          // Contact & Location (Strict: Never guess contact@ or domain fallbacks)
          const hasEmail = Boolean(c.emails && c.emails.length > 0);
          const primaryEmail = hasEmail ? c.emails[0] : null;
          const emailIcon = hasEmail ? 'mark_email_read' : 'mail_off';
          const emailColor = hasEmail ? 'text-secondary' : 'text-amber-500/80';
          const emailTextClass = hasEmail ? 'text-secondary font-medium' : 'text-amber-500/80 font-normal';
          const locationText = c.city ? `${c.city}, IN` : (cleanAddressText(c.address) || 'India');

          // Tech stack pills (Only show verified AI-enriched tech stack; never misleading placeholders)
          let techPillsHtml = '';
          if (c.profile && Array.isArray(c.profile.tech_stack) && c.profile.tech_stack.length > 0) {
            techPillsHtml = c.profile.tech_stack.slice(0, 4).map(t => `<span class="px-2 py-0.5 rounded text-[11px] font-mono tracking-wide bg-surface-container text-on-surface-variant border border-outline-variant/30">${escapeHTML(t)}</span>`).join('');
          } else if (c.is_enriched) {
            techPillsHtml = `<span class="px-2 py-0.5 rounded text-[11px] font-mono tracking-wide text-on-surface-variant/60 bg-surface-container/40 border border-outline-variant/20 italic">No frameworks detected</span>`;
          } else {
            techPillsHtml = `<span class="px-2 py-0.5 rounded text-[11px] font-mono tracking-wide text-on-surface-variant/60 bg-surface-container/40 border border-outline-variant/20 italic flex items-center gap-1.5"><span class="material-symbols-outlined text-[13px] text-amber-500/70">hourglass_top</span><span>Stack pending AI enrichment</span></span>`;
          }

          const excludeBtn = canManageLeads
            ? `<button class="btn-single-invalidate text-on-surface-variant hover:text-error p-1 rounded transition cursor-pointer" data-id="${c.id}" title="Exclude lead from outreach"><span class="material-symbols-outlined text-[16px]">block</span></button>`
            : '';
          const checkboxHtml = canManageLeads
            ? `<input type="checkbox" class="company-checkbox w-4 h-4 rounded border-outline-variant/60 bg-surface-container-lowest text-primary focus:ring-0 cursor-pointer shrink-0 mt-1" data-id="${c.id}" ${isSelected ? 'checked' : ''}/>`
            : '';

          card.className = `company-card group bg-surface-container-low border ${isSelected ? 'border-primary ring-1 ring-primary' : 'border-outline-variant/40 hover:border-outline-variant/80 hover:shadow-lg'} rounded-xl p-5 flex flex-col justify-between transition-all duration-150 relative cursor-pointer min-w-0`;
          card.innerHTML = `
            <div>
              <!-- Part 1: Header (Checkbox + Monogram + Name/Domain + Badge) -->
              <div class="flex items-start justify-between gap-3 mb-3">
                <div class="flex items-start gap-2.5 min-w-0 flex-1">
                  ${checkboxHtml}
                  <div class="w-9 h-9 rounded-md flex items-center justify-center font-bold text-label-sm ${monoTheme.bg} border shrink-0 font-mono shadow-sm">
                    ${monogram}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-start justify-between gap-1.5">
                      <h3 class="text-headline-sm font-headline-sm text-on-surface font-semibold break-words line-clamp-2 leading-snug" title="${escapeHTML(c.name)}">${escapeHTML(c.name)}</h3>
                      <a class="text-on-surface-variant hover:text-primary transition-colors shrink-0 mt-0.5" href="${c.website_url || 'https://' + c.domain}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" title="Visit website">
                        <span class="material-symbols-outlined text-[14px]">open_in_new</span>
                      </a>
                    </div>
                    <div class="flex items-center gap-2 mt-1">
                      <span class="text-caption font-mono text-on-surface-variant truncate block">${escapeHTML(c.domain || '')}</span>
                      ${ratingDisplay}
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-1.5 shrink-0 pt-0.5">
                  ${statusBadge}
                  ${excludeBtn}
                </div>
              </div>

              <!-- Part 2: Description (2 lines clamp, breathable) -->
              <p class="text-body-sm font-body-sm text-on-surface-variant mb-3.5 line-clamp-2 leading-relaxed">
                ${escapeHTML(descText)}
              </p>

              <!-- Part 3: Contact, Location & Tech (Clean vertical flow without cage border-y) -->
              <div class="flex flex-col gap-2.5 mb-4">
                <div class="flex items-center justify-between text-caption font-caption gap-2">
                  <div class="flex items-center gap-1.5 ${emailTextClass} truncate min-w-0 font-mono text-caption">
                    <span class="material-symbols-outlined text-[15px] ${emailColor} shrink-0">${emailIcon}</span>
                    <span class="truncate">${hasEmail ? escapeHTML(primaryEmail) : '<span class="text-amber-500 font-medium not-italic">Email not found</span>'}</span>
                  </div>
                  <div class="flex items-center gap-1 text-on-surface-variant shrink-0 font-mono text-[11px]">
                    <span class="material-symbols-outlined text-[14px]">location_on</span>
                    <span>${escapeHTML(locationText)}</span>
                  </div>
                </div>
                <div class="flex flex-wrap gap-1.5">
                  ${techPillsHtml}
                </div>
              </div>
            </div>

            <!-- Part 4: Tactile Action Buttons (Milled Hardware Look with rest-state subtle pitch button) -->
            <div class="grid grid-cols-2 gap-2 mt-auto pt-3.5 border-t border-outline-variant/30">
              <button type="button" class="btn-single-details btn-tactile-slate px-3 py-2 rounded text-label-sm font-label-sm font-semibold transition-all text-center cursor-pointer flex items-center justify-center gap-1.5 text-on-surface">
                <span class="material-symbols-outlined text-[16px]">visibility</span>
                <span class="text-on-surface">View Intel</span>
              </button>
              <button type="button" class="btn-single-pitch btn-card-pitch px-3 py-2 rounded text-label-sm font-label-sm font-semibold transition-all text-center cursor-pointer flex items-center justify-center gap-1.5">
                <span class="material-symbols-outlined text-[16px]">send</span>
                <span>Draft Pitch</span>
              </button>
            </div>
          `;

          const btnDetails = card.querySelector(".btn-single-details");
          const btnPitch = card.querySelector(".btn-single-pitch");
          const btnInvalidate = card.querySelector(".btn-single-invalidate");
          if (btnDetails) {
            btnDetails.addEventListener("click", (e) => {
              e.stopPropagation();
              openCompanyDetailsModal(c);
            });
          }
          if (btnPitch) {
            btnPitch.addEventListener("click", (e) => {
              e.stopPropagation();
              handleGeneratePitch(c.id);
            });
          }
          if (btnInvalidate) {
            btnInvalidate.addEventListener("click", (e) => {
              e.stopPropagation();
              handleInvalidateCompany(c.id, c.name);
            });
          }
        }

        // Checkbox change listener
        const chk = card.querySelector(".company-checkbox");
        if (chk) {
          chk.addEventListener("click", (e) => e.stopPropagation());
          chk.addEventListener("change", (e) => {
            e.stopPropagation();
            if (chk.checked) {
              selectedCompanyIds.add(c.id);
              card.classList.add("border-primary", "ring-1", "ring-primary");
              card.classList.remove("border-outline-variant/30");
            } else {
              selectedCompanyIds.delete(c.id);
              card.classList.remove("border-primary", "ring-1", "ring-primary");
              card.classList.add("border-outline-variant/30");
            }
            updateBulkActionBar();
            updateSelectAllCheckboxState(pagedList);
          });
        }

        card.addEventListener("click", (e) => {
          if (e.target.closest("button") || e.target.closest("a") || e.target.closest("input")) return;
          openCompanyDetailsModal(c);
        });
        companiesContainer.appendChild(card);
      }
    });

    updateBulkActionBar();
    updateSelectAllCheckboxState(pagedList);

    const handleCompaniesPageChange = (newPage) => {
      companiesCurrentPage = newPage;
      fetchCompanies(true);
      if (companiesContainer) {
        companiesContainer.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };

    renderPaginationControls({
      paginationEl: companiesPagination,
      rangeEl: companiesPageRange,
      totalEl: companiesPageTotal,
      buttonsEl: companiesPageButtons,
      totalItems: totalItems,
      currentPage: companiesCurrentPage,
      pageSize: companiesPerPage,
      onPageChange: handleCompaniesPageChange
    });

    renderPaginationControls({
      paginationEl: companiesPaginationBottom,
      rangeEl: companiesPageRangeBottom,
      totalEl: companiesPageTotalBottom,
      buttonsEl: companiesPageButtonsBottom,
      totalItems: totalItems,
      currentPage: companiesCurrentPage,
      pageSize: companiesPerPage,
      onPageChange: handleCompaniesPageChange
    });

    refreshIcons();
  }

  if (companiesPerPageSelect) {
    companiesPerPageSelect.addEventListener("change", (e) => {
      companiesPerPage = parseInt(e.target.value, 10);
      companiesCurrentPage = 1;
      fetchCompanies(false);
    });
  }

  // Export Leads to CSV Controller
  const btnExportCsv = document.getElementById("btn-export-csv");
  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", () => {
      if (!companies || companies.length === 0) {
        showToast("No companies found to export.", "warning");
        return;
      }
      const headers = ["ID", "Company Name", "Domain", "Website URL", "Phone", "Address", "Rating", "Reviews Count", "Enriched", "Discovered Emails", "Tech Stack", "Summary"];
      const rows = companies.map(c => [
        c.id,
        `"${(c.name || '').replace(/"/g, '""')}"`,
        `"${(c.domain || '').replace(/"/g, '""')}"`,
        `"${(c.website_url || '').replace(/"/g, '""')}"`,
        `"${(c.phone || '').replace(/"/g, '""')}"`,
        `"${(c.address || '').replace(/"/g, '""')}"`,
        c.rating || 0.0,
        c.reviews_count || 0,
        c.is_enriched ? "Yes" : "No",
        `"${(c.emails || []).join('; ').replace(/"/g, '""')}"`,
        `"${((c.profile && c.profile.tech_stack) || []).join(', ').replace(/"/g, '""')}"`,
        `"${((c.profile && c.profile.summary) || '').replace(/"/g, '""')}"`
      ]);
      const csvContent = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `outreachpilot_leads_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  }

  // ==========================================
  // COMPANY DETAILS MODAL CONTROLLER
  // ==========================================
  const cmodal = document.getElementById("company-modal");
  const cmodalClose = document.getElementById("cmodal-close");
  const cmodalName = document.getElementById("cmodal-name");
  const cmodalBadge = document.getElementById("cmodal-badge");
  const cmodalDomain = document.getElementById("cmodal-domain");
  const cmodalWebsite = document.getElementById("cmodal-website");
  const cmodalRating = document.getElementById("cmodal-rating");
  const cmodalPhone = document.getElementById("cmodal-phone");
  const cmodalAddress = document.getElementById("cmodal-address");
  const cmodalLocationLink = document.getElementById("cmodal-location-link");
  const cmodalEmailsCount = document.getElementById("cmodal-emails-count");
  const cmodalEmailsContainer = document.getElementById("cmodal-emails-container");
  const cmodalSummary = document.getElementById("cmodal-summary");
  const cmodalIndustry = document.getElementById("cmodal-industry");
  const cmodalTone = document.getElementById("cmodal-tone");
  const cmodalTechstack = document.getElementById("cmodal-techstack");
  const cmodalBtnEnrich = document.getElementById("cmodal-btn-enrich");
  const cmodalBtnPitch = document.getElementById("cmodal-btn-pitch");
  const cmodalBtnAdminAction = document.getElementById("cmodal-btn-admin-action");
  let activeModalCompany = null;

  const cmodalTabBtnOverview = document.getElementById("cmodal-tab-btn-overview");
  const cmodalTabBtnAi = document.getElementById("cmodal-tab-btn-ai");
  const cmodalPanelOverview = document.getElementById("cmodal-panel-overview");
  const cmodalPanelAi = document.getElementById("cmodal-panel-ai");
  const cmodalBtnCancel = document.getElementById("cmodal-btn-cancel");
  const cmodalBtnCopyReport = document.getElementById("cmodal-btn-copy-report");

  function switchCmodalTab(tab) {
    if (tab === "overview") {
      cmodalTabBtnOverview?.classList.add("active", "bg-surface-container-highest", "text-on-surface", "shadow-sm");
      cmodalTabBtnOverview?.classList.remove("text-on-surface-variant", "hover:bg-surface-container", "bg-primary-container", "text-white", "bg-primary-container", "text-on-primary-container");
      cmodalTabBtnAi?.classList.remove("active", "bg-surface-container-highest", "text-on-surface", "shadow-sm", "bg-primary-container", "text-white", "bg-primary-container", "text-on-primary-container");
      cmodalTabBtnAi?.classList.add("text-on-surface-variant", "hover:bg-surface-container");
      cmodalPanelOverview?.classList.remove("hidden");
      cmodalPanelAi?.classList.add("hidden");
    } else {
      cmodalTabBtnAi?.classList.add("active", "bg-surface-container-highest", "text-on-surface", "shadow-sm");
      cmodalTabBtnAi?.classList.remove("text-on-surface-variant", "hover:bg-surface-container", "bg-primary-container", "text-white", "bg-primary-container", "text-on-primary-container");
      cmodalTabBtnOverview?.classList.remove("active", "bg-surface-container-highest", "text-on-surface", "shadow-sm", "bg-primary-container", "text-white", "bg-primary-container", "text-on-primary-container");
      cmodalTabBtnOverview?.classList.add("text-on-surface-variant", "hover:bg-surface-container");
      cmodalPanelAi?.classList.remove("hidden");
      cmodalPanelOverview?.classList.add("hidden");
    }
    refreshIcons();
  }

  if (cmodalTabBtnOverview) cmodalTabBtnOverview.addEventListener("click", () => switchCmodalTab("overview"));
  if (cmodalTabBtnAi) cmodalTabBtnAi.addEventListener("click", () => switchCmodalTab("ai"));
  if (cmodalBtnCancel) cmodalBtnCancel.addEventListener("click", () => cmodal.classList.add("hidden"));

  if (cmodalBtnCopyReport) {
    cmodalBtnCopyReport.addEventListener("click", () => {
      const rawText = cmodalDetailedAnalysis?.dataset?.rawText || cmodalDetailedAnalysis?.innerText || "";
      if (!rawText || rawText.includes("Not enriched yet") || rawText.includes("Click 'Enrich")) return;
      const cleanText = stripMarkdownForCopy(rawText);
      navigator.clipboard.writeText(cleanText).then(() => {
        cmodalBtnCopyReport.innerHTML = `<i data-lucide="check" class="w-3 h-3 text-emerald-400"></i><span>Copied!</span>`;
        refreshIcons();
        setTimeout(() => {
          cmodalBtnCopyReport.innerHTML = `<i data-lucide="copy" class="w-3 h-3"></i><span>Copy</span>`;
          refreshIcons();
        }, 1500);
      });
    });
  }

  function openCompanyDetailsModal(company) {
    activeModalCompany = company;
    switchCmodalTab("overview");
    cmodalName.textContent = company.name;
    cmodalDomain.textContent = company.domain;
    cmodalWebsite.href = company.website_url || `https://${company.domain}`;
    cmodalRating.innerHTML = `<i data-lucide="star" class="w-3.5 h-3.5 text-amber-400 fill-amber-400"></i><span>${company.rating ? Number(company.rating).toFixed(1) : 'N/A'} (${company.reviews_count || 0} reviews)</span>`;
    cmodalPhone.textContent = company.phone || "No direct phone listed";

    const modalCleanAddr = cleanAddressText(company.address);
    const modalMapsUrl = company.location_url || buildMapsUrl(company.name, modalCleanAddr, company.city);
    if (cmodalLocationLink) {
      cmodalLocationLink.href = modalMapsUrl;
    }
    if (cmodalAddress) {
      cmodalAddress.textContent = modalCleanAddr || "Open in Google Maps";
    }

    const canManageLeads = Boolean((isMasterAdmin && currentUser && currentUser.is_logged_in) || isDevMode);
    // Exclude / Restore Button in Modal
    if (cmodalBtnAdminAction) {
      if (canManageLeads) {
        cmodalBtnAdminAction.classList.remove("hidden");
        if (company.is_invalid) {
          cmodalBtnAdminAction.className = "px-3.5 py-2 rounded-lg text-label-sm font-label-sm font-semibold transition flex items-center gap-1.5 cursor-pointer bg-secondary/15 hover:bg-secondary/25 text-secondary border border-secondary/30";
          cmodalBtnAdminAction.innerHTML = `<span class="material-symbols-outlined text-[16px]">restore</span><span>Restore Lead</span>`;
          cmodalBtnAdminAction.onclick = () => handleRestoreCompany(company.id, company.name);
        } else {
          cmodalBtnAdminAction.className = "px-3.5 py-2 rounded-lg text-label-sm font-label-sm font-semibold transition flex items-center gap-1.5 cursor-pointer bg-error/10 hover:bg-error/20 border border-error/30 text-error";
          cmodalBtnAdminAction.innerHTML = `<span class="material-symbols-outlined text-[16px]">block</span><span>Mark as Excluded</span>`;
          cmodalBtnAdminAction.onclick = () => handleInvalidateCompany(company.id, company.name);
        }
      } else {
        cmodalBtnAdminAction.classList.add("hidden");
      }
    }

    // Status Badge
    cmodalBadge.onclick = null;
    cmodalBadge.removeAttribute("title");
    if (company.is_invalid) {
      cmodalBadge.className = "px-2.5 py-0.5 rounded-full text-caption font-bold bg-error/10 hover:bg-error/20 text-error border border-error/30 flex items-center gap-1 shadow-xs";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">shield</span><span>INVALID LEAD</span>`;
    } else if (company.already_contacted) {
      cmodalBadge.className = "px-2.5 py-0.5 rounded-full text-caption font-semibold bg-secondary/15 hover:bg-secondary/25 text-secondary border border-secondary/30 flex items-center gap-1 cursor-pointer transition shadow-xs";
      cmodalBadge.title = "Click to view message sent";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">check_circle</span><span>Contacted ${company.contacted_at || ''}</span>`;
      cmodalBadge.onclick = () => window.viewSentEmailForCompany(company.id);
    } else if (company.is_enriched) {
      cmodalBadge.className = "px-2.5 py-0.5 rounded-full text-caption font-semibold bg-primary/10 text-primary border border-primary/30 flex items-center gap-1 shadow-xs";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">auto_awesome</span><span>AI Enriched</span>`;
    } else {
      cmodalBadge.className = "px-2.5 py-0.5 rounded-full bg-surface-container text-on-surface-variant border border-outline-variant/60 text-caption font-mono flex items-center gap-1";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">verified</span><span>Verified Lead</span>`;
    }

    // Discovered Emails
    const emails = company.emails || [];
    cmodalEmailsCount.textContent = `${emails.length} discovered`;
    if (emails.length > 0) {
      cmodalEmailsContainer.innerHTML = emails.map(em => `
        <div class="flex items-center space-x-2 px-2.5 py-1 bg-surface-container border border-outline-variant/40 rounded-lg text-secondary font-mono text-xs">
          <span class="material-symbols-outlined text-[16px] text-secondary shrink-0">mail</span>
          <span class="break-all">${escapeHTML(em)}</span>
          <button class="text-on-surface-variant hover:text-on-surface copy-em-btn text-xs ml-1 p-0.5 rounded hover:bg-surface-container-high flex items-center cursor-pointer" data-email="${escapeHTML(em)}" title="Copy email">
            <span class="material-symbols-outlined text-[14px]">content_copy</span>
          </button>
        </div>
      `).join("");

      cmodalEmailsContainer.querySelectorAll(".copy-em-btn").forEach(b => {
        b.addEventListener("click", () => {
          navigator.clipboard.writeText(b.dataset.email);
          b.innerHTML = `<span class="material-symbols-outlined text-[14px] text-secondary">check</span>`;
          setTimeout(() => {
            b.innerHTML = `<span class="material-symbols-outlined text-[14px]">content_copy</span>`;
          }, 1500);
        });
      });
    } else {
      cmodalEmailsContainer.innerHTML = `
        <div class="flex items-center gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-500 text-xs font-mono">
          <span class="material-symbols-outlined text-[16px]">mail_off</span>
          <span>Email not found -- Click "Enrich with AI" below to scan company website for verified contacts.</span>
        </div>
      `;
    }

    // AI Intelligence Profile
    const cmodalDetailedAnalysis = document.getElementById("cmodal-detailed-analysis");
    if (company.profile && company.profile.summary) {
      cmodalSummary.textContent = company.profile.summary;
      cmodalIndustry.textContent = company.profile.industry || "Technology";
      cmodalTone.textContent = company.profile.tone || "Professional";

      const stack = company.profile.tech_stack || [];
      if (stack.length > 0) {
        cmodalTechstack.innerHTML = stack.map(tech => `
          <span class="px-2.5 py-1 rounded bg-surface-container-high border border-outline-variant/40 text-on-surface text-xs font-mono font-medium">${escapeHTML(tech)}</span>
        `).join("");
      } else {
        cmodalTechstack.innerHTML = `<span class="text-on-surface-variant italic text-[11px]">No tech stack detected</span>`;
      }
    } else {
      cmodalSummary.textContent = "Awaiting AI enrichment...";
      cmodalIndustry.textContent = "Pending Analysis";
      cmodalTone.textContent = "Professional";
      cmodalTechstack.innerHTML = `<span class="text-on-surface-variant italic text-[11px]">Pending AI enrichment</span>`;
    }

    // Check if detailed analysis is already loaded or in local memory cache
    const cachedDetail = companyDetailCache.get(company.id);
    if (cachedDetail && cachedDetail.profile && cachedDetail.profile.detailed_analysis) {
      cmodalDetailedAnalysis.dataset.rawText = cachedDetail.profile.detailed_analysis;
      cmodalDetailedAnalysis.innerHTML = formatMarkdown(cachedDetail.profile.detailed_analysis);
      if (cachedDetail.profile.industry) cmodalIndustry.textContent = cachedDetail.profile.industry;
      if (cachedDetail.profile.tone) cmodalTone.textContent = cachedDetail.profile.tone;
    } else if (company.profile && company.profile.detailed_analysis) {
      cmodalDetailedAnalysis.dataset.rawText = company.profile.detailed_analysis;
      cmodalDetailedAnalysis.innerHTML = formatMarkdown(company.profile.detailed_analysis);
    } else {
      // Show tactile skeleton shimmer and fetch on-demand via AJAX
      cmodalDetailedAnalysis.dataset.rawText = "";
      cmodalDetailedAnalysis.innerHTML = `
        <div class="space-y-3 py-4 animate-pulse">
          <div class="h-4 bg-surface-container-high rounded w-3/4"></div>
          <div class="h-3.5 bg-surface-container rounded w-full"></div>
          <div class="h-3.5 bg-surface-container rounded w-5/6"></div>
          <div class="h-3.5 bg-surface-container rounded w-2/3"></div>
        </div>
      `;

      fetch(`/api/companies/${company.id}`)
        .then(res => res.ok ? res.json() : null)
        .then(detailData => {
          if (!detailData) return;
          companyDetailCache.set(company.id, detailData);
          if (activeModalCompany && activeModalCompany.id === company.id) {
            if (detailData.profile) {
              company.profile = Object.assign({}, company.profile, detailData.profile);
              if (detailData.profile.summary) cmodalSummary.textContent = detailData.profile.summary;
              if (detailData.profile.industry) cmodalIndustry.textContent = detailData.profile.industry;
              if (detailData.profile.tone) cmodalTone.textContent = detailData.profile.tone;
              if (detailData.profile.detailed_analysis) {
                cmodalDetailedAnalysis.dataset.rawText = detailData.profile.detailed_analysis;
                cmodalDetailedAnalysis.innerHTML = formatMarkdown(detailData.profile.detailed_analysis);
              } else {
                cmodalDetailedAnalysis.innerHTML = `<span class="text-on-surface-variant italic">Click 'Enrich with AI' below to generate comprehensive intelligence report.</span>`;
              }
              const stack = detailData.profile.tech_stack || [];
              if (stack.length > 0) {
                cmodalTechstack.innerHTML = stack.map(tech => `
                  <span class="px-2.5 py-1 rounded bg-surface-container-high border border-outline-variant/40 text-on-surface text-xs font-mono font-medium">${escapeHTML(tech)}</span>
                `).join("");
              } else {
                cmodalTechstack.innerHTML = `<span class="text-on-surface-variant italic text-[11px]">No tech stack detected</span>`;
              }
            } else {
              cmodalDetailedAnalysis.innerHTML = `<span class="text-on-surface-variant italic">Not enriched yet. Click 'Enrich with AI' below to generate comprehensive intelligence report.</span>`;
            }

            if (detailData.emails && detailData.emails.length > 0) {
              company.emails = detailData.emails;
              cmodalEmailsCount.textContent = `${detailData.emails.length} discovered`;
              cmodalEmailsContainer.innerHTML = detailData.emails.map(em => `
                <div class="flex items-center space-x-2 px-2.5 py-1 bg-surface-container border border-outline-variant/40 rounded-lg text-secondary font-mono text-xs">
                  <span class="material-symbols-outlined text-[16px] text-secondary shrink-0">mail</span>
                  <span class="break-all">${escapeHTML(em)}</span>
                  <button class="text-on-surface-variant hover:text-on-surface copy-em-btn text-xs ml-1 p-0.5 rounded hover:bg-surface-container-high flex items-center cursor-pointer" data-email="${escapeHTML(em)}" title="Copy email">
                    <span class="material-symbols-outlined text-[14px]">content_copy</span>
                  </button>
                </div>
              `).join("");
            }
          }
        })
        .catch(err => {
          console.warn("Failed to fetch on-demand company intel:", err);
          if (activeModalCompany && activeModalCompany.id === company.id) {
            cmodalDetailedAnalysis.innerHTML = `<span class="text-on-surface-variant italic">Click 'Enrich with AI' below to generate comprehensive intelligence report.</span>`;
          }
        });
    }

    cmodal.classList.remove("hidden");
    refreshIcons();
  }

  cmodalClose.addEventListener("click", () => cmodal.classList.add("hidden"));
  cmodal.addEventListener("click", (e) => {
    if (e.target === cmodal) cmodal.classList.add("hidden");
  });

  cmodalBtnEnrich.addEventListener("click", async () => {
    if (!activeModalCompany) return;
    companyDetailCache.delete(activeModalCompany.id);
    requireLogin(async () => {
      const oldHtml = cmodalBtnEnrich.innerHTML;
      cmodalBtnEnrich.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Analyzing with AI...</span>`;
      cmodalBtnEnrich.disabled = true;
      refreshIcons();

      try {
        const res = await fetch(`/api/companies/${activeModalCompany.id}/enrich?force_refresh=true`, { method: "POST" });
        if (res.status === 401) {
          currentUser.is_logged_in = false;
          showToast("Please sign in with Google to use AI Deep Enrichment.", "warning");
          showLoginModal("Please sign in with Google to use AI Deep Enrichment.");
          return;
        }
        await res.json();
        await fetchCompanies();
        const updated = companies.find(c => c.id === activeModalCompany.id);
        if (updated) openCompanyDetailsModal(updated);
      } catch (err) {
        showToast("Enrichment failed: " + err.message, "error");
      } finally {
        cmodalBtnEnrich.innerHTML = oldHtml;
        cmodalBtnEnrich.disabled = false;
        refreshIcons();
      }
    }, "Please sign in with Google to use AI Deep Enrichment.");
  });

  cmodalBtnPitch.addEventListener("click", () => {
    if (!activeModalCompany) return;
    requireLogin(() => {
      cmodal.classList.add("hidden");
      handleGeneratePitch(activeModalCompany.id);
    }, "generate outreach pitches");
  });

  if (filterInput) {
    filterInput.addEventListener("input", applyCompanyFiltersAndRender);
  }

  const filterTabAll = document.getElementById("filter-tab-all");
  const filterTabUncontacted = document.getElementById("filter-tab-uncontacted");
  const filterTabResearched = document.getElementById("filter-tab-researched");
  const filterTabPitched = document.getElementById("filter-tab-pitched");
  const filterTabExcludedBtn = document.getElementById("filter-tab-excluded");

  function setSegmentedFilterTab(tab) {
    [filterTabAll, filterTabUncontacted, filterTabResearched, filterTabPitched, filterTabExcludedBtn].forEach(b => {
      if (!b) return;
      b.classList.remove("active", "bg-surface-container-highest", "text-on-surface", "bg-error/20", "text-error");
      b.classList.add("text-on-surface-variant");
    });
    if (tab === "all" && filterTabAll) {
      filterTabAll.classList.add("active", "bg-surface-container-highest", "text-on-surface");
      filterTabAll.classList.remove("text-on-surface-variant");
      activeMetricFilter = "";
    } else if (tab === "uncontacted" && filterTabUncontacted) {
      filterTabUncontacted.classList.add("active", "bg-surface-container-highest", "text-on-surface");
      filterTabUncontacted.classList.remove("text-on-surface-variant");
      activeMetricFilter = "uncontacted";
    } else if (tab === "researched" && filterTabResearched) {
      filterTabResearched.classList.add("active", "bg-surface-container-highest", "text-on-surface");
      filterTabResearched.classList.remove("text-on-surface-variant");
      activeMetricFilter = "enriched";
    } else if (tab === "pitched" && filterTabPitched) {
      filterTabPitched.classList.add("active", "bg-surface-container-highest", "text-on-surface");
      filterTabPitched.classList.remove("text-on-surface-variant");
      activeMetricFilter = "contacted";
    } else if (tab === "excluded" && filterTabExcludedBtn) {
      filterTabExcludedBtn.classList.add("active", "bg-error/20", "text-error");
      filterTabExcludedBtn.classList.remove("text-on-surface-variant");
      activeMetricFilter = "invalid";
    }
    applyCompanyFiltersAndRender(true);
  }

  filterTabAll?.addEventListener("click", () => setSegmentedFilterTab("all"));
  filterTabUncontacted?.addEventListener("click", () => setSegmentedFilterTab("uncontacted"));
  filterTabResearched?.addEventListener("click", () => setSegmentedFilterTab("researched"));
  filterTabPitched?.addEventListener("click", () => setSegmentedFilterTab("pitched"));
  filterTabExcludedBtn?.addEventListener("click", () => setSegmentedFilterTab("excluded"));

  // ⌘K / Ctrl+K keyboard shortcut to focus search
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      filterInput?.focus();
    }
  });

  const btnViewOptions = document.getElementById("btn-view-options");
  if (btnViewOptions) {
    btnViewOptions.addEventListener("click", () => {
      filterInput?.focus();
      filterInput?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  const btnQuickRefreshBtn = document.getElementById("btn-quick-refresh-btn");
  if (btnQuickRefreshBtn) {
    btnQuickRefreshBtn.addEventListener("click", () => {
      fetchCompanies();
      showToast("Directory refreshed", "info");
    });
  }

  const btnBulkEnrich = document.getElementById("btn-bulk-enrich");
  const btnBulkPitch = document.getElementById("btn-bulk-pitch");
  const btnBulkExport = document.getElementById("btn-bulk-export");

  if (btnBulkEnrich) {
    btnBulkEnrich.addEventListener("click", () => {
      const selected = Array.from(selectedCompanyIds);
      if (selected.length === 0) {
        showToast("Please select at least 1 company to research", "warning");
        return;
      }
      handleBulkEnrich(btnBulkEnrich);
    });
  }

  if (btnBulkPitch) {
    btnBulkPitch.addEventListener("click", () => {
      const selected = Array.from(selectedCompanyIds);
      if (selected.length === 0) {
        showToast("Please select at least 1 company to draft pitches", "warning");
        return;
      }
      handleGeneratePitch(selected[0]);
    });
  }

  if (btnBulkExport) {
    btnBulkExport.addEventListener("click", () => {
      const btnExport = document.getElementById("btn-export-csv");
      if (btnExport) {
        btnExport.click();
      } else {
        exportCompaniesToCSV(companies.filter(c => selectedCompanyIds.has(c.id)));
      }
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", applyCompanyFiltersAndRender);
  }

  if (btnLoadCompanies) {
    btnLoadCompanies.addEventListener("click", (e) => {
      e.preventDefault();
      btnLoadCompanies.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Loading...</span>`;
      refreshIcons();
      fetchCompanies().finally(() => {
        btnLoadCompanies.innerHTML = `<i data-lucide="refresh-cw" class="w-3.5 h-3.5 text-on-surface-variant"></i><span>Refresh</span>`;
        refreshIcons();
      });
    });
  }

  async function handleScoutStart(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    const inputKwEl = document.getElementById("input-keyword");
    const inputCityEl = document.getElementById("input-city");
    const inputUrlEl = document.getElementById("input-url");

    const keyword = (inputKwEl?.value || "").trim();
    const city = (inputCityEl?.value || "").trim();
    const direct_url = (inputUrlEl?.value || "").trim();

    // Required Field Validations
    if (!direct_url) {
      if (!keyword && !city) {
        highlightFieldWarning(inputKwEl, "Please enter a Target Keyword / Industry and City / Location to find leads.");
        inputCityEl?.classList.add("input-warning-highlight");
        setTimeout(() => inputCityEl?.classList.remove("input-warning-highlight"), 3200);
        return;
      }
      if (!keyword) {
        highlightFieldWarning(inputKwEl, "Target Keyword / Industry is required (e.g. IT Companies, Software Agencies).");
        return;
      }
      if (!city) {
        highlightFieldWarning(inputCityEl, "City / Location is required (e.g. Surat, Austin, London).");
        return;
      }
    } else {
      if (!/^https?:\/\//i.test(direct_url)) {
        highlightFieldWarning(inputUrlEl, "Direct Google Search URL must start with http:// or https://");
        return;
      }
    }

    scoutCurrentPage = 1;
    liveScrapedResults = [];
    const max_pages = parseInt(document.getElementById("input-pages")?.value || "2", 10);
    const gl = document.getElementById("input-gl")?.value || "in";
    const hl = document.getElementById("input-hl")?.value || "en";

    const searchTag = (keyword && city)
      ? `"${keyword}" in "${city}"`
      : (keyword ? `"${keyword}"` : (city ? `in "${city}"` : (direct_url || "Search")));

    renderScoutResults([], `Searching: ${searchTag}`);

    scoutMonitor.classList.remove("hidden");
    monitorProgressBar.style.width = "8%";
    monitorStatus.textContent = `Initializing browser engine for ${searchTag}...`;
    monitorCount.textContent = "Starting...";
    btnStartScout.disabled = true;
    btnStartScout.classList.add("opacity-50");

    try {
      const res = await fetch("/api/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword, city, direct_url, max_pages, gl, hl })
      });
      const data = await res.json();
      if (data.status === "error") {
        monitorStatus.textContent = data.message || "A scrape job is already running.";
        btnStartScout.disabled = false;
        btnStartScout.classList.remove("opacity-50");
        showToast(data.message || "A scrape job is already active. Please wait for it to finish.", "error");
        return;
      }
      startPolling(data.job_id);
    } catch (err) {
      showToast("Failed to start scout job: " + err.message, "error");
      btnStartScout.disabled = false;
      btnStartScout.classList.remove("opacity-50");
    }
  }

  if (scoutForm) {
    scoutForm.addEventListener("submit", handleScoutStart);
  }
  if (btnStartScout) {
    btnStartScout.addEventListener("click", handleScoutStart);
  }

  function formatUserFriendlyLog(rawLog) {
    if (!rawLog || typeof rawLog !== "string") return "";

    const lower = rawLog.toLowerCase();
    // Suppress technical debug noise (ChromeDriver, devtools, websocket, curl, session headers)
    if (
      lower.includes("devtools") ||
      lower.includes("chromedriver") ||
      lower.includes("selenium") ||
      lower.includes("ws://") ||
      lower.includes("post /session") ||
      lower.includes("caps=") ||
      lower.includes("error: device or resource busy") ||
      lower.includes("insecure-requests") ||
      lower.includes("sec-ch-ua") ||
      lower.includes("python ") ||
      lower.includes("traceback") ||
      lower.includes("exit code")
    ) {
      return "";
    }

    // Extract optional timestamp [HH:MM:SS]
    let timeStr = "";
    let cleanMsg = rawLog;
    const timeMatch = rawLog.match(/^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*)$/);
    if (timeMatch) {
      timeStr = timeMatch[1];
      cleanMsg = timeMatch[2];
    }

    // Map system/cloud logs into clear, human-understandable operational messages
    let icon = "info";
    let iconColor = "text-secondary";
    let friendlyText = cleanMsg;

    if (/github\s*actions|cloud\s*runner|job\s*registered|dispatching/i.test(cleanMsg)) {
      icon = "rocket_launch";
      iconColor = "text-tertiary";
      friendlyText = "Initializing cloud search engine...";
    } else if (/chromium|headless|browser\s*engine|connecting/i.test(cleanMsg)) {
      icon = "travel_explore";
      iconColor = "text-secondary";
      friendlyText = "Connecting to Google Local & Maps directory...";
    } else if (/fetching\s*listings.*page\s*(\d+)/i.test(cleanMsg)) {
      const pageNum = cleanMsg.match(/page\s*(\d+)/i)?.[1] || "1";
      icon = "search";
      iconColor = "text-primary";
      friendlyText = `Scanning Google Local listings (Page ${pageNum})...`;
    } else if (/extracted\s*(\d+)\s*genuine/i.test(cleanMsg)) {
      const count = cleanMsg.match(/extracted\s*(\d+)/i)?.[1] || "several";
      icon = "verified";
      iconColor = "text-secondary";
      friendlyText = `Verified ${count} authentic company websites with active domains.`;
    } else if (/discovered\s*(\d+)\s*potential/i.test(cleanMsg)) {
      const count = cleanMsg.match(/discovered\s*(\d+)/i)?.[1] || "several";
      icon = "place";
      iconColor = "text-tertiary";
      friendlyText = `Located ${count} candidate businesses in Google Maps.`;
    } else if (/discovered\s*(\d+)\s*genuine/i.test(cleanMsg)) {
      const count = cleanMsg.match(/discovered\s*(\d+)/i)?.[1] || "several";
      icon = "domain_verification";
      iconColor = "text-secondary";
      friendlyText = `Identified ${count} verified businesses with working official websites.`;
    } else if (/saving.*companies|registered.*neon\s*db|successfully\s*saved/i.test(cleanMsg)) {
      const countMatch = cleanMsg.match(/(\d+)/);
      const count = countMatch ? countMatch[1] : "";
      icon = "save";
      iconColor = "text-tertiary";
      friendlyText = count ? `Saved ${count} verified companies to your outreach directory.` : "Saved verified companies to directory.";
    } else if (/cloud_enrich|ai\s*enrichment|ai\s*worker|enriching/i.test(cleanMsg)) {
      icon = "auto_awesome";
      iconColor = "text-secondary";
      friendlyText = "Initiated AI analysis: inspecting websites, tech stacks, and recruiter contacts.";
    } else if (/completed|finished/i.test(cleanMsg)) {
      icon = "check_circle";
      iconColor = "text-secondary";
      friendlyText = "Search complete! Companies are ready to browse below.";
    } else if (/error|failed/i.test(cleanMsg)) {
      icon = "warning";
      iconColor = "text-amber-500";
      friendlyText = cleanMsg.replace(/\[Fast-Path HTTP Error\]/i, "Notice:").replace(/Traceback.*/i, "");
    }

    return `
      <div class="flex items-center gap-2.5 py-1 px-2 rounded hover:bg-surface-container/60 transition text-xs font-mono text-on-surface-variant border-b border-outline-variant/20 last:border-0">
        ${timeStr ? `<span class="text-on-surface-variant/70 text-[10px] shrink-0 font-mono">${escapeHTML(timeStr)}</span>` : ""}
        <span class="material-symbols-outlined text-[15px] ${iconColor} shrink-0">${icon}</span>
        <span class="text-on-surface leading-snug">${escapeHTML(friendlyText)}</span>
      </div>
    `;
  }

  function startPolling(jobId = null) {
    if (pollInterval) clearInterval(pollInterval);
    let polls = 0;
    let hasStartedRunning = false;
    const pollUrl = jobId ? `/api/progress?job_id=${jobId}` : "/api/progress";

    pollInterval = setInterval(async () => {
      polls++;
      try {
        const res = await fetch(pollUrl);
        const data = await res.json();

        if (data.is_running) {
          hasStartedRunning = true;
        }

        // Clean user-friendly status message
        let friendlyStatus = data.status_message || "Searching for verified business leads...";
        if (/cloud_enrich|ai\s*enrichment|ai\s*worker/i.test(friendlyStatus)) {
          friendlyStatus = "AI analyzing company tech stacks & contacts...";
        } else if (/saving.*companies|registered.*neon/i.test(friendlyStatus)) {
          friendlyStatus = "Saving verified leads to outreach directory...";
        } else if (/fetching listings from page\s*(\d+)/i.test(friendlyStatus)) {
          const p = friendlyStatus.match(/page\s*(\d+)/i)?.[1] || "1";
          friendlyStatus = `Scanning Google Local listings (Page ${p})...`;
        }
        monitorStatus.textContent = friendlyStatus;
        monitorCount.textContent = `${data.total_results || 0} Found`;
        monitorProgressBar.style.width = `${Math.min(100, Math.max(8, data.progress || 0))}%`;

        // Real-time user-friendly terminal log console stream
        if (scoutTerminalLogs && Array.isArray(data.logs) && data.logs.length > 0) {
          const formatted = data.logs.map(formatUserFriendlyLog).filter(Boolean);
          if (formatted.length > 0) {
            scoutTerminalLogs.innerHTML = formatted.join('');
            scoutTerminalLogs.scrollTop = scoutTerminalLogs.scrollHeight;
          }
        }

        // Real-time stream of live scraped cards while browser is discovering them
        if (Array.isArray(data.results) && data.results.length > 0) {
          liveScrapedResults = data.results;
          const activeKw = inputKeyword?.value?.trim() || "";
          const activeCity = inputCity?.value?.trim() || "";
          const queryTag = (activeKw && activeCity)
            ? `"${activeKw}" in "${activeCity}"`
            : (activeKw ? `"${activeKw}"` : (activeCity ? `in "${activeCity}"` : ""));
          renderScoutResults(liveScrapedResults, data.is_running 
            ? (queryTag ? `Live Cloud Scouting: ${queryTag}` : `Live Cloud Scouting`)
            : (queryTag ? `Discovered Leads: ${queryTag}` : `Discovered Leads`));
        }

        if (data.error) {
          clearInterval(pollInterval);
          btnStartScout.disabled = false;
          btnStartScout.classList.remove("opacity-50");
          monitorStatus.textContent = "Error: " + data.error;
          showToast("Scraping error: " + data.error, "error");
          return;
        }

        // Complete when the scraper has finished or if stopped
        const hasFinished = (!data.is_running && (hasStartedRunning || polls > 2)) || polls > 120;
        if (hasFinished) {
          clearInterval(pollInterval);
          btnStartScout.disabled = false;
          btnStartScout.classList.remove("opacity-50");
          // Automatically refresh the companies list in the UI for directory & badges
          await fetchCompanies();
          const activeKw = inputKeyword?.value?.trim() || "";
          const activeCity = inputCity?.value?.trim() || "";
          const queryTag = (activeKw && activeCity)
            ? `"${activeKw}" in "${activeCity}"`
            : (activeKw ? `"${activeKw}"` : (activeCity ? `in "${activeCity}"` : ""));
          if (liveScrapedResults && liveScrapedResults.length > 0) {
            renderScoutResults(liveScrapedResults, queryTag
              ? `Discovered ${liveScrapedResults.length} Leads for ${queryTag}`
              : `Discovered ${liveScrapedResults.length} Leads`);
          }
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    }, 5000); // Clean 5-second polling interval as requested
  }

  // ==========================================
  // STAGE 2: DEEP ENRICHMENT
  // ==========================================
  // ==========================================
  // AUTHENTICATION & LOGIN GATE CONTROLLER
  // ==========================================
  currentUser = (window.__INITIAL_AUTH__ && typeof window.__INITIAL_AUTH__.is_logged_in === "boolean")
    ? { ...window.__INITIAL_AUTH__ }
    : { is_logged_in: false, email: null, is_master_admin: false, dev_mode: false };
  const loginModal = document.getElementById("login-modal");
  const loginModalClose = document.getElementById("login-modal-close");
  const btnModalDemoLogin = document.getElementById("btn-modal-demo-login");
  const btnSidebarDemoLogin = document.getElementById("btn-sidebar-demo-login");
  const btnModalAdminLogin = document.getElementById("btn-modal-admin-login");
  const btnSidebarAdminLogin = document.getElementById("btn-sidebar-admin-login");
  const btnHeaderAdminLogin = document.getElementById("btn-header-admin-login");

  function showLoginModal(customMessage = null) {
    const modalDesc = document.getElementById("login-modal-desc");
    if (modalDesc) {
      if (customMessage) {
        modalDesc.textContent = customMessage;
      } else {
        modalDesc.textContent = "Please log in to use this feature. Sign in with Google to analyze leads, detect tech stacks, and generate personalized outreach.";
      }
    }
    loginModal?.classList.remove("hidden");
    refreshIcons();
  }
  window.showLoginModal = showLoginModal;

  function requireLogin(callback, actionPrompt = "Please sign in with Google to use AI Deep Enrichment.") {
    if (currentUser && currentUser.is_logged_in) {
      callback();
    } else {
      const message = actionPrompt.startsWith("Please") ? actionPrompt : `Please sign in with Google to ${actionPrompt}.`;
      showToast(message, "warning");
      showLoginModal(message);
    }
  }
  const sidebarAdminBadge = document.getElementById("sidebar-admin-badge");
  const btnLogout = document.getElementById("btn-logout");
  const authBoxLoggedIn = document.getElementById("auth-box-logged-in");
  const authBoxLoggedOut = document.getElementById("auth-box-logged-out");
  const userDisplayEmail = document.getElementById("user-display-email");

  async function checkAuthStatus() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has("auth_error")) {
      const err = urlParams.get("auth_error");
      showToast("Google Sign-In Issue: " + err, "error");
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (urlParams.has("auth_success")) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    try {
      const res = await fetch("/api/auth/status");
      const data = await res.json();
      currentUser = data;
      isMasterAdmin = !!data.is_master_admin;
      if (typeof data.dev_mode === "boolean") {
        isDevMode = data.dev_mode;
      }

      if (currentUser.is_logged_in) {
        authBoxLoggedIn?.classList.remove("hidden");
        authBoxLoggedOut?.classList.add("hidden");
        if (userDisplayEmail) userDisplayEmail.textContent = currentUser.email || "Verified User";
        const avatarEl = document.getElementById("user-avatar-initials");
        if (avatarEl) {
          const raw = (currentUser.name || currentUser.email || "U").trim();
          const initials = raw.includes("@")
            ? raw.slice(0, 2).toUpperCase()
            : raw.split(/\s+/).map(p => p[0]).join("").slice(0, 2).toUpperCase();
          avatarEl.textContent = initials || "U";
        }
        if (isMasterAdmin) {
          sidebarAdminBadge?.classList.remove("hidden");
          setAdminViewMode(adminViewMode || "admin");
        } else {
          sidebarAdminBadge?.classList.add("hidden");
          adminModeToggleGroup?.classList.add("hidden");
          adminModeToggleGroup?.classList.remove("flex");
          adminPreviewBanner?.classList.add("hidden");
          statCardInvalid?.classList.add("hidden");
        }
      } else {
        authBoxLoggedIn?.classList.add("hidden");
        authBoxLoggedOut?.classList.remove("hidden");
        sidebarAdminBadge?.classList.add("hidden");
        adminModeToggleGroup?.classList.add("hidden");
        adminModeToggleGroup?.classList.remove("flex");
        adminPreviewBanner?.classList.add("hidden");
        statCardInvalid?.classList.add("hidden");
      }
      refreshIcons();
      fetchCompaniesFilters();
    } catch (err) {
      console.warn("Auth status fetch error:", err);
    }
  }

  if (loginModalClose) {
    loginModalClose.addEventListener("click", () => loginModal?.classList.add("hidden"));
  }
  if (loginModal) {
    loginModal.addEventListener("click", (e) => {
      if (e.target === loginModal) loginModal.classList.add("hidden");
    });
  }

  async function performDemoLogin(opts = {}) {
    try {
      const res = await fetch("/auth/demo/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(opts)
      });
      const data = await res.json();
      if (data.success) {
        document.cookie = `pilot_user_email=${data.email}; path=/; max-age=86400; SameSite=Lax`;
        loginModal?.classList.add("hidden");
        await checkAuthStatus();
        await fetchCompanies();
        const roleLabel = data.is_master_admin ? " [MASTER ADMIN]" : "";
        showToast(`Signed in successfully as ${data.email}${roleLabel}!`, "success");
      }
    } catch (err) {
      showToast("Sign-in failed: " + err.message, "error");
    }
  }

  if (btnModalAdminLogin) {
    btnModalAdminLogin.addEventListener("click", () => performDemoLogin({ as_admin: true }));
  }
  if (btnSidebarAdminLogin) {
    btnSidebarAdminLogin.addEventListener("click", () => performDemoLogin({ as_admin: true }));
  }
  if (btnHeaderAdminLogin) {
    btnHeaderAdminLogin.addEventListener("click", () => performDemoLogin({ as_admin: true }));
  }
  if (btnModalDemoLogin) {
    btnModalDemoLogin.addEventListener("click", () => performDemoLogin({ as_admin: false, email: "demo_user@outreachpilot.ai" }));
  }
  if (btnSidebarDemoLogin) {
    btnSidebarDemoLogin.addEventListener("click", () => performDemoLogin({ as_admin: false, email: "demo_user@outreachpilot.ai" }));
  }

  if (btnLogout) {
    btnLogout.addEventListener("click", async () => {
      try {
        await fetch("/auth/logout", { method: "POST" });
        document.cookie = "pilot_user_email=; path=/; max-age=0; SameSite=Lax";
        await checkAuthStatus();
        await fetchCompanies();
        showToast("You have signed out.", "info");
      } catch (err) {
        showToast("Sign-out failed: " + err.message, "error");
      }
    });
  }

  // ==========================================
  // STAGE 2: DEEP ENRICHMENT (LOGIN GATED)
  // ==========================================
  async function handleSingleEnrich(btn, companyId) {
    requireLogin(async () => {
      const oldHtml = btn.innerHTML;
      btn.innerHTML = `<i data-lucide="loader-2" class="w-3 h-3 animate-spin"></i><span>Analyzing...</span>`;
      btn.disabled = true;
      refreshIcons();
      try {
        const res = await fetch(`/api/companies/${companyId}/enrich`, { method: "POST" });
        if (res.status === 401) {
          currentUser.is_logged_in = false;
          showToast("Please sign in with Google to use AI Deep Enrichment.", "warning");
          showLoginModal("Please sign in with Google to use AI Deep Enrichment.");
          return;
        }
        await res.json();
        await fetchCompanies();
      } catch (err) {
        showToast("Enrichment failed: " + err.message, "error");
      } finally {
        btn.innerHTML = oldHtml;
        btn.disabled = false;
        refreshIcons();
      }
    }, "Please sign in with Google to use AI Deep Enrichment.");
  }

  // Bulk Enrichment Handlers
  const btnBulkEnrichTop = document.getElementById("btn-bulk-enrich-top");
  const btnGenAllPitches = document.getElementById("btn-gen-all-pitches");

  async function handleBulkEnrich(btn) {
    if (!companies || companies.length === 0) {
      showToast("No companies found to enrich. Scout companies in Step 1 first!", "warning");
      return;
    }
    requireLogin(async () => {
      const pending = companies.filter(c => !c.is_enriched);
      const targetList = pending.length > 0 ? pending : companies;
      const oldText = btn.innerHTML;
      btn.disabled = true;

      let completed = 0;
      const total = targetList.length;
      const CONCURRENCY = 6; // 6 parallel worker threads for ultra-fast throughput

      btn.innerHTML = `<i data-lucide="zap" class="w-3.5 h-3.5 text-amber-300 animate-spin"></i><span>Enriching (0/${total})...</span>`;
      refreshIcons();

      let index = 0;
      let unauthorizedOccurred = false;
      async function worker() {
        while (index < targetList.length) {
          if (unauthorizedOccurred) break;
          const comp = targetList[index++];
          try {
            const res = await fetch(`/api/companies/${comp.id}/enrich`, { method: "POST" });
            if (res.status === 401) {
              unauthorizedOccurred = true;
              currentUser.is_logged_in = false;
              showToast("Please sign in with Google to run bulk AI enrichment.", "warning");
              showLoginModal("Please sign in with Google to run bulk AI enrichment.");
              break;
            }
          } catch (err) {
            console.error("Enrich error for", comp.name, err);
          }
          completed++;
          btn.innerHTML = `<i data-lucide="zap" class="w-3.5 h-3.5 text-amber-300"></i><span>Enriching (${completed}/${total}): ${comp.name.substring(0, 14)}...</span>`;
          refreshIcons();
          fetchCompanies();
        }
      }

      // Launch 6 parallel workers simultaneously
      const workerPromises = [];
      const activeWorkers = Math.min(CONCURRENCY, targetList.length);
      for (let w = 0; w < activeWorkers; w++) {
        workerPromises.push(worker());
      }
      await Promise.all(workerPromises);

      if (!unauthorizedOccurred) {
        btn.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span>Completed (${total} Enriched)</span>`;
        refreshIcons();
        await fetchCompanies();
      }
      setTimeout(() => {
        btn.innerHTML = oldText;
        btn.disabled = false;
        refreshIcons();
      }, 2500);
    }, "Please sign in with Google to run bulk AI enrichment.");
  }

  if (btnBulkEnrichTop) {
    btnBulkEnrichTop.addEventListener("click", () => handleBulkEnrich(btnBulkEnrichTop));
  }

  if (btnGenAllPitches) {
    btnGenAllPitches.addEventListener("click", async () => {
      const targets = (allOutreachCompanies && allOutreachCompanies.length > 0) ? allOutreachCompanies : (companies || []);
      const eligible = targets.filter(c => !c.is_invalid);

      if (eligible.length === 0) {
        showToast("No companies found to generate pitches for.", "warning");
        return;
      }

      requireLogin(async () => {
        const oldText = btnGenAllPitches.innerHTML;
        btnGenAllPitches.disabled = true;

        let authFailed = false;
        let generatedCount = 0;
        const BATCH_SIZE = 20;

        for (let i = 0; i < eligible.length; i += BATCH_SIZE) {
          if (authFailed) break;
          const chunk = eligible.slice(i, i + BATCH_SIZE);
          const chunkIds = chunk.map(c => c.id);
          const currentEnd = Math.min(i + chunk.length, eligible.length);

          btnGenAllPitches.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin text-amber-300">progress_activity</span><span>Preparing (${currentEnd}/${eligible.length})...</span>`;
          try {
            const res = await fetch("/api/pitch/bulk-generate", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ company_ids: chunkIds })
            });

            if (res.status === 401) {
              authFailed = true;
              currentUser.is_logged_in = false;
              showToast("Authentication required. Please connect your Google account to generate personalized pitches.", "warning");
              showLoginModal("Authentication required. Please connect your Google account to generate personalized pitches.");
              break;
            }

            if (res.ok) {
              const data = await res.json();
              if (data.success && data.generated_count) {
                generatedCount += data.generated_count;
                if (data.pitches) {
                  data.pitches.forEach(p => {
                    const comp = eligible.find(c => c.id === p.company_id);
                    if (comp) comp.pitch_id = p.pitch_id;
                  });
                }
              }
            } else {
              const errData = await res.json().catch(() => ({}));
              showToast(errData.detail || "Failed to generate pitches for batch.", "error");
            }
          } catch (err) {
            console.error("Bulk pitch error:", err);
          }
        }

        if (!authFailed) {
          btnGenAllPitches.innerHTML = `<span class="material-symbols-outlined text-[16px] text-emerald-400">check</span><span>${generatedCount} Pitches Prepared!</span>`;
          renderPitchesList();
        }

        setTimeout(() => {
          btnGenAllPitches.innerHTML = oldText;
          btnGenAllPitches.disabled = false;
        }, 2500);
      }, "Authentication required. Please connect your Google account to generate personalized pitches.");
    });
  }

  // --- Send All Outreach Emails (Strict: Never sends to companies without discovered emails) ---
  const btnSendAllOutreach = document.getElementById("btn-send-all-outreach");
  if (btnSendAllOutreach) {
    btnSendAllOutreach.addEventListener("click", async () => {
      const targets = (allOutreachCompanies && allOutreachCompanies.length > 0) ? allOutreachCompanies : (companies || []);
      const eligible = targets.filter(c => !c.is_invalid);

      if (eligible.length === 0) {
        showToast("No companies available for outreach.", "warning");
        return;
      }

      requireLogin(async () => {
        // Strictly filter to companies with at least one discovered email
        const withEmail = eligible.filter(c => c.emails && c.emails.length > 0 && !c.already_contacted);
        const alreadySentCount = eligible.filter(c => c.emails && c.emails.length > 0 && c.already_contacted).length;
        const noEmailCompanies = eligible.filter(c => !c.emails || c.emails.length === 0);
        const noEmailCount = noEmailCompanies.length;

        if (withEmail.length === 0) {
          if (alreadySentCount > 0 && noEmailCount > 0) {
            showToast(`All ${alreadySentCount} companies with verified emails have already been contacted. Skipped ${noEmailCount} companies with no email.`, "info");
          } else if (noEmailCount > 0) {
            showToast(`Company email not found! All ${noEmailCount} companies have no discovered email address. Enrich companies first.`, "error");
          } else {
            showToast("No pending outreach targets with email addresses.", "info");
          }
          return;
        }

        const confirmMsg = `Ready to send personalized cold emails via Gmail to ${withEmail.length} companies with discovered emails?\n\n(${noEmailCount} companies with no email address will be strictly skipped and will NOT receive any email).`;
        if (!confirm(confirmMsg)) {
          return;
        }

        const oldText = btnSendAllOutreach.innerHTML;
        btnSendAllOutreach.disabled = true;

        // Check which companies already have prepared pitches and which still need generation
        const alreadyPrepared = withEmail.filter(c => c.pitch_id);
        const needPreparation = withEmail.filter(c => !c.pitch_id);

        let pitchIdsToSend = alreadyPrepared.map(c => c.pitch_id);
        let authFailed = false;
        const BATCH_SIZE = 20;

        // ONLY generate pitches for companies that don't have a prepared draft yet!
        if (needPreparation.length > 0) {
          btnSendAllOutreach.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span><span>Preparing (${needPreparation.length})...</span>`;

          for (let i = 0; i < needPreparation.length; i += BATCH_SIZE) {
            if (authFailed) break;
            const chunk = needPreparation.slice(i, i + BATCH_SIZE);
            const chunkIds = chunk.map(c => c.id);
            const currentEnd = Math.min(i + chunk.length, needPreparation.length);

            btnSendAllOutreach.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span><span>Preparing (${currentEnd}/${needPreparation.length})...</span>`;
            try {
              const res = await fetch("/api/pitch/bulk-generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ company_ids: chunkIds })
              });

              if (res.status === 401) {
                authFailed = true;
                currentUser.is_logged_in = false;
                showToast("Session expired. Please reconnect your Google account to send emails.", "warning");
                showLoginModal("Session expired. Please reconnect your Google account to send emails.");
                break;
              }

              if (res.ok) {
                const data = await res.json();
                if (data.success && data.pitches) {
                  data.pitches.forEach(p => {
                    if (p.pitch_id && p.target_email) {
                      pitchIdsToSend.push(p.pitch_id);
                    }
                    const comp = withEmail.find(c => c.id === p.company_id);
                    if (comp) comp.pitch_id = p.pitch_id;
                  });
                }
              }
            } catch (err) {
              console.error("Failed to bulk prepare pitches for send:", err);
            }
          }
        }

        if (authFailed || pitchIdsToSend.length === 0) {
          btnSendAllOutreach.disabled = false;
          btnSendAllOutreach.innerHTML = oldText;
          if (!authFailed && pitchIdsToSend.length === 0) {
            showToast("Could not prepare email pitches. Please try again.", "error");
          }
          return;
        }

        // Dispatch bulk send via API strictly with valid pitch IDs
        btnSendAllOutreach.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin text-primary">progress_activity</span><span>Dispatching (${pitchIdsToSend.length})...</span>`;

        try {
          const bulkRes = await fetch("/api/pitch/bulk-send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              pitch_ids: pitchIdsToSend,
              delay_min: 2.0,
              delay_max: 3.5
            })
          });

          if (bulkRes.status === 401) {
            showToast("Session expired. Please reconnect your Google account.", "warning");
            showLoginModal("Session expired. Please reconnect your Google account.");
            return;
          }

          const bulkData = await bulkRes.json();
          const sent = bulkData.sent || 0;
          const skipped = (bulkData.skipped_no_email || 0) + noEmailCount;

          showToast(`Success: Dispatched ${sent} emails via Gmail! (${skipped} companies without email were skipped).`, "success");
          btnSendAllOutreach.innerHTML = `<span class="material-symbols-outlined text-[16px] text-emerald-400">check</span><span>${sent} Dispatched!</span>`;

          await fetchCompanies();
          fetchAuditLogs();
          renderPitchesList();
        } catch (err) {
          showToast("Batch dispatch error: " + err.message, "error");
        } finally {
          setTimeout(() => {
            btnSendAllOutreach.innerHTML = oldText;
            btnSendAllOutreach.disabled = false;
          }, 3000);
        }
      }, "connect your Google account to perform automated outreach.");
    });
  }

  // ==========================================
  // STAGE 3: RESUME UPLOAD & PARSING
  // ==========================================
  const resumeForm = document.getElementById("resume-form");
  const fileInput = document.getElementById("input-resume-file");
  const dropzone = document.getElementById("dropzone");
  const fileLabel = document.getElementById("file-label");
  const btnParseResume = document.getElementById("btn-parse-resume");

  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      fileLabel.textContent = `Selected: ${fileInput.files[0].name}`;
    }
  });

  async function loadCandidateProfile() {
    try {
      const res = await fetch("/api/resume/profile");
      if (res.status === 401) return;
      const data = await res.json();
      if (data.resume_link) {
        const linkEl = document.getElementById("input-resume-link");
        if (linkEl) linkEl.value = data.resume_link;
      }
      if (data.target_role) {
        const roleEl = document.getElementById("input-target-role");
        if (roleEl) roleEl.value = data.target_role;
      }
      if (data.profile) {
        renderCandidateProfile(data.profile);
      }
    } catch (err) {
      console.warn("Could not load candidate profile:", err);
    }
  }

  function renderCandidateProfile(profile) {
    if (!profile) return;
    const pitchEl = document.getElementById("profile-pitch");
    if (pitchEl && profile.elevator_pitch) {
      pitchEl.textContent = profile.elevator_pitch;
    }

    const archetypeBadge = document.getElementById("profile-archetype-badge");
    if (archetypeBadge) {
      if (profile.archetype) {
        archetypeBadge.textContent = profile.archetype;
        archetypeBadge.classList.remove("hidden");
      } else {
        archetypeBadge.classList.add("hidden");
      }
    }

    const skillsContainer = document.getElementById("profile-skills");
    if (skillsContainer && profile.top_skills) {
      skillsContainer.innerHTML = profile.top_skills.map(s => `
        <span class="px-2.5 py-1 rounded bg-primary/10 text-primary border border-primary/30 text-xs font-medium">${escapeHTML(s)}</span>
      `).join("");
    }

    const achContainer = document.getElementById("profile-achievements");
    if (achContainer) {
      const achievements = profile.strong_points || profile.key_achievements;
      if (achievements && achievements.length > 0) {
        achContainer.innerHTML = achievements.map(a => `
          <li>${escapeHTML(a)}</li>
        `).join("");
      }
    }

    const rolesSec = document.getElementById("profile-roles-section");
    const rolesContainer = document.getElementById("profile-best-fit-roles");
    if (rolesSec && rolesContainer) {
      if (profile.best_fit_roles && profile.best_fit_roles.length > 0) {
        rolesContainer.innerHTML = profile.best_fit_roles.map(r => `
          <span class="px-2.5 py-0.5 rounded bg-surface-container text-on-surface border border-outline-variant/40 text-xs font-medium">${escapeHTML(r)}</span>
        `).join("");
        rolesSec.classList.remove("hidden");
      } else {
        rolesSec.classList.add("hidden");
      }
    }

    const atsSec = document.getElementById("profile-ats-section");
    const atsContainer = document.getElementById("profile-ats-keywords");
    if (atsSec && atsContainer) {
      if (profile.ats_keywords && profile.ats_keywords.length > 0) {
        atsContainer.innerHTML = profile.ats_keywords.map(k => `
          <span class="px-2 py-0.5 rounded bg-surface-container-high/60 text-on-surface-variant border border-outline-variant/30 text-[11px] font-mono">${escapeHTML(k)}</span>
        `).join("");
        atsSec.classList.remove("hidden");
      } else {
        atsSec.classList.add("hidden");
      }
    }

    const detailedAnalysisEl = document.getElementById("profile-detailed-analysis");
    if (detailedAnalysisEl && profile.detailed_profile_analysis) {
      detailedAnalysisEl.dataset.rawText = profile.detailed_profile_analysis;
      detailedAnalysisEl.innerHTML = formatMarkdown(profile.detailed_profile_analysis);
    }
  }

  resumeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    requireLogin(async () => {
      const inputTargetRole = document.getElementById("input-target-role");
      const inputResumeLink = document.getElementById("input-resume-link");
      const dropzoneEl = document.getElementById("dropzone");
      const hasFile = fileInput.files && fileInput.files.length > 0;
      const resumeLink = (inputResumeLink?.value || "").trim();
      const targetRole = (inputTargetRole?.value || "").trim();

      if (!targetRole) {
        highlightFieldWarning(inputTargetRole, "Target Job Role is required (e.g. Senior Full-Stack Engineer, B2B Growth Lead).");
        return;
      }

      if (!hasFile && !resumeLink) {
        highlightFieldWarning(inputResumeLink, "Please select a resume file (PDF or TXT) or enter a portfolio/resume link.");
        dropzoneEl?.classList.add("input-warning-highlight");
        setTimeout(() => dropzoneEl?.classList.remove("input-warning-highlight"), 3200);
        return;
      }

      const formData = new FormData();
      if (hasFile) {
        formData.append("file", fileInput.files[0]);
      }
      formData.append("resume_link", resumeLink);
      formData.append("target_role", targetRole);

      btnParseResume.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Analyzing with AI...</span>`;
      btnParseResume.disabled = true;
      refreshIcons();

      try {
        const res = await fetch("/api/resume/upload", {
          method: "POST",
          body: formData
        });
        if (res.status === 401) {
          currentUser.is_logged_in = false;
          showToast("Please sign in with Google to analyze your resume with AI.", "warning");
          showLoginModal("Please sign in with Google to analyze your resume with AI.");
          return;
        }
        const data = await res.json();
        if (data.success && data.profile) {
          renderCandidateProfile(data.profile);
          showToast("Candidate Profile updated successfully!", "success");
        } else {
          showToast(data.detail || data.message || "Failed to update profile.", "error");
        }
      } catch (err) {
        showToast("Resume analysis failed: " + err.message, "error");
      } finally {
        btnParseResume.innerHTML = `<i data-lucide="sparkles" class="w-3.5 h-3.5 text-amber-300"></i><span>Analyze Resume with AI</span>`;
        btnParseResume.disabled = false;
        refreshIcons();
      }
    }, "Please sign in with Google to analyze your resume with AI.");
  });

  const btnCopyProfileAnalysis = document.getElementById("btn-copy-profile-analysis");
  if (btnCopyProfileAnalysis) {
    btnCopyProfileAnalysis.addEventListener("click", () => {
      const detailedAnalysisEl = document.getElementById("profile-detailed-analysis");
      const rawText = detailedAnalysisEl?.dataset?.rawText || detailedAnalysisEl?.innerText || "";
      if (!rawText || rawText.includes("Upload your resume above")) {
        showToast("Please upload and analyze a resume first to copy the dossier.", "warning");
        return;
      }
      const cleanText = stripMarkdownForCopy(rawText);
      navigator.clipboard.writeText(cleanText).then(() => {
        btnCopyProfileAnalysis.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span class="text-emerald-400">Copied!</span>`;
        refreshIcons();
        setTimeout(() => {
          btnCopyProfileAnalysis.innerHTML = `<i data-lucide="copy" class="w-3.5 h-3.5 text-primary"></i><span>Copy Analysis</span>`;
          refreshIcons();
        }, 2000);
      }).catch(err => {
        console.error("Clipboard copy failed:", err);
      });
    });
  }

  // ==========================================
  // STAGE 4: PITCH GENERATOR & OUTREACH HUB
  // ==========================================
  const modal = document.getElementById("pitch-modal");
  const modalClose = document.getElementById("modal-close");
  const modalCompanyName = document.getElementById("modal-company-name");
  const modalTargetEmail = document.getElementById("modal-target-email");
  const modalSubject = document.getElementById("modal-subject");
  const modalBody = document.getElementById("modal-body");
  const btnLaunchGmail = document.getElementById("btn-launch-gmail");
  const btnSendDirectOauth = document.getElementById("btn-send-direct-oauth");
  const btnSendDirectText = document.getElementById("btn-send-direct-text");
  const btnCopyPitch = document.getElementById("btn-copy-pitch");
  let currentPitchId = null;
  let currentPitchTargetEmail = null;

  // Temporary session resume attachment state (cleared upon tab/session close)
  let sessionResumeFile = null;
  let attachResumeInEmail = false;

  const outreachResumeFile = document.getElementById("outreach-resume-file");
  const btnChooseOutreachResume = document.getElementById("btn-choose-outreach-resume");
  const btnChooseResumeText = document.getElementById("btn-choose-resume-text");
  const btnRemoveOutreachResume = document.getElementById("btn-remove-outreach-resume");
  const outreachResumeStatus = document.getElementById("outreach-resume-status");
  const toggleAttachResume = document.getElementById("toggle-attach-resume");

  const pitchModalResumeName = document.getElementById("pitch-modal-resume-name");
  const btnPitchModalChooseResume = document.getElementById("btn-pitch-modal-choose-resume");
  const pitchModalAttachToggle = document.getElementById("pitch-modal-attach-toggle");

  function updateResumeAttachmentUI() {
    if (sessionResumeFile) {
      const sizeKb = Math.round(sessionResumeFile.size / 1024);
      const fileLabel = `${sessionResumeFile.name} (${sizeKb} KB)`;
      
      if (outreachResumeStatus) {
        outreachResumeStatus.innerHTML = `<span class="text-emerald-400 font-medium">Selected:</span> <span class="font-mono text-slate-200">${escapeHTML(fileLabel)}</span>`;
      }
      if (btnChooseResumeText) btnChooseResumeText.textContent = "Change File";
      if (btnRemoveOutreachResume) btnRemoveOutreachResume.classList.remove("hidden");
      if (toggleAttachResume) toggleAttachResume.checked = attachResumeInEmail;

      if (pitchModalResumeName) {
        pitchModalResumeName.textContent = fileLabel;
        pitchModalResumeName.className = "font-mono text-emerald-400 truncate max-w-[200px] sm:max-w-[280px]";
      }
      if (pitchModalAttachToggle) pitchModalAttachToggle.checked = attachResumeInEmail;

      if (btnSendDirectText) {
        btnSendDirectText.textContent = attachResumeInEmail ? "Send with Resume" : "Send via Gmail";
      }
    } else {
      if (outreachResumeStatus) {
        outreachResumeStatus.textContent = "No resume selected for this session. Choose a PDF file to attach when sending cold emails.";
      }
      if (btnChooseResumeText) btnChooseResumeText.textContent = "Choose Resume File";
      if (btnRemoveOutreachResume) btnRemoveOutreachResume.classList.add("hidden");
      if (toggleAttachResume) toggleAttachResume.checked = false;

      if (pitchModalResumeName) {
        pitchModalResumeName.textContent = "No file selected";
        pitchModalResumeName.className = "font-mono text-slate-500 truncate max-w-[200px] sm:max-w-[280px]";
      }
      if (pitchModalAttachToggle) pitchModalAttachToggle.checked = false;

      if (btnSendDirectText) {
        btnSendDirectText.textContent = "Send via Gmail";
      }
    }
    refreshIcons();
  }

  function handleFileSelected(file) {
    if (!file) return;
    sessionResumeFile = file;
    attachResumeInEmail = true;
    updateResumeAttachmentUI();
    showToast(`Resume attached for this session: ${file.name}`, "info");
  }

  if (btnChooseOutreachResume && outreachResumeFile) {
    btnChooseOutreachResume.addEventListener("click", () => outreachResumeFile.click());
  }

  if (btnPitchModalChooseResume && outreachResumeFile) {
    btnPitchModalChooseResume.addEventListener("click", () => outreachResumeFile.click());
  }

  if (outreachResumeFile) {
    outreachResumeFile.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        handleFileSelected(file);
      }
    });
  }

  if (btnRemoveOutreachResume) {
    btnRemoveOutreachResume.addEventListener("click", () => {
      sessionResumeFile = null;
      attachResumeInEmail = false;
      if (outreachResumeFile) outreachResumeFile.value = "";
      updateResumeAttachmentUI();
      showToast("Session resume attachment removed.", "info");
    });
  }

  if (toggleAttachResume) {
    toggleAttachResume.addEventListener("change", (e) => {
      if (e.target.checked && !sessionResumeFile) {
        if (outreachResumeFile) outreachResumeFile.click();
      } else {
        attachResumeInEmail = e.target.checked;
        updateResumeAttachmentUI();
      }
    });
  }

  if (pitchModalAttachToggle) {
    pitchModalAttachToggle.addEventListener("change", (e) => {
      if (e.target.checked && !sessionResumeFile) {
        if (outreachResumeFile) outreachResumeFile.click();
      } else {
        attachResumeInEmail = e.target.checked;
        updateResumeAttachmentUI();
      }
    });
  }

  modalClose.addEventListener("click", () => modal.classList.add("hidden"));

  // State for pitch deliverables
  let currentPitchCompanyId = null;
  let currentPitchData = null;
  let activeVariant = "primary";
  let activeSubjectAngle = "specificity";

  const btnModalRegenerate = document.getElementById("btn-modal-regenerate");
  const pitchWordCount = document.getElementById("pitch-word-count");
  const pitchStrategyToggle = document.getElementById("pitch-strategy-toggle");
  const pitchStrategyContent = document.getElementById("pitch-strategy-content");
  const pitchStrategyChevron = document.getElementById("pitch-strategy-chevron");
  const pitchPersonalizationFacts = document.getElementById("pitch-personalization-facts");
  const pitchStratNotHiring = document.getElementById("pitch-strat-not-hiring");
  const pitchStratRecruiter = document.getElementById("pitch-strat-recruiter");

  function updatePitchWordCount() {
    if (!modalBody || !pitchWordCount) return;
    const text = (modalBody.value || "").trim();
    const count = text ? text.split(/\s+/).length : 0;
    let limitLabel = "(<120w)";
    let isOver = false;

    if (activeVariant === "linkedin") {
      limitLabel = "(<80w)";
      isOver = count > 80;
    } else if (activeVariant === "referral") {
      limitLabel = "(<140w)";
      isOver = count > 140;
    } else {
      isOver = count > 120;
    }

    pitchWordCount.textContent = `${count} words ${limitLabel}`;
    if (isOver) {
      pitchWordCount.className = "text-caption font-mono text-amber-500 font-semibold";
    } else {
      pitchWordCount.className = "text-caption font-mono text-outline";
    }
  }

  function updateGmailComposeUrls() {
    if (!btnLaunchGmail) return;
    const to = currentPitchTargetEmail || "";
    const subj = (modalSubject?.value || "").trim();
    const body = (modalBody?.value || "").trim();
    btnLaunchGmail.href = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subj)}&body=${encodeURIComponent(body)}`;
  }

  if (modalBody) {
    modalBody.addEventListener("input", () => {
      updatePitchWordCount();
      updateGmailComposeUrls();
    });
  }

  if (modalSubject) {
    modalSubject.addEventListener("input", updateGmailComposeUrls);
  }

  function setupSubjectAngleButtons(subjs, initialActive = "specificity") {
    activeSubjectAngle = initialActive;
    const angleMap = [
      { id: "btn-subj-specificity", key: "specificity" },
      { id: "btn-subj-curiosity", key: "curiosity" },
      { id: "btn-subj-benefit", key: "benefit_led" }
    ];

    angleMap.forEach(item => {
      const btn = document.getElementById(item.id);
      if (!btn) return;
      const angleVal = (subjs && subjs[item.key]) || "";
      const previewSpan = btn.querySelector(".subject-preview");
      if (previewSpan) {
        previewSpan.textContent = angleVal || "N/A";
      }

      if (item.key === activeSubjectAngle) {
        btn.className = "pitch-subject-btn active px-2.5 py-1 rounded-lg text-caption font-medium border border-primary/40 bg-primary/10 text-primary transition cursor-pointer flex items-center gap-1 shadow-xs";
      } else {
        btn.className = "pitch-subject-btn px-2.5 py-1 rounded-lg text-caption font-medium border border-outline-variant/40 bg-surface-container text-on-surface-variant hover:text-on-surface transition cursor-pointer flex items-center gap-1";
      }

      btn.onclick = (e) => {
        e.preventDefault();
        activeSubjectAngle = item.key;
        if (angleVal) {
          modalSubject.value = angleVal;
          updateGmailComposeUrls();
        }
        setupSubjectAngleButtons(subjs, item.key);
      };
    });
  }

  function switchPitchVariant(variantKey) {
    activeVariant = variantKey;
    const tabsContainer = document.getElementById("pitch-variant-tabs");
    if (tabsContainer) {
      tabsContainer.querySelectorAll(".pitch-tab-btn").forEach(btn => {
        if (btn.dataset.variant === variantKey) {
          btn.className = "pitch-tab-btn active px-2.5 py-1 rounded text-caption font-semibold transition cursor-pointer bg-primary-container text-on-primary shadow-xs";
        } else {
          btn.className = "pitch-tab-btn px-2.5 py-1 rounded text-caption font-medium transition cursor-pointer text-on-surface-variant hover:text-on-surface";
        }
      });
    }

    if (!currentPitchData) return;
    if (variantKey === "primary") {
      modalBody.value = currentPitchData.primary_email || currentPitchData.email_body || "";
    } else if (variantKey === "linkedin") {
      modalBody.value = currentPitchData.variant_a_linkedin || "";
    } else if (variantKey === "referral") {
      modalBody.value = currentPitchData.variant_b_referral || currentPitchData.cover_letter || "";
    }

    updatePitchWordCount();
    updateGmailComposeUrls();
  }

  const pitchVariantTabs = document.getElementById("pitch-variant-tabs");
  if (pitchVariantTabs) {
    pitchVariantTabs.querySelectorAll(".pitch-tab-btn").forEach(btn => {
      btn.addEventListener("click", () => switchPitchVariant(btn.dataset.variant));
    });
  }

  function populateStrategyNotes(notes, whatToChange) {
    if (pitchPersonalizationFacts) {
      if (notes && notes.length > 0) {
        pitchPersonalizationFacts.innerHTML = notes.map(n => `<li>${escapeHTML(n)}</li>`).join("");
      } else {
        pitchPersonalizationFacts.innerHTML = `<li class="italic text-outline">Tailored to company tech stack and industry scope.</li>`;
      }
    }

    if (pitchStratNotHiring) {
      pitchStratNotHiring.textContent = (whatToChange && whatToChange.if_not_hiring) || "Shift focus to peer knowledge sharing or ad-hoc contract engineering.";
    }

    if (pitchStratRecruiter) {
      pitchStratRecruiter.textContent = (whatToChange && whatToChange.if_recruiter) || "State target role, immediate availability, and core tech stack match directly.";
    }
  }

  if (pitchStrategyToggle && pitchStrategyContent) {
    pitchStrategyToggle.addEventListener("click", () => {
      const isHidden = pitchStrategyContent.classList.contains("hidden");
      if (isHidden) {
        pitchStrategyContent.classList.remove("hidden");
        if (pitchStrategyChevron) pitchStrategyChevron.style.transform = "rotate(180deg)";
      } else {
        pitchStrategyContent.classList.add("hidden");
        if (pitchStrategyChevron) pitchStrategyChevron.style.transform = "rotate(0deg)";
      }
    });
  }

  if (btnModalRegenerate) {
    btnModalRegenerate.addEventListener("click", () => {
      if (currentPitchCompanyId) {
        handleGeneratePitch(currentPitchCompanyId, true);
      }
    });
  }

  async function handleGeneratePitch(companyId, forceRegenerate = false) {
    currentPitchCompanyId = companyId;
    const triggerBtn = document.querySelector(`.btn-gen-pitch-row[data-id="${companyId}"]`);
    const origHtml = triggerBtn ? triggerBtn.innerHTML : "";
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Preparing...</span>`;
      refreshIcons();
    }
    if (btnModalRegenerate) {
      btnModalRegenerate.disabled = true;
      btnModalRegenerate.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Regenerating...</span>`;
      refreshIcons();
    }

    try {
      const res = await fetch("/api/pitch/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: companyId, force_regenerate: forceRegenerate })
      });
      if (res.status === 401) {
        currentUser.is_logged_in = false;
        showToast("Please sign in with Google to generate personalized outreach pitches.", "warning");
        showLoginModal("Please sign in with Google to generate personalized outreach pitches.");
        return;
      }
      const data = await res.json();
      if (data.success) {
        currentPitchData = data;
        currentPitchId = data.pitch_id;
        currentPitchTargetEmail = (data.target_email || "").trim();
        modalCompanyName.textContent = `Personalized Outreach for ${data.company_name}`;
        if (currentPitchTargetEmail) {
          modalTargetEmail.innerHTML = `<span class="material-symbols-outlined text-[14px] text-secondary">alternate_email</span> <span class="font-mono text-secondary font-semibold">${escapeHTML(currentPitchTargetEmail)}</span>`;
        } else {
          modalTargetEmail.innerHTML = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-amber-500/10 text-amber-500 border border-amber-500/20 font-semibold"><span class="material-symbols-outlined text-[13px]">mail_off</span><span>Email not found (Sending disabled)</span></span>`;
        }

        // Setup subject lines and default selection
        const subjs = data.subject_lines || {
          specificity: data.subject_line || "Engineering inquiry",
          curiosity: "Quick question on your tech stack",
          benefit_led: "Scaling backend pipelines"
        };
        modalSubject.value = data.subject_line || subjs.specificity || "";
        setupSubjectAngleButtons(subjs, "specificity");

        // Set primary email as active variant
        activeVariant = "primary";
        modalBody.value = data.primary_email || data.email_body || "";
        switchPitchVariant("primary");

        // Populate strategy notes
        populateStrategyNotes(data.personalization_notes, data.what_to_change_if);

        // Update URLs and attachment UI
        updateGmailComposeUrls();
        updateResumeAttachmentUI();
        modal.classList.remove("hidden");
        refreshIcons();
      } else {
        showToast(data.detail || data.message || "Failed to generate outreach pitch.", "error");
      }
    } catch (err) {
      showToast("Pitch generation failed: " + err.message, "error");
    } finally {
      if (triggerBtn) {
        triggerBtn.disabled = false;
        triggerBtn.innerHTML = origHtml;
        refreshIcons();
      }
      if (btnModalRegenerate) {
        btnModalRegenerate.disabled = false;
        btnModalRegenerate.innerHTML = `<span class="material-symbols-outlined text-[15px] text-amber-400">autorenew</span><span class="hidden sm:inline">Regenerate</span>`;
        refreshIcons();
      }
    }
  }

  if (btnSendDirectOauth) {
    btnSendDirectOauth.addEventListener("click", async () => {
      if (!currentPitchId) return;

      if (!currentPitchTargetEmail || !currentPitchTargetEmail.trim()) {
        showToast("Company email not found! Cannot send email.", "error");
        return;
      }

      const subject = (modalSubject.value || "").trim();
      const body = (modalBody.value || "").trim();

      if (!subject) {
        highlightFieldWarning(modalSubject, "Email Subject is required before sending.");
        return;
      }
      if (!body) {
        highlightFieldWarning(modalBody, "Email Message Body is required before sending.");
        return;
      }

      btnSendDirectOauth.disabled = true;
      btnSendDirectOauth.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Sending via Gmail...</span>`;
      refreshIcons();

      const formData = new FormData();
      formData.append("subject", subject);
      formData.append("body", body);
      formData.append("attach_resume", attachResumeInEmail ? "true" : "false");
      if (attachResumeInEmail && sessionResumeFile) {
        formData.append("resume_file", sessionResumeFile);
      }

      try {
        const res = await fetch(`/api/pitch/${currentPitchId}/send-direct`, {
          method: "POST",
          body: formData
        });
        const data = await res.json();
        if (data.success) {
          const successMsg = (attachResumeInEmail && sessionResumeFile)
            ? `Email and resume attachment dispatched directly via Gmail!`
            : "Email sent directly through your authorized Gmail account!";
          showToast(successMsg, "success");
          modal.classList.add("hidden");
          await fetchCompanies();
          fetchAuditLogs();
        } else {
          const errMsg = data.detail || data.error || "Company email not found! Cannot send email.";
          showToast(errMsg, "error");
          if (errMsg.toLowerCase().includes("session expired") || errMsg.toLowerCase().includes("reconnect") || errMsg.toLowerCase().includes("sign in with google")) {
            showLoginModal(errMsg);
          }
        }
      } catch (err) {
        showToast("Email sending failed: " + err.message, "error");
      } finally {
        btnSendDirectOauth.disabled = false;
        btnSendDirectOauth.innerHTML = `<i data-lucide="send" class="w-3.5 h-3.5"></i><span id="btn-send-direct-text">${attachResumeInEmail ? 'Send with Resume' : 'Send via Gmail'}</span>`;
        refreshIcons();
      }
    });
  }

  btnLaunchGmail.addEventListener("click", async (e) => {
    if (!currentPitchTargetEmail || !currentPitchTargetEmail.trim()) {
      e.preventDefault();
      showToast("Company email not found! Cannot send email.", "error");
      return;
    }
    if (currentPitchId) {
      await fetch(`/api/pitch/${currentPitchId}/log-sent?method=GMAIL_WEB`, { method: "POST" });
      await fetchCompanies();
      fetchAuditLogs();
    }
  });

  btnCopyPitch.addEventListener("click", () => {
    const text = `Subject: ${modalSubject.value}\n\n${modalBody.value}`;
    navigator.clipboard.writeText(text).then(() => {
      btnCopyPitch.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span>Copied!</span>`;
      refreshIcons();
      setTimeout(() => {
        btnCopyPitch.innerHTML = `<i data-lucide="copy" class="w-3.5 h-3.5"></i><span>Copy Message</span>`;
        refreshIcons();
      }, 2000);
    });
  });

  // ==========================================
  // OUTREACH HUB CONTROLS & PIPELINE
  // ==========================================
  let outreachActiveFilter = "all"; // "all" | "emails" | "ready" | "sent"
  let outreachSearchQuery = "";
  let outreachSelectedTech = "";
  let outreachSelectedCity = "";
  let outreachViewMode = "grid"; // "grid" | "list"

  const outreachSearchInput = document.getElementById("outreach-search-input");
  const outreachFilterAll = document.getElementById("outreach-filter-all");
  const outreachFilterEmails = document.getElementById("outreach-filter-emails");
  const outreachFilterReady = document.getElementById("outreach-filter-ready");
  const outreachFilterSent = document.getElementById("outreach-filter-sent");

  const outreachTechSelect = document.getElementById("outreach-tech-select");
  const outreachCitySelect = document.getElementById("outreach-city-select");
  const btnOutreachReset = document.getElementById("btn-outreach-reset");
  const btnOutreachViewGrid = document.getElementById("btn-outreach-view-grid");
  const btnOutreachViewList = document.getElementById("btn-outreach-view-list");

  const outreachStatAll = document.getElementById("outreach-stat-all");
  const outreachStatEmails = document.getElementById("outreach-stat-emails");
  const outreachStatReady = document.getElementById("outreach-stat-ready");
  const outreachStatSent = document.getElementById("outreach-stat-sent");

  const outreachCountTotal = document.getElementById("outreach-count-total");
  const outreachCountEmails = document.getElementById("outreach-count-emails");
  const outreachCountReady = document.getElementById("outreach-count-ready");
  const outreachCountSent = document.getElementById("outreach-count-sent");

  const outreachPagination = document.getElementById("outreach-pagination");
  const outreachPageRange = document.getElementById("outreach-page-range");
  const outreachPageTotal = document.getElementById("outreach-page-total");
  const outreachPerPageSelect = document.getElementById("outreach-per-page");
  const outreachPageButtons = document.getElementById("outreach-page-buttons");
  const outreachPaginationBottom = document.getElementById("outreach-pagination-bottom");
  const outreachPageRangeBottom = document.getElementById("outreach-page-range-bottom");
  const outreachPageTotalBottom = document.getElementById("outreach-page-total-bottom");
  const outreachPageButtonsBottom = document.getElementById("outreach-page-buttons-bottom");

  async function fetchOutreachCompanies(preservePage = false) {
    if (isOutreachLoading) return;
    isOutreachLoading = true;
    try {
      const res = await fetch("/api/companies?page_size=0&status=all");
      if (res.ok) {
        const data = await res.json();
        allOutreachCompanies = data.companies || [];
        outreachLoaded = true;
      }
    } catch (err) {
      console.warn("Failed to fetch all outreach companies:", err);
    } finally {
      isOutreachLoading = false;
      if (!preservePage) outreachCurrentPage = 1;
      renderPitchesList();
    }
  }

  const btnToggleActivity = document.getElementById("btn-toggle-activity");
  const btnCloseActivity = document.getElementById("btn-close-activity");
  const outreachActivityDrawer = document.getElementById("outreach-activity-drawer");
  const outreachActivityBackdrop = document.getElementById("outreach-activity-backdrop");
  const activityBadgeCount = document.getElementById("activity-badge-count");

  function openActivityDrawer() {
    if (outreachActivityDrawer) outreachActivityDrawer.classList.remove("translate-x-full");
    if (outreachActivityBackdrop) {
      outreachActivityBackdrop.classList.remove("opacity-0", "pointer-events-none");
      outreachActivityBackdrop.classList.add("opacity-100", "pointer-events-auto");
    }
  }

  function closeActivityDrawer() {
    if (outreachActivityDrawer) outreachActivityDrawer.classList.add("translate-x-full");
    if (outreachActivityBackdrop) {
      outreachActivityBackdrop.classList.add("opacity-0", "pointer-events-none");
      outreachActivityBackdrop.classList.remove("opacity-100", "pointer-events-auto");
    }
  }

  if (btnToggleActivity) btnToggleActivity.addEventListener("click", openActivityDrawer);
  if (btnCloseActivity) btnCloseActivity.addEventListener("click", closeActivityDrawer);
  if (outreachActivityBackdrop) outreachActivityBackdrop.addEventListener("click", closeActivityDrawer);

  function updateOutreachPillStyles() {
    // Update Quick Metric Cards ring highlight as primary filters
    const statCards = [
      { id: "all", el: outreachStatAll },
      { id: "emails", el: outreachStatEmails },
      { id: "ready", el: outreachStatReady },
      { id: "sent", el: outreachStatSent }
    ];
    statCards.forEach(s => {
      if (!s.el) return;
      const isActive = (s.id === outreachActiveFilter);
      if (isActive) {
        s.el.classList.add("ring-2", "ring-primary/25", "border-primary", "bg-surface-container-high", "shadow-sm");
        s.el.classList.remove("border-outline-variant/30", "bg-surface-container-low", "opacity-80");
      } else {
        s.el.classList.remove("ring-2", "ring-primary/25", "border-primary", "bg-surface-container-high", "shadow-sm");
        s.el.classList.add("border-outline-variant/30", "bg-surface-container-low", "opacity-80");
      }
    });
  }

  function setOutreachFilter(filterName) {
    outreachActiveFilter = filterName;
    outreachCurrentPage = 1;
    updateOutreachPillStyles();
    renderPitchesList();
  }

  if (outreachSearchInput) {
    let outreachDebounce = null;
    outreachSearchInput.addEventListener("input", (e) => {
      clearTimeout(outreachDebounce);
      outreachDebounce = setTimeout(() => {
        outreachSearchQuery = (e.target.value || "").trim().toLowerCase();
        outreachCurrentPage = 1;
        renderPitchesList();
      }, 200);
    });
  }

  if (outreachTechSelect) {
    outreachTechSelect.addEventListener("change", (e) => {
      outreachSelectedTech = (e.target.value || "").trim().toLowerCase();
      outreachCurrentPage = 1;
      renderPitchesList();
    });
  }

  if (outreachCitySelect) {
    outreachCitySelect.addEventListener("change", (e) => {
      outreachSelectedCity = (e.target.value || "").trim().toLowerCase();
      outreachCurrentPage = 1;
      renderPitchesList();
    });
  }

  if (btnOutreachReset) {
    btnOutreachReset.addEventListener("click", () => {
      if (outreachSearchInput) outreachSearchInput.value = "";
      if (outreachTechSelect) outreachTechSelect.value = "";
      if (outreachCitySelect) outreachCitySelect.value = "";
      outreachSearchQuery = "";
      outreachSelectedTech = "";
      outreachSelectedCity = "";
      outreachActiveFilter = "all";
      outreachCurrentPage = 1;
      updateOutreachPillStyles();
      renderPitchesList();
      showToast("Outreach filters reset to default", "info");
    });
  }

  if (btnOutreachViewGrid) {
    btnOutreachViewGrid.addEventListener("click", () => {
      outreachViewMode = "grid";
      btnOutreachViewGrid.className = "h-9 px-2.5 rounded-md text-xs font-mono flex items-center gap-1 bg-surface-container-highest text-on-surface cursor-pointer transition";
      btnOutreachViewList.className = "h-9 px-2.5 rounded-md text-xs font-mono flex items-center gap-1 text-on-surface-variant hover:text-on-surface cursor-pointer transition";
      renderPitchesList();
    });
  }

  if (btnOutreachViewList) {
    btnOutreachViewList.addEventListener("click", () => {
      outreachViewMode = "list";
      btnOutreachViewList.className = "h-9 px-2.5 rounded-md text-xs font-mono flex items-center gap-1 bg-surface-container-highest text-on-surface cursor-pointer transition";
      btnOutreachViewGrid.className = "h-9 px-2.5 rounded-md text-xs font-mono flex items-center gap-1 text-on-surface-variant hover:text-on-surface cursor-pointer transition";
      renderPitchesList();
    });
  }

  if (outreachFilterAll) outreachFilterAll.addEventListener("click", () => setOutreachFilter("all"));
  if (outreachFilterEmails) outreachFilterEmails.addEventListener("click", () => setOutreachFilter("emails"));
  if (outreachFilterReady) outreachFilterReady.addEventListener("click", () => setOutreachFilter("ready"));
  if (outreachFilterSent) outreachFilterSent.addEventListener("click", () => setOutreachFilter("sent"));

  if (outreachStatAll) outreachStatAll.addEventListener("click", () => setOutreachFilter("all"));
  if (outreachStatEmails) outreachStatEmails.addEventListener("click", () => setOutreachFilter("emails"));
  if (outreachStatReady) outreachStatReady.addEventListener("click", () => setOutreachFilter("ready"));
  if (outreachStatSent) outreachStatSent.addEventListener("click", () => setOutreachFilter("sent"));

  if (outreachPerPageSelect) {
    outreachPerPageSelect.addEventListener("change", (e) => {
      outreachPerPage = parseInt(e.target.value, 10);
      outreachCurrentPage = 1;
      renderPitchesList();
    });
  }

  window.openCompanyModalById = function(companyId) {
    const target = (companies || []).find(c => c.id === companyId);
    if (target) openCompanyDetailsModal(target);
  };

  function renderPitchesList() {
    const container = document.getElementById("pitches-container");
    const countSpan = document.getElementById("pitches-count");
    if (!container) return;
    container.innerHTML = "";

    // Set responsive grid vs compact stream layout class
    container.className = (outreachViewMode === "grid")
      ? "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5"
      : "space-y-3";

    // Base genuine leads from dedicated allOutreachCompanies pool or fallback to companies
    const sourceCompanies = (allOutreachCompanies && allOutreachCompanies.length > 0) ? allOutreachCompanies : (companies || []);
    const validCompanies = sourceCompanies.filter(c => !c.is_invalid);

    // Compute metric counts
    const totalCount = validCompanies.length;
    const emailsCount = validCompanies.filter(c => c.emails && c.emails.length > 0).length;
    const isLoggedIn = Boolean(currentUser && currentUser.is_logged_in);
    const readyCount = validCompanies.filter(c => !c.already_contacted).length;
    const sentCount = isLoggedIn ? validCompanies.filter(c => c.already_contacted).length : null;

    // Update Quick Metric Strip
    if (outreachCountTotal) outreachCountTotal.textContent = totalCount.toLocaleString();
    if (outreachCountEmails) outreachCountEmails.textContent = emailsCount.toLocaleString();
    if (outreachCountReady) outreachCountReady.textContent = readyCount.toLocaleString();
    if (outreachCountSent) {
      outreachCountSent.textContent = isLoggedIn ? sentCount.toLocaleString() : "0";
    }

    // Update filter badge counts
    document.querySelectorAll(".outreach-badge-all").forEach(el => el.textContent = totalCount);
    document.querySelectorAll(".outreach-badge-emails").forEach(el => el.textContent = emailsCount);
    document.querySelectorAll(".outreach-badge-ready").forEach(el => el.textContent = readyCount);
    document.querySelectorAll(".outreach-badge-sent").forEach(el => {
      el.textContent = isLoggedIn ? sentCount : "—";
    });

    if (totalCount === 0) {
      if (countSpan) countSpan.textContent = "0";
      container.innerHTML = `
        <div class="col-span-full bg-surface-container-low border border-outline-variant/50 rounded-xl p-10 text-center space-y-3">
          <span class="material-symbols-outlined text-[36px] text-on-surface-variant">domain</span>
          <p class="text-sm font-semibold text-on-surface">No companies available for outreach</p>
          <p class="text-xs text-on-surface-variant max-w-sm mx-auto">Scout verified businesses in Step 1 or browse your directory first.</p>
        </div>
      `;
      if (outreachPagination) outreachPagination.classList.add("hidden");
      if (outreachPaginationBottom) outreachPaginationBottom.classList.add("hidden");
      refreshIcons();
      return;
    }

    // Filter by Active Filter Tab
    let filtered = validCompanies;
    if (outreachActiveFilter === "emails") {
      filtered = filtered.filter(c => c.emails && c.emails.length > 0);
    } else if (outreachActiveFilter === "ready") {
      filtered = filtered.filter(c => !c.already_contacted);
    } else if (outreachActiveFilter === "sent") {
      filtered = filtered.filter(c => c.already_contacted);
    }

    // Filter by Tech Stack Dropdown (supports multi-select comma-separated)
    if (outreachSelectedTech) {
      const selectedTechs = outreachSelectedTech.split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
      if (selectedTechs.length > 0) {
        filtered = filtered.filter(c => {
          const stack = (c.profile && Array.isArray(c.profile.tech_stack)) ? c.profile.tech_stack : [];
          return selectedTechs.some(sel =>
            stack.some(t => typeof t === "string" && t.toLowerCase().includes(sel))
          );
        });
      }
    }

    // Filter by City Dropdown (supports multi-select comma-separated)
    if (outreachSelectedCity) {
      const selectedCities = outreachSelectedCity.split(",").map(c => c.trim().toLowerCase()).filter(Boolean);
      if (selectedCities.length > 0) {
        filtered = filtered.filter(c => {
          const compCity = (c.city || "").toLowerCase();
          const addr = (c.address || "").toLowerCase();
          const srcQuery = (c.source_query || "").toLowerCase();
          return selectedCities.some(sel =>
            compCity.includes(sel) || addr.includes(sel) || srcQuery.includes(sel)
          );
        });
      }
    }

    // Filter by Search Query
    if (outreachSearchQuery) {
      filtered = filtered.filter(c => {
        const nameMatch = c.name && c.name.toLowerCase().includes(outreachSearchQuery);
        const domainMatch = c.domain && c.domain.toLowerCase().includes(outreachSearchQuery);
        const emailMatch = c.emails && c.emails.some(e => e.toLowerCase().includes(outreachSearchQuery));
        const cityMatch = c.city && c.city.toLowerCase().includes(outreachSearchQuery);
        const techMatch = c.profile && c.profile.tech_stack && c.profile.tech_stack.some(t => typeof t === "string" && t.toLowerCase().includes(outreachSearchQuery));
        return nameMatch || domainMatch || emailMatch || cityMatch || techMatch;
      });
    }

    if (countSpan) countSpan.textContent = filtered.length.toLocaleString();

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="col-span-full bg-surface-container-low border border-outline-variant/50 rounded-xl p-10 text-center space-y-3">
          <span class="material-symbols-outlined text-[36px] text-on-surface-variant">search_off</span>
          <p class="text-sm font-semibold text-on-surface">No matching outreach targets</p>
          <p class="text-xs text-on-surface-variant max-w-sm mx-auto">Try adjusting your search query or clearing dropdown filters.</p>
        </div>
      `;
      if (outreachPagination) outreachPagination.classList.add("hidden");
      if (outreachPaginationBottom) outreachPaginationBottom.classList.add("hidden");
      refreshIcons();
      return;
    }

    // Pagination calculations
    const totalPages = outreachPerPage > 0 ? Math.ceil(filtered.length / outreachPerPage) : 1;
    if (outreachCurrentPage > totalPages) outreachCurrentPage = totalPages;
    if (outreachCurrentPage < 1) outreachCurrentPage = 1;

    let pageItems = filtered;
    if (outreachPerPage > 0) {
      const startIndex = (outreachCurrentPage - 1) * outreachPerPage;
      pageItems = filtered.slice(startIndex, startIndex + outreachPerPage);
    }

    const monoThemes = [
      { bg: "bg-surface-container-high text-on-surface border-outline-variant/60" },
      { bg: "bg-secondary/15 text-secondary border-secondary/30" },
      { bg: "bg-tertiary/15 text-tertiary border-tertiary/30" },
      { bg: "bg-surface-container-highest text-on-surface-variant border-outline-variant/60" }
    ];

    pageItems.forEach(c => {
      const card = document.createElement("div");
      const monogram = getCompanyMonogram(c.name);
      const monoIdx = Math.abs((c.name || "C").split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0)) % monoThemes.length;
      const monoTheme = monoThemes[monoIdx];

      const hasDirectEmail = Boolean(c.emails && c.emails.length > 0);
      const directEmail = hasDirectEmail ? c.emails[0] : null;

      const ratingVal = (c.rating && c.rating > 0) ? Number(c.rating).toFixed(1) : null;
      const ratingDisplay = ratingVal
        ? `<span class="text-tertiary font-semibold flex items-center gap-1 font-mono text-[11px]"><span class="material-symbols-outlined text-[13px] text-tertiary">star</span><span>${ratingVal}</span><span class="text-on-surface-variant font-normal text-[10px]">(${c.reviews_count || 0})</span></span>`
        : `<span class="text-on-surface-variant text-[10px] font-mono">No reviews</span>`;

      const statusBadge = c.already_contacted
        ? `<button type="button" onclick="window.viewSentEmailForCompany(${c.id})" class="px-2 py-0.5 rounded text-[10px] font-mono bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 font-semibold flex items-center gap-1 shrink-0 cursor-pointer transition shadow-sm" title="Click to view message sent"><span class="material-symbols-outlined text-[12px]">check_circle</span><span>Sent</span></button>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-container text-on-surface-variant border border-outline-variant/60 shrink-0">Queue</span>`;

      // Tech stack pills (Strict: only verified AI-enriched tech stack)
      let techPillsHtml = '';
      if (c.profile && Array.isArray(c.profile.tech_stack) && c.profile.tech_stack.length > 0) {
        techPillsHtml = c.profile.tech_stack.slice(0, 4).map(t => `<span class="px-2 py-0.5 rounded text-[10px] font-mono tracking-wide bg-surface-container-lowest text-on-surface-variant border border-outline-variant/40">${escapeHTML(t)}</span>`).join('');
      } else if (c.is_enriched) {
        techPillsHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-mono tracking-wide text-on-surface-variant/60 bg-surface-container-lowest/50 border border-outline-variant/30 italic">No frameworks detected</span>`;
      } else {
        techPillsHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-mono tracking-wide text-on-surface-variant/60 bg-surface-container-lowest/50 border border-outline-variant/30 italic flex items-center gap-1"><span class="material-symbols-outlined text-[12px] text-amber-500/70">hourglass_top</span><span>Stack pending AI enrichment</span></span>`;
      }

      if (outreachViewMode === "grid") {
        // Mode A: Executive Dispatch Bento Card
        card.className = "company-card group bg-surface-container-low border border-outline-variant/50 hover:border-outline hover:bg-surface-container rounded-xl p-5 flex flex-col justify-between transition-all duration-200 shadow-sm hover:shadow-lg relative min-w-0";
        card.innerHTML = `
          <div>
            <!-- Part 1: Top Monogram + Name + Domain + Status -->
            <div class="flex items-start justify-between gap-3 mb-3">
              <div class="flex items-start gap-2.5 min-w-0 flex-1">
                <div class="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-label-md ${monoTheme.bg} border shrink-0 font-mono shadow-sm">
                  ${monogram}
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-1.5">
                    <h3 class="text-headline-sm font-headline-sm text-on-surface font-semibold break-words line-clamp-2 leading-snug cursor-pointer hover:text-primary" onclick="window.openCompanyModalById(${c.id})" title="${escapeHTML(c.name)}">${escapeHTML(c.name)}</h3>
                    <a class="text-on-surface-variant hover:text-primary transition-colors shrink-0 mt-0.5" href="${c.website_url || 'https://' + c.domain}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" title="Visit website">
                      <span class="material-symbols-outlined text-[14px]">open_in_new</span>
                    </a>
                  </div>
                  <div class="flex items-center gap-2 mt-1">
                    <span class="text-caption font-mono text-on-surface-variant truncate block">${escapeHTML(c.domain || '')}</span>
                    ${c.city ? `<span class="text-on-surface-variant font-mono text-[11px] flex items-center gap-0.5 shrink-0"><span class="material-symbols-outlined text-[12px]">location_on</span>${escapeHTML(c.city)}</span>` : ''}
                  </div>
                </div>
              </div>
              <div class="shrink-0 pt-0.5">
                ${statusBadge}
              </div>
            </div>

            <!-- Part 2: Recipient Email Well -->
            ${hasDirectEmail ? `
              <div class="bg-surface-container-lowest border border-outline-variant/40 rounded-lg p-2.5 mb-3 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="material-symbols-outlined text-[15px] text-secondary shrink-0">
                    alternate_email
                  </span>
                  <div class="min-w-0">
                    <span class="text-[10px] font-mono uppercase tracking-wider block text-secondary font-semibold">
                      Verified Direct Email
                    </span>
                    <span class="font-mono text-xs text-on-surface font-semibold truncate block">
                      ${escapeHTML(directEmail)}
                    </span>
                  </div>
                </div>
                <button type="button" class="btn-copy-email p-1.5 rounded hover:bg-surface-container text-on-surface-variant hover:text-on-surface transition shrink-0 cursor-pointer" data-email="${escapeHTML(directEmail)}" title="Copy email address">
                  <span class="material-symbols-outlined text-[15px]">content_copy</span>
                </button>
              </div>
            ` : `
              <div class="bg-surface-container-lowest/70 border border-dashed border-amber-500/30 rounded-lg p-2.5 mb-3 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="material-symbols-outlined text-[15px] text-amber-500 shrink-0">
                    mail_off
                  </span>
                  <div class="min-w-0">
                    <span class="text-[10px] font-mono uppercase tracking-wider block text-amber-500 font-semibold">
                      Email Not Found
                    </span>
                    <span class="font-mono text-xs text-on-surface-variant italic truncate block">
                      No verified recruiter email discovered
                    </span>
                  </div>
                </div>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-500 border border-amber-500/20 font-medium">Unreachable</span>
              </div>
            `}

            <!-- Part 3: Detected Tech Stack Chips & Rating -->
            <div class="space-y-1.5 mb-4">
              <div class="flex items-center justify-between text-[10px] font-mono text-on-surface-variant">
                <span>${(c.profile && Array.isArray(c.profile.tech_stack) && c.profile.tech_stack.length > 0) ? 'DETECTED TECH STACK' : 'INTELLIGENCE STATUS'}</span>
                ${ratingDisplay}
              </div>
              <div class="flex flex-wrap gap-1.5">
                ${techPillsHtml}
              </div>
            </div>
          </div>

          <!-- Part 4: Bottom Tactile Actions -->
          <div class="pt-3 border-t border-outline-variant/40 flex items-center justify-between gap-2">
            <button type="button" class="btn-view-intel-row btn-tactile-slate px-3 py-1.5 rounded-lg text-xs font-mono font-medium flex items-center gap-1.5 transition cursor-pointer shadow-sm text-on-surface" data-id="${c.id}" title="Inspect full intelligence profile">
              <span class="material-symbols-outlined text-[15px]">visibility</span>
              <span>View Intel</span>
            </button>
            <div class="flex items-center gap-2">
              ${c.already_contacted ? `
                <button type="button" onclick="window.viewSentEmailForCompany(${c.id})" class="btn-tactile-slate px-3 py-1.5 rounded text-xs font-mono font-medium transition flex items-center gap-1 cursor-pointer">
                  <span class="material-symbols-outlined text-[14px]">history</span>
                  <span>Sent Log</span>
                </button>
              ` : `
                <button type="button" class="btn-gen-pitch-row btn-card-pitch px-3.5 py-1.5 rounded text-xs font-headline font-semibold transition flex items-center gap-1.5 cursor-pointer shadow-sm" data-id="${c.id}">
                  <span class="material-symbols-outlined text-[15px]">send</span>
                  <span>Review & Send</span>
                </button>
              `}
            </div>
          </div>
        `;
      } else {
        // Mode B: Streamlined Compact Row
        card.className = "company-card group bg-surface-container-low border border-outline-variant/50 hover:border-outline hover:bg-surface-container rounded-xl p-4 transition-all duration-150 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-sm min-w-0";
        card.innerHTML = `
          <div class="flex items-center gap-3 min-w-0 flex-1">
            <div class="w-9 h-9 rounded-md flex items-center justify-center font-bold text-xs ${monoTheme.bg} border shrink-0 font-mono shadow-sm">
              ${monogram}
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <h4 class="font-semibold text-sm text-on-surface break-words cursor-pointer hover:text-primary" onclick="window.openCompanyModalById(${c.id})">${escapeHTML(c.name)}</h4>
                ${statusBadge}
                ${hasDirectEmail ? `
                  <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary/15 text-secondary border border-secondary/30 font-semibold">
                    @ Direct Recruiter
                  </span>
                ` : `
                  <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 font-semibold flex items-center gap-1">
                    <span class="material-symbols-outlined text-[12px]">mail_off</span>
                    <span>Email Not Found</span>
                  </span>
                `}
              </div>
              <div class="flex items-center gap-2 text-xs font-mono text-on-surface-variant mt-0.5 flex-wrap">
                ${hasDirectEmail ? `
                  <span class="text-on-surface font-medium">${escapeHTML(directEmail)}</span>
                ` : `
                  <span class="text-amber-500 font-medium italic">Email not found</span>
                `}
                <span class="text-outline-variant">|</span>
                <span class="text-on-surface-variant">${escapeHTML(c.domain || '')}</span>
                ${c.city ? `<span class="text-outline-variant">|</span><span class="text-on-surface-variant flex items-center gap-0.5"><span class="material-symbols-outlined text-[12px]">location_on</span>${escapeHTML(c.city)}</span>` : ''}
              </div>
            </div>
          </div>

          <div class="flex items-center gap-2 shrink-0 pt-2 md:pt-0">
            <button type="button" class="btn-view-intel-row text-xs font-mono text-on-surface-variant hover:text-on-surface flex items-center gap-1 transition cursor-pointer px-2.5 py-1.5 rounded hover:bg-surface-container" data-id="${c.id}">
              <span class="material-symbols-outlined text-[15px]">visibility</span>
              <span class="hidden sm:inline">Intel</span>
            </button>
            ${c.already_contacted ? `
              <button type="button" onclick="window.viewSentEmailForCompany(${c.id})" class="btn-tactile-slate px-3 py-1.5 rounded text-xs font-mono font-medium transition flex items-center gap-1 cursor-pointer">
                <span class="material-symbols-outlined text-[14px]">history</span>
                <span>Sent</span>
              </button>
            ` : `
              <button type="button" class="btn-gen-pitch-row btn-card-pitch px-3.5 py-1.5 rounded text-xs font-headline font-semibold transition flex items-center gap-1.5 cursor-pointer shadow-sm" data-id="${c.id}">
                <span class="material-symbols-outlined text-[15px]">send</span>
                <span>Review & Send</span>
              </button>
            `}
          </div>
        `;
      }

      // Event listeners for card buttons
      const btnPitch = card.querySelector(".btn-gen-pitch-row");
      if (btnPitch) {
        btnPitch.addEventListener("click", (e) => {
          e.stopPropagation();
          handleGeneratePitch(c.id);
        });
      }

      const btnIntel = card.querySelector(".btn-view-intel-row");
      if (btnIntel) {
        btnIntel.addEventListener("click", (e) => {
          e.stopPropagation();
          openCompanyDetailsModal(c);
        });
      }

      const btnCopy = card.querySelector(".btn-copy-email");
      if (btnCopy) {
        btnCopy.addEventListener("click", (e) => {
          e.stopPropagation();
          const em = btnCopy.dataset.email;
          navigator.clipboard.writeText(em);
          btnCopy.innerHTML = `<span class="material-symbols-outlined text-[15px] text-[#86B29B]">check</span>`;
          setTimeout(() => {
            btnCopy.innerHTML = `<span class="material-symbols-outlined text-[15px]">content_copy</span>`;
          }, 1500);
        });
      }

      container.appendChild(card);
    });

    // Render pagination controls (top and bottom)
    const handleOutreachPageChange = (newPage) => {
      outreachCurrentPage = newPage;
      renderPitchesList();
      if (container) container.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    renderPaginationControls({
      paginationEl: outreachPagination,
      rangeEl: outreachPageRange,
      totalEl: outreachPageTotal,
      buttonsEl: outreachPageButtons,
      totalItems: filtered.length,
      currentPage: outreachCurrentPage,
      pageSize: outreachPerPage,
      onPageChange: handleOutreachPageChange
    });

    renderPaginationControls({
      paginationEl: outreachPaginationBottom,
      rangeEl: outreachPageRangeBottom,
      totalEl: outreachPageTotalBottom,
      buttonsEl: outreachPageButtonsBottom,
      totalItems: filtered.length,
      currentPage: outreachCurrentPage,
      pageSize: outreachPerPage,
      onPageChange: handleOutreachPageChange
    });

    refreshIcons();
  }

  // ==========================================
  // SENT EMAIL DETAILS MODAL
  // ==========================================
  const sentEmailModal = document.getElementById("sent-email-modal");
  const sentModalClose = document.getElementById("sent-modal-close");
  const btnCloseSentEmail = document.getElementById("btn-close-sent-email");
  const btnCopySentEmail = document.getElementById("btn-copy-sent-email");
  const sentModalMethod = document.getElementById("sent-modal-method");
  const sentModalCompanyName = document.getElementById("sent-modal-company-name");
  const sentModalRecipient = document.getElementById("sent-modal-recipient");
  const sentModalDate = document.getElementById("sent-modal-date");
  const sentModalSubject = document.getElementById("sent-modal-subject");
  const sentModalBody = document.getElementById("sent-modal-body");

  function openSentEmailModal(data) {
    if (!sentEmailModal) return;
    if (sentModalMethod) sentModalMethod.textContent = (data.delivery_method || "SENT").toUpperCase();
    if (sentModalCompanyName) sentModalCompanyName.textContent = data.company_name || "Company";
    if (sentModalRecipient) sentModalRecipient.textContent = data.recipient_email || "N/A";
    if (sentModalDate) sentModalDate.textContent = data.sent_at || "Recent";
    if (sentModalSubject) sentModalSubject.textContent = data.subject || "No subject";
    if (sentModalBody) sentModalBody.textContent = data.email_body || "(No message body logged for this outreach.)";
    sentEmailModal.classList.remove("hidden");
    refreshIcons();
  }

  function closeSentEmailModal() {
    if (sentEmailModal) sentEmailModal.classList.add("hidden");
  }

  if (sentModalClose) sentModalClose.addEventListener("click", closeSentEmailModal);
  if (btnCloseSentEmail) btnCloseSentEmail.addEventListener("click", closeSentEmailModal);
  if (sentEmailModal) {
    sentEmailModal.addEventListener("click", (e) => {
      if (e.target === sentEmailModal) closeSentEmailModal();
    });
  }

  if (btnCopySentEmail) {
    btnCopySentEmail.addEventListener("click", () => {
      const textToCopy = `Subject: ${sentModalSubject?.textContent || ''}\n\n${sentModalBody?.textContent || ''}`;
      navigator.clipboard.writeText(textToCopy);
      const originalHTML = btnCopySentEmail.innerHTML;
      btnCopySentEmail.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span>Copied!</span>`;
      refreshIcons();
      setTimeout(() => {
        btnCopySentEmail.innerHTML = originalHTML;
        refreshIcons();
      }, 2000);
    });
  }

  async function viewSentEmailForCompany(companyId) {
    try {
      const res = await fetch(`/api/outreach/sent/${companyId}`);
      if (res.status === 401) {
        showLoginModal();
        return;
      }
      const data = await res.json();
      if (data.found) {
        openSentEmailModal(data);
      } else {
        showToast("No sent outreach record found for this company.", "warning");
      }
    } catch (err) {
      showToast("Failed to load sent email details: " + err.message, "error");
    }
  }

  window.viewSentEmailForCompany = viewSentEmailForCompany;

  async function fetchAuditLogs() {
    try {
      const res = await fetch("/api/outreach/logs");
      if (res.status === 401) {
        const logsContainer = document.getElementById("audit-logs");
        if (logsContainer) {
          logsContainer.innerHTML = `<p class="text-outline italic text-caption py-4 text-center">Sign in to view your sent outreach history.</p>`;
        }
        return;
      }
      const data = await res.json();
      const logsContainer = document.getElementById("audit-logs");
      if (!logsContainer) return;
      if (!data.logs || data.logs.length === 0) {
        logsContainer.innerHTML = `<p class="text-outline italic text-caption py-4 text-center">No emails sent yet today.</p>`;
        return;
      }

      window._cachedAuditLogs = data.logs;

      logsContainer.innerHTML = data.logs.map((l, idx) => `
        <div onclick="window._openCachedLog(${idx})" class="bg-surface-container border border-outline-variant/40 hover:border-outline-variant/80 rounded-lg p-3 space-y-1.5 transition cursor-pointer group shadow-sm" title="Click to view message sent">
          <div class="flex items-center justify-between gap-2">
            <span class="font-bold text-on-surface group-hover:text-primary transition truncate text-body-sm">${escapeHTML(l.company_name)}</span>
            <span class="text-[10px] font-mono text-secondary font-semibold uppercase bg-secondary/15 border border-secondary/30 px-1.5 py-0.5 rounded shrink-0">${escapeHTML(l.delivery_method)}</span>
          </div>
          <p class="text-caption font-mono text-on-surface-variant truncate">To: ${escapeHTML(l.recipient_email)}</p>
          <div class="flex items-center justify-between text-[11px] font-mono text-outline pt-0.5">
            <span>${escapeHTML(l.sent_at)}</span>
            <span class="text-primary group-hover:underline font-medium flex items-center space-x-0.5 text-caption">
              <span>View message</span>
              <i data-lucide="chevron-right" class="w-3 h-3"></i>
            </span>
          </div>
        </div>
      `).join("");
      refreshIcons();
    } catch (err) {
      console.error("Failed to load audit logs:", err);
    }
  }

  window._openCachedLog = function(idx) {
    if (window._cachedAuditLogs && window._cachedAuditLogs[idx]) {
      openSentEmailModal(window._cachedAuditLogs[idx]);
    }
  };

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

  document.querySelectorAll("#btn-theme-toggle, #btn-theme-toggle-mobile").forEach(btn => {
    btn.addEventListener("click", toggleThemeMode);
  });

  // Sync initial theme icons based on current html class
  const initialTheme = document.documentElement.classList.contains("light") ? "light" : "dark";
  updateThemeIcons(initialTheme);

  // Dynamic system theme listener (auto-switches if user has not set an explicit override in localStorage)
  const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)");
  if (systemPrefersDark && systemPrefersDark.addEventListener) {
    systemPrefersDark.addEventListener("change", (e) => {
      const savedTheme = localStorage.getItem("pilot_theme");
      if (!savedTheme) {
        const autoTheme = e.matches ? "dark" : "light";
        if (autoTheme === "light") {
          document.documentElement.classList.remove("dark");
          document.documentElement.classList.add("light");
        } else {
          document.documentElement.classList.remove("light");
          document.documentElement.classList.add("dark");
        }
        updateThemeIcons(autoTheme);
        refreshIcons();
      }
    });
  }

  // Initial Data Load & Render Lucide Icons
  refreshIcons();
  checkAuthStatus();
  loadCandidateProfile();
  fetchCompanies();
  fetchAuditLogs();
});

