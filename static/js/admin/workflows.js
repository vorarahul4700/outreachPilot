/* OutreachPilot admin: Builds the input fields for a GitHub Actions workflow run.
   Moved unchanged out of static/js/admin.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before admin.js. */

function renderDynamicWorkflowInputs(wf) {
  const wrapper = document.getElementById("wf-dynamic-fields-wrapper");
  const countBadge = document.getElementById("wf-dynamic-inputs-count");
  if (!wrapper) return;

  const inputs = (wf && Array.isArray(wf.inputs)) ? wf.inputs : [];

  if (countBadge) {
    countBadge.textContent = inputs.length > 0 
      ? `${inputs.length} Parameter${inputs.length > 1 ? 's' : ''}`
      : "No Parameters";
  }

  if (inputs.length === 0) {
    wrapper.innerHTML = `
      <div class="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant/30 flex items-start gap-2.5">
        <span class="material-symbols-outlined text-primary text-[18px] mt-0.5">info</span>
        <div class="flex flex-col gap-0.5">
          <span class="font-semibold text-on-surface text-xs">No Custom Parameters Required</span>
          <span class="text-[11px] text-on-surface-variant leading-relaxed">This workflow does not require any input parameters. Click <strong>Trigger Execution</strong> to dispatch directly on the specified branch.</span>
        </div>
      </div>
    `;
    return;
  }

  wrapper.innerHTML = inputs.map(param => {
    const pName = param.name || "";
    const pDesc = param.description || "";
    const pDefault = param.default !== undefined ? String(param.default) : "";
    const pReq = !!param.required;
    const pType = (param.type || "string").toLowerCase();
    const options = Array.isArray(param.options) ? param.options : [];

    let inputControl = "";

    if (pType === "choice" || options.length > 0) {
      const optsHtml = options.map(opt => {
        const optStr = String(opt);
        const isSel = (optStr === pDefault) ? "selected" : "";
        return `<option value="${optStr}" ${isSel}>${optStr}</option>`;
      }).join("");

      inputControl = `
        <select data-wf-param="${pName}" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant/40 rounded-lg text-on-surface text-xs focus:outline-none focus:border-primary">
          ${optsHtml}
        </select>
      `;
    } else if (pType === "boolean") {
      const isChecked = (pDefault.toLowerCase() === "true");
      inputControl = `
        <label class="flex items-center gap-2 cursor-pointer pt-1">
          <input type="checkbox" data-wf-param="${pName}" ${isChecked ? "checked" : ""} class="rounded border-outline-variant/50 text-primary focus:ring-primary w-4 h-4">
          <span class="text-xs text-on-surface font-mono">${pName} (Enable / True)</span>
        </label>
      `;
    } else if (pType === "number") {
      inputControl = `
        <input type="number" data-wf-param="${pName}" value="${pDefault}" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant/40 rounded-lg text-on-surface text-xs font-mono focus:outline-none focus:border-primary">
      `;
    } else {
      inputControl = `
        <input type="text" data-wf-param="${pName}" value="${pDefault}" placeholder="${pDesc ? pDesc.replace(/"/g, '&quot;') : pName}" class="w-full px-3 py-2 bg-surface-container-lowest border border-outline-variant/40 rounded-lg text-on-surface text-xs focus:outline-none focus:border-primary">
      `;
    }

    return `
      <div class="flex flex-col gap-1 p-2.5 rounded-lg bg-surface-container-lowest/80 border border-outline-variant/20 hover:border-outline-variant/40 transition-colors">
        <div class="flex items-center justify-between">
          <label class="text-on-surface font-semibold text-xs flex items-center gap-1 font-mono">
            <span>${pName}</span>
            ${pReq ? '<span class="text-rose-500 font-bold" title="Required">*</span>' : ''}
          </label>
          <span class="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant font-medium">${pType}</span>
        </div>
        ${inputControl}
        ${pDesc ? `<span class="text-[11px] text-on-surface-variant leading-snug">${pDesc}</span>` : ''}
      </div>
    `;
  }).join("");
}
