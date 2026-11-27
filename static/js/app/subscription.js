/* OutreachPilot app: Plan badge, quota meters and the plan cards in the subscription modal.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

// --- Subscription & Daily Quota Controller ---
function updateUserSubscriptionUI(data) {
  if (!data) return;
  const isMaster = !!data.is_master_admin;
  const isKillSwitch = !!data.subscription_kill_switch;
  const tierCode = isKillSwitch && !isMaster ? "temp_user" : (data.subscription_tier || "free");
  const tierName = data.subscription_tier_name || (isMaster ? "Master Admin" : (isKillSwitch ? "Temp User (Unlimited Applications)" : (tierCode === "pro" ? "Job Seeker Pro" : tierCode === "premium_plus" ? "Premium+" : "Free Job Seeker")));
  const totalLimit = (isMaster || isKillSwitch) ? 999999 : (typeof data.daily_pitch_limit === "number" ? data.daily_pitch_limit : 10);
  const sentToday = typeof data.pitches_sent_today === "number" ? data.pitches_sent_today : 0;
  const remaining = (isMaster || isKillSwitch) ? 999999 : (typeof data.pitches_remaining === "number" ? data.pitches_remaining : Math.max(0, totalLimit - sentToday));

  // Emails the user can still send today; app.js caps Outreach Hub selections to it.
  // Guests are not capped here: sending asks them to sign in first.
  window.__quotaRemaining = (isMaster || isKillSwitch || data.is_logged_in === false) ? Infinity : remaining;

  const totalLimitStr = (isMaster || isKillSwitch) ? "∞" : String(totalLimit);
  const remainingStr = (isMaster || isKillSwitch) ? "∞" : String(remaining);
  const pct = (isMaster || isKillSwitch) ? 100 : (totalLimit > 0 ? Math.min(100, Math.max(0, Math.round((remaining / totalLimit) * 100))) : 0);

  // If Kill Switch is active, ensure DOM elements are suppressed
  if (isKillSwitch) {
    const hw = document.getElementById("header-quota-widget");
    if (hw) hw.classList.add("hidden");
    const sc = document.getElementById("sidebar-quota-card");
    if (sc) sc.classList.add("hidden");
  }

  // 1. Header Quota Widget
  const headerTierBadge = document.getElementById("user-header-tier-badge");
  const headerRemaining = document.getElementById("user-header-quota-remaining");
  const headerTotal = document.getElementById("user-header-quota-total");
  const headerBar = document.getElementById("user-header-quota-bar");

  if (headerTierBadge) headerTierBadge.textContent = tierName;
  if (headerRemaining) headerRemaining.textContent = remainingStr;
  if (headerTotal) headerTotal.textContent = totalLimitStr;
  if (headerBar) {
    headerBar.style.width = `${pct}%`;
    // Unlimited quota has no meaningful progress; hide the bar track so it
    // doesn't render as a solid filled block. Use inline display (not the
    // "hidden" class) so it isn't overridden by the track's sm:block utility.
    if (headerBar.parentElement) headerBar.parentElement.style.display = (isMaster || isKillSwitch) ? "none" : "";
  }

  // 2. Sidebar Quota Card
  const sidebarTierBadge = document.getElementById("sidebar-tier-badge");
  const sidebarRemaining = document.getElementById("sidebar-quota-remaining");
  const sidebarTotal = document.getElementById("sidebar-quota-total");
  const sidebarBar = document.getElementById("sidebar-quota-progress");

  if (sidebarTierBadge) sidebarTierBadge.textContent = tierName;
  if (sidebarRemaining) sidebarRemaining.textContent = remainingStr;
  if (sidebarTotal) sidebarTotal.textContent = totalLimitStr;
  if (sidebarBar) {
    sidebarBar.style.width = `${pct}%`;
    if (sidebarBar.parentElement) sidebarBar.parentElement.style.display = (isMaster || isKillSwitch) ? "none" : "";
  }

  // 3. Subscription & Quota Modal
  const subModalTierBadge = document.getElementById("sub-modal-tier-badge");
  const subModalTierTitle = document.getElementById("sub-modal-tier-title");
  const subModalRemaining = document.getElementById("sub-modal-remaining-count");
  const subModalTotal = document.getElementById("sub-modal-total-limit");

  if (subModalTierBadge) subModalTierBadge.textContent = tierName;
  if (subModalTierTitle) subModalTierTitle.textContent = tierName;
  if (subModalRemaining) subModalRemaining.textContent = remainingStr;
  if (subModalTotal) subModalTotal.textContent = totalLimitStr;

  // Mark the current plan's card (cards come from the admin plans, see index.html).
  // Other cards keep their own "Upgrade to" / "Switch to" link; recomputed on
  // every call so a plan change moves the mark instead of leaving two.
  document.querySelectorAll("[data-tier-card]").forEach(card => {
    const cardCode = card.getAttribute("data-tier-card");
    const btn = card.querySelector(".btn-tier-action");
    const isCurrent = cardCode === tierCode || (isMaster && cardCode === "premium_plus");
    card.classList.toggle("ring-2", isCurrent);
    card.classList.toggle("ring-primary", isCurrent);
    if (!btn || btn.dataset.static) return;  // fixed notes (Free card) keep their text
    btn.textContent = isCurrent ? "Current Active Plan" : (btn.dataset.defaultLabel || btn.textContent);
    if (isCurrent) {
      btn.removeAttribute("href");
      btn.setAttribute("aria-disabled", "true");
    } else {
      if (btn.dataset.href) btn.setAttribute("href", btn.dataset.href);
      btn.removeAttribute("aria-disabled");
    }
    ["opacity-60", "cursor-default", "pointer-events-none"].forEach(c => btn.classList.toggle(c, isCurrent));
  });
}
