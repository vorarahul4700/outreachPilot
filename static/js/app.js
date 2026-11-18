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

  // Expose globally for modular usage
  window.showToast = showToast;
  window.handleHttpError = handleHttpError;

  function switchTab(tabId) {
    const navItems = [
      { id: "companies", btn: tabCompanies, sec: secCompanies },
      { id: "resume", btn: tabResume, sec: secResume },
      { id: "outreach", btn: tabOutreach, sec: secOutreach }
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

    if (tabId === "companies") {
      applyCompanyFiltersAndRender();
    } else if (tabId === "outreach") {
      if (!outreachLoaded || allOutreachCompanies.length === 0) {
        fetchOutreachCompanies(false);
      } else {
        renderPitchesList();
      }
      fetchAuditLogs();
    } else if (tabId === "resume") {
      loadCandidateProfile();
    }
    activeTab = tabId;
    refreshIcons();
  }

  if (tabCompanies) tabCompanies.addEventListener("click", () => switchTab("companies"));
  if (tabResume) tabResume.addEventListener("click", () => switchTab("resume"));
  if (tabOutreach) tabOutreach.addEventListener("click", () => switchTab("outreach"));

  // Header quick actions
  const btnHeaderRefresh = document.getElementById("btn-header-refresh");
  if (btnHeaderRefresh) btnHeaderRefresh.addEventListener("click", () => fetchCompanies());

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
    } else {
      appSidebar?.classList.remove("mobile-open");
      mobileSidebarOverlay?.classList.remove("active");
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

  // Multi-Selection and Bulk Lead Management removed from /app (Shifted strictly to Master Admin Panel /admin)
  const selectedCompanyIds = new Set();
  const companiesContainer = document.getElementById("companies-container");
  function updateBulkActionBar() {}
  function updateSelectAllCheckboxState() {}

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
  let companiesPerPage = 24; // multiples of 6 keep 2- and 3-column grids full
  let currentFilteredCompanies = [];
  const companyDetailCache = new Map();

  // Scout Leads Pagination State & Elements
  const scoutPagination = document.getElementById("scout-pagination");
  const scoutPageRange = document.getElementById("scout-page-range");
  const scoutPageTotal = document.getElementById("scout-page-total");
  const scoutPerPageSelect = document.getElementById("scout-per-page");
  const scoutPageButtons = document.getElementById("scout-page-buttons");
  let scoutCurrentPage = 1;
  let scoutPerPage = 24;
  let currentScoutList = [];
  let currentScoutQueryLabel = "";
  let liveScrapedResults = [];

  // Outreach Hub Pagination & Pipeline State
  let outreachLoaded = false;
  let allOutreachCompanies = [];
  let isOutreachLoading = false;
  let outreachCurrentPage = 1;
  let outreachPerPage = 24;

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
    if (scoutQueryLabel) scoutQueryLabel.textContent = queryLabel || '-';

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
        ? `<span class="text-on-surface-variant font-semibold flex items-center space-x-1 font-mono text-[11px]">
             <span class="material-symbols-outlined text-[12px] text-on-surface-variant">star</span><span class="text-on-surface">${Number(c.rating).toFixed(1)}</span>
             <span class="text-on-surface-variant font-normal text-[10px]">Google (${c.reviews_count || 0})</span>
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
                  <span class="material-symbols-outlined text-[13px] text-on-surface-variant">star</span>
                  <span class="font-semibold text-on-surface">${ratingVal}</span>
                  <span class="text-on-surface-variant">Google (${c.reviews_count || 0})</span>
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
    if (!scoutCardsContainer) return;
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
      renderScoutResults([], queryTag ? `Ready to Search: ${queryTag}` : "-");
    }
  }

  let scoutInputTimer = null;
  if (inputKeyword) {
    inputKeyword.addEventListener("input", () => {
      clearTimeout(scoutInputTimer);
      scoutInputTimer = setTimeout(updateScoutViewFromInputs, 350);
    });
    inputKeyword.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(scoutInputTimer);
        updateScoutViewFromInputs();
      }
    });
  }
  if (inputCity) {
    inputCity.addEventListener("input", () => {
      clearTimeout(scoutInputTimer);
      scoutInputTimer = setTimeout(updateScoutViewFromInputs, 350);
    });
    inputCity.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(scoutInputTimer);
        updateScoutViewFromInputs();
      }
    });
  }

  // Close modals on Escape key press
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      cmodal?.classList.add("hidden");
      modal?.classList.add("hidden");
      loginModal?.classList.add("hidden");
      document.getElementById("resume-confirm-modal")?.classList.add("hidden");
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
      if (totalCountEl) totalCountEl.textContent = fmtNum(total);

      const navBadgeEl = document.getElementById("nav-companies-badge");
      if (navBadgeEl) navBadgeEl.textContent = fmtNum(total);

      const headerCounter = document.getElementById("header-leads-counter");
      if (headerCounter) headerCounter.textContent = fmtNum(total);

      document.querySelectorAll(".badge-total-count").forEach(el => el.textContent = fmtNum(total));

      const statEnriched = document.getElementById("stat-enriched-count");
      if (statEnriched) statEnriched.textContent = fmtNum(enriched);

      const statEmails = document.getElementById("stat-emails-count");
      if (statEmails) statEmails.textContent = fmtNum(withEmails);

      const badgeEmails = document.getElementById("badge-emails-count");
      if (badgeEmails) badgeEmails.textContent = fmtNum(withEmails);

      // Contacted / Pitched Stat Card (STRICT: only visible if user is logged in and only for this user)
      const statContacted = document.getElementById("stat-contacted-count");
      const statContactedBadge = document.getElementById("stat-contacted-badge");
      const statContactedText = document.getElementById("stat-contacted-text");

      if (statContacted && statContactedBadge && statContactedText) {
        if (!isLoggedIn) {
          statContacted.textContent = "0";
          statContactedBadge.textContent = "Sign in";
          statContactedBadge.className = "mini-badge";
          statContactedText.textContent = "Sign in to track sent emails";
        } else {
          const userContacted = contacted !== null ? contacted : 0;
          statContacted.textContent = fmtNum(userContacted);
          if (userContacted === 0) {
            statContactedBadge.textContent = "0% reached";
            statContactedBadge.className = "mini-badge";
            statContactedText.textContent = "No emails sent yet";
          } else {
            const responseRatePct = total > 0 ? Math.round((userContacted / total) * 100) : 0;
            statContactedBadge.textContent = `${responseRatePct}% reached`;
            statContactedBadge.className = "mini-badge accent";
            statContactedText.textContent = `${fmtNum(userContacted)} of ${fmtNum(total)} contacted`;
          }
        }
      }

      const statEmailsTotal = document.getElementById("stat-emails-total");
      if (statEmailsTotal) statEmailsTotal.textContent = fmtNum(total);

      const statYield = document.getElementById("stat-yield-text");
      if (statYield) {
        const yieldPct = total > 0 ? Math.round((withEmails / total) * 100) : 0;
        statYield.textContent = `${yieldPct}% have an email`;
      }

      const pillAll = document.getElementById("pill-count-all");
      if (pillAll) pillAll.textContent = fmtNum(total);
      const pillResearched = document.getElementById("pill-count-researched");
      if (pillResearched) pillResearched.textContent = fmtNum(enriched);
      const pillPitched = document.getElementById("pill-count-pitched");
      if (pillPitched) {
        pillPitched.textContent = (isLoggedIn && contacted !== null) ? fmtNum(contacted) : "0";
      }
      const pillExcluded = document.getElementById("pill-count-excluded");
      if (pillExcluded) pillExcluded.textContent = fmtNum(invalid);

      if (statInvalidCount) statInvalidCount.textContent = fmtNum(invalid);

      // Outreach Hub Quick Metric Strip & Badges (Globally synchronized from server stats)
      const outreachTotalEl = document.getElementById("outreach-count-total");
      if (outreachTotalEl) outreachTotalEl.textContent = total.toLocaleString();

      const outreachEmailsEl = document.getElementById("outreach-count-emails");
      if (outreachEmailsEl) outreachEmailsEl.textContent = withEmails.toLocaleString();

      const userContactedCount = (isLoggedIn && contacted !== null) ? contacted : 0;
      const outreachReadyEl = document.getElementById("outreach-count-ready");
      if (outreachReadyEl) outreachReadyEl.textContent = Math.max(0, withEmails - userContactedCount).toLocaleString();

      const outreachSentEl = document.getElementById("outreach-count-sent");
      if (outreachSentEl) outreachSentEl.textContent = isLoggedIn ? userContactedCount.toLocaleString() : "0";

      document.querySelectorAll(".outreach-badge-all").forEach(el => el.textContent = fmtNum(total));
      document.querySelectorAll(".outreach-badge-emails").forEach(el => el.textContent = fmtNum(withEmails));
      document.querySelectorAll(".outreach-badge-ready").forEach(el => el.textContent = fmtNum(Math.max(0, withEmails - userContactedCount)));
      document.querySelectorAll(".outreach-badge-sent").forEach(el => {
        el.textContent = isLoggedIn ? fmtNum(userContactedCount) : "-";
      });
    } else if (Array.isArray(statsOrList)) {
      const validList = statsOrList.filter(c => !c.is_invalid);
      const total = validList.length;
      const enriched = validList.filter(c => c.is_enriched).length;
      const withEmails = validList.filter(c => c.emails && c.emails.length > 0).length;
      const contacted = isLoggedIn ? validList.filter(c => c.already_contacted).length : null;

      const totalCountEl = document.getElementById("companies-total-count");
      if (totalCountEl) totalCountEl.textContent = fmtNum(total);
      const statEnriched = document.getElementById("stat-enriched-count");
      if (statEnriched) statEnriched.textContent = fmtNum(enriched);
      const statEmails = document.getElementById("stat-emails-count");
      if (statEmails) statEmails.textContent = fmtNum(withEmails);
      const statContacted = document.getElementById("stat-contacted-count");
      if (statContacted) {
        statContacted.textContent = isLoggedIn ? fmtNum(contacted ?? 0) : "0";
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
      <div class="skeleton-shimmer sk-card" aria-hidden="true">
        <div class="sk-row"><span class="sk" style="width:42px;height:42px;border-radius:13px"></span><span class="sk-col"><span class="sk" style="height:16px;width:70%"></span><span class="sk" style="height:11px;width:45%"></span></span></div>
        <div class="sk-col"><span class="sk" style="height:11px"></span><span class="sk" style="height:11px;width:80%"></span></div>
        <div class="flex gap-1.5"><span class="sk" style="height:24px;width:64px;border-radius:99px"></span><span class="sk" style="height:24px;width:80px;border-radius:99px"></span></div>
        <div class="flex gap-2"><span class="sk" style="height:36px;flex:1;border-radius:99px"></span><span class="sk" style="height:36px;flex:1;border-radius:99px"></span></div>
      </div>
    `).join('');
  }

  let filterDebounceTimer = null;
  function applyCompanyFiltersAndRender(resetPage = false) {
    const shouldReset = resetPage === true || (resetPage && typeof resetPage !== "object");
    if (shouldReset) {
      companiesCurrentPage = 1;
    }
    clearTimeout(filterDebounceTimer);
    filterDebounceTimer = setTimeout(() => {
      fetchCompanies(!shouldReset);
    }, 400);
  }

  const btnResetFilters = document.getElementById("btn-reset-filters");
  if (btnResetFilters) {
    btnResetFilters.addEventListener("click", () => {
      if (filterInput) filterInput.value = "";
      if (filterTechSelect) filterTechSelect.value = "";
      if (filterCitySelect) filterCitySelect.value = "";
      if (ddFilterTech) ddFilterTech.reset();
      if (ddFilterCity) ddFilterCity.reset();
      updateCityDropdownOptions("all");
      activeMetricFilter = null;
      activeDomainFilter = "all";
      const domainPillContainer = document.getElementById("companies-domain-filter-pills");
      if (domainPillContainer) {
        domainPillContainer.querySelectorAll(".domain-filter-pill").forEach(p => {
          if ((p.getAttribute("data-domain") || "all") === "all") {
            p.classList.remove("border-outline-variant/40", "bg-surface-container", "text-on-surface-variant");
            p.classList.add("active", "border-secondary", "bg-secondary/15", "text-primary", "font-semibold");
          } else {
            p.classList.remove("active", "border-secondary", "bg-secondary/15", "text-primary", "font-semibold");
            p.classList.add("border-outline-variant/40", "bg-surface-container", "text-on-surface-variant");
          }
        });
      }
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
      fetchOutreachCompanies(false);
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
      fetchOutreachCompanies(false);
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
      { value: "0", label: "All Available Pages" }
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
    defaultLabel: "24",
    onSelect: (val) => {
      companiesPerPage = parseInt(val, 10);
      companiesCurrentPage = 1;
      fetchCompanies();
    }
  });
  if (ddCompaniesPerPage) {
    ddCompaniesPerPage.setOptions([
      { value: "12", label: "12" },
      { value: "24", label: "24" },
      { value: "48", label: "48" },
      { value: "96", label: "96" },
      { value: "192", label: "192" }
    ]);
  }

  const ddOutreachPerPage = initCustomDropdown({
    containerId: "dropdown-outreach-per-page",
    inputId: "outreach-per-page",
    defaultLabel: "24",
    onSelect: (val) => {
      outreachPerPage = parseInt(val, 10);
      outreachCurrentPage = 1;
      fetchOutreachCompanies(false);
    }
  });
  if (ddOutreachPerPage) {
    ddOutreachPerPage.setOptions([
      { value: "12", label: "12" },
      { value: "24", label: "24" },
      { value: "48", label: "48" },
      { value: "96", label: "96" },
      { value: "192", label: "192" }
    ]);
  }

  const ddScoutPerPage = initCustomDropdown({
    containerId: "dropdown-scout-per-page",
    inputId: "scout-per-page",
    defaultLabel: "24",
    onSelect: (val) => {
      scoutPerPage = parseInt(val, 10);
      scoutCurrentPage = 1;
      renderScoutResults(currentScoutList, currentScoutQueryLabel);
    }
  });
  if (ddScoutPerPage) {
    ddScoutPerPage.setOptions([
      { value: "12", label: "12" },
      { value: "24", label: "24" },
      { value: "48", label: "48" },
      { value: "96", label: "96" },
      { value: "192", label: "192" }
    ]);
  }

  if (filterTechSelect) {
    filterTechSelect.addEventListener("change", () => applyCompanyFiltersAndRender(true));
  }

  if (filterCitySelect) {
    filterCitySelect.addEventListener("change", () => applyCompanyFiltersAndRender(true));
  }

  // Domain quick-filter pills in Company directory section (Delegated click event)
  let activeDomainFilter = "all";
  let globalStats = null;
  let domainsData = [];
  let cachedCitiesData = [];

  function updateCityDropdownOptions(domainCode = "all") {
    if (!cachedCitiesData || !cachedCitiesData.length) return;
    const dom = (domainCode || "all").toLowerCase().trim();
    const cityOpts = [{ value: "", label: "All Cities", count: null }];

    const mapped = cachedCitiesData.map(c => {
      let cnt = c.count;
      if (c.domain_counts) {
        cnt = c.domain_counts[dom] !== undefined ? c.domain_counts[dom] : (dom === "all" ? c.count : 0);
      }
      return { value: c.slug || (c.name || "").toLowerCase(), label: c.name, count: cnt };
    });

    // ALL cities dropdown will ALWAYS be in alphabetical order (A to Z)
    mapped.sort((a, b) => (a.label || "").localeCompare(b.label || "", undefined, { sensitivity: "base" }));

    mapped.forEach(item => cityOpts.push(item));

    if (ddFilterCity) ddFilterCity.setOptions(cityOpts);
    if (ddOutreachCity) ddOutreachCity.setOptions(cityOpts);
  }

  const DOMAIN_DISPLAY_NAMES = {
    all: "All Domains",
    it: "Information Technology & Software",
    sales: "Sales & Business Development",
    marketing: "Marketing, Advertising & PR",
    pharma: "Pharmaceuticals & Healthcare",
    finance: "Finance, Accounting & Legal",
    manufacturing: "Manufacturing & Logistics",
    realestate: "Real Estate & Construction",
    hr: "HR, Staffing & Consulting"
  };

  function updateHeaderSubtitle(domainCode, totalCount) {
    const subtitleEl = document.getElementById("header-leads-subtitle");
    const countEl = document.getElementById("header-leads-counter");
    if (countEl) countEl.textContent = Number(totalCount || 0).toLocaleString();
    if (subtitleEl) {
      if (!domainCode || domainCode === "all") {
        subtitleEl.innerHTML = `Manage and engage with <span id="header-leads-counter">${Number(totalCount || 0).toLocaleString()}</span> verified prospective companies.`;
      } else {
        const domName = DOMAIN_DISPLAY_NAMES[domainCode] || domainCode.toUpperCase();
        subtitleEl.innerHTML = `Manage and engage with <span id="header-leads-counter">${Number(totalCount || 0).toLocaleString()}</span> verified prospective companies in ${domName}.`;
      }
    }
  }

  function setDomainFilter(domainCode = "all") {
    activeDomainFilter = (domainCode || "all").toLowerCase().trim();
    const pillContainer = document.getElementById("companies-domain-filter-pills");
    if (pillContainer) {
      const pills = pillContainer.querySelectorAll(".domain-filter-pill");
      pills.forEach(p => {
        const pDom = (p.getAttribute("data-domain") || "all").toLowerCase().trim();
        if (pDom === activeDomainFilter) {
          p.classList.remove("border-outline-variant/40", "bg-surface-container", "text-on-surface-variant");
          p.classList.add("active", "border-secondary", "bg-secondary/15", "text-primary", "font-semibold");
        } else {
          p.classList.remove("active", "border-secondary", "bg-secondary/15", "text-primary", "font-semibold");
          p.classList.add("border-outline-variant/40", "bg-surface-container", "text-on-surface-variant");
        }
      });
    }

    // Instantly update the metric cards above based on selected domain
    if (activeDomainFilter === "all") {
      if (globalStats) {
        updateCompanyMetrics(globalStats);
      }
      if (globalStats) updateHeaderSubtitle("all", globalStats.total);
    } else {
      const domItem = domainsData.find(d => d.code === activeDomainFilter);
      const domCount = domItem ? (domItem.count || 0) : 0;
      const domEnriched = domItem ? (domItem.enriched_count || 0) : 0;
      const domEmails = domItem ? (domItem.emails_count || 0) : 0;

      updateCompanyMetrics({
        total: domCount,
        enriched: domEnriched,
        emails: domEmails,
        contacted: (activeDomainFilter === "it" && globalStats) ? globalStats.contacted : 0,
        invalid: (activeDomainFilter === "it" && globalStats) ? globalStats.invalid : 0,
        is_logged_in: globalStats ? globalStats.is_logged_in : false
      });
      updateHeaderSubtitle(activeDomainFilter, domCount);
    }

    // Dynamically update city dropdown options and counts for active domain
    updateCityDropdownOptions(activeDomainFilter);

    fetchCompanies(false);
  }

  const domainPillContainer = document.getElementById("companies-domain-filter-pills");
  if (domainPillContainer) {
    domainPillContainer.addEventListener("click", (e) => {
      const pill = e.target.closest(".domain-filter-pill");
      if (!pill) return;
      e.preventDefault();
      const domainCode = pill.getAttribute("data-domain") || "all";
      setDomainFilter(domainCode);
    });
  }

  // Scout Industry Domain quick-fill chips (Delegated click event)
  const scoutChipsContainer = document.getElementById("scout-domain-chips");
  if (scoutChipsContainer) {
    scoutChipsContainer.addEventListener("click", (e) => {
      const chip = e.target.closest(".scout-chip");
      if (!chip) return;
      e.preventDefault();
      const inputKw = document.getElementById("input-keyword");
      if (inputKw) {
        inputKw.value = chip.getAttribute("data-keyword") || "";
        inputKw.focus();
      }
    });
  }

  if (btnFilterEmails) {
    btnFilterEmails.addEventListener("click", () => {
      setActiveMetricFilter("emails");
    });
  }

  let totalServerCount = 0;
  let totalServerPages = 1;

  let filterOptionsLoaded = false;
  let filterFetchAbortController = null;
  let lastFilterFetchKey = "";

  // Fetch dynamic, interdependent filter options (Tech Stacks, Cities, Domains with reactive counts) from backend
  async function fetchCompaniesFilters(opts = {}) {
    const context = opts.context || "companies"; // "companies" or "outreach"
    const isOutreach = context === "outreach";

    const domain = opts.domain !== undefined ? opts.domain : (isOutreach ? "" : (activeDomainFilter || "all"));
    const city = opts.city !== undefined ? opts.city : (isOutreach ? (outreachCitySelect?.value || outreachSelectedCity || "") : (filterCitySelect?.value || ""));
    const tech = opts.tech !== undefined ? opts.tech : (isOutreach ? (outreachTechSelect?.value || outreachSelectedTech || "") : (filterTechSelect?.value || ""));
    const status = opts.status !== undefined ? opts.status : (isOutreach ? (outreachActiveFilter || "all") : (activeMetricFilter || "all"));
    const search = opts.search !== undefined ? opts.search : (isOutreach ? (outreachSearchInput?.value || outreachSearchQuery || "") : (filterInput?.value || ""));

    const filterKey = `${context}|${domain}|${city}|${tech}|${status}|${search}`;
    if (filterKey === lastFilterFetchKey && filterOptionsLoaded) return;

    if (filterFetchAbortController) {
      try { filterFetchAbortController.abort(); } catch (_) {}
    }
    filterFetchAbortController = new AbortController();
    const signal = filterFetchAbortController.signal;

    try {
      const qParams = new URLSearchParams({
        domain: (domain && domain !== "all") ? domain : "",
        city: city || "",
        tech: tech || "",
        status: status || "all",
        search: search || ""
      });

      const res = await fetch(`/api/companies/filters?${qParams.toString()}`, { signal });
      if (!res.ok) return;
      const data = await res.json();
      lastFilterFetchKey = filterKey;
      filterOptionsLoaded = true;

      // 1. Reactive Tech Options
      if (data.tech_stacks && Array.isArray(data.tech_stacks)) {
        const techOpts = [{ value: "", label: "Tech Stack (All)", count: null }];
        data.tech_stacks.forEach(t => {
          if (t && t.name) {
            techOpts.push({ value: t.slug || t.name.toLowerCase(), label: t.name, count: t.count });
          }
        });
        if (isOutreach) {
          if (ddOutreachTech) ddOutreachTech.setOptions(techOpts);
        } else {
          if (ddFilterTech) ddFilterTech.setOptions(techOpts);
        }
      }

      // 2. Reactive City Options (Only show cities that have matching records; counts match pagination exactly)
      if (data.cities && Array.isArray(data.cities)) {
        cachedCitiesData = data.cities;
        const cityOpts = [{ value: "", label: "All Cities", count: null }];
        data.cities.forEach(c => {
          if (c && c.name && (c.count === undefined || c.count > 0)) {
            cityOpts.push({ value: c.slug || (c.name || "").toLowerCase(), label: c.name, count: c.count });
          }
        });
        if (isOutreach) {
          if (ddOutreachCity) ddOutreachCity.setOptions(cityOpts);
        } else {
          if (ddFilterCity) ddFilterCity.setOptions(cityOpts);
        }
      }

      // 3. Reactive Domain Filter Counts (Companies tab)
      if (!isOutreach && data.domains && Array.isArray(data.domains)) {
        domainsData = data.domains;
        let totalAllDomains = 0;
        data.domains.forEach(d => {
          totalAllDomains += (d.count || 0);
          const countEl = document.getElementById(`domain-count-${d.code}`);
          if (countEl) {
            countEl.textContent = d.count ? `(${Number(d.count).toLocaleString()})` : "(0)";
          }
        });
        const countAllEl = document.getElementById("domain-count-all");
        if (countAllEl) {
          // Every company has exactly one industry, so "All" is the sum of the industry pills
          // (stats.total is narrowed to the selected industry).
          const allCount = totalAllDomains;
          countAllEl.textContent = `(${Number(allCount).toLocaleString()})`;
        }
      }

      // 4. Reactive Metrics
      if (data.stats) {
        globalStats = { ...data.stats };
        if (!isOutreach) {
          updateCompanyMetrics(data.stats);
          updateHeaderSubtitle(domain || "all", data.stats.total);
        }
      }
    } catch (e) {
      if (e.name === "AbortError") return;
      console.warn("Failed to fetch reactive company filters:", e);
    }
  }

  let companiesAbortController = null;

  async function fetchCompanies(preservePage = true) {
    try {
      if (companiesAbortController) {
        try { companiesAbortController.abort(); } catch (_) {}
      }
      companiesAbortController = new AbortController();
      const signal = companiesAbortController.signal;

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
      const pageSize = (companiesPerPage !== undefined && companiesPerPage !== null) ? companiesPerPage : 24;

      const params = new URLSearchParams({
        page: companiesCurrentPage,
        page_size: pageSize,
        search: q,
        tech: selectedTech,
        city: selectedCity,
        domain: (activeDomainFilter && activeDomainFilter !== "all") ? activeDomainFilter : "",
        status: statusParam,
        sort: selectedSort
      });

      const res = await fetch(`/api/companies?${params.toString()}`, { signal });
      if (!res.ok) {
        console.warn(`[Directory] API responded with HTTP ${res.status}.`);
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

      if (data.stats) {
        updateCompanyMetrics(data.stats);
        updateHeaderSubtitle(activeDomainFilter, data.stats.total);
      }

      // Keep filter dropdowns and option counts reactive to active selection
      fetchCompaniesFilters({ context: "companies" });

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
      if (err.name === "AbortError") return;
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
      if (activeDomainFilter && activeDomainFilter !== "all") {
        const domainNames = {
          it: "Information Technology & Software",
          sales: "Sales & Business Development",
          marketing: "Marketing, Advertising & PR",
          pharma: "Pharmaceuticals & Healthcare",
          finance: "Finance, Accounting & Legal",
          manufacturing: "Manufacturing & Logistics",
          realestate: "Real Estate & Construction",
          hr: "HR, Staffing & Consulting"
        };
        const domName = domainNames[activeDomainFilter] || activeDomainFilter.toUpperCase();
        emptyTitle = `No ${domName} Leads Saved Yet`;
        emptyMsg = `There are no ${domName} companies in the directory yet. Switch back to All Domains to see every company.`;
      } else if (activeMetricFilter === "invalid") {
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
          <div class="app-empty">
            <span class="ic"><i data-lucide="layers"></i></span>
            <p class="t">${emptyTitle}</p>
            <p>${emptyMsg}</p>
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
          // Invalid Lead Grid Card (Read-only notice, curation is strictly in /admin)
          card.className = "company-card-invalid app-card is-invalid";
          card.innerHTML = `
            <div class="ac-head">
              <div class="ac-id"><div class="ac-name"><h4>${escapeHTML(c.name)}</h4></div></div>
              <span class="status-pill excluded"><i data-lucide="shield-alert" class="w-3 h-3"></i><span>EXCLUDED</span></span>
            </div>
            <div class="invalid-note">
              <b><i data-lucide="alert-circle" class="w-3 h-3"></i><span>Excluded by Admin</span></b>
              <p class="break-words">${escapeHTML(c.invalid_reason || 'Excluded by Admin')}</p>
              ${c.invalid_at ? `<p class="font-mono subtle">Date: ${escapeHTML(c.invalid_at)}</p>` : ''}
            </div>
            <div class="ac-sub"><span><i data-lucide="globe" class="w-3 h-3"></i><span class="dom">${escapeHTML(c.domain)}</span></span></div>
          `;
        } else {
          // Genuine Active Company Grid Card
          const monogram = getCompanyMonogram(c.name);
          const monoThemes = [{ bg: "" }, { bg: "t1" }, { bg: "t2" }, { bg: "t3" }];
          const monoTheme = monoThemes[(c.id || 0) % monoThemes.length];

          // Rating & Reviews display
          const ratingVal = (c.rating && c.rating > 0) ? Number(c.rating).toFixed(1) : null;
          const ratingDisplay = ratingVal
            ? `<span class="ac-rating"><span class="material-symbols-outlined">star</span><b>${ratingVal}</b><span>Google (${c.reviews_count || 0})</span></span>`
            : '';

          // Status Badge: Pitched, Researched, Uncontacted
          let statusBadge = "";
          if (c.already_contacted) {
            statusBadge = `<span onclick="event.stopPropagation(); window.viewSentEmailForCompany && window.viewSentEmailForCompany(${c.id})" class="status-pill sent" title="Click to view outreach sent"><span class="material-symbols-outlined">check_circle</span><span>Pitched</span></span>`;
          } else if (c.is_enriched) {
            statusBadge = `<span class="status-pill researched"><span class="material-symbols-outlined">auto_awesome</span><span>Researched</span></span>`;
          } else {
            statusBadge = `<span class="status-pill">Uncontacted</span>`;
          }

          // Description: Only use actual scraped description or AI summary. Never manufacture fake text.
          let rawDesc = (c.profile && c.profile.summary) ? c.profile.summary : (c.description || '');
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
          const descText = typeof rawDesc === 'string' ? rawDesc.trim() : '';

          // Contact & Location (Strict: Never guess contact@ or domain fallbacks)
          const hasEmail = Boolean(c.emails && c.emails.length > 0);
          const primaryEmail = hasEmail ? c.emails[0] : null;
          const emailIcon = hasEmail ? 'mark_email_read' : 'mail_off';
          const emailTextClass = hasEmail ? 'has' : 'none';
          const locationText = c.city ? `${c.city}, IN` : (cleanAddressText(c.address) || 'India');

          // Tech stack pills (Only show verified AI-enriched tech stack; never misleading placeholders)
          let techPillsHtml = '';
          if (c.profile && Array.isArray(c.profile.tech_stack) && c.profile.tech_stack.length > 0) {
            techPillsHtml = c.profile.tech_stack.slice(0, 4).map(t => `<span class="ac-tag">${escapeHTML(t)}</span>`).join('');
          } else if (c.is_enriched) {
            techPillsHtml = `<span class="ac-tag muted">No frameworks detected</span>`;
          } else {
            techPillsHtml = `<span class="ac-tag muted"><span class="material-symbols-outlined">hourglass_top</span><span>Stack pending AI enrichment</span></span>`;
          }

          card.className = "company-card app-card is-clickable";
          card.innerHTML = `
            <div class="ac-head">
              <div class="ac-id">
                <div class="ac-mono ${monoTheme.bg}">${monogram}</div>
                <div class="min-w-0 flex-1">
                  <div class="ac-name">
                    <h3 title="${escapeHTML(c.name)}">${escapeHTML(c.name)}</h3>
                    ${c.domain ? `
                    <a href="${c.website_url || 'https://' + c.domain}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" title="Visit ${escapeHTML(c.domain)}">
                      <span class="material-symbols-outlined">open_in_new</span>
                    </a>` : ''}
                  </div>
                  ${c.domain ? `<div class="ac-sub"><span class="dom">${escapeHTML(c.domain)}</span></div>` : ''}
                </div>
              </div>
              ${statusBadge}
            </div>

            <div class="ac-meta">
              ${c.industry_domain ? `<span class="ac-industry" title="${escapeHTML(c.industry_domain)}">${escapeHTML(c.industry_domain)}</span>` : '<span class="ac-industry">Technology</span>'}
              ${ratingDisplay}
            </div>

            ${descText
              ? `<p class="ac-desc">${escapeHTML(descText)}</p>`
              : `<p class="ac-desc is-empty">Capabilities profile pending extraction</p>`}

            <div class="ac-contact">
              <span class="${emailTextClass}">
                <span class="material-symbols-outlined">${emailIcon}</span>
                <span>${hasEmail ? escapeHTML(primaryEmail) : 'Email not found'}</span>
              </span>
              <span class="loc">
                <span class="material-symbols-outlined">location_on</span>
                <span>${escapeHTML(locationText)}</span>
              </span>
            </div>

            <div class="ac-tags">${techPillsHtml}</div>

            <div class="ac-actions">
              <button type="button" class="btn-single-details btn btn-secondary btn-sm">
                <span class="material-symbols-outlined">visibility</span>
                <span class="truncate">View Intel</span>
              </button>
              <button type="button" class="btn-single-pitch btn btn-primary btn-sm">
                <span class="material-symbols-outlined">send</span>
                <span class="truncate">Draft Pitch</span>
              </button>
            </div>
          `;

          const btnDetails = card.querySelector(".btn-single-details");
          const btnPitch = card.querySelector(".btn-single-pitch");
          if (btnDetails) {
            btnDetails.addEventListener("click", (e) => {
              e.stopPropagation();
              openCompanyDetailsModal(c);
            });
          }
          if (btnPitch) {
            btnPitch.addEventListener("click", (e) => {
              e.stopPropagation();
              confirmResendIfNeeded(c, () => handleGeneratePitch(c.id));
            });
          }
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
  const cmodalBtnPitch = document.getElementById("cmodal-btn-pitch");
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

    // Status Badge
    cmodalBadge.onclick = null;
    cmodalBadge.removeAttribute("title");
    if (company.is_invalid) {
      cmodalBadge.className = "modal-badge invalid";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">shield</span><span>INVALID LEAD</span>`;
    } else if (company.already_contacted) {
      cmodalBadge.className = "modal-badge contacted";
      cmodalBadge.title = "Click to view message sent";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">check_circle</span><span>Contacted ${company.contacted_at || ''}</span>`;
      cmodalBadge.onclick = () => window.viewSentEmailForCompany(company.id);
    } else if (company.is_enriched) {
      cmodalBadge.className = "modal-badge enriched";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">auto_awesome</span><span>AI Enriched</span>`;
    } else {
      cmodalBadge.className = "modal-badge verified";
      cmodalBadge.innerHTML = `<span class="material-symbols-outlined text-[13px]">verified</span><span>Verified Lead</span>`;
    }

    // Discovered Emails
    const emails = company.emails || [];
    cmodalEmailsCount.textContent = `${emails.length} discovered`;
    if (emails.length > 0) {
      cmodalEmailsContainer.innerHTML = emails.map(em => `
        <div class="email-chip">
          <span class="material-symbols-outlined">mail</span>
          <span class="break-all">${escapeHTML(em)}</span>
          <button class="copy-em-btn" data-email="${escapeHTML(em)}" title="Copy email">
            <span class="material-symbols-outlined">content_copy</span>
          </button>
        </div>
      `).join("");

      cmodalEmailsContainer.querySelectorAll(".copy-em-btn").forEach(b => {
        b.addEventListener("click", () => {
          navigator.clipboard.writeText(b.dataset.email);
          b.innerHTML = `<span class="material-symbols-outlined text-emerald-400">check</span>`;
          setTimeout(() => {
            b.innerHTML = `<span class="material-symbols-outlined">content_copy</span>`;
          }, 1500);
        });
      });
    } else {
      cmodalEmailsContainer.innerHTML = `
        <div class="no-email">
          <span class="material-symbols-outlined">mail_off</span>
          <span>No contact email found for this company yet.</span>
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
          <span class="tech-chip">${escapeHTML(tech)}</span>
        `).join("");
      } else {
        cmodalTechstack.innerHTML = `<span class="muted-note">No tech stack detected</span>`;
      }
    } else {
      cmodalSummary.textContent = "No research for this company yet.";
      cmodalIndustry.textContent = "Not available yet";
      cmodalTone.textContent = "Professional";
      cmodalTechstack.innerHTML = `<span class="muted-note">Not detected yet</span>`;
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
        <div class="sk-lines">
          <span class="sk" style="height:16px;width:75%"></span>
          <span class="sk" style="height:12px"></span>
          <span class="sk" style="height:12px;width:85%"></span>
          <span class="sk" style="height:12px;width:65%"></span>
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
                cmodalDetailedAnalysis.innerHTML = `<span class="muted-note">No research report for this company yet.</span>`;
              }
              const stack = detailData.profile.tech_stack || [];
              if (stack.length > 0) {
                cmodalTechstack.innerHTML = stack.map(tech => `
                  <span class="tech-chip">${escapeHTML(tech)}</span>
                `).join("");
              } else {
                cmodalTechstack.innerHTML = `<span class="muted-note">No tech stack detected</span>`;
              }
            } else {
              cmodalDetailedAnalysis.innerHTML = `<span class="muted-note">No research report for this company yet.</span>`;
            }

            if (detailData.emails && detailData.emails.length > 0) {
              company.emails = detailData.emails;
              cmodalEmailsCount.textContent = `${detailData.emails.length} discovered`;
              cmodalEmailsContainer.innerHTML = detailData.emails.map(em => `
                        <div class="email-chip">
                  <span class="material-symbols-outlined">mail</span>
                  <span class="break-all">${escapeHTML(em)}</span>
                  <button class="copy-em-btn" data-email="${escapeHTML(em)}" title="Copy email">
                    <span class="material-symbols-outlined">content_copy</span>
                  </button>
                </div>
              `).join("");
            }
          }
        })
        .catch(err => {
          console.warn("Failed to fetch on-demand company intel:", err);
          if (activeModalCompany && activeModalCompany.id === company.id) {
            cmodalDetailedAnalysis.innerHTML = `<span class="muted-note">No research report for this company yet.</span>`;
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

  cmodalBtnPitch.addEventListener("click", () => {
    if (!activeModalCompany) return;
    requireLogin(() => {
      cmodal.classList.add("hidden");
      handleGeneratePitch(activeModalCompany.id);
    }, "generate outreach pitches");
  });

  if (filterInput) {
    filterInput.addEventListener("input", () => applyCompanyFiltersAndRender(true));
    filterInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(filterDebounceTimer);
        companiesCurrentPage = 1;
        fetchCompanies(false);
      }
    });
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
    const max_pages = parseInt(document.getElementById("input-pages")?.value || "0", 10) || 0;
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

  function requireLogin(callback, actionPrompt = "Please sign in with Google to continue.") {
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

      const navAdminLink = document.getElementById("nav-admin-link");
      if (navAdminLink) {
        if (isMasterAdmin) {
          navAdminLink.classList.remove("hidden");
        } else {
          navAdminLink.classList.add("hidden");
        }
      }

      if (data.stats) {
        updateCompanyMetrics(data.stats);
        updateHeaderSubtitle(activeDomainFilter, data.stats.total);
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
      updateUserSubscriptionUI(currentUser);
      refreshIcons();
    } catch (err) {
      console.warn("Auth status fetch error:", err);
    }
  }

  // Initial SSR Hydration for Subscription & Daily Quota
  if (window.__INITIAL_AUTH__) {
    updateUserSubscriptionUI(window.__INITIAL_AUTH__);
  }

  const subModal = document.getElementById("modal-user-subscription");
  const btnCloseSubModal = document.getElementById("btn-close-sub-modal");
  const headerQuotaWidget = document.getElementById("header-quota-widget");
  const sidebarQuotaCard = document.getElementById("sidebar-quota-card");

  function openSubscriptionModal() {
    if (subModal) {
      subModal.classList.remove("hidden");
      window.ScrollLock?.refresh();
      if (currentUser) updateUserSubscriptionUI(currentUser);
    }
  }

  function closeSubscriptionModal() {
    if (subModal) {
      subModal.classList.add("hidden");
      window.ScrollLock?.refresh();
    }
  }

  headerQuotaWidget?.addEventListener("click", openSubscriptionModal);
  sidebarQuotaCard?.addEventListener("click", openSubscriptionModal);
  btnCloseSubModal?.addEventListener("click", closeSubscriptionModal);
  if (subModal) {
    subModal.addEventListener("click", (e) => {
      if (e.target === subModal) closeSubscriptionModal();
    });
  }

  if (loginModalClose) {
    loginModalClose.addEventListener("click", () => loginModal?.classList.add("hidden"));
  }
  if (loginModal) {
    loginModal.addEventListener("click", (e) => {
      if (e.target === loginModal) loginModal.classList.add("hidden");
    });
  }

  // Background scroll lock for every modal lives in static/js/scroll-lock.js.

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

  const btnGenAllPitches = document.getElementById("btn-gen-all-pitches");
  if (btnGenAllPitches) {
    btnGenAllPitches.addEventListener("click", async () => {
      if (!selectedOutreachCompanyIds || selectedOutreachCompanyIds.size === 0) {
        showToast("Please select at least one company using the checkboxes to prepare pitches.", "warning");
        return;
      }

      const targets = (allOutreachCompanies && allOutreachCompanies.length > 0) ? allOutreachCompanies : (companies || []);
      const eligible = targets.filter(c => selectedOutreachCompanyIds.has(c.id) && !c.is_invalid);

      if (eligible.length === 0) {
        showToast("No valid companies selected to prepare pitches for.", "warning");
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
          updateOutreachSelectionUI();
        }, 2500);
      }, "Authentication required. Please connect your Google account to generate personalized pitches.");
    });
  }

  // --- Send Outreach Emails (Strict: Operates only on user-selected companies with verified emails) ---
  const btnSendAllOutreach = document.getElementById("btn-send-all-outreach");
  if (btnSendAllOutreach) {
    btnSendAllOutreach.addEventListener("click", async () => {
      if (!selectedOutreachCompanyIds || selectedOutreachCompanyIds.size === 0) {
        showToast("Please select at least one company to send emails.", "warning");
        return;
      }

      const targets = (allOutreachCompanies && allOutreachCompanies.length > 0) ? allOutreachCompanies : (companies || []);
      const eligible = targets.filter(c => selectedOutreachCompanyIds.has(c.id) && !c.is_invalid);

      if (eligible.length === 0) {
        showToast("No valid companies selected for outreach.", "warning");
        return;
      }

      confirmResumeAttachmentIfNeeded(
        `cold outreach emails to ${eligible.length} selected companies`,
        () => {
          requireLogin(async () => {
            // Strictly filter to selected companies with at least one discovered email
            const withEmail = eligible.filter(c => c.emails && c.emails.length > 0 && !c.already_contacted);
            const alreadySentCount = eligible.filter(c => c.emails && c.emails.length > 0 && c.already_contacted).length;
            const noEmailCompanies = eligible.filter(c => !c.emails || c.emails.length === 0);
            const noEmailCount = noEmailCompanies.length;

            if (withEmail.length === 0) {
              if (alreadySentCount > 0 && noEmailCount > 0) {
                showToast(`All ${alreadySentCount} selected companies with verified emails have already been contacted. Skipped ${noEmailCount} companies with no email.`, "info");
              } else if (noEmailCount > 0) {
                showToast(`Company email not found! All ${noEmailCount} selected companies have no discovered email address. Enrich companies first.`, "error");
              } else {
                showToast("No pending outreach targets with email addresses among selected companies.", "info");
              }
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
              let bulkRes;
              if (attachResumeInEmail && sessionResumeFile) {
                const formData = new FormData();
                formData.append("pitch_ids", JSON.stringify(pitchIdsToSend));
                formData.append("delay_min", "2.0");
                formData.append("delay_max", "3.5");
                formData.append("resume_file", sessionResumeFile);
                bulkRes = await fetch("/api/pitch/bulk-send", {
                  method: "POST",
                  body: formData
                });
              } else {
                bulkRes = await fetch("/api/pitch/bulk-send", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    pitch_ids: pitchIdsToSend,
                    delay_min: 2.0,
                    delay_max: 3.5
                  })
                });
              }

              if (bulkRes.status === 401) {
                showToast("Session expired. Please reconnect your Google account.", "warning");
                showLoginModal("Session expired. Please reconnect your Google account.");
                return;
              }

              const bulkData = await bulkRes.json();
              const sent = bulkData.sent || 0;
              const skipped = (bulkData.skipped_no_email || 0) + noEmailCount;

              const resumeSuffix = (attachResumeInEmail && sessionResumeFile) ? " (with resume attached)" : " (without resume)";
              showToast(`Success: Dispatched ${sent} emails via Gmail${resumeSuffix}! (${skipped} companies without email were skipped).`, "success");
              btnSendAllOutreach.innerHTML = `<span class="material-symbols-outlined text-[16px] text-emerald-400">check</span><span>${sent} Dispatched!</span>`;

              withEmail.forEach(c => {
                c.already_contacted = true;
                selectedOutreachCompanyIds.delete(c.id);
              });

              await fetchCompanies();
              fetchAuditLogs();
              renderPitchesList();
              checkAuthStatus();
            } catch (err) {
              showToast("Batch dispatch error: " + err.message, "error");
            } finally {
              setTimeout(() => {
                btnSendAllOutreach.innerHTML = oldText;
                btnSendAllOutreach.disabled = false;
                updateOutreachSelectionUI();
              }, 3000);
            }
          }, "connect your Google account to perform automated outreach.");
        }
      );
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

  // Before drafting for a company this user already emailed: show the sent email, or write another on purpose.
  function confirmResendIfNeeded(company, onProceed) {
    const modal = document.getElementById("resend-confirm-modal");
    if (!company || !company.already_contacted || !modal) {
      onProceed();
      return;
    }
    const when = company.contacted_at ? ` on ${company.contacted_at}` : "";
    document.getElementById("resend-confirm-desc").textContent =
      `You sent an email to ${company.name}${when}. Sending another one counts toward your daily limit.`;
    modal.classList.remove("hidden");
    const btnView = document.getElementById("btn-resend-view");
    const btnProceed = document.getElementById("btn-resend-proceed");
    const btnCancel = document.getElementById("btn-resend-cancel");
    const close = (next) => () => {
      modal.classList.add("hidden");
      btnView.onclick = btnProceed.onclick = btnCancel.onclick = null;
      if (next) next();
    };
    btnView.onclick = close(() => viewSentEmailForCompany(company.id));
    btnProceed.onclick = close(onProceed);
    btnCancel.onclick = close(null);
    btnView.focus();
  }

  function confirmResumeAttachmentIfNeeded(actionDescription, onProceed) {
    const hasResume = Boolean(attachResumeInEmail && sessionResumeFile);
    if (hasResume) {
      onProceed();
      return;
    }

    const modal = document.getElementById("resume-confirm-modal");
    const btnAttach = document.getElementById("btn-resume-confirm-attach");
    const btnProceed = document.getElementById("btn-resume-confirm-proceed");
    const btnCancel = document.getElementById("btn-resume-confirm-cancel");
    const descEl = document.getElementById("resume-confirm-desc");

    if (!modal || !btnProceed || !btnCancel) {
      if (confirm("No resume file is currently attached. Are you sure you want to send email without a resume attachment?")) {
        onProceed();
      }
      return;
    }

    if (descEl && actionDescription) {
      descEl.textContent = `No resume file is currently attached. Sending ${actionDescription} without your resume attached may lower response rates from hiring teams.`;
    }

    modal.classList.remove("hidden");

    const cleanup = () => {
      modal.classList.add("hidden");
      btnAttach?.removeEventListener("click", onAttachClick);
      btnProceed?.removeEventListener("click", onProceedClick);
      btnCancel?.removeEventListener("click", onCancelClick);
    };

    const onAttachClick = () => {
      cleanup();
      if (outreachResumeFile) outreachResumeFile.click();
      showToast("Please select your resume PDF file to attach.", "info");
    };

    const onProceedClick = () => {
      cleanup();
      onProceed();
    };

    const onCancelClick = () => {
      cleanup();
    };

    btnAttach?.addEventListener("click", onAttachClick);
    btnProceed?.addEventListener("click", onProceedClick);
    btnCancel?.addEventListener("click", onCancelClick);
  }

  const resumeConfirmModalEl = document.getElementById("resume-confirm-modal");
  if (resumeConfirmModalEl) {
    resumeConfirmModalEl.addEventListener("click", (e) => {
      if (e.target === resumeConfirmModalEl) {
        resumeConfirmModalEl.classList.add("hidden");
      }
    });
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
    const count = text ? text.split(/\s+/).filter(Boolean).length : 0;
    pitchWordCount.textContent = `${count} words`;
    pitchWordCount.className = "word-count";
  }

  if (modalBody) {
    modalBody.addEventListener("input", () => {
      updatePitchWordCount();
    });
  }

  if (modalSubject) {
    modalSubject.addEventListener("input", () => {});
  }

  function setupSubjectAngleButtons(subjs, initialActive = "specificity") {
    // Subject line angle options removed per clean direct UI standards
  }

  function switchPitchVariant(variantKey) {
    // Variant switcher tabs removed per clean direct UI standards
  }

  function populateStrategyNotes(notes, whatToChange) {
    // Strategy notes box removed per clean direct UI standards
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
          modalTargetEmail.innerHTML = `<span class="em">${escapeHTML(currentPitchTargetEmail)}</span>`;
        } else {
          modalTargetEmail.innerHTML = `<span class="recipient-missing"><span class="material-symbols-outlined">mail_off</span><span>Email not found (Sending disabled)</span></span>`;
        }

        modalSubject.value = data.subject_line || "";
        modalBody.value = data.email_body || data.primary_email || "";
        updatePitchWordCount();
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

      confirmResumeAttachmentIfNeeded("this cold email", async () => {
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
            const sentCompany = companies.find(c => c.id === currentPitchCompanyId);
            if (sentCompany) {
              sentCompany.already_contacted = true;
              renderCompanies(companies);
            }
            await fetchCompanies();
            fetchAuditLogs();
            checkAuthStatus();
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
    });
  }

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
  const selectedOutreachCompanyIds = new Set();

  // Daily send limit: refuse selecting more companies than emails left today.
  function outreachQuotaLeft() {
    const r = window.__quotaRemaining;
    return typeof r === "number" ? r : Infinity;
  }
  function warnOverQuota(left) {
    showToast(left <= 0
      ? "You have no emails left today. Your limit resets at midnight IST."
      : `You can send ${left} more email${left === 1 ? "" : "s"} today. Select up to ${left} compan${left === 1 ? "y" : "ies"}.`,
      "warning");
  }

  function updateOutreachSelectionUI(currentPageItems = []) {
    const badge = document.getElementById("outreach-selected-badge");
    const countEl = document.getElementById("outreach-selected-count");
    const clearBtn = document.getElementById("btn-outreach-clear-selection");
    const selectAllChk = document.getElementById("outreach-select-all");
    const btnGenText = document.getElementById("btn-gen-all-pitches-text");
    const btnSendText = document.getElementById("btn-send-all-outreach-text");

    const count = selectedOutreachCompanyIds.size;
    if (countEl) countEl.textContent = count;

    if (badge) {
      if (count > 0) {
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }

    if (clearBtn) {
      if (count > 0) {
        clearBtn.classList.remove("hidden");
      } else {
        clearBtn.classList.add("hidden");
      }
    }

    if (btnGenText) {
      btnGenText.textContent = count > 0 ? `Prepare Pitches (${count})` : "Prepare Pitches";
    }
    if (btnSendText) {
      btnSendText.textContent = count > 0 ? `Send Emails (${count})` : "Send Emails";
    }

    if (selectAllChk) {
      if (currentPageItems && currentPageItems.length > 0) {
        const pageSelectedCount = currentPageItems.filter(c => selectedOutreachCompanyIds.has(c.id)).length;
        if (pageSelectedCount === currentPageItems.length) {
          selectAllChk.checked = true;
          selectAllChk.indeterminate = false;
        } else if (pageSelectedCount > 0) {
          selectAllChk.checked = false;
          selectAllChk.indeterminate = true;
        } else {
          selectAllChk.checked = false;
          selectAllChk.indeterminate = false;
        }
      } else {
        selectAllChk.checked = false;
        selectAllChk.indeterminate = false;
      }
    }
  }

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

  let outreachAbortController = null;
  let outreachTotalServerCount = 0;
  let outreachTotalServerPages = 1;

  async function fetchOutreachCompanies(preservePage = false) {
    if (outreachAbortController) {
      try { outreachAbortController.abort(); } catch (_) {}
    }
    outreachAbortController = new AbortController();
    const signal = outreachAbortController.signal;

    if (!preservePage) {
      outreachCurrentPage = 1;
    }

    try {
      const q = (outreachSearchInput?.value || outreachSearchQuery || "").trim();
      const selectedTech = (outreachTechSelect?.value || outreachSelectedTech || "").trim();
      const selectedCity = (outreachCitySelect?.value || outreachSelectedCity || "").trim();
      const pageSize = outreachPerPage > 0 ? outreachPerPage : 24;

      const params = new URLSearchParams({
        page: outreachCurrentPage,
        page_size: pageSize,
        search: q,
        tech: selectedTech,
        city: selectedCity,
        status: outreachActiveFilter || "all"
      });

      const res = await fetch(`/api/companies?${params.toString()}`, { signal });
      if (res.ok) {
        const data = await res.json();
        allOutreachCompanies = data.companies || [];
        outreachTotalServerCount = data.total_count || 0;
        outreachTotalServerPages = data.total_pages || 1;
        outreachCurrentPage = data.current_page || 1;
        outreachLoaded = true;
        if (data.stats) {
          updateCompanyMetrics(data.stats);
        }
        fetchCompaniesFilters({
          context: "outreach",
          tech: selectedTech,
          city: selectedCity,
          status: outreachActiveFilter || "all",
          search: q
        });
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      console.warn("Failed to fetch all outreach companies:", err);
    } finally {
      isOutreachLoading = false;
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
    fetchOutreachCompanies(false);
  }

  if (outreachSearchInput) {
    let outreachDebounce = null;
    outreachSearchInput.addEventListener("input", (e) => {
      clearTimeout(outreachDebounce);
      outreachDebounce = setTimeout(() => {
        outreachSearchQuery = (e.target.value || "").trim().toLowerCase();
        outreachCurrentPage = 1;
        fetchOutreachCompanies(false);
      }, 350);
    });
    outreachSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(outreachDebounce);
        outreachSearchQuery = (e.target.value || "").trim().toLowerCase();
        outreachCurrentPage = 1;
        fetchOutreachCompanies(false);
      }
    });
  }

  const outreachSelectAll = document.getElementById("outreach-select-all");
  if (outreachSelectAll) {
    outreachSelectAll.addEventListener("change", (e) => {
      const isChecked = e.target.checked;
      const left = outreachQuotaLeft();
      let skipped = 0;
      (allOutreachCompanies || []).forEach(c => {
        if (isChecked) {
          if (selectedOutreachCompanyIds.has(c.id)) return;
          if (selectedOutreachCompanyIds.size >= left) { skipped++; return; }
          selectedOutreachCompanyIds.add(c.id);
        } else {
          selectedOutreachCompanyIds.delete(c.id);
        }
      });
      if (skipped) warnOverQuota(left);
      renderPitchesList();
    });
  }

  const btnOutreachClear = document.getElementById("btn-outreach-clear-selection");
  if (btnOutreachClear) {
    btnOutreachClear.addEventListener("click", () => {
      selectedOutreachCompanyIds.clear();
      renderPitchesList();
      showToast("Selection cleared.", "info");
    });
  }

  if (outreachTechSelect) {
    outreachTechSelect.addEventListener("change", (e) => {
      outreachSelectedTech = (e.target.value || "").trim().toLowerCase();
      outreachCurrentPage = 1;
      fetchOutreachCompanies(false);
    });
  }

  if (outreachCitySelect) {
    outreachCitySelect.addEventListener("change", (e) => {
      outreachSelectedCity = (e.target.value || "").trim().toLowerCase();
      outreachCurrentPage = 1;
      fetchOutreachCompanies(false);
    });
  }

  if (btnOutreachReset) {
    btnOutreachReset.addEventListener("click", () => {
      if (outreachSearchInput) outreachSearchInput.value = "";
      if (outreachTechSelect) outreachTechSelect.value = "";
      if (outreachCitySelect) outreachCitySelect.value = "";
      if (ddOutreachTech) ddOutreachTech.reset();
      if (ddOutreachCity) ddOutreachCity.reset();
      outreachSearchQuery = "";
      outreachSelectedTech = "";
      outreachSelectedCity = "";
      outreachActiveFilter = "all";
      outreachCurrentPage = 1;
      updateOutreachPillStyles();
      fetchOutreachCompanies(false);
      showToast("Outreach filters reset to default", "info");
    });
  }

  if (btnOutreachViewGrid) {
    btnOutreachViewGrid.addEventListener("click", () => {
      outreachViewMode = "grid";
      btnOutreachViewGrid.className = "is-active";
      btnOutreachViewList.className = "";
      renderPitchesList();
    });
  }

  if (btnOutreachViewList) {
    btnOutreachViewList.addEventListener("click", () => {
      outreachViewMode = "list";
      btnOutreachViewList.className = "is-active";
      btnOutreachViewGrid.className = "";
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
      fetchOutreachCompanies(false);
    });
  }

  window.openCompanyModalById = function(companyId) {
    const target = (allOutreachCompanies || []).find(c => c.id === companyId) || (companies || []).find(c => c.id === companyId);
    if (target) openCompanyDetailsModal(target);
  };

  function renderPitchesList() {
    const container = document.getElementById("pitches-container");
    const countSpan = document.getElementById("pitches-count");
    if (!container) return;
    container.innerHTML = "";

    // Set responsive grid vs compact stream layout class
    container.className = (outreachViewMode === "grid") ? "card-grid" : "row-list";

    const totalCount = outreachTotalServerCount || (allOutreachCompanies ? allOutreachCompanies.length : 0);
    if (countSpan) countSpan.textContent = totalCount.toLocaleString();

    if (!allOutreachCompanies || allOutreachCompanies.length === 0) {
      if (outreachPagination) outreachPagination.classList.add("hidden");
      if (outreachPaginationBottom) outreachPaginationBottom.classList.add("hidden");
      container.innerHTML = `
        <div class="app-empty">
          <span class="ic"><span class="material-symbols-outlined">search_off</span></span>
          <p class="t">No matching outreach targets</p>
          <p>Try adjusting your search query or clearing dropdown filters.</p>
        </div>
      `;
      updateOutreachSelectionUI([]);
      refreshIcons();
      return;
    }

    const pageItems = allOutreachCompanies;

    const monoThemes = [{ bg: "" }, { bg: "t1" }, { bg: "t2" }, { bg: "t3" }];

    pageItems.forEach(c => {
      const card = document.createElement("div");
      const monogram = getCompanyMonogram(c.name);
      const monoIdx = Math.abs((c.name || "C").split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0)) % monoThemes.length;
      const monoTheme = monoThemes[monoIdx];

      const hasDirectEmail = Boolean(c.emails && c.emails.length > 0);
      const directEmail = hasDirectEmail ? c.emails[0] : null;

      const ratingVal = (c.rating && c.rating > 0) ? Number(c.rating).toFixed(1) : null;
      const ratingDisplay = ratingVal
        ? `<span class="ac-rating"><span class="material-symbols-outlined">star</span><b>${ratingVal}</b><span>Google (${c.reviews_count || 0})</span></span>`
        : `<span class="subtle">No reviews</span>`;

      const statusBadge = c.already_contacted
        ? `<button type="button" onclick="window.viewSentEmailForCompany(${c.id})" class="status-pill sent" title="Click to view message sent"><span class="material-symbols-outlined">check_circle</span><span>Sent</span></button>`
        : `<span class="status-pill">Queue</span>`;

      // Tech stack pills (Strict: only verified AI-enriched tech stack)
      let techPillsHtml = '';
      if (c.profile && Array.isArray(c.profile.tech_stack) && c.profile.tech_stack.length > 0) {
        techPillsHtml = c.profile.tech_stack.slice(0, 4).map(t => `<span class="ac-tag">${escapeHTML(t)}</span>`).join('');
      } else if (c.is_enriched) {
        techPillsHtml = `<span class="ac-tag muted">No frameworks detected</span>`;
      } else {
        techPillsHtml = `<span class="ac-tag muted"><span class="material-symbols-outlined">hourglass_top</span><span>Stack pending AI enrichment</span></span>`;
      }

      const isSelected = selectedOutreachCompanyIds.has(c.id);

      if (outreachViewMode === "grid") {
        // Mode A: Executive Dispatch Bento Card
        card.className = "company-card app-card";
        card.innerHTML = `
          <div class="ac-head">
            <div class="ac-id">
              <label class="ac-check" onclick="event.stopPropagation();" title="Select company">
                <input type="checkbox" class="outreach-card-checkbox" data-id="${c.id}" ${isSelected ? 'checked' : ''}>
              </label>
              <div class="ac-mono ${monoTheme.bg}">${monogram}</div>
              <div class="min-w-0 flex-1">
                <div class="ac-name">
                  <h3 class="clickable" onclick="window.openCompanyModalById(${c.id})" title="${escapeHTML(c.name)}">${escapeHTML(c.name)}</h3>
                  <a href="${c.website_url || 'https://' + c.domain}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation();" title="Visit website">
                    <span class="material-symbols-outlined">open_in_new</span>
                  </a>
                </div>
                <div class="ac-sub">
                  <span class="dom">${escapeHTML(c.domain || '')}</span>
                  ${c.city ? `<span><span class="material-symbols-outlined">location_on</span>${escapeHTML(c.city)}</span>` : ''}
                </div>
              </div>
            </div>
            ${statusBadge}
          </div>

          ${hasDirectEmail ? `
            <div class="email-well">
              <div class="l">
                <span class="material-symbols-outlined">alternate_email</span>
                <div class="min-w-0"><small>Verified Direct Email</small><b>${escapeHTML(directEmail)}</b></div>
              </div>
              <button type="button" class="btn-copy-email icon-btn sm bare" data-email="${escapeHTML(directEmail)}" title="Copy email address">
                <span class="material-symbols-outlined">content_copy</span>
              </button>
            </div>
          ` : `
            <div class="email-well missing">
              <div class="l">
                <span class="material-symbols-outlined">mail_off</span>
                <div class="min-w-0"><small>Email Not Found</small><b>No verified recruiter email discovered</b></div>
              </div>
              <span class="chip-warn">Unreachable</span>
            </div>
          `}

          <div>
            <div class="intel-head">
              <span>${(c.profile && Array.isArray(c.profile.tech_stack) && c.profile.tech_stack.length > 0) ? 'Detected tech stack' : 'Research status'}</span>
              ${ratingDisplay}
            </div>
            <div class="ac-tags">${techPillsHtml}</div>
          </div>

          <div class="ac-actions split">
            <button type="button" class="btn-view-intel-row btn btn-secondary btn-sm" data-id="${c.id}" title="Inspect full intelligence profile">
              <span class="material-symbols-outlined">visibility</span>
              <span>View Intel</span>
            </button>
            ${c.already_contacted ? `
              <button type="button" onclick="window.viewSentEmailForCompany(${c.id})" class="btn btn-secondary btn-sm">
                <span class="material-symbols-outlined">history</span>
                <span>Sent Log</span>
              </button>
            ` : `
              <button type="button" class="btn-gen-pitch-row btn btn-primary btn-sm" data-id="${c.id}">
                <span class="material-symbols-outlined">send</span>
                <span>Review & Send</span>
              </button>
            `}
          </div>
        `;
      } else {
        // Mode B: Streamlined Compact Row
        card.className = "company-card app-row";
        card.innerHTML = `
          <div class="l">
            <label class="ac-check" onclick="event.stopPropagation();" title="Select company">
              <input type="checkbox" class="outreach-card-checkbox" data-id="${c.id}" ${isSelected ? 'checked' : ''}>
            </label>
            <div class="ac-mono ${monoTheme.bg}">${monogram}</div>
            <div class="min-w-0 flex-1">
              <div class="row-badges">
                <div class="ac-name"><h4 class="clickable" onclick="window.openCompanyModalById(${c.id})">${escapeHTML(c.name)}</h4></div>
                ${statusBadge}
                ${hasDirectEmail
                  ? `<span class="chip-ok">Direct email</span>`
                  : `<span class="chip-warn"><span class="material-symbols-outlined">mail_off</span><span>Email Not Found</span></span>`}
              </div>
              <div class="row-meta">
                ${hasDirectEmail ? `<span class="em">${escapeHTML(directEmail)}</span>` : `<span class="miss">Email not found</span>`}
                <span>${escapeHTML(c.domain || '')}</span>
                ${c.city ? `<span class="inline-flex items-center gap-1"><span class="material-symbols-outlined" style="font-size:14px">location_on</span>${escapeHTML(c.city)}</span>` : ''}
              </div>
            </div>
          </div>

          <div class="r">
            <button type="button" class="btn-view-intel-row btn btn-ghost btn-sm" data-id="${c.id}">
              <span class="material-symbols-outlined">visibility</span>
              <span class="hidden sm:inline">Intel</span>
            </button>
            ${c.already_contacted ? `
              <button type="button" onclick="window.viewSentEmailForCompany(${c.id})" class="btn btn-secondary btn-sm">
                <span class="material-symbols-outlined">history</span>
                <span>Sent</span>
              </button>
            ` : `
              <button type="button" class="btn-gen-pitch-row btn btn-primary btn-sm" data-id="${c.id}">
                <span class="material-symbols-outlined">send</span>
                <span>Review & Send</span>
              </button>
            `}
          </div>
        `;
      }

      // Selection Checkbox change listener
      const chk = card.querySelector(".outreach-card-checkbox");
      if (chk) {
        chk.addEventListener("click", (e) => e.stopPropagation());
        chk.addEventListener("change", (e) => {
          e.stopPropagation();
          if (chk.checked && !selectedOutreachCompanyIds.has(c.id) && selectedOutreachCompanyIds.size >= outreachQuotaLeft()) {
            chk.checked = false;
            warnOverQuota(outreachQuotaLeft());
            return;
          }
          if (chk.checked) {
            selectedOutreachCompanyIds.add(c.id);
            card.classList.add("ring-2", "ring-primary/50", "bg-surface-container-high", "border-primary/60");
            card.classList.remove("bg-surface-container-low", "border-outline-variant/50");
          } else {
            selectedOutreachCompanyIds.delete(c.id);
            card.classList.remove("ring-2", "ring-primary/50", "bg-surface-container-high", "border-primary/60");
            card.classList.add("bg-surface-container-low", "border-outline-variant/50");
          }
          updateOutreachSelectionUI(pageItems);
        });
      }

      // Event listeners for card buttons
      const btnPitch = card.querySelector(".btn-gen-pitch-row");
      if (btnPitch) {
        btnPitch.addEventListener("click", (e) => {
          e.stopPropagation();
          confirmResendIfNeeded(c, () => handleGeneratePitch(c.id));
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
          btnCopy.innerHTML = `<span class="material-symbols-outlined text-emerald-400">check</span>`;
          setTimeout(() => {
            btnCopy.innerHTML = `<span class="material-symbols-outlined">content_copy</span>`;
          }, 1500);
        });
      }

      container.appendChild(card);
    });

    updateOutreachSelectionUI(pageItems);

    // Render pagination controls (top and bottom)
    const handleOutreachPageChange = (newPage) => {
      outreachCurrentPage = newPage;
      fetchOutreachCompanies(true);
      if (container) container.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    renderPaginationControls({
      paginationEl: outreachPagination,
      rangeEl: outreachPageRange,
      totalEl: outreachPageTotal,
      buttonsEl: outreachPageButtons,
      totalItems: totalCount,
      currentPage: outreachCurrentPage,
      pageSize: outreachPerPage,
      onPageChange: handleOutreachPageChange
    });

    renderPaginationControls({
      paginationEl: outreachPaginationBottom,
      rangeEl: outreachPageRangeBottom,
      totalEl: outreachPageTotalBottom,
      buttonsEl: outreachPageButtonsBottom,
      totalItems: totalCount,
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

  window._openCachedLog = function(idx) {
    if (window._cachedAuditLogs && window._cachedAuditLogs[idx]) {
      openSentEmailModal(window._cachedAuditLogs[idx]);
    }
  };

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

  // Handle Deep-Linked Actions from Public Directory & Company Profiles
  async function handleDeepLinkedActions() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const action = urlParams.get("action");
      const companyId = urlParams.get("company_id") || urlParams.get("id");
      const companyName = urlParams.get("company_name") || "";
      const city = urlParams.get("city");
      const tech = urlParams.get("tech");
      const domain = urlParams.get("domain");
      const q = urlParams.get("q") || urlParams.get("search");

      if (!action && !companyId && !city && !tech && !q && !domain) return;
      // Apply the link once: drop it from the address bar so Reset sticks and a reload does not reopen it.
      window.history.replaceState({}, document.title, window.location.pathname);

      // 1. Direct Pitch Trigger (?action=pitch&company_id=123)
      if (action === "pitch" && companyId) {
        switchTab("companies");
        const cId = parseInt(companyId, 10);
        if (!isNaN(cId)) {
          showToast(`Opening AI pitch generator for ${companyName || 'company'}...`, "info");
          // Allow auth check and table initialization to finish
          setTimeout(() => {
            requireLogin(() => {
              handleGeneratePitch(cId);
            }, "generate an AI pitch for this company");
          }, 400);
        }
        return;
      }

      // 2. Direct Company Dossier Modal (?action=view&company_id=123)
      if (action === "view" && companyId) {
        const cId = parseInt(companyId, 10);
        if (!isNaN(cId)) {
          try {
            const res = await fetch(`/api/companies/${cId}`);
            if (res.ok) {
              const companyData = await res.json();
              switchTab("companies");
              openCompanyDetailsModal(companyData);
            }
          } catch (e) {
            console.warn("[DeepLink] Failed to load company details:", e);
          }
        }
        return;
      }

      // 3. Filter Directory by City and/or Tech and/or Search Query
      if (city || tech || q) {
        switchTab("companies");
        const filterTerms = [city, tech, q].filter(Boolean);

        // City and tech are ID filters (dropdowns below); only ?q= is free-text search.
        if (filterInput && q) {
          filterInput.value = q;
        }

        // Dropdown values are slugs (exact keys the server maps to IDs).
        const toSlug = (v) => v.toLowerCase().trim().replace(/[^\w\s-]/g, "").replace(/[\s_]+/g, "-");
        if (city && filterCitySelect) {
          filterCitySelect.value = toSlug(city);
          if (typeof ddFilterCity !== "undefined" && ddFilterCity) {
            ddFilterCity.setValue(toSlug(city));
          }
        }

        if (tech && filterTechSelect) {
          filterTechSelect.value = toSlug(tech);
          if (typeof ddFilterTech !== "undefined" && ddFilterTech) {
            ddFilterTech.setValue(toSlug(tech));
          }
        }

        companiesCurrentPage = 1;
        fetchCompanies(false);
        showToast(`Filtered directory for ${filterTerms.join(", ")}`, "info");
      }

      // 4. Filter Directory by Domain (?domain=it or ?domain=pharma)
      if (domain) {
        switchTab("companies");
        setDomainFilter(domain);
      }
    } catch (err) {
      console.warn("[DeepLink] Error executing deep-linked action:", err);
    }
  }

  // Initial Data Load & Render Lucide Icons
  refreshIcons();
  checkAuthStatus();
  fetchCompanies().finally(() => {
    handleDeepLinkedActions();
  });
});
