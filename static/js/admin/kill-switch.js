/* OutreachPilot admin: Shows the subscription kill switch state on the overview and plans tabs.
   Moved unchanged out of static/js/admin.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before admin.js. */

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
