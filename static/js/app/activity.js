/* OutreachPilot app: friendly lines for the scout progress log.
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
