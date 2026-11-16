/* Living topographic map behind every page (loaded from base.html).
   The background is a contour map of an imaginary terrain, drawn the way a
   field survey sheet would draw it:
   - The terrain slowly breathes, and it scrolls with the page in parallax, so
     every scroll reveals new ground.
   - Your pointer raises a hill: contour lines bend and close into rings
     around it, and the summit shows a survey mark.
   - Click or tap open background: a ripple runs out through the lines.
   - Every fifth line is an index contour, drawn heavier, as on real maps.
   Colors come from the CSS tokens, so light and dark share one design.
   Pauses when the tab is hidden. With reduced motion it draws a still map
   that only updates on scroll. Decorative only: aria-hidden, no focus. */
(function () {
  var canvas = document.getElementById("page-canvas");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var W = 0, H = 0, DPR = 1, CELL = 16, cols = 0, rows = 0;
  var field = null;
  var scrollY = window.scrollY || 0;
  var mouse = { x: -9999, y: -9999, on: false };
  var hill = { x: -9999, y: -9999, h: 0 };    // eased pointer hill
  var ripples = [];                            // {x, y (viewport), t0}
  var colors = {};
  var raf = 0, hidden = false, lastFrame = 0;
  var LEVELS = 14;                             // contour levels across the value range

  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    colors.line = cs.getPropertyValue("--line-3").trim() || "#908B7A";
    colors.accent = cs.getPropertyValue("--accent").trim() || "#607037";
    colors.accentText = cs.getPropertyValue("--accent-text").trim() || "#4B5A24";
    colors.dark = document.documentElement.classList.contains("dark");
  }

  /* ---------- 2D gradient noise (Perlin style) ---------- */
  var perm = new Uint8Array(512);
  (function () {
    var p = [], i, j, t, seed = 1337;
    for (i = 0; i < 256; i++) p[i] = i;
    for (i = 255; i > 0; i--) {
      seed = (seed * 16807) % 2147483647;
      j = seed % (i + 1); t = p[i]; p[i] = p[j]; p[j] = t;
    }
    for (i = 0; i < 512; i++) perm[i] = p[i & 255];
  })();
  function fade(t) { return t * t * t * (t * (t * 6 - 15) + 10); }
  function grad(h, x, y) {
    switch (h & 7) {
      case 0: return x + y; case 1: return -x + y; case 2: return x - y; case 3: return -x - y;
      case 4: return x; case 5: return -x; case 6: return y; default: return -y;
    }
  }
  function noise(x, y) {
    var X = Math.floor(x), Y = Math.floor(y);
    x -= X; y -= Y; X &= 255; Y &= 255;
    var u = fade(x), v = fade(y);
    var a = perm[X] + Y, b = perm[X + 1] + Y;
    var n00 = grad(perm[a], x, y), n10 = grad(perm[b], x - 1, y);
    var n01 = grad(perm[a + 1], x, y - 1), n11 = grad(perm[b + 1], x - 1, y - 1);
    var nx0 = n00 + u * (n10 - n00), nx1 = n01 + u * (n11 - n01);
    return nx0 + v * (nx1 - nx0);   // about -1..1
  }

  /* ---------- terrain ---------- */
  function measure() {
    W = window.innerWidth; H = window.innerHeight;
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    CELL = W < 640 ? 20 : 16;
    cols = Math.ceil(W / CELL) + 2; rows = Math.ceil(H / CELL) + 2;
    field = new Float32Array(cols * rows);
  }

  function height(px, py, t) {
    // Terrain lives in page coordinates, so scrolling moves over it (with parallax).
    var x = px / 520, y = (py + scrollY * 0.55) / 520;
    var v = noise(x + t * 0.018, y - t * 0.011) * 0.75
          + noise(x * 2.1 - t * 0.025, y * 2.1 + 3.7) * 0.3
          + noise(x * 4.3 + 9.1, y * 4.3 + t * 0.03) * 0.09;
    if (hill.h > 0.001) {
      var dx = px - hill.x, dy = py - hill.y;
      v += hill.h * 0.95 * Math.exp(-(dx * dx + dy * dy) / (2 * 120 * 120));
    }
    for (var i = 0; i < ripples.length; i++) {
      var r = ripples[i], age = (t * 1000 - r.t0) / 1000;
      var rad = age * 420, life = Math.max(0, 1 - age / 1.8);
      if (life <= 0) continue;
      var rx = px - r.x, ry = py - r.y, w = Math.sqrt(rx * rx + ry * ry) - rad;
      v += 0.42 * life * Math.exp(-(w * w) / (2 * 34 * 34));
    }
    return v;
  }

  function sample(t) {
    for (var j = 0; j < rows; j++) {
      for (var i = 0; i < cols; i++) {
        field[j * cols + i] = height((i - 1) * CELL, (j - 1) * CELL, t);
      }
    }
  }

  // Marching squares for one level; appends segments to the current path.
  function seg(ax, ay, bx, by) { ctx.moveTo(ax, ay); ctx.lineTo(bx, by); }
  function contour(level) {
    var c = CELL;
    for (var j = 0; j < rows - 1; j++) {
      var y0 = (j - 1) * c, y1 = y0 + c, r0 = j * cols, r1 = r0 + cols;
      for (var i = 0; i < cols - 1; i++) {
        var a = field[r0 + i], b = field[r0 + i + 1], d = field[r1 + i], e = field[r1 + i + 1];
        var idx = (a > level ? 8 : 0) | (b > level ? 4 : 0) | (e > level ? 2 : 0) | (d > level ? 1 : 0);
        if (idx === 0 || idx === 15) continue;
        var x0 = (i - 1) * c, x1 = x0 + c;
        var top = x0 + c * (level - a) / (b - a);
        var right = y0 + c * (level - b) / (e - b);
        var bottom = x0 + c * (level - d) / (e - d);
        var left = y0 + c * (level - a) / (d - a);
        switch (idx) {
          case 1: case 14: seg(x0, left, bottom, y1); break;
          case 2: case 13: seg(bottom, y1, x1, right); break;
          case 3: case 12: seg(x0, left, x1, right); break;
          case 4: case 11: seg(top, y0, x1, right); break;
          case 6: case 9: seg(top, y0, bottom, y1); break;
          case 7: case 8: seg(x0, left, top, y0); break;
          case 5: seg(x0, left, top, y0); seg(bottom, y1, x1, right); break;
          case 10: seg(top, y0, x1, right); seg(x0, left, bottom, y1); break;
        }
      }
    }
  }

  /* ---------- drawing ---------- */
  function draw(now) {
    var t = now / 1000;
    // Ease the pointer hill toward the pointer, and let it sink when the pointer leaves.
    if (mouse.on) {
      if (hill.x < -9000) { hill.x = mouse.x; hill.y = mouse.y; }
      hill.x += (mouse.x - hill.x) * 0.12; hill.y += (mouse.y - hill.y) * 0.12;
      hill.h += (1 - hill.h) * 0.06;
    } else {
      hill.h *= 0.94;
    }
    ripples = ripples.filter(function (r) { return now - r.t0 < 1800; });

    sample(t);
    ctx.clearRect(0, 0, W, H);
    ctx.lineJoin = "round"; ctx.lineCap = "round";

    var lo = -1.1, hi = 1.6, step = (hi - lo) / LEVELS;
    var base = colors.dark ? 0.75 : 0.8;
    for (var k = 1; k < LEVELS; k++) {
      var index = k % 5 === 0;
      ctx.beginPath();
      contour(lo + k * step);
      ctx.strokeStyle = index ? colors.accent : colors.line;
      ctx.globalAlpha = index ? base : base * 0.62;
      ctx.lineWidth = index ? 1.3 : 0.85;
      ctx.stroke();
    }

    // Survey mark on the pointer summit.
    if (hill.h > 0.25 && hill.x > -9000) {
      var hx = hill.x, hy = hill.y, s = 5;
      ctx.globalAlpha = Math.min(1, hill.h) * 0.9;
      ctx.strokeStyle = colors.accentText; ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(hx, hy - s - 2); ctx.lineTo(hx + s, hy + s - 1); ctx.lineTo(hx - s, hy + s - 1); ctx.closePath();
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function loop(now) {
    raf = 0;
    if (hidden) return;
    // About 30 frames a second is plenty for a slow terrain and keeps the CPU calm.
    if (reduce || now - lastFrame >= 32) { lastFrame = now; draw(now); }
    if (!reduce) raf = requestAnimationFrame(loop);
  }
  function kick() { if (!raf) raf = requestAnimationFrame(loop); }

  /* ---------- events ---------- */
  var rt = 0;
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { measure(); kick(); }, 150); });
  window.addEventListener("scroll", function () { scrollY = window.scrollY || 0; if (reduce) kick(); }, { passive: true });
  window.addEventListener("pointermove", function (e) {
    if (e.pointerType === "touch") return;
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.on = true;
    if (reduce) kick();
  }, { passive: true });
  document.documentElement.addEventListener("mouseleave", function () { mouse.on = false; if (reduce) kick(); });

  // True when the click landed on a solid panel (card, sidebar, table, modal) rather than
  // on the open page background. Keeps the map out of the way in /app and /admin.
  var SKIP = "a,button,input,textarea,select,label,summary,details,[role=button],[role=tab],.fixed";
  function onSolid(el) {
    for (var n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      if (n.tagName === "MAIN") continue;
      var m = getComputedStyle(n).backgroundColor.match(/rgba?\(([^)]+)\)/);
      if (!m) continue;
      var parts = m[1].split(/[\s,\/]+/).filter(Boolean);
      if ((parts.length > 3 ? parseFloat(parts[3]) : 1) >= 0.9) return true;
    }
    return false;
  }
  document.addEventListener("click", function (e) {
    if (reduce || e.target.closest(SKIP) || onSolid(e.target)) return;
    if (document.documentElement.classList.contains("scroll-locked")) return;
    if (window.getSelection && String(window.getSelection())) return;
    ripples.push({ x: e.clientX, y: e.clientY, t0: performance.now() });
    if (ripples.length > 4) ripples.shift();
    kick();
  });

  new MutationObserver(function () { readColors(); kick(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  document.addEventListener("visibilitychange", function () { hidden = document.hidden; if (!hidden) kick(); });

  readColors(); measure(); kick();
})();
