// anti_block/forms/scripts/form_inspector.js
//
// Inspect contact forms on a page — return structured field list + captcha flags.
// Used by Hermes form-filler skill as the first step after navigate + autoconsent.
//
// Why a separate inspector (vs the existing /opt/payment-scout/payment-scout/anti_block/browser/inspect_form.js):
//   - scan-side inspect_form.js is tuned for casino payment forms (currency selects,
//     hidden honeypots, GA dataLayer cross-check).
//   - This one is tuned for corporate contact forms (label-driven mapping,
//     captcha provider detection, multi-step form awareness, iframes).
//
// Output schema:
// {
//   ok: true,
//   forms: [
//     {
//       index: 0,
//       method: "POST",
//       action: "https://...",
//       in_iframe: false,
//       fields: [
//         {tag, type, name, id, label, placeholder, required, autocomplete,
//          options? (for select), visible, hidden_attr, value_present}
//       ],
//       submit_buttons: [{tag, text, type, ref}],  // for tracking — NOT for clicking
//       has_consent_checkbox: bool,
//     }
//   ],
//   captcha: {
//     recaptcha_v2: {sitekey, invisible, present},
//     recaptcha_v3: {sitekey, action, present},
//     hcaptcha: {sitekey, present},
//     turnstile: {sitekey, present},
//     geetest: {captcha_id, present},
//     friendly_captcha: {sitekey, present}
//   },
//   iframes: [{src, sandbox, is_recaptcha, is_hcaptcha}],
//   page_title: string,
//   body_size: int,
//   js_frameworks: [list of detected: angular, react, vue, nuxt, next]
// }

(() => {
  const result = {
    ok: true,
    forms: [],
    captcha: {
      recaptcha_v2: null,
      recaptcha_v3: null,
      hcaptcha: null,
      turnstile: null,
      geetest: null,
      friendly_captcha: null,
    },
    iframes: [],
    page_title: document.title,
    body_size: document.body ? document.body.innerHTML.length : 0,
    js_frameworks: [],
  };

  // Detect JS frameworks.
  if (window.ng || window.getAllAngularRootElements) result.js_frameworks.push('angular');
  if (window.React || document.querySelector('[data-reactroot], [data-reactid]')) result.js_frameworks.push('react');
  if (window.Vue || document.querySelector('[data-v-]')) result.js_frameworks.push('vue');
  if (window.__NUXT__) result.js_frameworks.push('nuxt');
  if (window.__NEXT_DATA__) result.js_frameworks.push('next');

  function fieldLabel(el) {
    if (!el) return '';
    // 1. <label for="id">
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) return (lbl.innerText || lbl.textContent || '').trim();
    }
    // 2. parent <label>
    let parent = el.parentElement;
    for (let i = 0; i < 4 && parent; i++) {
      if (parent.tagName === 'LABEL') {
        return (parent.innerText || parent.textContent || '').trim();
      }
      parent = parent.parentElement;
    }
    // 3. aria-label / aria-labelledby
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const lbl = document.getElementById(labelledby);
      if (lbl) return (lbl.innerText || lbl.textContent || '').trim();
    }
    // 4. placeholder fallback
    return (el.placeholder || el.title || '').trim();
  }

  function visible(el) {
    try {
      const r = el.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) return false;
      const st = getComputedStyle(el);
      return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
    } catch (_) { return false; }
  }

  // Honeypot detection.
  // Heuristics (any one of these flags the field as a likely honeypot):
  //   1. type=hidden + required=true — explicit trap, real users can't see, only bots fill
  //   2. visually hidden (display:none / visibility:hidden / opacity:0 / off-screen)
  //      but NOT type=hidden — CSS-cloaked traps (most common Wordfence/wpcf7 honeypot)
  //   3. name matches common honeypot conventions: "honeypot", "honey_pot", "url" (off
  //      a form that already has another url field), "email_confirm" left blank, etc.
  //   4. tabindex="-1" + invisible — explicitly excluded from tab order
  //   5. autocomplete="off" + name containing "url"/"website"/"phone" on a non-relevant form
  //
  // We mark honeypots so the skill can SKIP them entirely (filling = instant bot flag).
  const HONEYPOT_NAME_RE = /^(honeypot|honey_pot|hp_|bot_field|bot-field|antispam|anti_spam|spam_protect|website_url|company_phone|fax|url)$/i;
  function isHoneypot(el, f) {
    // type=hidden + required is a classic trap.
    if (f.hidden_attr && f.required) return { is: true, reason: 'hidden+required' };

    // CSS-cloaked but not type=hidden.
    try {
      const style = getComputedStyle(el);
      if (!f.hidden_attr && (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0)) {
        return { is: true, reason: 'css_hidden' };
      }
      // Off-screen positioning (negative coordinates >5000px from viewport).
      const rect = el.getBoundingClientRect();
      if (!f.hidden_attr && (rect.left < -5000 || rect.top < -5000 || rect.left > 5000 || rect.top > 5000)) {
        return { is: true, reason: 'off_screen' };
      }
    } catch (_) {}

    // Name matches honeypot convention.
    if (f.name && HONEYPOT_NAME_RE.test(f.name)) return { is: true, reason: 'name_pattern:' + f.name };

    // tabindex=-1 + invisible (excluded from tab order = not for humans)
    const tabidx = el.getAttribute('tabindex');
    if (tabidx === '-1' && !f.visible) return { is: true, reason: 'tabindex_-1+invisible' };

    return { is: false, reason: null };
  }

  function inspectField(el) {
    const f = {
      tag: el.tagName.toLowerCase(),
      type: (el.type || '').toLowerCase(),
      name: el.name || null,
      id: el.id || null,
      label: fieldLabel(el),
      placeholder: el.placeholder || null,
      required: el.required === true,
      autocomplete: el.getAttribute('autocomplete') || null,
      visible: visible(el),
      hidden_attr: el.hidden || el.type === 'hidden',
      value_present: !!(el.value && String(el.value).length > 0),
    };
    const hp = isHoneypot(el, f);
    f.honeypot = hp.is;
    f.honeypot_reason = hp.reason;
    if (el.tagName === 'SELECT') {
      f.options = Array.from(el.options).slice(0, 50).map((o) => ({
        value: o.value,
        text: (o.textContent || '').trim().substring(0, 80),
      }));
    }
    return f;
  }

  // Collect forms (including those without <form> — use heuristic: cluster of inputs near "contact" heading).
  const formsList = Array.from(document.querySelectorAll('form'));
  formsList.forEach((form, idx) => {
    const fields = Array.from(form.querySelectorAll('input, textarea, select')).map(inspectField);
    const submit_buttons = Array.from(form.querySelectorAll('button, input[type="submit"], input[type="button"]'))
      .filter((b) => {
        const txt = (b.textContent || b.value || '').toLowerCase();
        return /submit|send|contact|envoyer|enviar|senden|invia|отправить/.test(txt) || b.type === 'submit';
      })
      .map((b) => ({
        tag: b.tagName.toLowerCase(),
        text: (b.textContent || b.value || '').trim().substring(0, 60),
        type: b.type || null,
      }));
    const has_consent = fields.some(
      (f) => f.type === 'checkbox' && /consent|agree|privacy|gdpr|terms/i.test([f.name, f.id, f.label].join(' '))
    );
    result.forms.push({
      index: idx,
      method: (form.method || 'GET').toUpperCase(),
      action: form.action || '',
      in_iframe: false,
      fields,
      submit_buttons,
      has_consent_checkbox: has_consent,
    });
  });

  // Captcha detection.
  // reCAPTCHA v2 / v3 (both use g-recaptcha class or grecaptcha object)
  try {
    const rec = document.querySelector('.g-recaptcha, [data-sitekey], #recaptcha');
    if (rec) {
      const sitekey = rec.getAttribute('data-sitekey') || (window.___grecaptcha_cfg && Object.values(window.___grecaptcha_cfg.clients || {})[0]?.sitekey);
      const invisible = rec.getAttribute('data-size') === 'invisible' || (rec.getAttribute('data-callback') && !rec.querySelector('div'));
      result.captcha.recaptcha_v2 = { sitekey: sitekey || null, invisible: !!invisible, present: true };
    }
    if (window.grecaptcha && window.grecaptcha.enterprise) {
      result.captcha.recaptcha_v3 = { sitekey: null, action: 'enterprise', present: true };
    }
    // v3 sometimes only present via script include
    const v3script = document.querySelector('script[src*="recaptcha/api.js?render="]');
    if (v3script) {
      const m = v3script.src.match(/render=([^&]+)/);
      result.captcha.recaptcha_v3 = result.captcha.recaptcha_v3 || { sitekey: m ? m[1] : null, action: null, present: true };
    }
  } catch (_) {}

  // hCaptcha
  try {
    const h = document.querySelector('.h-captcha, [data-hcaptcha-sitekey]');
    if (h) {
      const sitekey = h.getAttribute('data-sitekey') || h.getAttribute('data-hcaptcha-sitekey');
      result.captcha.hcaptcha = { sitekey: sitekey || null, present: true };
    }
  } catch (_) {}

  // Cloudflare Turnstile
  try {
    const t = document.querySelector('.cf-turnstile, [data-sitekey][data-callback]');
    if (t && t.classList.contains('cf-turnstile')) {
      result.captcha.turnstile = { sitekey: t.getAttribute('data-sitekey'), present: true };
    }
  } catch (_) {}

  // GeeTest
  try {
    if (window.initGeetest || document.querySelector('[gt][challenge]')) {
      const el = document.querySelector('[gt][challenge]');
      result.captcha.geetest = { captcha_id: el ? el.getAttribute('gt') : null, present: true };
    }
  } catch (_) {}

  // Friendly Captcha
  try {
    const fc = document.querySelector('.frc-captcha, [data-sitekey][class*="friendly"]');
    if (fc) result.captcha.friendly_captcha = { sitekey: fc.getAttribute('data-sitekey'), present: true };
  } catch (_) {}

  // Iframes (in case form is inside one).
  result.iframes = Array.from(document.querySelectorAll('iframe')).slice(0, 10).map((f) => ({
    src: (f.src || '').substring(0, 200),
    sandbox: f.sandbox ? f.sandbox.toString() : null,
    is_recaptcha: (f.src || '').includes('recaptcha'),
    is_hcaptcha: (f.src || '').includes('hcaptcha'),
    is_turnstile: (f.src || '').includes('challenges.cloudflare'),
  }));

  return result;
})();
