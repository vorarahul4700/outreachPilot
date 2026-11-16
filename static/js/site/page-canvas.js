/* Folded paper background behind every page (loaded from base.html).
   The page is a sheet of softly folded paper made of triangle facets:
   - The cursor is a lamp. Facets turned toward it catch light, the rest fall
     into shade, so the whole sheet shifts as you move. The brightest facets
     take the moss accent.
   - The sheet scrolls with the page in parallax, so new folds come into view.
   - Click open background: a ring of light runs out across the folds.
   - With no pointer (touch, or the pointer has left) the lamp drifts slowly.
   Colors come from the CSS tokens, so light and dark share one design.
   Pauses when the tab is hidden. With reduced motion it draws a still sheet
   that only updates on scroll. Decorative only: aria-hidden, no focus. */
(function () {
  var canvas = document.getElementById("page-canvas");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var W = 0, H = 0, DPR = 1, S = 90;
  var scrollY = window.scrollY || 0;
  var mouse = { x: 0, y: 0, on: false };
  var lamp = { x: 0, y: 0, ready: false };
  var flashes = [];                 // {x, y (viewport), t0}
  var colors = {};
  var raf = 0, hidden = false, lastFrame = 0;

  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    colors.accent = cs.getPropertyValue("--accent").trim() || "#607037";
    colors.accentText = cs.getPropertyValue("--accent-text").trim() || "#A9BC72";
    colors.shade = cs.getPropertyValue("--text").trim() || "#1F2018";
    colors.line = cs.getPropertyValue("--line-3").trim() || "#908B7A";
    colors.dark = document.documentElement.classList.contains("dark");
  }

  // Stable pseudo-random value per grid point, so folds never jump while scrolling.
  function hash(a, b, k) {
    var h = (a * 374761393 + b * 668265263 + k * 2147483647) | 0;
    h = (h ^ (h >>> 13)) * 1274126177 | 0;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
  }

  function measure() {
    W = window.innerWidth; H = window.innerHeight;
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    S = W < 640 ? 72 : 96;
    if (!lamp.ready) { lamp.x = W * 0.6; lamp.y = H * 0.3; lamp.ready = true; }
  }

  // Vertex of the sheet at grid (row r, col c), in viewport coordinates.
  function vert(r, c, off) {
    var x = c * S + ((r & 1) ? S / 2 : 0) + (hash(r, c, 1) - 0.5) * S * 0.36;
    var y = r * S - off + (hash(r, c, 2) - 0.5) * S * 0.36;
    var z = (hash(r, c, 3) - 0.5) * S * 0.7;
    return [x, y, z];
  }

  function draw(now) {
    // Lamp follows the pointer; without one it drifts on a slow loop.
    var tx = mouse.on ? mouse.x : W * (0.5 + 0.32 * Math.cos(now / 5200));
    var ty = mouse.on ? mouse.y : H * (0.35 + 0.18 * Math.sin(now / 4100));
    lamp.x += (tx - lamp.x) * (reduce ? 1 : 0.12);
    lamp.y += (ty - lamp.y) * (reduce ? 1 : 0.12);
    flashes = flashes.filter(function (f) { return now - f.t0 < 1600; });

    ctx.clearRect(0, 0, W, H);
    var par = scrollY * 0.35;
    var r0 = Math.floor(par / S) - 1, r1 = r0 + Math.ceil(H / S) + 3;
    var c1 = Math.ceil(W / S) + 1;
    var rowsV = [];
    for (var r = r0; r <= r1; r++) {
      var row = [];
      for (var c = -1; c <= c1; c++) row.push(vert(r, c, par));
      rowsV.push(row);
    }
    var shadeA = colors.dark ? 0.2 : 0.16, litA = colors.dark ? 0.16 : 0.13;
    ctx.lineWidth = 0.7;
    for (var j = 0; j < rowsV.length - 1; j++) {
      var odd = ((r0 + j) & 1) === 1, A = rowsV[j], B = rowsV[j + 1];
      for (var i = 0; i < A.length - 1; i++) {
        var a = A[i], b = A[i + 1], cc = B[i], d = B[i + 1];
        if (odd) { facet(a, b, d, now, shadeA, litA); facet(a, d, cc, now, shadeA, litA); }
        else { facet(a, b, cc, now, shadeA, litA); facet(b, d, cc, now, shadeA, litA); }
      }
    }
    ctx.globalAlpha = 1;
  }

  function facet(p, q, s, now, shadeA, litA) {
    var ux = q[0] - p[0], uy = q[1] - p[1], uz = q[2] - p[2];
    var vx = s[0] - p[0], vy = s[1] - p[1], vz = s[2] - p[2];
    var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    if (nz < 0) { nx = -nx; ny = -ny; nz = -nz; }
    var nl = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    var cx = (p[0] + q[0] + s[0]) / 3, cy = (p[1] + q[1] + s[1]) / 3;
    var Lx = lamp.x - cx, Ly = lamp.y - cy, Lz = 240;
    var Ll = Math.sqrt(Lx * Lx + Ly * Ly + Lz * Lz);
    var light = Math.max(0, (nx * Lx + ny * Ly + nz * Lz) / (nl * Ll));
    // Fall-off with distance from the lamp keeps the glow local.
    var near = Math.max(0, 1 - Math.sqrt(Lx * Lx + Ly * Ly) / (Math.max(W, H) * 0.75));
    var boost = 0;
    for (var k = 0; k < flashes.length; k++) {
      var f = flashes[k], age = (now - f.t0) / 1000, rad = age * 620;
      var dd = Math.sqrt((cx - f.x) * (cx - f.x) + (cy - f.y) * (cy - f.y)) - rad;
      boost += Math.max(0, 1 - age / 1.6) * Math.exp(-(dd * dd) / (2 * 60 * 60));
    }
    ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.lineTo(s[0], s[1]); ctx.closePath();
    var lit = light * (0.35 + 0.65 * near) + boost * 0.6;
    if (lit > 0.82) {
      // The facets facing the lamp most directly take the moss accent.
      ctx.fillStyle = colors.dark ? colors.accentText : colors.accent;
      ctx.globalAlpha = litA * Math.min(1.6, lit);
    } else if (colors.dark) {
      // On near-black the lamp brightens the paper instead of shading it.
      ctx.fillStyle = "#FFFFFF"; ctx.globalAlpha = 0.012 + 0.07 * Math.min(1, lit);
    } else {
      // On light paper, facets that face away from the lamp fall into shade.
      ctx.fillStyle = colors.shade; ctx.globalAlpha = shadeA * (1 - Math.min(1, lit)) * 0.55;
    }
    ctx.fill();
    ctx.strokeStyle = colors.line; ctx.globalAlpha = colors.dark ? 0.1 : 0.12;
    ctx.stroke();
  }

  function loop(now) {
    raf = 0;
    if (hidden) return;
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
  // on the open page background. Keeps the sheet out of the way in /app and /admin.
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
    if (reduce || !e.target.closest || e.target.closest(SKIP) || onSolid(e.target)) return;
    if (document.documentElement.classList.contains("scroll-locked")) return;
    if (window.getSelection && String(window.getSelection())) return;
    flashes.push({ x: e.clientX, y: e.clientY, t0: performance.now() });
    if (flashes.length > 3) flashes.shift();
    kick();
  });

  new MutationObserver(function () { readColors(); kick(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  document.addEventListener("visibilitychange", function () { hidden = document.hidden; if (!hidden) kick(); });

  readColors(); measure(); kick();
})();
