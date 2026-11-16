/* OutreachPilot app: Toasts, HTTP error messages and form field warnings.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "app-toast-stack";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  
  let kind = "info";
  let icon = "info";
  let tag = "Info";

  if (type === "error") {
    kind = "error";
    icon = "alert-octagon";
    tag = "Error";
  } else if (type === "warning") {
    kind = "warning";
    const isAuthPrompt = message.toLowerCase().includes("sign in") || message.toLowerCase().includes("login") || message.toLowerCase().includes("auth");
    icon = isAuthPrompt ? "lock" : "alert-triangle";
    tag = isAuthPrompt ? "Sign In Required" : "Attention";
  } else if (type === "success") {
    kind = "success";
    icon = "check-circle-2";
    tag = "Success";
  }

  toast.className = `app-toast ${kind} -translate-y-4 opacity-0 scale-95`;
  toast.innerHTML = `
    <div class="l">
      <span class="ic"><i data-lucide="${icon}"></i></span>
      <div class="min-w-0"><span class="tag">${tag}</span><span class="msg">${message}</span></div>
    </div>
    <button type="button" class="toast-close" title="Dismiss" aria-label="Dismiss">
      <i data-lucide="x"></i>
    </button>
  `;

  const closeBtn = toast.querySelector(".toast-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      toast.classList.add("opacity-0", "-translate-y-4", "scale-95");
      setTimeout(() => toast.remove(), 250);
    });
  }

  container.appendChild(toast);
  refreshIcons();

  requestAnimationFrame(() => {
    toast.classList.remove("-translate-y-4", "opacity-0", "scale-95");
    toast.classList.add("translate-y-0", "opacity-100", "scale-100");
  });

  const displayDuration = type === "error" ? 5500 : (type === "warning" ? 4500 : 3500);
  setTimeout(() => {
    if (toast.isConnected) {
      toast.classList.add("opacity-0", "-translate-y-4", "scale-95");
      setTimeout(() => toast.remove(), 250);
    }
  }, displayDuration);
}

// Centralized HTTP error prompt handler for 4xx/5xx status codes
async function handleHttpError(response, defaultMsg = "Request failed") {
  let errorDetail = "";
  try {
    const clone = response.clone();
    const contentType = clone.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await clone.json();
      errorDetail = data.detail || data.error || data.message || "";
    } else {
      const text = await clone.text();
      if (text && text.length < 200 && !text.includes("<html")) {
        errorDetail = text;
      }
    }
  } catch (_) {}

  const status = response ? response.status : 0;
  if (status === 401) {
    showToast(errorDetail || "Authentication required. Please sign in to continue.", "warning");
  } else if (status === 403) {
    showToast(errorDetail || "Access restricted. Master Admin privileges required.", "error");
  } else if (status === 404) {
    showToast(errorDetail || "Requested resource or endpoint was not found.", "warning");
  } else if (status === 422) {
    showToast(errorDetail || "Invalid request payload. Please verify your input parameters.", "warning");
  } else if (status === 429) {
    showToast(errorDetail || "Rate limit reached. Please wait a moment before retrying.", "warning");
  } else if (status >= 500) {
    showToast(errorDetail || "Server telemetry error. Please try again in a few moments.", "error");
  } else {
    showToast(errorDetail || defaultMsg || `Request failed with HTTP ${status}`, "error");
  }
}

function highlightFieldWarning(element, message = null) {
  if (!element) return;
  element.classList.add("input-warning-highlight");
  try {
    if (typeof element.focus === "function") {
      element.focus();
    }
    if (typeof element.scrollIntoView === "function") {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  } catch (_) {}

  if (message) {
    showToast(message, "warning");
  }

  const cleanup = () => {
    element.classList.remove("input-warning-highlight");
    element.removeEventListener("input", cleanup);
    element.removeEventListener("change", cleanup);
  };
  element.addEventListener("input", cleanup);
  element.addEventListener("change", cleanup);

  setTimeout(() => {
    element.classList.remove("input-warning-highlight");
  }, 3200);
}
