/*
 * Background scroll lock for every modal / overlay.
 *
 * Any full-screen overlay (an element with both `fixed` and `inset-0` classes)
 * that is currently visible locks the page behind it. New modals are picked up
 * automatically, so nothing has to be registered by id.
 *
 * Paired CSS in style.css: `html.scroll-locked` and overscroll containment.
 */
(function () {
  "use strict";

  const root = document.documentElement;
  let locked = false;

  function isVisible(el) {
    // Judge by computed style, not the `hidden` class: some overlays keep the
    // class and are shown by a CSS override (e.g. #mobile-sidebar-overlay.active).
    const cs = window.getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return false;
    // Closed fade-style overlays are click-through. Opacity is not checked:
    // modals fade in from opacity 0, which would read as "closed".
    if (cs.pointerEvents === "none") return false;
    return el.getClientRects().length > 0;
  }

  function anyOverlayOpen() {
    const overlays = document.querySelectorAll(".fixed.inset-0");
    for (const el of overlays) {
      if (isVisible(el)) return true;
    }
    return false;
  }

  function apply(shouldLock) {
    if (shouldLock === locked) return;
    locked = shouldLock;
    if (shouldLock) {
      // Keep the layout from jumping when the scrollbar disappears.
      const gap = window.innerWidth - root.clientWidth;
      root.style.setProperty("--scroll-lock-gap", gap > 0 ? gap + "px" : "0px");
      root.classList.add("scroll-locked");
    } else {
      root.classList.remove("scroll-locked");
      root.style.removeProperty("--scroll-lock-gap");
    }
  }

  function refresh() {
    apply(anyOverlayOpen());
  }

  // Run right away. MutationObserver callbacks are already batched per task,
  // and timers/rAF get throttled or paused in background tabs, which left the
  // lock unapplied. The check itself only looks at a handful of overlays.
  function schedule() {
    refresh();
  }

  function start() {
    refresh();
    try {
      new MutationObserver(schedule).observe(document.body, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ["class", "style", "hidden"],
      });
    } catch (_) {}
    // Overlays that fade in/out with CSS transitions finish after the class change.
    document.addEventListener("transitionend", schedule, true);
    document.addEventListener("animationend", schedule, true);
    window.addEventListener("resize", schedule);
  }

  window.ScrollLock = { refresh: refresh };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
