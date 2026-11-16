/* OutreachPilot app: Small helpers shared by the workspace: icons, escaping, markdown, monograms, addresses.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

function escapeHTML(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function stripMarkdownForCopy(text) {
  if (!text) return "";
  return text
    .replace(/^###\s*(.*$)/gm, "\n$1\n" + "-".repeat(30))
    .replace(/^##\s*(.*$)/gm, "\n$1\n" + "=".repeat(30))
    .replace(/^#\s*(.*$)/gm, "\n$1\n" + "=".repeat(40))
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/^\s*[\-\*]\s+/gm, "- ")
    .replace(/^\s*\-\-\s*/gm, "- ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatMarkdown(text) {
  if (!text) return "";
  if (typeof marked !== "undefined" && marked.parse) {
    try {
      return marked.parse(text, { breaks: true, gfm: true });
    } catch (e) {
      console.warn("marked.parse error:", e);
    }
  }
  let html = escapeHTML(text);
  html = html.replace(/^### (.*$)/gim, '<h4>$1</h4>');
  html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
  html = html.replace(/^\- (.*$)/gim, '<div class="md-li"><span>$1</span></div>');
  html = html.replace(/\n\n/gim, '<div class="md-gap"></div>');
  html = html.replace(/\n/gim, '<br>');
  return html;
}

function getCompanyMonogram(name) {
  if (!name) return "CO";
  const clean = String(name).trim().replace(/[^a-zA-Z0-9\s]/g, "");
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return clean.slice(0, 2).toUpperCase() || "CO";
}

function cleanAddressText(address) {
  if (!address) return "";
  const trimmed = address.trim();
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("open") ||
    lower.startsWith("closed") ||
    lower.includes("on-site") ||
    lower.includes("online appointments") ||
    /^\d\.\d\s*\(\d+\)/.test(trimmed)
  ) {
    return "";
  }
  return trimmed;
}

function buildMapsUrl(name, address, city) {
  const clean = cleanAddressText(address);
  const query = [name, clean, city].filter(Boolean).join(", ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query || name || 'Google Maps')}`;
}

// Display formatting for counters (redesign): 55119 -> "55,119". Display only; nothing reads these back.
function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString() : String(n ?? "");
}
