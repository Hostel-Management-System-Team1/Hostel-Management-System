/* admin.js — account menu: close on outside click or Escape. No dependencies. */
(function () {
  var menu = document.querySelector(".hms-menu");
  if (!menu) return;
  document.addEventListener("click", function (e) {
    if (menu.open && !menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menu.open) { menu.open = false; menu.querySelector("summary").focus(); }
  });
})();
