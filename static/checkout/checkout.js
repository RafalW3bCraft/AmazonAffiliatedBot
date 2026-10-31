/* DealPilot checkout/shop client logic. No secrets here - CSRF token is
 * fetched from /api/csrf and sent as a header on POSTs only. */
(function () {
  'use strict';

  function getCsrf() {
    return fetch('/api/csrf', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) { return d.csrf_token || ''; });
  }

  function postJson(url, body) {
    return getCsrf().then(function (token) {
      return fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': token
        },
        body: JSON.stringify(body)
      });
    });
  }

  // --- AI recommend panel (shop page) ---
  var aiForm = document.getElementById('dp-ai-form');
  if (aiForm) {
    aiForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var query = document.getElementById('dp-ai-query').value;
      var out = document.getElementById('dp-ai-results');
      out.textContent = 'Thinking…';
      postJson('/api/ai/recommend', { query: query })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (!res.ok) {
            out.textContent = res.body.error || 'Recommendation unavailable.';
            return;
          }
          var b = res.body;
          var html = '';
          if (b.ai_disclaimer) {
            html += '<p class="dp-notice">' + b.ai_disclaimer + '</p>';
          }
          (b.items || []).forEach(function (it) {
            html += '<div class="dp-card dp-ai-card">' +
              '<span class="dp-badge">MERCHANT - PayPal checkout</span>' +
              '<h3>' + it.sku + '</h3>' +
              '<p>' + it.reason + '</p>' +
              '<p class="dp-card-price">' + it.price + ' ' + it.currency + '</p></div>';
          });
          if (b.tradeoffs) { html += '<p>' + b.tradeoffs + '</p>'; }
          if ((b.missing_info || []).length) {
            html += '<p>Missing: ' + b.missing_info.join(', ') + '</p>';
          }
          out.innerHTML = html || '<p>No matches.</p>';
        })
        .catch(function () { out.textContent = 'Network error.'; });
    });
  }

  // --- Quote form: convert checkbox selections into JSON POST ---
  var quoteForm = document.getElementById('dp-quote-form');
  if (quoteForm) {
    quoteForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var items = [];
      quoteForm.querySelectorAll('input[name="sel"]:checked').forEach(function (cb) {
        var sku = cb.getAttribute('data-sku');
        var qtyInput = quoteForm.querySelector('input[name="qty_' + sku + '"]');
        var qty = qtyInput ? parseInt(qtyInput.value, 10) : 1;
        items.push({ sku: sku, quantity: isNaN(qty) ? 1 : qty });
      });
      if (!items.length) { return; }
      postJson('/cart/quote', { items: items })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.redirect) { window.location = j.redirect; }
          else if (j.error) { alert(j.error); }
        })
        .catch(function () { alert('Network error creating quote.'); });
    });
  }

  // --- Checkout start button (cart/checkout pages) ---
  var checkoutBtn = document.getElementById('dp-checkout-btn');
  if (checkoutBtn) {
    checkoutBtn.addEventListener('click', function () {
      var msg = document.getElementById('dp-checkout-msg');
      var quoteId = checkoutBtn.getAttribute('data-quote-id');
      msg.textContent = 'Contacting PayPal sandbox…';
      postJson('/checkout/start', { quote_id: quoteId })
        .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); })
        .then(function (res) {
          if (res.status === 503) {
            msg.textContent = (res.body && res.body.detail) ||
              'PayPal sandbox is not configured on this server. Checkout is unavailable.';
            return;
          }
          if (res.body && res.body.approve_url) {
            window.location = res.body.approve_url;
            return;
          }
          msg.textContent = (res.body && res.body.error) || 'Checkout failed.';
        })
        .catch(function () { msg.textContent = 'Network error starting checkout.'; });
    });
  }

  // --- Quote expiry countdown ---
  var expiryEl = document.getElementById('dp-expiry');
  if (expiryEl) {
    var ts = parseInt(expiryEl.getAttribute('data-expires'), 10);
    if (ts > 0) {
      var cd = document.getElementById('dp-countdown');
      var tick = function () {
        var left = ts - Math.floor(Date.now() / 1000);
        if (left <= 0) { cd.textContent = '(expired)'; return; }
        var m = Math.floor(left / 60), s = left % 60;
        cd.textContent = '(expires in ' + m + 'm ' + s + 's)';
        setTimeout(tick, 1000);
      };
      tick();
    }
  }
})();
