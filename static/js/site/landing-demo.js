/* Homepage hero preview: a looping, decorative walk through the five steps
   (search, find emails, research, write, send) using sample data.
   Starts when visible, pauses when off-screen, shows the final state for
   prefers-reduced-motion. */
(function () {
  var el = document.getElementById("hero-console");
  if (!el) return;

  var steps = el.querySelectorAll(".pipeline li");
  var countEl = el.querySelector("[data-demo-count]");
  var statusEl = el.querySelector("[data-demo-status]");
  var typed = el.querySelector(".typed");
  var subject = typed ? typed.getAttribute("data-text") : "";
  var STATES = ["is-searching", "is-pinned", "is-listed", "is-verified", "is-drafting", "is-written", "is-sent"];
  var timers = [];
  var running = false;

  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
  function clear() { timers.forEach(clearTimeout); timers = []; }
  function setStep(n) {
    steps.forEach(function (li, i) {
      li.classList.toggle("is-done", i < n);
      li.classList.toggle("is-active", i === n);
    });
  }
  function setStatus(text) { if (statusEl) statusEl.textContent = text; }
  function count(to, ms) {
    if (!countEl) return;
    var start = performance.now();
    (function tick(now) {
      var p = Math.min(1, (now - start) / ms);
      countEl.textContent = Math.round(to * p);
      if (p < 1 && running) requestAnimationFrame(tick);
    })(start);
  }
  function type(text, ms) {
    if (!typed) return;
    var i = 0, per = Math.max(18, ms / text.length);
    (function next() {
      typed.textContent = text.slice(0, i++);
      if (i <= text.length && running) timers.push(setTimeout(next, per));
    })();
  }
  function reset() {
    STATES.forEach(function (s) { el.classList.remove(s); });
    setStep(-1);
    if (countEl) countEl.textContent = "0";
    if (typed) typed.textContent = "";
    setStatus("Searching");
  }
  function finalState() {
    STATES.forEach(function (s) { if (s !== "is-searching") el.classList.add(s); });
    setStep(5);
    if (countEl) countEl.textContent = "24";
    if (typed) typed.textContent = subject;
    setStatus("Ready");
  }

  function play() {
    clear(); reset();
    el.classList.add("is-searching"); setStep(0);
    later(function () { el.classList.add("is-pinned"); count(24, 1100); }, 600);
    later(function () { el.classList.remove("is-searching"); el.classList.add("is-listed"); setStep(1); setStatus("Finding emails"); }, 1900);
    later(function () { el.classList.add("is-verified"); setStatus("3 verified"); }, 2700);
    later(function () { setStep(2); setStatus("Researching"); el.classList.add("is-drafting"); }, 3700);
    later(function () { setStep(3); setStatus("Writing"); type(subject, 1500); }, 4500);
    later(function () { el.classList.add("is-written"); }, 5600);
    later(function () { setStep(4); setStatus("Ready to send"); }, 6600);
    later(function () { el.classList.add("is-sent"); setStep(5); setStatus("Sent"); }, 7600);
    later(play, 10500);
  }

  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    finalState();
    return;
  }
  if (!("IntersectionObserver" in window)) { running = true; play(); return; }
  new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting && !running) { running = true; play(); }
      else if (!en.isIntersecting && running) { running = false; clear(); }
    });
  }, { threshold: 0.25 }).observe(el);
})();
