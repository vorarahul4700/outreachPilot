/* OutreachPilot app: Page buttons for the company and outreach lists.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

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
  mobileWrapper.className = "pg-mobile";

  const prevBtnMobile = document.createElement("button");
  prevBtnMobile.type = "button";
  prevBtnMobile.className = `pg-btn${safeCurrentPage <= 1 ? ' is-disabled' : ''}`;
  prevBtnMobile.innerHTML = `<i data-lucide="chevron-left" class="w-3.5 h-3.5"></i>`;
  prevBtnMobile.disabled = safeCurrentPage <= 1;
  prevBtnMobile.addEventListener("click", () => {
    if (safeCurrentPage > 1) onPageChange(safeCurrentPage - 1);
  });

  const pageInfoMobile = document.createElement("span");
  pageInfoMobile.className = "pg-info";
  pageInfoMobile.textContent = `${safeCurrentPage} / ${totalPages}`;

  const nextBtnMobile = document.createElement("button");
  nextBtnMobile.type = "button";
  nextBtnMobile.className = `pg-btn${safeCurrentPage >= totalPages ? ' is-disabled' : ''}`;
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
  desktopWrapper.className = "pg-desktop";

  const prevBtnDesktop = document.createElement("button");
  prevBtnDesktop.type = "button";
  prevBtnDesktop.className = `pg-btn${safeCurrentPage <= 1 ? ' is-disabled' : ''}`;
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
      dots.className = "pg-dots";
      dots.textContent = "...";
      desktopWrapper.appendChild(dots);
    } else {
      const btn = document.createElement("button");
      btn.type = "button";
      const isActive = (p === safeCurrentPage);
      btn.className = `pg-btn${isActive ? ' is-current' : ''}`;
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
  nextBtnDesktop.className = `pg-btn${safeCurrentPage >= totalPages ? ' is-disabled' : ''}`;
  nextBtnDesktop.innerHTML = `<span>Next</span><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>`;
  nextBtnDesktop.disabled = safeCurrentPage >= totalPages;
  nextBtnDesktop.addEventListener("click", () => {
    if (safeCurrentPage < totalPages) onPageChange(safeCurrentPage + 1);
  });
  desktopWrapper.appendChild(nextBtnDesktop);

  buttonsEl.appendChild(desktopWrapper);
  refreshIcons();
}
