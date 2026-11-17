/* Presentational motion shared by all redesigned pages:
   - .reveal / .reveal-stagger fade in when they enter the viewport and out when they leave
   - [data-count] numbers count up once (value stays correct without JS)
   - .marquee tracks are cloned for a seamless loop
   - .rotator cycles its child words
   Everything is skipped for prefers-reduced-motion. */
(function () {
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Stagger index for children */
  document.querySelectorAll(".reveal-stagger").forEach(function (group) {
    Array.prototype.forEach.call(group.children, function (el, i) { el.style.setProperty("--i", i); });
  });

  /* Reveal */
  var revealables = document.querySelectorAll(".reveal, .reveal-stagger");
  if (reduce || !("IntersectionObserver" in window)) {
    revealables.forEach(function (el) { el.classList.add("is-in"); });
  } else {
    // Two-way, like the reference: in on enter, out on leave. Elements that leave
    // through the top get .is-above so they drift up instead of down.
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var el = en.target;
        if (en.isIntersecting) { el.classList.remove("is-above"); el.classList.add("is-in"); }
        else {
          el.classList.remove("is-in");
          el.classList.toggle("is-above", en.boundingClientRect.top < 0);
        }
      });
    }, { rootMargin: "-4% 0px -6% 0px", threshold: 0 });
    revealables.forEach(function (el) { io.observe(el); });
  }

  /* Count up */
  var fmt = new Intl.NumberFormat("en-IN");
  function countUp(el) {
    var target = parseFloat(el.getAttribute("data-count"));
    if (!isFinite(target)) return;
    var dur = 1400, start = null;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt.format(Math.round(target * eased));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var counters = document.querySelectorAll("[data-count]");
  if (!reduce && counters.length && "IntersectionObserver" in window) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { countUp(en.target); cio.unobserve(en.target); }
      });
    }, { threshold: 0.4 });
    counters.forEach(function (el) { cio.observe(el); });
  }

  /* Marquee clone */
  document.querySelectorAll(".marquee").forEach(function (m) {
    var track = m.querySelector(".marquee-track");
    if (!track || m.dataset.cloned) return;
    var clone = track.cloneNode(true);
    clone.setAttribute("aria-hidden", "true");
    clone.querySelectorAll("a, button").forEach(function (el) { el.setAttribute("tabindex", "-1"); });
    m.appendChild(clone);
    m.dataset.cloned = "1";
  });

  /* Word rotator */
  if (!reduce) {
    document.querySelectorAll(".rotator").forEach(function (rot) {
      var words = rot.children;
      if (words.length < 2) return;
      var i = 0;
      for (var k = 0; k < words.length; k++) { if (words[k].classList.contains("is-current")) i = k; }
      // Width stays at the widest word (inline-grid), so the line never reflows (no layout shift).
      setInterval(function () {
        var cur = words[i];
        i = (i + 1) % words.length;
        var next = words[i];
        cur.classList.remove("is-current");
        cur.classList.add("is-leaving");
        next.classList.add("is-current");
        setTimeout(function () { cur.classList.remove("is-leaving"); }, 600);
      }, 2600);
    });
  }
})();
