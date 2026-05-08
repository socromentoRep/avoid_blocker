// anti_block/browser/inspect_form.js
//
// JS snippet для extracting ВСЕХ form inputs (visible + hidden + selects + textareas)
// со значениями, defaults, и состоянием visibility.
//
// Использование через MCP browser_evaluate:
//   mcp__playwright-proxy__browser_evaluate <содержимое этого файла>
//
// Возвращает массив объектов с полями:
//   { tag, type, name, id, value, defaultValue, hidden, required, options, label }
//
// Use case: registration / deposit forms with hidden inputs that get filled
// programmatically (currency picker, terms checkbox, country dropdown).
// If submit is disabled despite filling visible fields, GA dataLayer often
// reports form_length > visible — this snippet exposes ALL inputs (visible + hidden).

(() => {
  // Find all form-like elements; if multiple <form>, dump each separately
  const forms = Array.from(document.querySelectorAll('form'));
  const out = [];

  function describe(el) {
    const rect = el.getBoundingClientRect();
    const cs = window.getComputedStyle(el);
    const visible = (
      el.type !== 'hidden' &&
      cs.display !== 'none' &&
      cs.visibility !== 'hidden' &&
      cs.opacity !== '0' &&
      rect.width > 0 &&
      rect.height > 0
    );

    // Try to find label text
    let label = '';
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) label = (lab.textContent || '').trim().slice(0, 80);
    }
    if (!label && el.parentElement) {
      const parentLab = el.parentElement.querySelector('label');
      if (parentLab) label = (parentLab.textContent || '').trim().slice(0, 80);
    }
    if (!label) {
      label = el.placeholder || el.getAttribute('aria-label') || '';
    }

    return {
      tag: el.tagName.toLowerCase(),
      type: el.type || (el.tagName.toLowerCase() === 'select' ? 'select' : 'text'),
      name: el.name || '',
      id: el.id || '',
      value: (el.value || '').slice(0, 100),
      defaultValue: (el.defaultValue || '').slice(0, 100),
      hidden_attr: el.type === 'hidden',
      visible_in_dom: visible,
      display: cs.display,
      visibility: cs.visibility,
      required: el.required || false,
      readonly: el.readOnly || false,
      disabled: el.disabled || false,
      options: el.tagName.toLowerCase() === 'select'
        ? Array.from(el.options).slice(0, 30).map(o => ({
            value: o.value,
            text: (o.textContent || '').trim().slice(0, 60),
            selected: o.selected
          }))
        : [],
      label: label,
      attrs: ['data-required', 'data-validate', 'data-type', 'pattern', 'minlength', 'maxlength']
        .filter(a => el.hasAttribute(a))
        .reduce((acc, a) => { acc[a] = el.getAttribute(a); return acc; }, {})
    };
  }

  // Forms found explicitly
  forms.forEach((form, i) => {
    const inputs = Array.from(form.querySelectorAll('input, select, textarea'));
    out.push({
      form_index: i,
      form_id: form.id || '',
      form_name: form.name || '',
      form_action: form.action || '',
      form_method: form.method || 'get',
      total_inputs: inputs.length,
      visible_inputs: inputs.filter(e => {
        const cs = window.getComputedStyle(e);
        return e.type !== 'hidden' && cs.display !== 'none' && cs.visibility !== 'hidden';
      }).length,
      inputs: inputs.map(describe)
    });
  });

  // Also any inputs OUTSIDE <form> (modals/SPAs often don't wrap in <form>)
  const allInputs = Array.from(document.querySelectorAll('input, select, textarea'));
  const orphanInputs = allInputs.filter(e => !e.form);
  if (orphanInputs.length > 0) {
    out.push({
      form_index: -1,
      form_id: '(orphan inputs — no <form> wrapper)',
      total_inputs: orphanInputs.length,
      visible_inputs: orphanInputs.filter(e => {
        const cs = window.getComputedStyle(e);
        return e.type !== 'hidden' && cs.display !== 'none' && cs.visibility !== 'hidden';
      }).length,
      inputs: orphanInputs.map(describe)
    });
  }

  // GA dataLayer hint (some sites push form_length in GA — useful cross-check)
  const gaFormLengths = (window.dataLayer || [])
    .filter(e => e.event && /form/i.test(e.event) && e.form_length !== undefined)
    .slice(-5)
    .map(e => ({ event: e.event, form_length: e.form_length, form_id: e.form_id }));

  return {
    forms_found: forms.length,
    total_inputs_in_dom: allInputs.length,
    ga_form_events: gaFormLengths,
    forms: out
  };
})()
