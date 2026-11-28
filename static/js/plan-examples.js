/* "See example" popovers on plan cards: hover on desktop (CSS), tap to open or close anywhere. */
(function () {
  function closeAll(except) {
    document.querySelectorAll(".ex-wrap.is-open").forEach(function (w) {
      if (w !== except) {
        w.classList.remove("is-open");
        var b = w.querySelector(".ex-btn");
        if (b) b.setAttribute("aria-expanded", "false");
      }
    });
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".ex-btn") : null;
    if (!btn) {
      if (!(e.target.closest && e.target.closest(".ex-pop"))) closeAll(null);
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    var wrap = btn.closest(".ex-wrap");
    closeAll(wrap);
    var open = !wrap.classList.contains("is-open");
    wrap.classList.toggle("is-open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAll(null); });
})();
