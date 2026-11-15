/* Public site header: scrolled state, reading progress, sliding hover pill,
   scrollspy for in-page links, and the full-screen mobile menu.
   Presentational only. */
(function () {
  var nav = document.querySelector(".site-nav");
  if (!nav) return;

  /* Scrolled state + progress bar */
  var ticking = false;
  function onScroll() {
    var y = window.scrollY || 0;
    nav.classList.toggle("is-scrolled", y > 8);
    var max = document.documentElement.scrollHeight - window.innerHeight;
    nav.style.setProperty("--progress", max > 0 ? Math.min(1, y / max).toFixed(4) : 0);
    ticking = false;
  }
  window.addEventListener("scroll", function () {
    if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
  }, { passive: true });
  onScroll();

  /* Hover pill that slides between links */
  var links = nav.querySelector(".nav-links");
  var pill = links && links.querySelector(".nav-pill");
  if (links && pill) {
    var moveTo = function (a) {
      pill.style.width = a.offsetWidth + "px";
      pill.style.transform = "translateX(" + a.offsetLeft + "px)";
      pill.style.opacity = "1";
    };
    links.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("mouseenter", function () { moveTo(a); });
      a.addEventListener("focus", function () { moveTo(a); });
    });
    links.addEventListener("mouseleave", function () { pill.style.opacity = "0"; });
  }

  /* Scrollspy: mark the in-page link whose section is in view */
  if (links && "IntersectionObserver" in window) {
    var map = {};
    links.querySelectorAll('a[href^="#"]').forEach(function (a) {
      var id = a.getAttribute("href").slice(1);
      var sec = id && document.getElementById(id);
      if (sec) map[id] = a;
    });
    var ids = Object.keys(map);
    if (ids.length) {
      var spy = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            ids.forEach(function (k) { map[k].classList.remove("is-current"); });
            map[en.target.id].classList.add("is-current");
          }
        });
      }, { rootMargin: "-45% 0px -50% 0px" });
      ids.forEach(function (k) { spy.observe(document.getElementById(k)); });
    }
  }

  /* Mobile menu */
  var btn = document.querySelector(".menu-btn");
  var menu = document.getElementById(btn ? btn.getAttribute("aria-controls") : "");
  if (btn && menu) {
    var setOpen = function (open) {
      btn.setAttribute("aria-expanded", String(open));
      btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      menu.classList.toggle("is-open", open);
      if (open) menu.removeAttribute("inert"); else menu.setAttribute("inert", "");
      document.documentElement.classList.toggle("no-scroll", open);
      nav.classList.toggle("is-scrolled", open || (window.scrollY || 0) > 8);
    };
    btn.addEventListener("click", function () { setOpen(btn.getAttribute("aria-expanded") !== "true"); });
    menu.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", function () { setOpen(false); }); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && menu.classList.contains("is-open")) { setOpen(false); btn.focus(); } });
    window.addEventListener("resize", function () { if (window.innerWidth >= 1024) setOpen(false); });
  }
})();
