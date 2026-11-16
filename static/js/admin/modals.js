/* OutreachPilot admin: Opening and closing admin modals.
   Moved unchanged out of static/js/admin.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before admin.js. */

// --- Modal Helpers with Non-Scrollable Background Enforcement ---
// Shared lock in static/js/scroll-lock.js watches every overlay; this just
// asks it to re-check immediately after a modal opens or closes.
function updateBodyScrollLock() {
  if (window.ScrollLock) window.ScrollLock.refresh();
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
