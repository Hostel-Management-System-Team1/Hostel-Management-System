/* hostel.js — password reveal, live list filter, clock. No dependencies. */
(function () {

  /* Password reveal: <button data-hm-reveal="#id"> */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-hm-reveal]');
    if (!b) return;
    var input = document.querySelector(b.getAttribute('data-hm-reveal'));
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    b.setAttribute('aria-pressed', show);
    b.textContent = show ? 'Hide' : 'Show';
  });

  /* Live filter: <input data-hm-filter="#list"> hides [data-filter-item] not matching */
  document.querySelectorAll('[data-hm-filter]').forEach(function (inp) {
    var items = document.querySelectorAll(inp.getAttribute('data-hm-filter') + ' [data-filter-item]');
    var empty = document.querySelector(inp.getAttribute('data-hm-filter-empty') || '#none');
    inp.addEventListener('input', function () {
      var q = inp.value.trim().toLowerCase(), n = 0;
      items.forEach(function (li) {
        var ok = !q || li.textContent.toLowerCase().indexOf(q) > -1;
        li.hidden = !ok; if (ok) n++;
      });
      if (empty) empty.hidden = n > 0;
    });
  });

  /* Gate clock */
  var clock = document.querySelector('[data-hm-clock]');
  if (clock) {
    var tick = function () {
      var d = new Date();
      clock.textContent = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
    };
    tick(); setInterval(tick, 15000);
  }
})();
