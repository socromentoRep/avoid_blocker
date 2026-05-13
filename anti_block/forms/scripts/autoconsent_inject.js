// anti_block/forms/scripts/autoconsent_inject.js
//
// Hand-rolled cookie-consent banner dismisser.
// Covers the top-15 CMP families seen on PSP corporate sites:
//   - OneTrust, Cookiebot, TrustArc, Cookieyes, Termly, Iubenda
//   - cmplz (WordPress Complianz), Borlabs (German), CookieYes
//   - GDPR-styled custom popups with "Accept all" / "Reject all" text
//   - Cloudflare bot challenge "I'm not a robot" — NOT clicked (different beast)
//
// Why hand-rolled instead of vendoring DuckDuckGo's autoconsent:
//   1. Bundle size: autoconsent.cjs.bundle.js is ~400KB.
//   2. Many corporate PSP sites use non-standard markup not in autoconsent rules.
//   3. We need synchronous, deterministic behaviour for the test report.
//
// Strategy:
//   - Prefer REJECT-all if present (less data exfiltration, lower bot score).
//   - Else ACCEPT-all (still better than leaving overlay blocking the form).
//   - Search by visible button text + common selectors + accessibility roles.
//   - Wait up to 800ms for CMP iframe/shadow-dom to settle, then re-try once.
//
// Return: {ok: bool, cmp: <name|null>, action: "rejected"|"accepted"|"none", clicked: <text|null>}

(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Phrases that identify the action (case-insensitive).
  const REJECT_PHRASES = [
    'reject all', 'reject cookies', 'reject non-essential', 'reject optional',
    'decline all', 'decline cookies', 'decline non-essential',
    'отклонить', 'отказаться от cookies', 'отказаться',
    'tout refuser', 'refuser tout', 'refuser les cookies',
    'alle ablehnen', 'ablehnen',
    'rechazar todo', 'rechazar', 'rifiuta tutto', 'rifiuta',
    'rejeitar tudo', 'rejeitar', 'odmów wszystkie', 'odmów',
  ];
  const ACCEPT_PHRASES = [
    'accept all', 'accept cookies', 'accept', 'allow all', 'agree all',
    'i agree', 'i accept', 'got it', 'continue',
    'принять', 'принять все', 'согласен', 'согласиться',
    'tout accepter', 'accepter tout', 'accepter',
    'alle akzeptieren', 'akzeptieren',
    'aceptar todo', 'aceptar', 'accetta tutto', 'accetta',
    'aceitar tudo', 'aceitar', 'zaakceptuj wszystkie',
  ];
  // Phrases that we MUST NOT click — these are submit/send buttons.
  const FORBIDDEN_PHRASES = [
    'submit', 'send', 'send message', 'contact us', 'отправить',
    'envoyer', 'enviar', 'senden', 'invia',
  ];

  // CMP detector by DOM signatures. Returns {name, scope_selector?} or null.
  function detectCMP() {
    const checks = [
      { name: 'OneTrust', test: () => document.getElementById('onetrust-banner-sdk') || document.querySelector('#onetrust-consent-sdk'), scope: '#onetrust-banner-sdk' },
      { name: 'Cookiebot', test: () => document.getElementById('CybotCookiebotDialog'), scope: '#CybotCookiebotDialog' },
      { name: 'TrustArc', test: () => document.querySelector('iframe[src*="trustarc"]') || document.querySelector('#truste-consent-track'), scope: '#truste-consent-track' },
      { name: 'CookieYes', test: () => document.getElementById('cky-consent') || document.querySelector('.cky-banner'), scope: '#cky-consent' },
      { name: 'Termly', test: () => document.querySelector('.termly-dialog-trigger'), scope: '.termly-dialog-trigger' },
      { name: 'Iubenda', test: () => document.getElementById('iubenda-cs-banner'), scope: '#iubenda-cs-banner' },
      { name: 'cmplz', test: () => document.querySelector('.cmplz-cookiebanner') || document.querySelector('#cmplz-cookiebanner-container'), scope: '.cmplz-cookiebanner' },
      { name: 'Borlabs', test: () => document.querySelector('#BorlabsCookieBox'), scope: '#BorlabsCookieBox' },
      { name: 'Didomi', test: () => document.getElementById('didomi-popup') || document.getElementById('didomi-notice'), scope: '#didomi-host' },
      { name: 'Quantcast', test: () => document.querySelector('.qc-cmp2-container'), scope: '.qc-cmp2-container' },
      { name: 'Osano', test: () => document.querySelector('.osano-cm-window'), scope: '.osano-cm-window' },
      { name: 'Klaro', test: () => document.querySelector('.klaro'), scope: '.klaro' },
      { name: 'Usercentrics', test: () => document.getElementById('usercentrics-root'), scope: '#usercentrics-root' },
      { name: 'CivicUK', test: () => document.querySelector('#ccc'), scope: '#ccc' },
      { name: 'Sourcepoint', test: () => document.querySelector('iframe[id^="sp_message_iframe"]'), scope: 'body' },
      // Additional CMPs found in PSP corp sites + general high-traffic corporate sites
      { name: 'CookieScript', test: () => document.getElementById('cookiescript_injected') || document.querySelector('.cookiescript_wrapper'), scope: '#cookiescript_injected' },
      { name: 'Cookiehub', test: () => document.querySelector('.ch2, [class*="cookiehub"]'), scope: '.ch2' },
      { name: 'Crownpeak', test: () => document.querySelector('#evidon-banner, #_evidon-popup-container'), scope: '#evidon-banner' },
      { name: 'Piwik PRO', test: () => document.querySelector('[class*="ppms_cm_"]') || document.querySelector('#ppms_cm_popup_overlay'), scope: '.ppms_cm_popup' },
      { name: 'Ezoic', test: () => document.querySelector('#ez-cookie-dialog-wrapper, .ez-cookie-dialog'), scope: '#ez-cookie-dialog-wrapper' },
      { name: 'AdRoll', test: () => document.querySelector('#adroll_consent_banner, [data-adroll-consent]'), scope: '#adroll_consent_banner' },
      { name: 'Termly', test: () => document.querySelector('.termly-dialog-trigger, .t-consent-banner'), scope: '.termly-dialog-trigger' },
      { name: 'StripeCustom', test: () => document.querySelector('[data-testid="cookie-banner"]') || (document.title && /stripe/i.test(document.title) && document.querySelector('[role="dialog"]')), scope: '[data-testid="cookie-banner"]' },
      // GDPR-styled custom popups with role=dialog + cookie-related text content.
      { name: 'GenericRoleDialog', test: () => {
          const dialogs = document.querySelectorAll('[role="dialog"]:not([style*="display: none"]), [role="alertdialog"]');
          for (const d of dialogs) {
            const txt = (d.textContent || '').toLowerCase();
            if (/cookie|consent|gdpr|privacy.policy/.test(txt) && txt.length < 5000) return d;
          }
          return null;
        }, scope: 'body' },
      // Generic catch-all for custom popups using common class/aria patterns.
      { name: 'GenericCustom', test: () => document.querySelector('[class*="cookie-banner"], [class*="cookie-consent"], [id*="cookie-banner"], [id*="cookie-popup"], [aria-label*="cookie" i], [role="dialog"][aria-label*="consent" i]'), scope: 'body' },
    ];
    for (const c of checks) {
      try {
        const el = c.test();
        if (el) return { name: c.name, scope: c.scope };
      } catch (_) { /* keep going */ }
    }
    return null;
  }

  // Find a button matching ANY phrase, optionally restricted to `root`.
  function findClickable(phrases, root) {
    root = root || document;
    // Buttons, links, inputs with text/value/aria-label/title.
    const candidates = root.querySelectorAll(
      'button, a[role="button"], a, input[type="button"], input[type="submit"], [role="button"], [data-cookie-action], [class*="accept"], [class*="reject"], [class*="decline"]'
    );
    for (const el of candidates) {
      if (!isVisible(el)) continue;
      const txt = collectText(el).toLowerCase().trim();
      if (!txt) continue;
      // Hard skip submit-like buttons (form-filler safety).
      if (FORBIDDEN_PHRASES.some((f) => txt.includes(f))) {
        // Allow only if it's clearly a cookie context (e.g. "accept and send" — no, still risky).
        // Don't click. Skip.
        continue;
      }
      for (const p of phrases) {
        if (txt === p || txt.includes(p)) {
          return { el, text: txt, phrase: p };
        }
      }
    }
    // Try shadow DOM too (OneTrust, Usercentrics)
    try {
      const allHosts = root.querySelectorAll ? root.querySelectorAll('*') : [];
      for (const host of allHosts) {
        if (host.shadowRoot) {
          const inner = findClickable(phrases, host.shadowRoot);
          if (inner) return inner;
        }
      }
    } catch (_) { /* shadow disabled or X-origin */ }
    return null;
  }

  function collectText(el) {
    return (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
  }

  function isVisible(el) {
    try {
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return false;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      return true;
    } catch (_) { return false; }
  }

  // Main flow.
  await sleep(200); // let initial JS settle
  let cmp = detectCMP();
  if (!cmp) {
    // Maybe banner appears lazily; wait once more.
    await sleep(800);
    cmp = detectCMP();
  }
  if (!cmp) {
    return { ok: true, cmp: null, action: 'none', clicked: null };
  }

  // Prefer reject-all → fall back to accept-all.
  const scopeEl = cmp.scope ? document.querySelector(cmp.scope) || document : document;
  let target = findClickable(REJECT_PHRASES, scopeEl);
  let action = 'rejected';
  if (!target) {
    target = findClickable(ACCEPT_PHRASES, scopeEl);
    action = target ? 'accepted' : 'none';
  }
  if (!target) {
    return { ok: false, cmp: cmp.name, action: 'none', clicked: null, reason: 'no_matching_button' };
  }

  try {
    target.el.click();
    await sleep(300);
    return { ok: true, cmp: cmp.name, action, clicked: target.text.substring(0, 60), phrase: target.phrase };
  } catch (e) {
    return { ok: false, cmp: cmp.name, action: 'none', clicked: null, reason: 'click_failed:' + e.message };
  }
})();
