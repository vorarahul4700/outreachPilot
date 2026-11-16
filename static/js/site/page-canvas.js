/* Full-page interactive map behind every page (loaded from base.html).
   The page is a map you scroll over:
   - Street-light dots drift with a slow parallax as you scroll.
   - A dashed route winds from the top of the page to the bottom. A paper
     plane flies along it with your scroll and drops a pin at every section.
   - Dots near the pointer light up and link to it with thin lines.
   - Click or tap any empty spot: a plane flies there from the route and
     drops a pin, and the nearby dots light up.
   - Every few seconds a short flight goes out to a company dot.
   Colors come from the CSS tokens, so light and dark share one design.
   Pauses when the tab is hidden. With reduced motion it draws a still map
   that only updates on scroll. Decorative only: aria-hidden, no focus. */
(function () {
  var canvas = document.getElementById("page-canvas");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var W = 0, H = 0, DPR = 1, S = 34, docH = 0;
  var scrollY = window.scrollY || 0;
  var mouse = { x: -9999, y: -9999, on: false };
  var colors = {};
  var waypoints = [];        // {y (doc), hit: time or 0}
  var flights = [];          // {t0, dur, x0,y0 (doc), cx,cy, x1,y1, pin}
  var pins = [];             // {x,y (doc), t0, big}
  var glow = [];             // {x,y (doc), t0}
  var raf = 0, hidden = false, lastAmbient = 0;

  /* ---------- helpers ---------- */
  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    colors.dot = cs.getPropertyValue("--line-3").trim() || "#908B7A";
    colors.faint = cs.getPropertyValue("--line-2").trim() || "#CFCAB8";
    colors.accent = cs.getPropertyValue("--accent").trim() || "#607037";
    colors.accentText = cs.getPropertyValue("--accent-text").trim() || "#4B5A24";
    colors.surface = cs.getPropertyValue("--surface").trim() || "#FBF9F3";
  }
  function hash(a, b) {
    var h = (a * 374761393 + b * 668265263) | 0;
    h = (h ^ (h >>> 13)) * 1274126177 | 0;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
  }
  function bez(t, a, c, b) { var u = 1 - t; return u * u * a + 2 * u * t * c + t * t * b; }

  /* The route: x as a function of document y. Wide sweeps from edge to edge,
     so it shows in the margins and the gaps between sections. */
  var ROUTE_START = 0;
  function routeX(y) {
    // Phones have no side margins: keep the route as a thin line on the right edge.
    if (W < 760) return W - 12 + 5 * Math.sin((y - ROUTE_START) / 140);
    var amp = Math.min(W * 0.44, 640);
    var t = (y - ROUTE_START) / Math.max(700, H * 1.15);
    return W / 2 + amp * Math.sin(t * Math.PI + 0.6) * (0.75 + 0.25 * Math.cos(t * 1.7));
  }

  function measure() {
    W = window.innerWidth; H = window.innerHeight;
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    S = W < 640 ? 40 : 34;
    docH = document.documentElement.scrollHeight;
    var hero = document.querySelector(".hero-cta");
    ROUTE_START = hero ? hero.getBoundingClientRect().bottom + scrollY + 60 : H * 0.6;
    waypoints = [];
    document.querySelectorAll("main > section").forEach(function (sec, i) {
      if (i === 0) return;
      var top = sec.getBoundingClientRect().top + scrollY;
      if (top > ROUTE_START) waypoints.push({ y: top + 10, hit: 0 });
    });
  }

  /* ---------- drawing ---------- */
  function drawDots(now) {
    var par = scrollY * 0.45;
    var r0 = Math.floor((par - S) / S), r1 = Math.ceil((par + H + S) / S);
    var c1 = Math.ceil(W / S) + 1;
    var R = 150, R2 = R * R;
    var near = [];
    for (var r = r0; r <= r1; r++) {
      for (var c = -1; c <= c1; c++) {
        var h = hash(r, c);
        if (h < 0.24) continue;
        var x = c * S + (hash(c, r) - 0.5) * 6 + ((r % 2) ? S * 0.5 : 0);
        var y = r * S - par - c * S * 0.06 + (h - 0.5) * 6;
        if (y < -10 || y > H + 10) continue;
        var dx = x - mouse.x, dy = y - mouse.y, d2 = dx * dx + dy * dy;
        var k = mouse.on && d2 < R2 ? 1 - Math.sqrt(d2) / R : 0;
        var tw = reduce ? 0 : Math.sin(now / 1100 + h * 40) * 0.25;
        var size = 0.9 + h * 0.7 + tw * 0.4 + k * 2;
        ctx.globalAlpha = (W < 760 ? 0.3 : 0.42) + k * 0.58;
        ctx.fillStyle = k > 0.12 ? colors.accent : colors.dot;
        ctx.beginPath();
        ctx.arc(x - dx * k * 0.1, y - dy * k * 0.1, size, 0, 6.2832);
        ctx.fill();
        if (k > 0.2 && near.length < 14) near.push([x - dx * k * 0.1, y - dy * k * 0.1, k]);
      }
    }
    // Lines from the pointer to the nearest lit dots.
    if (near.length) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = colors.accent;
      near.forEach(function (p) {
        ctx.globalAlpha = p[2] * 0.5;
        ctx.beginPath(); ctx.moveTo(mouse.x, mouse.y); ctx.lineTo(p[0], p[1]); ctx.stroke();
      });
      ctx.globalAlpha = 0.5;
      ctx.beginPath(); ctx.arc(mouse.x, mouse.y, 18, 0, 6.2832); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function headY() { return Math.min(docH - 40, Math.max(ROUTE_START, scrollY + H * 0.62)); }

  function drawRoute(now) {
    var top = Math.max(ROUTE_START, scrollY - 40), bottom = Math.min(docH, scrollY + H + 40);
    if (bottom <= top) return;
    var hy = headY();
    ctx.lineWidth = 1.6;
    ctx.lineCap = "round";
    // Path ahead: faint
    ctx.setLineDash([2, 9]);
    ctx.strokeStyle = colors.faint;
    ctx.globalAlpha = 0.9;
    ctx.beginPath();
    for (var y = Math.max(top, hy); y <= bottom; y += 8) {
      var px = routeX(y), py = y - scrollY;
      if (y === Math.max(top, hy)) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.stroke();
    // Path travelled: accent
    if (hy > top) {
      ctx.setLineDash([6, 8]);
      ctx.lineDashOffset = reduce ? 0 : -now / 60;
      ctx.strokeStyle = colors.accent;
      ctx.globalAlpha = 0.7;
      ctx.beginPath();
      for (var y2 = top; y2 <= Math.min(hy, bottom); y2 += 8) {
        var qx = routeX(y2), qy = y2 - scrollY;
        if (y2 === top) ctx.moveTo(qx, qy); else ctx.lineTo(qx, qy);
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.lineDashOffset = 0;
    ctx.globalAlpha = 1;

    // Waypoint pins: drop when the plane passes them.
    waypoints.forEach(function (w) {
      if (!w.hit && hy >= w.y) {
        w.hit = now;
        glow.push({ x: routeX(w.y), y: w.y, t0: now });
      }
      var sy = w.y - scrollY;
      if (sy < -40 || sy > H + 40) return;
      var x = routeX(w.y);
      if (w.hit) {
        var age = reduce ? 1000 : now - w.hit;
        drawPin(x, sy - (1 - Math.min(1, age / 380)) * 18, 1, Math.min(1, age / 200));
      } else {
        ctx.globalAlpha = 0.8;
        ctx.strokeStyle = colors.faint;
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(x, sy, 4.5, 0, 6.2832); ctx.stroke();
        ctx.globalAlpha = 1;
      }
    });
  }

  function drawPlane(x, y, angle, scale) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.scale(scale, scale);
    ctx.beginPath();
    ctx.moveTo(11, 0); ctx.lineTo(-9, -8); ctx.lineTo(-4, 0); ctx.lineTo(-9, 8); ctx.closePath();
    ctx.fillStyle = colors.accent;
    ctx.fill();
    ctx.restore();
  }

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
    ctx.arc(0, -14, 2.6, 0, 6.2832);
    ctx.fillStyle = colors.surface;
    ctx.fill();
    ctx.restore();
  }

  function launch(x1, y1, now, big) {
    var hy = headY(), x0 = routeX(hy);
    var mx = (x0 + x1) / 2 + (Math.random() - 0.5) * 120;
    var my = Math.min(hy, y1) - 80 - Math.random() * 120;
    var dist = Math.hypot(x1 - x0, y1 - hy);
    flights.push({ t0: now, dur: Math.min(2200, 700 + dist * 1.4), x0: x0, y0: hy, cx: mx, cy: my, x1: x1, y1: y1, big: big });
  }

  function drawFlights(now) {
    for (var i = flights.length - 1; i >= 0; i--) {
      var f = flights[i];
      var t = Math.min(1, (now - f.t0) / f.dur);
      var e = 1 - Math.pow(1 - t, 2.2);
      ctx.setLineDash([3, 6]);
      ctx.lineWidth = 1.3;
      ctx.strokeStyle = colors.accent;
      ctx.globalAlpha = 0.55 * (t > 0.85 ? (1 - (t - 0.85) / 0.15) : 1);
      ctx.beginPath();
      for (var s = 0; s <= 30; s++) {
        var tt = (s / 30) * e;
        var px = bez(tt, f.x0, f.cx, f.x1), py = bez(tt, f.y0, f.cy, f.y1) - scrollY;
        if (s === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      var hx = bez(e, f.x0, f.cx, f.x1), hyy = bez(e, f.y0, f.cy, f.y1);
      var nx = bez(Math.min(1, e + 0.02), f.x0, f.cx, f.x1), ny = bez(Math.min(1, e + 0.02), f.y0, f.cy, f.y1);
      drawPlane(hx, hyy - scrollY, Math.atan2(ny - hyy, nx - hx), f.big ? 0.9 : 0.65);
      if (t >= 1) {
        pins.push({ x: f.x1, y: f.y1, t0: now, big: f.big });
        if (f.big) glow.push({ x: f.x1, y: f.y1, t0: now });
        flights.splice(i, 1);
      }
    }
  }

  function drawPins(now) {
    for (var i = pins.length - 1; i >= 0; i--) {
      var p = pins[i], age = now - p.t0, life = p.big ? 5200 : 3000;
      if (age > life) { pins.splice(i, 1); continue; }
      var sy = p.y - scrollY;
      var drop = Math.min(1, age / 360);
      var fade = age > life - 800 ? (life - age) / 800 : 1;
      drawPin(p.x, sy - (1 - drop) * 16, p.big ? 1.15 : 0.85, fade * drop);
    }
    for (var j = glow.length - 1; j >= 0; j--) {
      var g = glow[j], ga = now - g.t0;
      if (ga > 1400) { glow.splice(j, 1); continue; }
      var k = ga / 1400;
      ctx.globalAlpha = (1 - k) * 0.55;
      ctx.strokeStyle = colors.accent;
      ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.arc(g.x, g.y - scrollY, 6 + k * 46, 0, 6.2832); ctx.stroke();
      ctx.beginPath(); ctx.arc(g.x, g.y - scrollY, 6 + k * 24, 0, 6.2832); ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }

  function frame(now) {
    raf = 0;
    if (hidden) return;
    scrollY = window.scrollY || 0;
    ctx.clearRect(0, 0, W, H);
    drawDots(now);
    drawRoute(now);
    if (!reduce) {
      if (W >= 760 && now - lastAmbient > 2600 && flights.length < 2) {
        lastAmbient = now;
        var side = Math.random() < 0.5 ? 0.08 : 0.92;
        launch(W * (side + (Math.random() - 0.5) * 0.12), scrollY + H * (0.15 + Math.random() * 0.6), now, false);
      }
      drawFlights(now);
      drawPins(now);
    }
    var hy = headY();
    if (hy - scrollY < H + 20) {
      var a = Math.atan2(8, routeX(hy + 8) - routeX(hy));
      drawPlane(routeX(hy), hy - scrollY, a, W < 760 ? 0.8 : 1.1);
    }
    if (!reduce) raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf && !hidden) raf = requestAnimationFrame(frame); }

  /* ---------- events ---------- */
  readColors();
  measure();
  kick();

  var rt;
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { measure(); kick(); }, 150); });
  window.addEventListener("load", function () { measure(); kick(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { measure(); kick(); });
  window.addEventListener("scroll", function () { if (reduce) kick(); }, { passive: true });

  window.addEventListener("pointermove", function (e) {
    if (e.pointerType === "touch") return;
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.on = true;
    if (reduce) kick();
  }, { passive: true });
  document.addEventListener("pointerleave", function () { mouse.on = false; if (reduce) kick(); });

  var SKIP = "a,button,input,textarea,select,label,summary,details,[role=button],[role=tab],.card,.tile,.plan,.lab,.console,.mail,.cmp,.secure,.final,.faq,.flow-step,.browse-card,.m-item,.site-nav,.mobile-menu,.announce";
  // True when the click landed on a solid panel (card, sidebar, table, modal) rather than
  // on the open page background. Keeps the canvas out of the way in /app and /admin.
  function onSolid(el) {
    for (var n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      if (n.tagName === "MAIN") continue;
      var bg = getComputedStyle(n).backgroundColor;
      var m = bg.match(/rgba?\(([^)]+)\)/);
      if (!m) continue;
      var parts = m[1].split(/[\s,\/]+/).filter(Boolean);
      var a = parts.length > 3 ? parseFloat(parts[3]) : 1;
      if (a >= 0.9) return true;
    }
    return false;
  }
  document.addEventListener("click", function (e) {
    if (reduce || e.target.closest(SKIP)) return;
    if (document.documentElement.classList.contains("scroll-locked") || e.target.closest(".fixed")) return;
    if (onSolid(e.target)) return;
    if (window.getSelection && String(window.getSelection())) return;
    launch(e.clientX, e.clientY + (window.scrollY || 0), performance.now(), true);
    kick();
  });

  new MutationObserver(function () { readColors(); kick(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  document.addEventListener("visibilitychange", function () { hidden = document.hidden; if (!hidden) kick(); });
})();
