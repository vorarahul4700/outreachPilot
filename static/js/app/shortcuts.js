/* OutreachPilot app/shortcuts: press "/" to jump to the search box of the open tab.
   Added in the redesign review. Only moves focus; it does not change any search behavior. */
(function () {
  function visible(el) { return !!el && el.offsetParent !== null; }
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    if (document.documentElement.classList.contains("scroll-locked")) return; // a modal or drawer is open
    const box = ["filter-search", "outreach-search-input"].map(id => document.getElementById(id)).find(visible);
    if (!box) return;
    e.preventDefault();
    box.focus();
    box.select();
  });
})();
