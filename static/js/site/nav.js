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

  /* Scrollspy: mark the last linked section the reader has reached (its top is above the
     middle of the screen). Nothing is marked above the first one, and the dot never jumps
     back and forth: it only moves forward as you scroll down and back as you scroll up. */
  if (links) {
    var spyLinks = [];
    links.querySelectorAll('a[href^="#"]').forEach(function (a) {
      var sec = document.getElementById(a.getAttribute("href").slice(1));
      if (sec) spyLinks.push({ a: a, sec: sec });
    });
    if (spyLinks.length) {
      var spyTick = false;
      var spy = function () {
        var line = window.innerHeight * 0.45;
        var current = null;
        spyLinks.forEach(function (s) { if (s.sec.getBoundingClientRect().top <= line) current = s.a; });
        spyLinks.forEach(function (s) { s.a.classList.toggle("is-current", s.a === current); });
        spyTick = false;
      };
      // Page order, not nav order, decides which section comes "last".
      spyLinks.sort(function (x, y) {
        return x.sec.compareDocumentPosition(y.sec) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
      });
      window.addEventListener("scroll", function () {
        if (!spyTick) { spyTick = true; requestAnimationFrame(spy); }
      }, { passive: true });
      window.addEventListener("resize", spy);
      spy();
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
