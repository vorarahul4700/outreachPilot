/* Homepage hero background: an interactive "city map" canvas.
   - Dots sit along gently tilted streets, like a map seen from above.
   - Every few seconds a paper-plane path arcs from your spot to a company dot,
     which then drops a pin and ripples once.
   - Dots near the pointer grow and take the accent color.
   Colors come from the CSS tokens, so light and dark use the same design.
   Pauses off-screen and when the tab is hidden; static for reduced motion. */
(function () {
  var canvas = document.getElementById("hero-canvas");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var host = canvas.parentElement;
  var area = canvas.closest(".hero") || host;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var W = 0, H = 0, DPR = 1;
  var dots = [], flights = [], pins = [];
  var hub = { x: 0, y: 0 };
  var mouse = { x: -9999, y: -9999, active: false };
  var colors = {};
  var visible = true, raf = 0, lastLaunch = 0;

  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    colors.dot = cs.getPropertyValue("--line-3").trim() || "#B2AC96";
    colors.road = cs.getPropertyValue("--line").trim() || "#DFDBCD";
    colors.accent = cs.getPropertyValue("--accent").trim() || "#56672A";
    colors.surface = cs.getPropertyValue("--surface").trim() || "#FBF9F3";
  }

  function rand(a, b) { return a + Math.random() * (b - a); }

  function build() {
    var rect = host.getBoundingClientRect();
    W = Math.max(1, rect.width); H = Math.max(1, rect.height);
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    dots = [];
    var gap = W < 640 ? 34 : 30;
    var tiltA = -0.12, tiltB = 0.2;
    // Two families of streets; dots strung along them.
    for (var y = -H * 0.2; y < H * 1.2; y += gap * 2.4) {
      for (var x = -20; x < W + 20; x += gap) {
        if (Math.random() < 0.18) continue;
        dots.push({ x: x, y: y + x * tiltA + rand(-2, 2), r: rand(0.9, 1.6), p: Math.random() * Math.PI * 2 });
      }
    }
    for (var x2 = -W * 0.1; x2 < W * 1.1; x2 += gap * 3.2) {
      for (var y2 = -20; y2 < H + 20; y2 += gap) {
        if (Math.random() < 0.25) continue;
        dots.push({ x: x2 + y2 * tiltB + rand(-2, 2), y: y2, r: rand(0.9, 1.5), p: Math.random() * Math.PI * 2 });
      }
    }
    dots = dots.filter(function (d) { return d.x > -10 && d.x < W + 10 && d.y > -10 && d.y < H + 10; });
    // Your spot sits just under the hero buttons, above the product preview.
    var anchor = area.querySelector(".trust") || area.querySelector(".hero-cta");
    var cr = canvas.getBoundingClientRect();
    hub.x = W * 0.5;
    hub.y = anchor ? Math.min(H - 10, anchor.getBoundingClientRect().bottom - cr.top + 34) : H * 0.6;
    flights = []; pins = [];
  }

  function launch(now) {
    // Pick a target away from the center text column.
    var target, tries = 0;
    do {
      target = dots[(Math.random() * dots.length) | 0];
      tries++;
    } while (tries < 40 && target && ((Math.abs(target.x - W / 2) < W * 0.24 && target.y < hub.y) || target.y > hub.y - 20));
    if (!target) return;
    var mx = (hub.x + target.x) / 2, my = Math.min(hub.y, target.y) - rand(60, 160);
    flights.push({ t0: now, dur: rand(1600, 2400), x0: hub.x, y0: hub.y, cx: mx, cy: my, x1: target.x, y1: target.y });
  }

  function bez(t, a, c, b) { var u = 1 - t; return u * u * a + 2 * u * t * c + t * t * b; }

  function drawPin(x, y, s, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(x, y);
    ctx.scale(s, s);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.bezierCurveTo(-6, -7, -7, -11, -7, -14);
    ctx.arc(0, -14, 7, Math.PI, 0);
    ctx.bezierCurveTo(7, -11, 6, -7, 0, 0);
    ctx.fillStyle = colors.accent;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(0, -14, 2.6, 0, Math.PI * 2);
    ctx.fillStyle = colors.surface;
    ctx.fill();
    ctx.restore();
  }

  function frame(now) {
    raf = 0;
    if (!visible) return;
    ctx.clearRect(0, 0, W, H);

    // Dots, reacting to the pointer.
    var R = 120;
    for (var i = 0; i < dots.length; i++) {
      var d = dots[i];
      var dx = d.x - mouse.x, dy = d.y - mouse.y;
      var dist = Math.sqrt(dx * dx + dy * dy);
      var near = mouse.active && dist < R ? 1 - dist / R : 0;
      var twinkle = reduce ? 0 : 0.25 * Math.sin(now / 900 + d.p);
      ctx.beginPath();
      ctx.arc(d.x - dx * near * 0.08, d.y - dy * near * 0.08, d.r + near * 1.8 + twinkle * 0.4, 0, Math.PI * 2);
      ctx.globalAlpha = 0.55 + near * 0.45;
      ctx.fillStyle = near > 0.15 ? colors.accent : colors.dot;
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // Your spot.
    ctx.beginPath();
    ctx.arc(hub.x, hub.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = colors.accent;
    ctx.fill();

    if (!reduce) {
      if (now - lastLaunch > 1400 && flights.length < 3) { launch(now); lastLaunch = now; }

      // Flights: dashed trail + moving head.
      for (var f = flights.length - 1; f >= 0; f--) {
        var fl = flights[f];
        var t = Math.min(1, (now - fl.t0) / fl.dur);
        var e = 1 - Math.pow(1 - t, 2);
        ctx.beginPath();
        ctx.setLineDash([3, 5]);
        ctx.lineWidth = 1.3;
        ctx.strokeStyle = colors.accent;
        ctx.globalAlpha = 0.55 * (1 - Math.max(0, t - 0.85) / 0.15);
        var steps = 28;
        for (var s = 0; s <= steps; s++) {
          var tt = (s / steps) * e;
          var px = bez(tt, fl.x0, fl.cx, fl.x1), py = bez(tt, fl.y0, fl.cy, fl.y1);
          if (s === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
        var hx = bez(e, fl.x0, fl.cx, fl.x1), hy = bez(e, fl.y0, fl.cy, fl.y1);
        ctx.beginPath();
        ctx.arc(hx, hy, 3, 0, Math.PI * 2);
        ctx.fillStyle = colors.accent;
        ctx.fill();
        if (t >= 1) { pins.push({ x: fl.x1, y: fl.y1, t0: now }); flights.splice(f, 1); }
      }

      // Pins: drop, ripple, fade.
      for (var p = pins.length - 1; p >= 0; p--) {
        var pn = pins[p];
        var age = now - pn.t0;
        if (age > 3200) { pins.splice(p, 1); continue; }
        var drop = Math.min(1, age / 350);
        var fade = age > 2400 ? 1 - (age - 2400) / 800 : 1;
        var ring = Math.min(1, age / 1100);
        ctx.beginPath();
        ctx.arc(pn.x, pn.y, 4 + ring * 22, 0, Math.PI * 2);
        ctx.strokeStyle = colors.accent;
        ctx.lineWidth = 1.2;
        ctx.globalAlpha = (1 - ring) * 0.6 * fade;
        ctx.stroke();
        ctx.globalAlpha = 1;
        drawPin(pn.x, pn.y - (1 - drop) * 14, 0.9, fade * drop);
      }
      raf = requestAnimationFrame(frame);
    }
  }

  function kick() { if (!raf && visible) raf = requestAnimationFrame(frame); }

  readColors();
  build();
  kick();

  var resizeT;
  window.addEventListener("resize", function () {
    clearTimeout(resizeT);
    resizeT = setTimeout(function () { build(); kick(); }, 150);
  });
  area.addEventListener("pointermove", function (e) {
    var r = canvas.getBoundingClientRect();
    mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; mouse.active = true;
    if (reduce) kick();
  }, { passive: true });
  area.addEventListener("pointerleave", function () { mouse.active = false; if (reduce) kick(); });

  // Re-read colors when the theme changes.
  new MutationObserver(function () { readColors(); kick(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting && !document.hidden;
      kick();
    }).observe(host);
  }
  document.addEventListener("visibilitychange", function () {
    visible = !document.hidden;
    kick();
  });
})();
