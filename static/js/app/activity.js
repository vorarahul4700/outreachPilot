/* OutreachPilot app: Activity log lines and the sent-email drawer list.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

function formatUserFriendlyLog(rawLog) {
  if (!rawLog || typeof rawLog !== "string") return "";

  const lower = rawLog.toLowerCase();
  // Suppress technical debug noise (ChromeDriver, devtools, websocket, curl, session headers)
  if (
    lower.includes("devtools") ||
    lower.includes("chromedriver") ||
    lower.includes("selenium") ||
    lower.includes("ws://") ||
    lower.includes("post /session") ||
    lower.includes("caps=") ||
    lower.includes("error: device or resource busy") ||
    lower.includes("insecure-requests") ||
    lower.includes("sec-ch-ua") ||
    lower.includes("python ") ||
    lower.includes("traceback") ||
    lower.includes("exit code")
  ) {
    return "";
  }

  // Extract optional timestamp [HH:MM:SS]
  let timeStr = "";
  let cleanMsg = rawLog;
  const timeMatch = rawLog.match(/^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*)$/);
  if (timeMatch) {
    timeStr = timeMatch[1];
    cleanMsg = timeMatch[2];
  }

  // Map system/cloud logs into clear, human-understandable operational messages
  let icon = "info";
  let iconColor = "text-secondary";
  let friendlyText = cleanMsg;

  if (/github\s*actions|cloud\s*runner|job\s*registered|dispatching/i.test(cleanMsg)) {
    icon = "rocket_launch";
    iconColor = "text-tertiary";
    friendlyText = "Initializing cloud search engine...";
  } else if (/chromium|headless|browser\s*engine|connecting/i.test(cleanMsg)) {
    icon = "travel_explore";
    iconColor = "text-secondary";
    friendlyText = "Connecting to Google Local & Maps directory...";
  } else if (/fetching\s*listings.*page\s*(\d+)/i.test(cleanMsg)) {
    const pageNum = cleanMsg.match(/page\s*(\d+)/i)?.[1] || "1";
    icon = "search";
    iconColor = "text-primary";
    friendlyText = `Scanning Google Local listings (Page ${pageNum})...`;
  } else if (/extracted\s*(\d+)\s*genuine/i.test(cleanMsg)) {
    const count = cleanMsg.match(/extracted\s*(\d+)/i)?.[1] || "several";
    icon = "verified";
    iconColor = "text-secondary";
    friendlyText = `Verified ${count} authentic company websites with active domains.`;
  } else if (/discovered\s*(\d+)\s*potential/i.test(cleanMsg)) {
    const count = cleanMsg.match(/discovered\s*(\d+)/i)?.[1] || "several";
    icon = "place";
    iconColor = "text-tertiary";
    friendlyText = `Located ${count} candidate businesses in Google Maps.`;
  } else if (/discovered\s*(\d+)\s*genuine/i.test(cleanMsg)) {
    const count = cleanMsg.match(/discovered\s*(\d+)/i)?.[1] || "several";
    icon = "domain_verification";
    iconColor = "text-secondary";
    friendlyText = `Identified ${count} verified businesses with working official websites.`;
  } else if (/saving.*companies|registered.*neon\s*db|successfully\s*saved/i.test(cleanMsg)) {
    const countMatch = cleanMsg.match(/(\d+)/);
    const count = countMatch ? countMatch[1] : "";
    icon = "save";
    iconColor = "text-tertiary";
    friendlyText = count ? `Saved ${count} verified companies to your outreach directory.` : "Saved verified companies to directory.";
  } else if (/cloud_enrich|ai\s*enrichment|ai\s*worker|enriching/i.test(cleanMsg)) {
    icon = "auto_awesome";
    iconColor = "text-secondary";
    friendlyText = "Initiated AI analysis: inspecting websites, tech stacks, and recruiter contacts.";
  } else if (/completed|finished/i.test(cleanMsg)) {
    icon = "check_circle";
    iconColor = "text-secondary";
    friendlyText = "Search complete! Companies are ready to browse below.";
  } else if (/error|failed/i.test(cleanMsg)) {
    icon = "warning";
    iconColor = "text-amber-500";
    friendlyText = cleanMsg.replace(/\[Fast-Path HTTP Error\]/i, "Notice:").replace(/Traceback.*/i, "");
  }

  return `
    <div class="log-line">
      ${timeStr ? `<span class="ts">${escapeHTML(timeStr)}</span>` : ""}
      <span class="material-symbols-outlined ${iconColor}">${icon}</span>
      <span class="msg">${escapeHTML(friendlyText)}</span>
    </div>
  `;
}

async function fetchAuditLogs() {
  try {
    const res = await fetch("/api/outreach/logs");
    if (res.status === 401) {
      const logsContainer = document.getElementById("audit-logs");
      if (logsContainer) {
        logsContainer.innerHTML = `<p class="log-empty">Sign in to view your sent outreach history.</p>`;
      }
      return;
    }
    const data = await res.json();
    const logsContainer = document.getElementById("audit-logs");
    if (!logsContainer) return;
    if (!data.logs || data.logs.length === 0) {
      logsContainer.innerHTML = `<p class="log-empty">No emails sent yet today.</p>`;
      return;
    }

    window._cachedAuditLogs = data.logs;

    logsContainer.innerHTML = data.logs.map((l, idx) => `
      <div onclick="window._openCachedLog(${idx})" class="log-card" title="Click to view message sent">
        <div class="top">
          <b>${escapeHTML(l.company_name)}</b>
          <span class="method">${escapeHTML(l.delivery_method)}</span>
        </div>
        <p class="to">To: ${escapeHTML(l.recipient_email)}</p>
        <div class="bottom">
          <span>${escapeHTML(l.sent_at)}</span>
          <span class="view"><span>View message</span><i data-lucide="chevron-right" class="w-3 h-3"></i></span>
        </div>
      </div>
    `).join("");
    refreshIcons();
  } catch (err) {
    console.error("Failed to load audit logs:", err);
  }
}
