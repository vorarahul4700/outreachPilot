// OutreachPilot Frontend Application Controller
document.addEventListener("DOMContentLoaded", () => {
  
  // State
  let companies = [];
  let pollInterval = null;
  let activeTab = "companies";
  let currentViewMode = "grid";
  let isMasterAdmin = false;
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
    html = html.replace(/^### (.*$)/gim, '<h4 class="text-indigo-300 font-bold text-xs mt-3 mb-1 uppercase tracking-wider">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 class="text-white font-bold text-sm mt-3 mb-1.5">$1</h3>');
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong class="text-white font-semibold">$1</strong>');
    html = html.replace(/^\- (.*$)/gim, '<div class="flex items-start space-x-1.5 my-1 ml-2"><span class="text-indigo-400 font-bold">•</span><span class="text-slate-200">$1</span></div>');
    html = html.replace(/\n\n/gim, '<div class="h-2"></div>');
    html = html.replace(/\n/gim, '<br>');
    return html;
  }

  function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "fixed top-6 left-1/2 -translate-x-1/2 z-[9999] flex flex-col items-center space-y-2.5 pointer-events-none w-[92vw] max-w-lg";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    
    let bgClass = "bg-slate-900/95 border-indigo-500/80 text-indigo-100 shadow-[0_12px_40px_rgba(99,102,241,0.35)]";
    let icon = "info";
    let badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 uppercase tracking-wider shrink-0">Info</span>`;

    if (type === "error") {
      bgClass = "bg-rose-950/95 border-rose-500 text-rose-100 shadow-[0_14px_45px_rgba(244,63,94,0.45)] ring-1 ring-rose-500/50";
      icon = "alert-octagon";
      badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 uppercase tracking-wider shrink-0">Error</span>`;
    } else if (type === "warning") {
      bgClass = "bg-amber-950/95 border-amber-500 text-amber-100 shadow-[0_14px_45px_rgba(245,158,11,0.45)] ring-1 ring-amber-500/50";
      const isAuthPrompt = message.toLowerCase().includes("sign in") || message.toLowerCase().includes("login") || message.toLowerCase().includes("auth");
      icon = isAuthPrompt ? "lock" : "alert-triangle";
      const badgeText = isAuthPrompt ? "Sign In Required" : "Attention";
      badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 uppercase tracking-wider shrink-0">${badgeText}</span>`;
    } else if (type === "success") {
      bgClass = "bg-emerald-950/95 border-emerald-500 text-emerald-100 shadow-[0_14px_45px_rgba(16,185,129,0.4)] ring-1 ring-emerald-500/50";
      icon = "check-circle-2";
      badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 uppercase tracking-wider shrink-0">Success</span>`;
    }

    toast.className = `${bgClass} border rounded-2xl px-4 py-3 flex items-center justify-between space-x-3 text-xs font-medium pointer-events-auto backdrop-blur-md transition-all duration-300 transform -translate-y-4 opacity-0 scale-95 w-full`;
    toast.innerHTML = `
      <div class="flex items-center space-x-2.5 min-w-0">
        <i data-lucide="${icon}" class="w-5 h-5 shrink-0"></i>
        ${badge}
        <span class="break-words leading-snug">${message}</span>
      </div>
      <button type="button" class="toast-close p-1 hover:bg-white/10 rounded-lg text-slate-400 hover:text-white transition shrink-0 cursor-pointer" title="Dismiss">
        <i data-lucide="x" class="w-3.5 h-3.5"></i>
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

  function switchTab(tabId) {
    [tabScout, tabCompanies, tabResume, tabOutreach].forEach(t => t?.classList.remove("active"));
    [secScout, secCompanies, secResume, secOutreach].forEach(s => s?.classList.add("hidden"));

    if (tabId === "scout") {
      tabScout?.classList.add("active");
      secScout?.classList.remove("hidden");
      if (pageTitle) pageTitle.innerHTML = '<i data-lucide="radar" class="w-4 h-4 text-indigo-400 shrink-0"></i><span class="whitespace-nowrap">Find New Leads</span>';
      if (pageSubtitle) pageSubtitle.textContent = "Search Google Maps in real time to find verified local businesses and contact details.";
      updateScoutViewFromInputs();
    } else if (tabId === "companies") {
      tabCompanies?.classList.add("active");
      secCompanies?.classList.remove("hidden");
      if (pageTitle) pageTitle.innerHTML = '<i data-lucide="building-2" class="w-4 h-4 text-sky-400 shrink-0"></i><span class="whitespace-nowrap">All Companies & Leads</span>';
      if (pageSubtitle) pageSubtitle.textContent = "Browse your verified business leads. Filter, sort, view contact details, and prepare outreach.";
      applyCompanyFiltersAndRender();
    } else if (tabId === "resume") {
      tabResume?.classList.add("active");
      secResume?.classList.remove("hidden");
      if (pageTitle) pageTitle.innerHTML = '<i data-lucide="user-check" class="w-4 h-4 text-amber-400 shrink-0"></i><span class="whitespace-nowrap">Candidate Profile & Skills</span>';
      if (pageSubtitle) pageSubtitle.textContent = "Upload your resume to extract skills, experience, and tailor your outreach with AI.";
    } else if (tabId === "outreach") {
      tabOutreach?.classList.add("active");
      secOutreach?.classList.remove("hidden");
      if (pageTitle) pageTitle.innerHTML = '<i data-lucide="mail" class="w-4 h-4 text-rose-400 shrink-0"></i><span class="whitespace-nowrap">1-on-1 Direct Outreach</span>';
      if (pageSubtitle) pageSubtitle.textContent = "Review personalized outreach emails, launch in 1-click, and track sent messages.";
      renderPitchesList();
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

  // View Switcher (Grid vs Table)
  const btnViewGrid = document.getElementById("btn-view-grid");
  const btnViewTable = document.getElementById("btn-view-table");
  const companiesContainer = document.getElementById("companies-container");
  const companiesTableContainer = document.getElementById("companies-table-container");
  const companiesTableBody = document.getElementById("companies-table-body");

  function setViewMode(mode) {
    currentViewMode = mode;
    if (mode === "grid") {
      companiesContainer?.classList.remove("hidden");
      companiesTableContainer?.classList.add("hidden");
      btnViewGrid?.classList.add("bg-slate-800", "text-white");
      btnViewGrid?.classList.remove("text-slate-400");
      btnViewTable?.classList.remove("bg-slate-800", "text-white");
      btnViewTable?.classList.add("text-slate-400");
    } else {
      companiesContainer?.classList.add("hidden");
      companiesTableContainer?.classList.remove("hidden");
      btnViewTable?.classList.add("bg-slate-800", "text-white");
      btnViewTable?.classList.remove("text-slate-400");
      btnViewGrid?.classList.remove("bg-slate-800", "text-white");
      btnViewGrid?.classList.add("text-slate-400");
    }
  }

  if (btnViewGrid) btnViewGrid.addEventListener("click", () => setViewMode("grid"));
  if (btnViewTable) btnViewTable.addEventListener("click", () => setViewMode("table"));

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
  const scoutTableContainer = document.getElementById("scout-table-container");
  const scoutTableBody = document.getElementById("scout-table-body");
  const scoutLeadsCount = document.getElementById("scout-leads-count");
  const scoutQueryLabel = document.getElementById("scout-query-label");
  const btnScoutViewGrid = document.getElementById("btn-scout-view-grid");
  const btnScoutViewTable = document.getElementById("btn-scout-view-table");
  const inputKeyword = document.getElementById("input-keyword");
  const inputCity = document.getElementById("input-city");
  let scoutViewMode = "grid";

  const filterInput = document.getElementById("filter-search");
  const filterKeywordSelect = document.getElementById("filter-keyword-select");
  const filterCitySelect = document.getElementById("filter-city-select");
  const sortSelect = document.getElementById("sort-select");
  const btnFilterEmails = document.getElementById("btn-filter-emails");

  // Companies Directory Pagination State & Elements
  const companiesPagination = document.getElementById("companies-pagination");
  const companiesPageRange = document.getElementById("companies-page-range");
  const companiesPageTotal = document.getElementById("companies-page-total");
  const companiesPerPageSelect = document.getElementById("companies-per-page");
  const companiesPageButtons = document.getElementById("companies-page-buttons");
  let companiesCurrentPage = 1;
  let companiesPerPage = 12;
  let currentFilteredCompanies = [];

  // Scout Leads Pagination State & Elements
  const scoutPagination = document.getElementById("scout-pagination");
  const scoutPageRange = document.getElementById("scout-page-range");
  const scoutPageTotal = document.getElementById("scout-page-total");
  const scoutPerPageSelect = document.getElementById("scout-per-page");
  const scoutPageButtons = document.getElementById("scout-page-buttons");
  let scoutCurrentPage = 1;
  let scoutPerPage = 12;
  let currentScoutList = [];
  let currentScoutQueryLabel = "";
  let liveScrapedResults = [];

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

    if (totalPages <= 1) {
      return;
    }

    // Mobile View (< 640px): Prev, Page X of Y, Next
    const mobileWrapper = document.createElement("div");
    mobileWrapper.className = "flex sm:hidden items-center space-x-1.5";

    const prevBtnMobile = document.createElement("button");
    prevBtnMobile.type = "button";
    prevBtnMobile.className = `p-1.5 rounded-lg text-xs font-medium border border-slate-700 ${safeCurrentPage === 1 ? 'opacity-40 cursor-not-allowed text-slate-500 bg-slate-900' : 'bg-slate-800 text-slate-200 hover:bg-slate-700 cursor-pointer'}`;
    prevBtnMobile.innerHTML = `<i data-lucide="chevron-left" class="w-3.5 h-3.5"></i>`;
    prevBtnMobile.disabled = safeCurrentPage === 1;
    prevBtnMobile.addEventListener("click", () => {
      if (safeCurrentPage > 1) onPageChange(safeCurrentPage - 1);
    });

    const pageInfoMobile = document.createElement("span");
    pageInfoMobile.className = "text-xs font-mono text-slate-300 px-1.5";
    pageInfoMobile.textContent = `${safeCurrentPage} / ${totalPages}`;

    const nextBtnMobile = document.createElement("button");
    nextBtnMobile.type = "button";
    nextBtnMobile.className = `p-1.5 rounded-lg text-xs font-medium border border-slate-700 ${safeCurrentPage === totalPages ? 'opacity-40 cursor-not-allowed text-slate-500 bg-slate-900' : 'bg-slate-800 text-slate-200 hover:bg-slate-700 cursor-pointer'}`;
    nextBtnMobile.innerHTML = `<i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>`;
    nextBtnMobile.disabled = safeCurrentPage === totalPages;
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
    prevBtnDesktop.className = `px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-700 flex items-center space-x-1 ${safeCurrentPage === 1 ? 'opacity-40 cursor-not-allowed text-slate-500 bg-slate-900' : 'bg-slate-800 text-slate-200 hover:bg-slate-700 cursor-pointer'}`;
    prevBtnDesktop.innerHTML = `<i data-lucide="chevron-left" class="w-3.5 h-3.5"></i><span>Prev</span>`;
    prevBtnDesktop.disabled = safeCurrentPage === 1;
    prevBtnDesktop.addEventListener("click", () => {
      if (safeCurrentPage > 1) onPageChange(safeCurrentPage - 1);
    });
    desktopWrapper.appendChild(prevBtnDesktop);

    const pageNumbers = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pageNumbers.push(i);
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
        dots.className = "px-2 py-1 text-xs text-slate-500";
        dots.textContent = "...";
        desktopWrapper.appendChild(dots);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `min-w-[32px] px-2 py-1 rounded-lg text-xs font-medium transition cursor-pointer ${p === safeCurrentPage ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700'}`;
        btn.textContent = p;
        btn.addEventListener("click", () => {
          if (p !== safeCurrentPage) onPageChange(p);
        });
        desktopWrapper.appendChild(btn);
      }
    });

    const nextBtnDesktop = document.createElement("button");
    nextBtnDesktop.type = "button";
    nextBtnDesktop.className = `px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-700 flex items-center space-x-1 ${safeCurrentPage === totalPages ? 'opacity-40 cursor-not-allowed text-slate-500 bg-slate-900' : 'bg-slate-800 text-slate-200 hover:bg-slate-700 cursor-pointer'}`;
    nextBtnDesktop.innerHTML = `<span>Next</span><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>`;
    nextBtnDesktop.disabled = safeCurrentPage === totalPages;
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

  function setScoutViewMode(mode) {
    scoutViewMode = mode;
    if (mode === "grid") {
      scoutCardsContainer?.classList.remove("hidden");
      scoutTableContainer?.classList.add("hidden");
      btnScoutViewGrid?.classList.add("bg-slate-800", "text-white");
      btnScoutViewGrid?.classList.remove("text-slate-400");
      btnScoutViewTable?.classList.remove("bg-slate-800", "text-white");
      btnScoutViewTable?.classList.add("text-slate-400");
    } else {
      scoutCardsContainer?.classList.add("hidden");
      scoutTableContainer?.classList.remove("hidden");
      btnScoutViewTable?.classList.add("bg-slate-800", "text-white");
      btnScoutViewTable?.classList.remove("text-slate-400");
      btnScoutViewGrid?.classList.remove("bg-slate-800", "text-white");
      btnScoutViewGrid?.classList.add("text-slate-400");
    }
    refreshIcons();
  }

  if (btnScoutViewGrid) btnScoutViewGrid.addEventListener("click", () => setScoutViewMode("grid"));
  if (btnScoutViewTable) btnScoutViewTable.addEventListener("click", () => setScoutViewMode("table"));

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
    if (scoutQueryLabel) scoutQueryLabel.textContent = queryLabel || '"IT Companies" in "Surat"';

    if (scoutCardsContainer) scoutCardsContainer.innerHTML = "";
    if (scoutTableBody) scoutTableBody.innerHTML = "";

    if (!list || list.length === 0) {
      if (scoutPagination) scoutPagination.classList.add("hidden");
      if (scoutCardsContainer) {
        scoutCardsContainer.innerHTML = `
          <div class="col-span-full py-12 px-4 text-center bg-slate-900/60 border border-slate-800 rounded-2xl space-y-3">
            <div class="inline-flex p-3 rounded-full bg-indigo-950/60 text-indigo-400 border border-indigo-800/60 shadow-sm">
              <i data-lucide="radar" class="w-6 h-6"></i>
            </div>
            <p class="text-sm font-semibold text-slate-200">Ready to Discover Leads</p>
            <p class="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
              Enter your Target Keyword and Location above, then click <strong class="text-indigo-400">"Find Leads"</strong>. Real-time scraped leads from your search session will appear here instantly.
            </p>
          </div>
        `;
      }
      if (scoutTableBody) {
        scoutTableBody.innerHTML = `
          <tr>
            <td colspan="6" class="py-10 text-center text-slate-400 text-xs">
              <div class="flex flex-col items-center justify-center space-y-1.5">
                <i data-lucide="radar" class="w-5 h-5 text-indigo-400"></i>
                <span class="font-medium text-slate-300">Ready to Discover Leads</span>
                <span class="text-[11px] text-slate-500">Click "Find Leads" above to start real-time lead discovery</span>
              </div>
            </td>
          </tr>
        `;
      }
      setScoutViewMode(scoutViewMode);
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
        ? `<span class="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800 text-[10px] font-semibold flex items-center space-x-1 shrink-0"><i data-lucide="check" class="w-3 h-3 text-emerald-400"></i><span>Contacted</span></span>`
        : (c.is_enriched 
            ? `<span class="px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-400 border border-indigo-800 text-[10px] font-semibold flex items-center space-x-1 shrink-0"><i data-lucide="zap" class="w-3 h-3 text-indigo-400"></i><span>Enriched</span></span>`
            : `<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px] shrink-0">Verified</span>`);

      const ratingDisplay = (c.rating && c.rating > 0)
        ? `<span class="text-amber-400 font-semibold flex items-center space-x-1">
             <i data-lucide="star" class="w-3.5 h-3.5 text-amber-400 fill-amber-400"></i><span>${Number(c.rating).toFixed(1)}</span>
             <span class="text-slate-500 font-normal text-[10px]">(${c.reviews_count || 0})</span>
           </span>`
        : `<span class="text-slate-500 text-[10px]">No ratings</span>`;

      // 1. Scout Lead Card
      if (scoutCardsContainer) {
        const card = document.createElement("div");
        card.className = "scout-lead-card bg-slate-900 border border-slate-800 hover:border-indigo-500/60 rounded-xl p-2.5 sm:p-4 flex flex-col justify-between transition group shadow-sm cursor-pointer relative min-w-0";
        card.innerHTML = `
          <div class="space-y-1.5 pointer-events-none">
            <!-- Top micro row: Badge -->
            <div class="flex items-center justify-between gap-1 pointer-events-auto">
              <div class="flex items-center space-x-1 min-w-0">
                ${badge}
              </div>
            </div>

            <!-- Company Name: Full-width, wraps up to 2 lines -->
            <h4 class="font-bold text-xs sm:text-sm text-white group-hover:text-indigo-400 transition leading-tight break-words pt-0.5" title="${escapeHTML(c.name)}">
              ${escapeHTML(c.name)}
            </h4>

            <!-- Domain Link -->
            <div class="flex items-center space-x-1.5 pt-0.5">
              <a href="${siteUrl}" target="_blank" rel="noopener noreferrer" class="scout-site-link inline-flex items-center space-x-1 px-2 py-0.5 sm:px-2.5 sm:py-1 rounded bg-slate-950 border border-slate-800 hover:border-indigo-600 text-indigo-400 hover:text-indigo-300 text-[10px] sm:text-[11px] font-mono transition max-w-full pointer-events-auto" onclick="event.stopPropagation();" title="Visit ${escapeHTML(c.domain)}">
                <i data-lucide="globe" class="w-3 h-3 sm:w-3.5 sm:h-3.5 shrink-0"></i>
                <span class="break-all">${escapeHTML(c.domain || 'Website')}</span>
                <i data-lucide="external-link" class="w-2.5 h-2.5 sm:w-3 sm:h-3 shrink-0 opacity-70"></i>
              </a>
            </div>

            <!-- Meta: Rating & Phone -->
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between text-[10px] sm:text-xs pt-1 border-t border-slate-800/60 gap-1">
              <div class="flex items-center shrink-0">${ratingDisplay}</div>
              ${c.phone ? `
                <a href="tel:${escapeHTML(c.phone)}" class="text-slate-400 hover:text-white font-mono text-[10px] sm:text-[11px] flex items-center space-x-0.5 whitespace-nowrap pointer-events-auto shrink-0" onclick="event.stopPropagation();" title="Call ${escapeHTML(c.phone)}">
                  <i data-lucide="phone" class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-slate-500 shrink-0"></i>
                  <span>${escapeHTML(c.phone)}</span>
                </a>
              ` : ''}
            </div>

            <!-- Address & Maps -->
            <div class="text-[10px] sm:text-[11px] text-slate-400 flex items-start space-x-1 pointer-events-auto min-w-0">
              <i data-lucide="map-pin" class="w-3 h-3 text-slate-500 shrink-0 mt-0.5"></i>
              <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="hover:text-indigo-400 break-words flex-1 leading-tight" onclick="event.stopPropagation();" title="${escapeHTML(cleanAddr || c.city || 'Google Maps')}">
                ${escapeHTML(cleanAddr || (c.city ? c.city + ', Location' : 'Location'))}
              </a>
            </div>
          </div>

          <!-- Bottom Action Buttons -->
          <div class="pt-2 sm:pt-3 mt-2 sm:mt-3 border-t border-slate-800/80 flex items-center justify-between gap-1.5 sm:gap-2">
            <a href="${siteUrl}" target="_blank" rel="noopener noreferrer" class="flex-1 text-center justify-center px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] sm:text-[11px] font-medium transition flex items-center space-x-1" onclick="event.stopPropagation();">
              <span>Site</span>
              <i data-lucide="external-link" class="w-2.5 h-2.5 sm:w-3 sm:h-3"></i>
            </a>
            <button type="button" class="btn-scout-card-enrich flex-1 text-center justify-center px-2 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] sm:text-[11px] font-semibold transition flex items-center space-x-1 shadow-sm">
              <span>Enrich with AI</span>
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

      // 2. Scout Table Row
      if (scoutTableBody) {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-800/40 transition cursor-pointer";
        tr.innerHTML = `
          <td class="py-3 px-4">
            <div class="font-semibold text-white truncate max-w-[180px]">${escapeHTML(c.name)}</div>
            <div class="text-[10px] text-slate-500">${c.city ? escapeHTML(c.city) : 'Scouted'}</div>
          </td>
          <td class="py-3 px-4">
            <a href="${siteUrl}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center space-x-1 text-indigo-400 hover:text-indigo-300 font-mono text-[11px]" onclick="event.stopPropagation();">
              <span class="truncate max-w-[140px]">${escapeHTML(c.domain || 'Visit Site')}</span>
              <i data-lucide="external-link" class="w-3 h-3"></i>
            </a>
          </td>
          <td class="py-3 px-4 text-slate-400 text-[11px] truncate max-w-[200px]">
            <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="hover:text-indigo-400" onclick="event.stopPropagation();">
              ${escapeHTML(cleanAddr || c.city || '-')}
            </a>
          </td>
          <td class="py-3 px-4 text-slate-400 font-mono text-[11px]">${escapeHTML(c.phone || '-')}</td>
          <td class="py-3 px-4">${ratingDisplay}</td>
          <td class="py-3 px-4 text-right">
            <button type="button" class="btn-scout-row-enrich px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition" onclick="event.stopPropagation();">
              View & Enrich
            </button>
          </td>
        `;

        tr.addEventListener("click", () => openCompanyDetailsModal(c));
        const btnRow = tr.querySelector(".btn-scout-row-enrich");
        if (btnRow) {
          btnRow.addEventListener("click", (e) => {
            e.stopPropagation();
            openCompanyDetailsModal(c);
          });
        }

        scoutTableBody.appendChild(tr);
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

    setScoutViewMode(scoutViewMode);
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
    const kwDisplay = inputKeyword?.value?.trim() || "IT Companies";
    const cityDisplay = inputCity?.value?.trim() || "Surat";

    // Find Leads tab ONLY shows live real-time scraped leads from current session
    if (liveScrapedResults && liveScrapedResults.length > 0) {
      renderScoutResults(liveScrapedResults, `Discovered Leads: "${kwDisplay}" in "${cityDisplay}"`);
    } else {
      renderScoutResults([], `Ready to Search: "${kwDisplay}" in "${cityDisplay}"`);
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
    // 1. All Genuine Card
    if (!activeMetricFilter || activeMetricFilter === "all") {
      statCardAll?.classList.add("ring-2", "ring-emerald-500/70", "border-emerald-500/80", "bg-emerald-950/20");
      statCardAll?.classList.remove("border-slate-800");
      const pill = statCardAll?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Active";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-emerald-300 bg-emerald-900/60 border border-emerald-700/60 transition";
      }
    } else {
      statCardAll?.classList.remove("ring-2", "ring-emerald-500/70", "border-emerald-500/80", "bg-emerald-950/20");
      statCardAll?.classList.add("border-slate-800");
      const pill = statCardAll?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "All";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-slate-500 group-hover:text-slate-300 bg-slate-950/60 border border-slate-800 transition";
      }
    }

    // 2. Enriched Card
    if (activeMetricFilter === "enriched") {
      statCardEnriched?.classList.add("ring-2", "ring-indigo-500/70", "border-indigo-500/80", "bg-indigo-950/30");
      statCardEnriched?.classList.remove("border-slate-800");
      const pill = statCardEnriched?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Active";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-indigo-200 bg-indigo-900/60 border border-indigo-700/60 transition";
      }
    } else {
      statCardEnriched?.classList.remove("ring-2", "ring-indigo-500/70", "border-indigo-500/80", "bg-indigo-950/30");
      statCardEnriched?.classList.add("border-slate-800");
      const pill = statCardEnriched?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Filter";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-slate-500 group-hover:text-indigo-300 bg-slate-950/60 border border-slate-800 transition";
      }
    }

    // 3. Emails Card & Toolbar Button
    if (activeMetricFilter === "emails") {
      statCardEmails?.classList.add("ring-2", "ring-emerald-500/70", "border-emerald-500/80", "bg-emerald-950/30");
      statCardEmails?.classList.remove("border-slate-800");
      const pill = statCardEmails?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Active";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-emerald-200 bg-emerald-900/60 border border-emerald-700/60 transition";
      }
      btnFilterEmails?.classList.add("bg-emerald-950/80", "text-emerald-300", "border-emerald-700");
      btnFilterEmails?.classList.remove("bg-slate-950", "text-slate-400");
    } else {
      statCardEmails?.classList.remove("ring-2", "ring-emerald-500/70", "border-emerald-500/80", "bg-emerald-950/30");
      statCardEmails?.classList.add("border-slate-800");
      const pill = statCardEmails?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Filter";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-slate-500 group-hover:text-emerald-300 bg-slate-950/60 border border-slate-800 transition";
      }
      btnFilterEmails?.classList.remove("bg-emerald-950/80", "text-emerald-300", "border-emerald-700");
      btnFilterEmails?.classList.add("bg-slate-950", "text-slate-400");
    }

    // 4. Contacted Card
    if (activeMetricFilter === "contacted") {
      statCardContacted?.classList.add("ring-2", "ring-sky-500/70", "border-sky-500/80", "bg-sky-950/30");
      statCardContacted?.classList.remove("border-slate-800");
      const pill = statCardContacted?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Active";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-sky-200 bg-sky-900/60 border border-sky-700/60 transition";
      }
    } else {
      statCardContacted?.classList.remove("ring-2", "ring-sky-500/70", "border-sky-500/80", "bg-sky-950/30");
      statCardContacted?.classList.add("border-slate-800");
      const pill = statCardContacted?.querySelector(".stat-pill");
      if (pill) {
        pill.textContent = "Filter";
        pill.className = "stat-pill text-[9px] px-1.5 py-0.5 rounded font-mono text-slate-500 group-hover:text-sky-300 bg-slate-950/60 border border-slate-800 transition";
      }
    }

    // 5. Invalid Card
    if (activeMetricFilter === "invalid") {
      statCardInvalid?.classList.add("ring-2", "ring-rose-500/70", "border-rose-500/80", "bg-rose-950/40");
      if (statInvalidHint) statInvalidHint.textContent = "Active (Click to reset)";
    } else {
      statCardInvalid?.classList.remove("ring-2", "ring-rose-500/70", "border-rose-500/80", "bg-rose-950/40");
      if (statInvalidHint) statInvalidHint.textContent = "Click to filter";
    }
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
      btnModeAdmin?.classList.add("bg-indigo-600", "text-white");
      btnModeAdmin?.classList.remove("text-slate-400");
      btnModePreview?.classList.remove("bg-amber-600", "text-white");
      btnModePreview?.classList.add("text-slate-400");
      adminPreviewBanner?.classList.add("hidden");
      statCardInvalid?.classList.remove("hidden");
    } else {
      btnModePreview?.classList.add("bg-amber-600", "text-white");
      btnModePreview?.classList.remove("text-slate-400");
      btnModeAdmin?.classList.remove("bg-indigo-600", "text-white");
      btnModeAdmin?.classList.add("text-slate-400");
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
  if (statCardContacted) statCardContacted.addEventListener("click", () => setActiveMetricFilter("contacted"));
  if (statCardInvalid) statCardInvalid.addEventListener("click", () => setActiveMetricFilter("invalid"));

  async function handleInvalidateCompany(id, companyName) {
    try {
      const res = await fetch(`/api/companies/${id}/invalidate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Excluded by Master Admin" })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        await fetchCompanies();
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
    try {
      const res = await fetch(`/api/companies/${id}/restore`, {
        method: "POST"
      });
      const data = await res.json();
      if (res.ok && data.success) {
        await fetchCompanies();
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

  function updateCompanyMetrics(list) {
    const validList = list.filter(c => !c.is_invalid);
    const total = validList.length;
    const enriched = validList.filter(c => c.is_enriched).length;
    const withEmails = validList.filter(c => c.emails && c.emails.length > 0).length;
    const contacted = validList.filter(c => c.already_contacted).length;

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

    const statContacted = document.getElementById("stat-contacted-count");
    if (statContacted) statContacted.textContent = contacted;

    if (statInvalidCount) statInvalidCount.textContent = invalidCount;

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

  function applyCompanyFiltersAndRender(resetPage = true) {
    if (resetPage) {
      companiesCurrentPage = 1;
    }
    const q = (filterInput?.value || "").trim().toLowerCase();
    const selectedKeyword = (filterKeywordSelect?.value || "").trim().toLowerCase();
    const selectedCity = (filterCitySelect?.value || "").trim().toLowerCase();
    let filtered = companies;

    // 1. Master Admin Invalid Leads Filtering
    if (activeMetricFilter === "invalid") {
      filtered = filtered.filter(c => c.is_invalid);
    } else {
      filtered = filtered.filter(c => !c.is_invalid);
    }

    // 2. Active Metric Card Filter
    if (activeMetricFilter === "enriched") {
      filtered = filtered.filter(c => c.is_enriched);
    } else if (activeMetricFilter === "emails") {
      filtered = filtered.filter(c => c.emails && c.emails.length > 0);
    } else if (activeMetricFilter === "contacted") {
      filtered = filtered.filter(c => c.already_contacted);
    }

    // 3. Filter by Scout Keyword / AI-Normalized Category
    if (selectedKeyword) {
      filtered = filtered.filter(c => {
        const normKw = (c.normalized_keyword || "").toLowerCase();
        const rawKw = (c.search_keyword || "").toLowerCase();
        const srcQuery = (c.source_query || "").toLowerCase();
        return normKw === selectedKeyword || rawKw === selectedKeyword || srcQuery.includes(selectedKeyword);
      });
    }

    // 4. Filter by City
    if (selectedCity) {
      filtered = filtered.filter(c => {
        const compCity = (c.city || "").toLowerCase();
        const addr = (c.address || "").toLowerCase();
        const srcQuery = (c.source_query || "").toLowerCase();
        return compCity === selectedCity || addr.includes(selectedCity) || srcQuery.includes(selectedCity);
      });
    }

    // 5. Filter by Search Query
    if (q) {
      filtered = filtered.filter(c => 
        (c.name || "").toLowerCase().includes(q) || 
        (c.domain || "").toLowerCase().includes(q) ||
        (c.address || "").toLowerCase().includes(q) ||
        (c.city || "").toLowerCase().includes(q) ||
        (c.normalized_keyword || "").toLowerCase().includes(q) ||
        (c.source_query || "").toLowerCase().includes(q) ||
        (c.profile && c.profile.summary && c.profile.summary.toLowerCase().includes(q)) ||
        (c.emails && c.emails.some(em => em.toLowerCase().includes(q)))
      );
    }

    renderCompanies(filtered);
  }

  if (filterKeywordSelect) {
    filterKeywordSelect.addEventListener("change", applyCompanyFiltersAndRender);
  }

  if (filterCitySelect) {
    filterCitySelect.addEventListener("change", applyCompanyFiltersAndRender);
  }

  if (btnFilterEmails) {
    btnFilterEmails.addEventListener("click", () => {
      setActiveMetricFilter("emails");
    });
  }

  async function fetchCompanies() {
    try {
      const res = await fetch("/api/companies");
      const data = await res.json();
      companies = data.companies || [];
      invalidCount = data.invalid_count || 0;
      if (typeof data.is_master_admin === "boolean") {
        isMasterAdmin = data.is_master_admin;
      }

      // Populate available AI-normalized keywords dropdown dynamically
      if (filterKeywordSelect && data.available_keywords) {
        const curVal = filterKeywordSelect.value;
        const opts = ['<option value="">All Keywords</option>'];
        data.available_keywords.forEach(kw => {
          opts.push(`<option value="${kw}">${kw}</option>`);
        });
        filterKeywordSelect.innerHTML = opts.join('');
        filterKeywordSelect.value = curVal;
      }

      // Populate available cities dropdown dynamically
      if (filterCitySelect && data.available_cities) {
        const curCityVal = filterCitySelect.value;
        const cityOpts = ['<option value="">All Cities</option>'];
        data.available_cities.forEach(city => {
          cityOpts.push(`<option value="${city}">${city}</option>`);
        });
        filterCitySelect.innerHTML = cityOpts.join('');
        filterCitySelect.value = curCityVal;
      }

      updateCompanyMetrics(companies);
      updateMetricCardStyles();
      applyCompanyFiltersAndRender();
      updateScoutViewFromInputs();
      if (activeTab === "outreach") {
        renderPitchesList();
      }
    } catch (err) {
      console.error("Failed to load companies:", err);
    }
  }

  function renderCompanies(list) {
    currentFilteredCompanies = list || [];

    if (companiesContainer) companiesContainer.innerHTML = "";
    if (companiesTableBody) companiesTableBody.innerHTML = "";

    if (!list || list.length === 0) {
      if (companiesPagination) companiesPagination.classList.add("hidden");
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
          <div class="col-span-full py-12 text-center text-slate-500 bg-slate-900/50 border border-slate-800 rounded-2xl">
            <p class="text-sm font-medium">${emptyTitle}</p>
            <p class="text-xs text-slate-600 mt-1">${emptyMsg}</p>
          </div>
        `;
      }
      if (companiesTableBody) {
        companiesTableBody.innerHTML = `
          <tr>
            <td colspan="6" class="py-8 text-center text-slate-500">${emptyMsg}</td>
          </tr>
        `;
      }
      return;
    }

    const sortedList = sortCompaniesList(list);
    const totalItems = sortedList.length;
    const totalPages = companiesPerPage > 0 ? Math.ceil(totalItems / companiesPerPage) : 1;
    companiesCurrentPage = Math.min(Math.max(1, companiesCurrentPage), totalPages);

    const pagedList = companiesPerPage > 0
      ? sortedList.slice((companiesCurrentPage - 1) * companiesPerPage, companiesCurrentPage * companiesPerPage)
      : sortedList;

    pagedList.forEach(c => {
      // 1. Grid Card
      if (companiesContainer) {
        const card = document.createElement("div");

        if (c.is_invalid) {
          // Invalid Lead Grid Card Styling
          card.className = "company-card-invalid bg-slate-900 border border-rose-900/60 hover:border-rose-600 rounded-xl p-3 sm:p-4 flex flex-col justify-between transition group shadow-sm cursor-pointer relative min-w-0";
          card.innerHTML = `
            <div class="space-y-2 pointer-events-none">
              <div class="flex items-start justify-between gap-1.5">
                <h4 class="font-bold text-xs sm:text-sm text-white group-hover:text-rose-400 transition flex items-center space-x-1.5 break-words flex-1">
                  <span>${escapeHTML(c.name)}</span>
                </h4>
                <span class="px-1.5 sm:px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 text-[9px] sm:text-[10px] font-bold flex items-center space-x-1 shrink-0">
                  <i data-lucide="shield-alert" class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-rose-400"></i>
                  <span>INVALID</span>
                </span>
              </div>
              <div class="text-[10px] sm:text-[11px] text-rose-300/90 bg-rose-950/40 p-2 rounded-lg border border-rose-900/50 space-y-0.5">
                <div class="flex items-center space-x-1 font-semibold text-rose-400 text-[9px] sm:text-[10px] uppercase tracking-wider">
                  <i data-lucide="alert-circle" class="w-3 h-3"></i>
                  <span>Excluded</span>
                </div>
                <p class="break-words leading-tight">${escapeHTML(c.invalid_reason || 'Excluded by Admin')}</p>
                ${c.invalid_at ? `<p class="text-[9px] sm:text-[10px] text-slate-400 font-mono">Date: ${escapeHTML(c.invalid_at)}</p>` : ''}
              </div>
              <div class="text-[10px] sm:text-[11px] font-mono text-slate-400 flex items-center space-x-1 break-all">
                <i data-lucide="globe" class="w-3 h-3 text-slate-500 shrink-0"></i>
                <span>${escapeHTML(c.domain)}</span>
              </div>
            </div>

            <div class="pt-2 sm:pt-3 mt-2 sm:mt-3 border-t border-rose-900/50 flex items-center justify-end">
              <button class="btn-single-restore w-full text-center justify-center text-[11px] sm:text-xs px-2 sm:px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition flex items-center space-x-1 shadow-sm cursor-pointer" data-id="${c.id}" title="Restore company to active directory">
                <i data-lucide="rotate-ccw" class="w-3 h-3"></i>
                <span>Restore Lead</span>
              </button>
            </div>
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
          const badge = c.already_contacted 
            ? `<span onclick="event.stopPropagation(); window.viewSentEmailForCompany(${c.id})" class="px-2 py-0.5 rounded bg-sky-950/80 hover:bg-sky-900 text-sky-400 border border-sky-800 text-[10px] font-semibold flex items-center space-x-1 shrink-0 cursor-pointer transition shadow-sm" title="Click to view message sent"><i data-lucide="check" class="w-3 h-3 text-sky-400"></i><span>Contacted ${c.contacted_at || ''}</span></span>`
            : (c.is_enriched 
                ? `<span class="px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-400 border border-indigo-800 text-[10px] font-semibold flex items-center space-x-1 shrink-0"><i data-lucide="zap" class="w-3 h-3 text-indigo-400"></i><span>Enriched</span></span>`
                : `<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px] shrink-0">Verified</span>`);

          const ratingDisplay = (c.rating && c.rating > 0)
            ? `<span class="text-amber-400 font-semibold flex items-center space-x-1">
                 <i data-lucide="star" class="w-3.5 h-3.5 text-amber-400 fill-amber-400 shrink-0"></i><span>${Number(c.rating).toFixed(1)}</span>
                 <span class="text-slate-500 font-normal text-[10px]">(${c.reviews_count || 0})</span>
               </span>`
            : `<span class="text-slate-500 text-[10px]">No ratings yet</span>`;

          const adminDeleteBtn = (isMasterAdmin && adminViewMode === "admin")
            ? `<button class="btn-single-invalidate text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 p-1 rounded transition cursor-pointer" data-id="${c.id}" title="Mark company as invalid (Master Admin)"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>`
            : '';

          const cardCleanAddr = cleanAddressText(c.address);
          const cardMapsUrl = c.location_url || buildMapsUrl(c.name, cardCleanAddr, c.city || "");

          card.className = "company-card bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-xl p-2.5 sm:p-4 flex flex-col justify-between transition group shadow-sm cursor-pointer relative min-w-0";
          card.innerHTML = `
            <div class="space-y-1.5 pointer-events-none">
              <!-- Top micro row: Badge & Admin Action -->
              <div class="flex items-center justify-between gap-1 pointer-events-auto">
                <div class="flex items-center space-x-1 overflow-hidden min-w-0">
                  ${badge}
                </div>
                ${adminDeleteBtn}
              </div>

              <!-- Company Name: Full width, wraps up to 2 lines so it is NEVER truncated to 2 letters! -->
              <h4 class="font-bold text-xs sm:text-sm text-white group-hover:text-indigo-400 transition leading-tight break-words pt-0.5" title="${escapeHTML(c.name)}">
                ${escapeHTML(c.name)}
              </h4>

              <!-- Domain Link -->
              <div class="flex items-center space-x-1.5 pt-0.5">
                <a href="${c.website_url || 'https://' + c.domain}" target="_blank" rel="noopener noreferrer" class="company-site-link inline-flex items-center space-x-1 px-2 py-0.5 sm:px-2.5 sm:py-1 rounded bg-slate-950 border border-slate-800 hover:border-indigo-600 text-indigo-400 hover:text-indigo-300 text-[10px] sm:text-[11px] font-mono transition max-w-full pointer-events-auto" onclick="event.stopPropagation();" title="Visit ${escapeHTML(c.domain)}">
                  <i data-lucide="globe" class="w-3 h-3 sm:w-3.5 sm:h-3.5 shrink-0"></i>
                  <span class="break-all">${escapeHTML(c.domain)}</span>
                  <i data-lucide="external-link" class="w-2.5 h-2.5 sm:w-3 sm:h-3 shrink-0 opacity-70"></i>
                </a>
              </div>

              <!-- Meta: Rating & Phone -->
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between text-[10px] sm:text-xs pt-1 border-t border-slate-800/60 gap-1">
                <div class="flex items-center shrink-0">${ratingDisplay}</div>
                ${c.phone ? `
                  <a href="tel:${escapeHTML(c.phone)}" class="text-slate-400 hover:text-white font-mono text-[10px] sm:text-[11px] flex items-center space-x-0.5 whitespace-nowrap pointer-events-auto shrink-0" onclick="event.stopPropagation();" title="Call ${escapeHTML(c.phone)}">
                    <i data-lucide="phone" class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-slate-500 shrink-0"></i>
                    <span>${escapeHTML(c.phone)}</span>
                  </a>
                ` : ''}
              </div>

              <!-- Keyword & City Badges -->
              <div class="flex items-center gap-1 flex-wrap pt-0.5">
                ${c.normalized_keyword ? `<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] sm:text-[10px] font-medium bg-indigo-950/70 text-indigo-300 border border-indigo-800/60 leading-tight">${escapeHTML(c.normalized_keyword)}</span>` : ''}
                ${c.city ? `<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] sm:text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700/60 leading-tight"><i data-lucide="map-pin" class="w-2 h-2 mr-0.5 text-slate-400 shrink-0"></i><span>${escapeHTML(c.city)}</span></span>` : ''}
              </div>

              <!-- Address & Maps -->
              ${cardMapsUrl ? `
                <div class="text-[10px] sm:text-[11px] text-slate-400 flex items-start space-x-1 pointer-events-auto min-w-0">
                  <i data-lucide="map-pin" class="w-3 h-3 text-slate-500 shrink-0 mt-0.5"></i>
                  <a href="${cardMapsUrl}" target="_blank" rel="noopener noreferrer" class="hover:text-indigo-400 break-words flex-1 leading-tight" onclick="event.stopPropagation()" title="${escapeHTML(cardCleanAddr || 'Google Maps')}">
                    ${escapeHTML(cardCleanAddr || (c.city ? c.city + ', Location' : 'Google Maps Location'))}
                  </a>
                </div>
              ` : ''}

              <!-- Discovered Emails -->
              ${c.emails && c.emails.length > 0 ? `
                <div class="text-[10px] sm:text-[11px] text-emerald-400 font-mono flex items-start space-x-1 min-w-0">
                  <i data-lucide="mail" class="w-3 h-3 text-emerald-400 shrink-0 mt-0.5"></i>
                  <span class="break-all leading-tight">${escapeHTML(c.emails[0])}${c.emails.length > 1 ? ` (+${c.emails.length - 1})` : ''}</span>
                </div>
              ` : ''}

              <!-- AI Profile Summary (if enriched) -->
              ${c.profile ? `
                <div class="pt-1.5 border-t border-slate-800/80">
                  <p class="text-[10px] sm:text-xs text-slate-300 line-clamp-2 leading-relaxed">${escapeHTML(c.profile.summary)}</p>
                  <div class="flex flex-wrap gap-1 mt-1">
                    ${(c.profile.tech_stack || []).slice(0, 2).map(t => `<span class="px-1.5 py-0.2 rounded text-[9px] sm:text-[10px] bg-slate-800 text-slate-300 border border-slate-700 font-mono">${escapeHTML(t)}</span>`).join('')}
                  </div>
                </div>
              ` : ''}
            </div>

            <!-- Bottom Action Buttons: 50/50 flex-1 compact -->
            <div class="pt-2 sm:pt-3 mt-2 sm:mt-3 border-t border-slate-800/80 flex items-center justify-between gap-1.5 sm:gap-2">
              <button class="btn-single-enrich flex-1 text-center justify-center text-[10px] sm:text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center space-x-1 cursor-pointer min-w-0" data-id="${c.id}" title="${c.is_enriched ? 'Re-crawl and re-enrich subpages' : 'Deep enrich subpages with AI'}">
                <i data-lucide="${c.is_enriched ? 'refresh-cw' : 'zap'}" class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-slate-300 shrink-0"></i>
                <span>${c.is_enriched ? 'Re-Enrich' : 'Enrich with AI'}</span>
              </button>
              <button class="btn-single-pitch flex-1 text-center justify-center text-[10px] sm:text-xs px-2 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition flex items-center space-x-1 cursor-pointer shadow-sm min-w-0" data-id="${c.id}" title="Generate personalized outreach email">
                <i data-lucide="send" class="w-2.5 h-2.5 sm:w-3 sm:h-3 shrink-0"></i>
                <span>Send Email</span>
              </button>
            </div>
          `;

          const btnEnrich = card.querySelector(".btn-single-enrich");
          const btnPitch = card.querySelector(".btn-single-pitch");
          const btnInvalidate = card.querySelector(".btn-single-invalidate");
          if (btnEnrich) {
            btnEnrich.addEventListener("click", (e) => {
              e.stopPropagation();
              handleSingleEnrich(btnEnrich, c.id);
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

        card.addEventListener("click", (e) => {
          if (e.target.closest("button") || e.target.closest("a")) return;
          openCompanyDetailsModal(c);
        });
        companiesContainer.appendChild(card);
      }

      // 2. Table Row
      if (companiesTableBody) {
        const tr = document.createElement("tr");

        if (c.is_invalid) {
          tr.className = "company-row-invalid hover:bg-rose-950/20 transition cursor-pointer";
          tr.innerHTML = `
            <td class="px-4 py-3 font-semibold text-rose-300">
              <div class="flex items-center space-x-2">
                <span class="line-through opacity-70">${escapeHTML(c.name)}</span>
              </div>
            </td>
            <td class="px-4 py-3 font-mono text-slate-400">
              <a href="${c.website_url || 'https://' + c.domain}" target="_blank" class="hover:underline flex items-center space-x-1" onclick="event.stopPropagation()">
                <i data-lucide="globe" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
                <span>${escapeHTML(c.domain)}</span>
              </a>
            </td>
            <td class="px-4 py-3 text-rose-400 text-[11px]">
              ${escapeHTML(c.invalid_reason || 'Excluded by Master Admin')}
            </td>
            <td class="px-4 py-3 text-emerald-400 font-mono text-[11px]">
              ${c.emails && c.emails.length > 0 ? c.emails.map(e => escapeHTML(e)).join(", ") : '<span class="text-slate-600">No emails</span>'}
            </td>
            <td class="px-4 py-3">
              <span class="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 text-[10px] font-bold">INVALID</span>
            </td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end space-x-1.5" onclick="event.stopPropagation()">
                <button class="btn-row-restore px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-[11px] transition flex items-center space-x-1 cursor-pointer" data-id="${c.id}">
                  <i data-lucide="rotate-ccw" class="w-3 h-3"></i>
                  <span>Restore</span>
                </button>
              </div>
            </td>
          `;

          const btnRowRestore = tr.querySelector(".btn-row-restore");
          if (btnRowRestore) {
            btnRowRestore.addEventListener("click", (e) => {
              e.stopPropagation();
              handleRestoreCompany(c.id, c.name);
            });
          }

        } else {
          const badge = c.already_contacted 
            ? `<span onclick="event.stopPropagation(); window.viewSentEmailForCompany(${c.id})" class="px-2 py-0.5 rounded bg-sky-950/80 hover:bg-sky-900 text-sky-400 border border-sky-800 text-[10px] font-semibold flex items-center space-x-1 cursor-pointer transition shadow-sm" title="Click to view message sent"><i data-lucide="check" class="w-3 h-3 text-sky-400"></i><span>Contacted ${c.contacted_at || ''}</span></span>`
            : (c.is_enriched 
                ? `<span class="px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-400 border border-indigo-800 text-[10px] font-semibold flex items-center space-x-1"><i data-lucide="zap" class="w-3 h-3 text-indigo-400"></i><span>Enriched</span></span>`
                : `<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px]">Scouted</span>`);

          const adminTableRowAction = (isMasterAdmin && adminViewMode === "admin")
            ? `<button class="btn-row-invalidate p-1 text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 rounded transition cursor-pointer" data-id="${c.id}" title="Mark as Invalid Lead (Admin)"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>`
            : '';

          const rowCleanAddr = cleanAddressText(c.address);
          const rowMapsUrl = c.location_url || buildMapsUrl(c.name, rowCleanAddr, c.city);

          tr.className = "hover:bg-slate-800/40 transition cursor-pointer";
          tr.innerHTML = `
            <td class="px-4 py-3 font-semibold text-white">
              <div class="flex items-center space-x-2">
                <span>${escapeHTML(c.name)}</span>
              </div>
              <div class="flex items-center gap-1 mt-1 flex-wrap font-normal">
                ${c.normalized_keyword ? `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-medium bg-indigo-950/70 text-indigo-300 border border-indigo-800/60">${escapeHTML(c.normalized_keyword)}</span>` : ''}
                ${c.city ? `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-medium bg-slate-800 text-slate-300 border border-slate-700/60"><i data-lucide="map-pin" class="w-2 h-2 mr-0.5 text-slate-400"></i>${escapeHTML(c.city)}</span>` : ''}
              </div>
            </td>
            <td class="px-4 py-3 font-mono text-indigo-400">
              <a href="${c.website_url || 'https://' + c.domain}" target="_blank" class="hover:underline flex items-center space-x-1" onclick="event.stopPropagation()">
                <i data-lucide="globe" class="w-3.5 h-3.5 text-indigo-400 shrink-0"></i>
                <span>${escapeHTML(c.domain)}</span>
              </a>
            </td>
            <td class="px-4 py-3">
              ${c.rating > 0 ? `<span class="text-amber-400 font-semibold flex items-center space-x-1"><i data-lucide="star" class="w-3 h-3 text-amber-400 fill-amber-400"></i><span>${Number(c.rating).toFixed(1)}</span> <span class="text-slate-500 text-[10px]">(${c.reviews_count || 0})</span></span>` : '<span class="text-slate-500">N/A</span>'}
            </td>
            <td class="px-4 py-3 text-slate-300">
              <div>${c.phone ? escapeHTML(c.phone) : '<span class="text-slate-600">No phone</span>'}</div>
              ${rowMapsUrl ? `
                <div class="text-[11px] break-words flex items-center space-x-1 mt-0.5" onclick="event.stopPropagation()">
                  <i data-lucide="map-pin" class="w-3 h-3 text-slate-500 shrink-0"></i>
                  <a href="${rowMapsUrl}" target="_blank" class="text-slate-400 hover:text-indigo-400 hover:underline break-words" title="Open in Google Maps">
                    ${escapeHTML(rowCleanAddr || 'Google Maps Location')}
                  </a>
                </div>
              ` : ''}
            </td>
            <td class="px-4 py-3">${badge}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end space-x-1.5" onclick="event.stopPropagation()">
                <button class="btn-row-enrich px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-[11px] transition flex items-center space-x-1 cursor-pointer" data-id="${c.id}" title="Enrich Profile">
                  <i data-lucide="${c.is_enriched ? 'refresh-cw' : 'zap'}" class="w-3 h-3"></i>
                  <span>${c.is_enriched ? 'Re-Enrich' : 'Enrich'}</span>
                </button>
                <button class="btn-row-pitch px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-[11px] transition flex items-center space-x-1 cursor-pointer shadow-sm" data-id="${c.id}">
                  <i data-lucide="send" class="w-3 h-3"></i>
                  <span>Pitch</span>
                </button>
                ${adminTableRowAction}
              </div>
            </td>
          `;

          const btnRowEnrich = tr.querySelector(".btn-row-enrich");
          const btnRowPitch = tr.querySelector(".btn-row-pitch");
          const btnRowInvalidate = tr.querySelector(".btn-row-invalidate");
          if (btnRowEnrich) {
            btnRowEnrich.addEventListener("click", (e) => {
              e.stopPropagation();
              handleSingleEnrich(btnRowEnrich, c.id);
            });
          }
          if (btnRowPitch) {
            btnRowPitch.addEventListener("click", (e) => {
              e.stopPropagation();
              handleGeneratePitch(c.id);
            });
          }
          if (btnRowInvalidate) {
            btnRowInvalidate.addEventListener("click", (e) => {
              e.stopPropagation();
              handleInvalidateCompany(c.id, c.name);
            });
          }
        }

        tr.addEventListener("click", () => openCompanyDetailsModal(c));
        companiesTableBody.appendChild(tr);
      }
    });

    renderPaginationControls({
      paginationEl: companiesPagination,
      rangeEl: companiesPageRange,
      totalEl: companiesPageTotal,
      buttonsEl: companiesPageButtons,
      totalItems: totalItems,
      currentPage: companiesCurrentPage,
      pageSize: companiesPerPage,
      onPageChange: (newPage) => {
        companiesCurrentPage = newPage;
        renderCompanies(currentFilteredCompanies);
        if (companiesContainer) {
          companiesContainer.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });

    refreshIcons();
  }

  if (companiesPerPageSelect) {
    companiesPerPageSelect.addEventListener("change", (e) => {
      companiesPerPage = parseInt(e.target.value, 10);
      companiesCurrentPage = 1;
      renderCompanies(currentFilteredCompanies);
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
      cmodalTabBtnOverview?.classList.add("active", "bg-indigo-600", "text-white", "shadow-sm");
      cmodalTabBtnOverview?.classList.remove("text-slate-400", "hover:text-white", "hover:bg-slate-900");
      cmodalTabBtnAi?.classList.remove("active", "bg-indigo-600", "text-white", "shadow-sm");
      cmodalTabBtnAi?.classList.add("text-slate-400", "hover:text-white", "hover:bg-slate-900");
      cmodalPanelOverview?.classList.remove("hidden");
      cmodalPanelAi?.classList.add("hidden");
    } else {
      cmodalTabBtnAi?.classList.add("active", "bg-indigo-600", "text-white", "shadow-sm");
      cmodalTabBtnAi?.classList.remove("text-slate-400", "hover:text-white", "hover:bg-slate-900");
      cmodalTabBtnOverview?.classList.remove("active", "bg-indigo-600", "text-white", "shadow-sm");
      cmodalTabBtnOverview?.classList.add("text-slate-400", "hover:text-white", "hover:bg-slate-900");
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

    // Master Admin Invalidate / Restore Button in Modal
    if (isMasterAdmin && adminViewMode === "admin") {
      cmodalBtnAdminAction?.classList.remove("hidden");
      if (company.is_invalid) {
        cmodalBtnAdminAction.className = "px-3 py-2 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 cursor-pointer bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm";
        cmodalBtnAdminAction.innerHTML = `<i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i><span>Restore Lead</span>`;
        cmodalBtnAdminAction.onclick = () => handleRestoreCompany(company.id, company.name);
      } else {
        cmodalBtnAdminAction.className = "px-3 py-2 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 cursor-pointer bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300";
        cmodalBtnAdminAction.innerHTML = `<i data-lucide="trash-2" class="w-3.5 h-3.5 text-rose-400"></i><span>Mark as Invalid</span>`;
        cmodalBtnAdminAction.onclick = () => handleInvalidateCompany(company.id, company.name);
      }
    } else {
      cmodalBtnAdminAction?.classList.add("hidden");
    }

    // Status Badge
    cmodalBadge.onclick = null;
    cmodalBadge.removeAttribute("title");
    if (company.is_invalid) {
      cmodalBadge.className = "px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 text-[10px] font-bold flex items-center space-x-1";
      cmodalBadge.innerHTML = `<i data-lucide="shield-alert" class="w-3 h-3 text-rose-400"></i><span>INVALID LEAD</span>`;
    } else if (company.already_contacted) {
      cmodalBadge.className = "px-2 py-0.5 rounded bg-sky-950 hover:bg-sky-900 text-sky-400 border border-sky-800 text-[10px] font-semibold flex items-center space-x-1 cursor-pointer transition shadow-sm";
      cmodalBadge.title = "Click to view message sent";
      cmodalBadge.innerHTML = `<i data-lucide="check" class="w-3 h-3 text-sky-400"></i><span>Contacted ${company.contacted_at || ''}</span>`;
      cmodalBadge.onclick = () => window.viewSentEmailForCompany(company.id);
    } else if (company.is_enriched) {
      cmodalBadge.className = "px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800 text-[10px] font-semibold flex items-center space-x-1";
      cmodalBadge.innerHTML = `<i data-lucide="zap" class="w-3 h-3 text-indigo-400"></i><span>AI Enriched</span>`;
    } else {
      cmodalBadge.className = "px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px]";
      cmodalBadge.textContent = "Verified Lead";
    }

    // Discovered Emails
    const emails = company.emails || [];
    cmodalEmailsCount.textContent = `${emails.length} discovered`;
    if (emails.length > 0) {
      cmodalEmailsContainer.innerHTML = emails.map(em => `
        <div class="flex items-center space-x-2 px-2.5 py-1 bg-slate-900 border border-slate-700 rounded-lg text-emerald-400 font-mono text-xs">
          <i data-lucide="mail" class="w-3.5 h-3.5 text-emerald-400 shrink-0"></i>
          <span class="break-all">${escapeHTML(em)}</span>
          <button class="text-slate-400 hover:text-white copy-em-btn text-xs ml-1 p-0.5 rounded hover:bg-slate-800 flex items-center" data-email="${escapeHTML(em)}" title="Copy email">
            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      `).join("");

      cmodalEmailsContainer.querySelectorAll(".copy-em-btn").forEach(b => {
        b.addEventListener("click", () => {
          navigator.clipboard.writeText(b.dataset.email);
          b.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i>`;
          refreshIcons();
          setTimeout(() => {
            b.innerHTML = `<i data-lucide="copy" class="w-3.5 h-3.5"></i>`;
            refreshIcons();
          }, 1500);
        });
      });
    } else {
      cmodalEmailsContainer.innerHTML = `<span class="text-slate-500 italic">No direct emails discovered yet. Click "Enrich with AI" below.</span>`;
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
          <span class="px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-indigo-300 text-xs font-medium">${escapeHTML(tech)}</span>
        `).join("");
      } else {
        cmodalTechstack.innerHTML = `<span class="text-slate-500 italic text-[11px]">General modern web stack</span>`;
      }

      if (company.profile.detailed_analysis) {
        cmodalDetailedAnalysis.dataset.rawText = company.profile.detailed_analysis;
        cmodalDetailedAnalysis.innerHTML = formatMarkdown(company.profile.detailed_analysis);
      } else {
        cmodalDetailedAnalysis.dataset.rawText = "";
        cmodalDetailedAnalysis.innerHTML = `<span class="text-slate-400 italic">Click 'Enrich with AI' below to generate comprehensive intelligence report.</span>`;
      }
    } else {
      cmodalSummary.textContent = "Not enriched yet. Click 'Enrich with AI' below to analyze company details and detect tech stack.";
      cmodalIndustry.textContent = "Pending Analysis";
      cmodalTone.textContent = "Pending Analysis";
      cmodalTechstack.innerHTML = `<span class="text-slate-500 italic text-[11px]">Run enrichment to identify tech stack.</span>`;
      cmodalDetailedAnalysis.dataset.rawText = "";
      cmodalDetailedAnalysis.innerHTML = `<span class="text-slate-400 italic">Not enriched yet. Click 'Enrich with AI' below to generate comprehensive intelligence report.</span>`;
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

  if (sortSelect) {
    sortSelect.addEventListener("change", applyCompanyFiltersAndRender);
  }

  if (btnLoadCompanies) {
    btnLoadCompanies.addEventListener("click", (e) => {
      e.preventDefault();
      btnLoadCompanies.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Loading...</span>`;
      refreshIcons();
      fetchCompanies().finally(() => {
        btnLoadCompanies.innerHTML = `<i data-lucide="refresh-cw" class="w-3.5 h-3.5 text-slate-300"></i><span>Refresh</span>`;
        refreshIcons();
      });
    });
  }

  async function handleScoutStart(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    scoutCurrentPage = 1;
    liveScrapedResults = [];
    const keyword = (document.getElementById("input-keyword")?.value || "").trim();
    const city = (document.getElementById("input-city")?.value || "").trim();
    const direct_url = (document.getElementById("input-url")?.value || "").trim();
    const max_pages = parseInt(document.getElementById("input-pages")?.value || "2", 10);
    const gl = document.getElementById("input-gl")?.value || "in";
    const hl = document.getElementById("input-hl")?.value || "en";

    renderScoutResults([], `Searching: "${keyword || 'Companies'}" in "${city || 'Location'}"`);

    scoutMonitor.classList.remove("hidden");
    monitorProgressBar.style.width = "8%";
    monitorStatus.textContent = `Initializing browser engine for "${keyword || 'Companies'} ${city}"...`;
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

        monitorStatus.textContent = data.status_message || "Scraping & AI Enriching...";
        monitorCount.textContent = `${data.total_results || 0} Found`;
        monitorProgressBar.style.width = `${Math.min(100, Math.max(8, data.progress || 0))}%`;

        // Real-time terminal log console stream
        if (scoutTerminalLogs && Array.isArray(data.logs) && data.logs.length > 0) {
          scoutTerminalLogs.innerHTML = data.logs.map(l => `<div class="break-all font-mono leading-relaxed">${escapeHTML(l)}</div>`).join('');
          scoutTerminalLogs.scrollTop = scoutTerminalLogs.scrollHeight;
        }

        // Real-time stream of live scraped cards while browser is discovering them
        if (Array.isArray(data.results) && data.results.length > 0) {
          liveScrapedResults = data.results;
          const activeKw = inputKeyword?.value?.trim() || "IT Companies";
          const activeCity = inputCity?.value?.trim() || "Surat";
          renderScoutResults(liveScrapedResults, data.is_running 
            ? `Live Cloud Scouting: "${activeKw}" in "${activeCity}"`
            : `Discovered Leads: "${activeKw}" in "${activeCity}"`);
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
          const activeKw = inputKeyword?.value?.trim() || "IT Companies";
          const activeCity = inputCity?.value?.trim() || "Surat";
          if (liveScrapedResults && liveScrapedResults.length > 0) {
            renderScoutResults(liveScrapedResults, `Discovered ${liveScrapedResults.length} Leads for "${activeKw}" in "${activeCity}"`);
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
  let currentUser = (window.__INITIAL_AUTH__ && typeof window.__INITIAL_AUTH__.is_logged_in === "boolean")
    ? window.__INITIAL_AUTH__
    : { is_logged_in: false, email: null };
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

      if (currentUser.is_logged_in) {
        authBoxLoggedIn?.classList.remove("hidden");
        authBoxLoggedOut?.classList.add("hidden");
        if (userDisplayEmail) userDisplayEmail.textContent = currentUser.email || "Verified User";
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
        document.cookie = `pilot_user_email=${data.email}; path=/; max-age=2592000; SameSite=Lax`;
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
    btnModalAdminLogin.addEventListener("click", () => performDemoLogin({ as_admin: true, email: "vorarahul111@gmail.com" }));
  }
  if (btnSidebarAdminLogin) {
    btnSidebarAdminLogin.addEventListener("click", () => performDemoLogin({ as_admin: true, email: "vorarahul111@gmail.com" }));
  }
  if (btnHeaderAdminLogin) {
    btnHeaderAdminLogin.addEventListener("click", () => performDemoLogin({ as_admin: true, email: "vorarahul111@gmail.com" }));
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
      if (!companies || companies.length === 0) {
        showToast("No companies found to generate pitches for.", "warning");
        return;
      }
      const oldText = btnGenAllPitches.innerHTML;
      btnGenAllPitches.disabled = true;

      for (let i = 0; i < companies.length; i++) {
        const comp = companies[i];
        btnGenAllPitches.innerHTML = `<i data-lucide="sparkles" class="w-3.5 h-3.5 text-amber-300 animate-pulse"></i><span>Generating (${i + 1}/${companies.length})...</span>`;
        refreshIcons();
        try {
          await fetch("/api/pitch/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_id: comp.id })
          });
        } catch (err) {
          console.error("Pitch error for", comp.name, err);
        }
      }
      btnGenAllPitches.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span>Pitches Generated!</span>`;
      refreshIcons();
      renderPitchesList();
      setTimeout(() => {
        btnGenAllPitches.innerHTML = oldText;
        btnGenAllPitches.disabled = false;
        refreshIcons();
      }, 2500);
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
        const pitchEl = document.getElementById("profile-pitch");
        if (pitchEl && data.profile.elevator_pitch) {
          pitchEl.textContent = data.profile.elevator_pitch;
        }

        const skillsContainer = document.getElementById("profile-skills");
        if (skillsContainer && data.profile.top_skills) {
          skillsContainer.innerHTML = data.profile.top_skills.map(s => `
            <span class="px-2.5 py-1 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800 text-xs font-medium">${escapeHTML(s)}</span>
          `).join("");
        }

        const achContainer = document.getElementById("profile-achievements");
        if (achContainer && data.profile.key_achievements) {
          achContainer.innerHTML = data.profile.key_achievements.map(a => `
            <li>${escapeHTML(a)}</li>
          `).join("");
        }

        const detailedAnalysisEl = document.getElementById("profile-detailed-analysis");
        if (detailedAnalysisEl && data.profile.detailed_profile_analysis) {
          detailedAnalysisEl.dataset.rawText = data.profile.detailed_profile_analysis;
          detailedAnalysisEl.innerHTML = formatMarkdown(data.profile.detailed_profile_analysis);
        }
      }
    } catch (err) {
      console.warn("Could not load candidate profile:", err);
    }
  }

  resumeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    requireLogin(async () => {
      const hasFile = fileInput.files && fileInput.files.length > 0;
      const resumeLink = (document.getElementById("input-resume-link")?.value || "").trim();
      const targetRole = document.getElementById("input-target-role").value.trim();

      if (!hasFile && !resumeLink) {
        showToast("Please select a resume file (PDF or TXT) or enter a portfolio/resume link.", "warning");
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
          document.getElementById("profile-pitch").textContent = data.profile.elevator_pitch || "Candidate Profile Active";
          
          const skillsContainer = document.getElementById("profile-skills");
          skillsContainer.innerHTML = (data.profile.top_skills || []).map(s => `
            <span class="px-2.5 py-1 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800 text-xs font-medium">${escapeHTML(s)}</span>
          `).join("");

          const achContainer = document.getElementById("profile-achievements");
          achContainer.innerHTML = (data.profile.key_achievements || []).map(a => `
            <li>${escapeHTML(a)}</li>
          `).join("");

          const detailedAnalysisEl = document.getElementById("profile-detailed-analysis");
          if (detailedAnalysisEl && data.profile.detailed_profile_analysis) {
            detailedAnalysisEl.dataset.rawText = data.profile.detailed_profile_analysis;
            detailedAnalysisEl.innerHTML = formatMarkdown(data.profile.detailed_profile_analysis);
          }

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
          btnCopyProfileAnalysis.innerHTML = `<i data-lucide="copy" class="w-3.5 h-3.5 text-indigo-400"></i><span>Copy Analysis</span>`;
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

  modalClose.addEventListener("click", () => modal.classList.add("hidden"));

  async function handleGeneratePitch(companyId) {
    const triggerBtn = document.querySelector(`.btn-gen-pitch-row[data-id="${companyId}"]`);
    const origHtml = triggerBtn ? triggerBtn.innerHTML : "";
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Preparing...</span>`;
      refreshIcons();
    }
    try {
      const res = await fetch("/api/pitch/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: companyId })
      });
      if (res.status === 401) {
        currentUser.is_logged_in = false;
        showToast("Please sign in with Google to generate personalized outreach pitches.", "warning");
        showLoginModal("Please sign in with Google to generate personalized outreach pitches.");
        return;
      }
      const data = await res.json();
      if (data.success) {
        currentPitchId = data.pitch_id;
        modalCompanyName.textContent = `Personalized Outreach for ${data.company_name}`;
        modalTargetEmail.textContent = `To: ${data.target_email}`;
        modalSubject.value = data.subject_line || "";
        modalBody.value = data.email_body || "";
        btnLaunchGmail.href = data.gmail_web_url;

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
    }
  }

  if (btnSendDirectOauth) {
    btnSendDirectOauth.addEventListener("click", async () => {
      if (!currentPitchId) return;

      btnSendDirectOauth.disabled = true;
      btnSendDirectOauth.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Sending via Gmail...</span>`;
      refreshIcons();

      try {
        const res = await fetch(`/api/pitch/${currentPitchId}/send-direct`, {
          method: "POST"
        });
        const data = await res.json();
        if (data.success) {
          showToast("Email sent directly through your authorized Gmail account!", "success");
          modal.classList.add("hidden");
          await fetchCompanies();
          fetchAuditLogs();
        } else {
          showToast(data.detail || data.error || "Failed to send email via Google OAuth.", "error");
        }
      } catch (err) {
        showToast("Email sending failed: " + err.message, "error");
      } finally {
        btnSendDirectOauth.disabled = false;
        btnSendDirectOauth.innerHTML = `<i data-lucide="send" class="w-3.5 h-3.5"></i><span id="btn-send-direct-text">Send via Gmail</span>`;
        refreshIcons();
      }
    });
  }

  btnLaunchGmail.addEventListener("click", async () => {
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
  let outreachCurrentPage = 1;
  let outreachPerPage = 10;
  let outreachActiveFilter = "all"; // "all" | "emails" | "ready" | "sent"
  let outreachSearchQuery = "";

  const outreachSearchInput = document.getElementById("outreach-search-input");
  const outreachFilterAll = document.getElementById("outreach-filter-all");
  const outreachFilterEmails = document.getElementById("outreach-filter-emails");
  const outreachFilterReady = document.getElementById("outreach-filter-ready");
  const outreachFilterSent = document.getElementById("outreach-filter-sent");

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

  function updateOutreachPillStyles() {
    const pills = [
      { id: "all", el: outreachFilterAll },
      { id: "emails", el: outreachFilterEmails },
      { id: "ready", el: outreachFilterReady },
      { id: "sent", el: outreachFilterSent }
    ];
    pills.forEach(p => {
      if (!p.el) return;
      if (p.id === outreachActiveFilter) {
        p.el.className = "outreach-pill active px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white transition cursor-pointer shadow-sm whitespace-nowrap shrink-0 focus:outline-none";
      } else {
        p.el.className = "outreach-pill px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white bg-slate-950 border border-slate-800 transition cursor-pointer whitespace-nowrap shrink-0 focus:outline-none";
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

  function renderPitchesList() {
    const container = document.getElementById("pitches-container");
    const countSpan = document.getElementById("pitches-count");
    if (!container) return;
    container.innerHTML = "";

    // Base genuine leads
    const validCompanies = (companies || []).filter(c => !c.is_invalid);

    // Compute metric counts
    const totalCount = validCompanies.length;
    const emailsCount = validCompanies.filter(c => c.emails && c.emails.length > 0).length;
    const readyCount = validCompanies.filter(c => !c.already_contacted).length;
    const sentCount = validCompanies.filter(c => c.already_contacted).length;

    // Update Quick Metric Strip
    if (outreachCountTotal) outreachCountTotal.textContent = totalCount.toLocaleString();
    if (outreachCountEmails) outreachCountEmails.textContent = emailsCount.toLocaleString();
    if (outreachCountReady) outreachCountReady.textContent = readyCount.toLocaleString();
    if (outreachCountSent) outreachCountSent.textContent = sentCount.toLocaleString();

    // Update filter badge counts
    document.querySelectorAll(".outreach-badge-all").forEach(el => el.textContent = totalCount);
    document.querySelectorAll(".outreach-badge-emails").forEach(el => el.textContent = emailsCount);
    document.querySelectorAll(".outreach-badge-ready").forEach(el => el.textContent = readyCount);
    document.querySelectorAll(".outreach-badge-sent").forEach(el => el.textContent = sentCount);

    if (totalCount === 0) {
      if (countSpan) countSpan.textContent = "0";
      container.innerHTML = `
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center space-y-2">
          <i data-lucide="building" class="w-8 h-8 text-slate-500 mx-auto"></i>
          <p class="text-xs font-semibold text-slate-300">No companies available for outreach</p>
          <p class="text-[11px] text-slate-500">Scout verified businesses in Step 1 or check your All Companies directory first.</p>
        </div>
      `;
      if (outreachPagination) outreachPagination.classList.add("hidden");
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

    // Filter by Search Query
    if (outreachSearchQuery) {
      filtered = filtered.filter(c => {
        const nameMatch = c.name && c.name.toLowerCase().includes(outreachSearchQuery);
        const domainMatch = c.domain && c.domain.toLowerCase().includes(outreachSearchQuery);
        const emailMatch = c.emails && c.emails.some(e => e.toLowerCase().includes(outreachSearchQuery));
        const cityMatch = c.city && c.city.toLowerCase().includes(outreachSearchQuery);
        return nameMatch || domainMatch || emailMatch || cityMatch;
      });
    }

    if (countSpan) countSpan.textContent = filtered.length.toLocaleString();

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center space-y-2">
          <i data-lucide="mail-search" class="w-8 h-8 text-slate-500 mx-auto"></i>
          <p class="text-xs font-semibold text-slate-300">No matching outreach targets</p>
          <p class="text-[11px] text-slate-500">Try adjusting your search query or switching filter tabs.</p>
        </div>
      `;
      if (outreachPagination) outreachPagination.classList.add("hidden");
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

    pageItems.forEach(c => {
      const card = document.createElement("div");
      card.className = "bg-slate-900 border border-slate-800 hover:border-slate-700/80 rounded-xl p-3 sm:p-3.5 transition shadow-sm";
      
      const hasDirectEmail = c.emails && c.emails.length > 0;
      const targetDisplay = hasDirectEmail ? escapeHTML(c.emails[0]) : ('contact@' + escapeHTML(c.domain));

      const emailBadge = hasDirectEmail 
        ? `<span class="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800 text-[10px] font-semibold flex items-center space-x-1 shrink-0"><i data-lucide="at-sign" class="w-3 h-3 text-emerald-400"></i><span>Direct Email</span></span>`
        : `<span class="px-2 py-0.5 rounded bg-slate-950 text-slate-500 border border-slate-800 text-[10px] flex items-center space-x-1 shrink-0"><i data-lucide="globe" class="w-3 h-3 text-slate-500"></i><span>Company Domain</span></span>`;

      const statusBadge = c.already_contacted 
        ? `<button onclick="window.viewSentEmailForCompany(${c.id})" class="px-2 py-0.5 rounded bg-sky-950 hover:bg-sky-900 text-sky-400 border border-sky-800 text-[10px] font-semibold flex items-center space-x-1 shrink-0 cursor-pointer transition shadow-sm" title="Click to view message sent"><i data-lucide="check" class="w-3 h-3 text-sky-400"></i><span>Sent ${c.contacted_at ? escapeHTML(c.contacted_at) : ''}</span></button>`
        : `<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px] font-medium border border-slate-700 shrink-0">Not Contacted</span>`;

      card.innerHTML = `
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <div class="min-w-0 flex-1 space-y-1">
            <div class="flex items-center space-x-2 flex-wrap gap-y-1">
              <h4 class="font-bold text-xs sm:text-sm text-white break-words">${escapeHTML(c.name)}</h4>
              <div class="flex items-center space-x-1 shrink-0">
                ${statusBadge}
                ${emailBadge}
              </div>
            </div>
            <div class="flex items-center space-x-1.5 text-[11px] sm:text-xs text-slate-400 font-mono flex-wrap">
              <i data-lucide="mail" class="w-3 h-3 text-indigo-400 shrink-0"></i>
              <span class="text-slate-500 shrink-0">Recipient:</span>
              <span class="${hasDirectEmail ? 'text-emerald-400 font-medium' : 'text-slate-300'} break-all">${targetDisplay}</span>
              ${c.domain ? `<span class="text-slate-600 hidden md:inline">|</span><span class="text-slate-500 hidden md:inline break-all">${escapeHTML(c.domain)}</span>` : ''}
            </div>
          </div>

          <div class="flex items-center space-x-2 shrink-0 pt-1 sm:pt-0">
            ${c.already_contacted ? `
              <button onclick="window.viewSentEmailForCompany(${c.id})" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-400 rounded-lg text-xs font-semibold transition flex items-center justify-center space-x-1.5 cursor-pointer shadow-sm" title="View email sent to this company">
                <i data-lucide="eye" class="w-3.5 h-3.5"></i>
                <span>View Sent</span>
              </button>
            ` : ''}
            <button class="btn-gen-pitch-row w-full sm:w-auto px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition flex items-center justify-center space-x-1.5 cursor-pointer shadow-sm active:scale-95" data-id="${c.id}">
              <i data-lucide="send" class="w-3.5 h-3.5"></i>
              <span>${c.already_contacted ? 'Send Follow-up' : 'Review & Send Email'}</span>
            </button>
          </div>
        </div>
      `;

      card.querySelector(".btn-gen-pitch-row").addEventListener("click", () => handleGeneratePitch(c.id));
      container.appendChild(card);
    });

    // Render pagination controls
    renderPaginationControls({
      paginationEl: outreachPagination,
      rangeEl: outreachPageRange,
      totalEl: outreachPageTotal,
      buttonsEl: outreachPageButtons,
      totalItems: filtered.length,
      currentPage: outreachCurrentPage,
      pageSize: outreachPerPage,
      onPageChange: (newPage) => {
        outreachCurrentPage = newPage;
        renderPitchesList();
        const pipelineHeader = document.getElementById("outreach-pipeline-header");
        if (pipelineHeader) pipelineHeader.scrollIntoView({ behavior: "smooth", block: "start" });
      }
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
          logsContainer.innerHTML = `<p class="text-slate-500 italic">Sign in to view your sent outreach history.</p>`;
        }
        return;
      }
      const data = await res.json();
      const logsContainer = document.getElementById("audit-logs");
      if (!logsContainer) return;
      if (!data.logs || data.logs.length === 0) {
        logsContainer.innerHTML = `<p class="text-slate-500 italic">No emails sent yet today.</p>`;
        return;
      }

      window._cachedAuditLogs = data.logs;

      logsContainer.innerHTML = data.logs.map((l, idx) => `
        <div onclick="window._openCachedLog(${idx})" class="bg-slate-950 border border-slate-800 hover:border-sky-500/60 rounded-lg p-2.5 space-y-1 transition cursor-pointer group shadow-sm select-none" title="Click to view message sent">
          <div class="flex items-center justify-between">
            <span class="font-bold text-slate-200 group-hover:text-sky-300 transition truncate">${escapeHTML(l.company_name)}</span>
            <span class="text-[10px] text-sky-400 font-semibold uppercase bg-sky-950/60 border border-sky-800/80 px-1.5 py-0.2 rounded shrink-0">${escapeHTML(l.delivery_method)}</span>
          </div>
          <p class="text-[11px] font-mono text-slate-400 truncate">To: ${escapeHTML(l.recipient_email)}</p>
          <div class="flex items-center justify-between text-[10px] text-slate-500 pt-0.5">
            <span>${escapeHTML(l.sent_at)}</span>
            <span class="text-indigo-400 group-hover:text-indigo-300 font-medium flex items-center space-x-0.5">
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

  // Initial Data Load & Render Lucide Icons
  refreshIcons();
  checkAuthStatus();
  loadCandidateProfile();
  fetchCompanies();
  fetchAuditLogs();
});
