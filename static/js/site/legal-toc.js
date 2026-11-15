/* Builds the "On this page" list for legal pages from each section's <h2>,
   and highlights the section currently in view. Presentational only. */
(function () {
  var box = document.getElementById("legal-toc-links");
  if (!box) return;
  var sections = Array.prototype.slice.call(document.querySelectorAll(".legal-section[id]"));
  var links = {};
  sections.forEach(function (sec, i) {
    var h = sec.querySelector("h2");
    if (!h) return;
    var a = document.createElement("a");
    a.href = "#" + sec.id;
    a.innerHTML = '<span class="n">' + String(i + 1).padStart(2, "0") + "</span>";
    a.appendChild(document.createTextNode(h.textContent.trim()));
    box.appendChild(a);
    links[sec.id] = a;
  });
  if (!("IntersectionObserver" in window)) return;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) {
        Object.keys(links).forEach(function (k) { links[k].classList.remove("is-current"); });
        if (links[en.target.id]) links[en.target.id].classList.add("is-current");
      }
    });
  }, { rootMargin: "-30% 0px -60% 0px" });
  sections.forEach(function (s) { io.observe(s); });
})();
