// anti_block/forms/scripts/fingerprint_overrides.js
//
// Drop-in anti-fingerprint overrides for Hermes form-filler.
// Inject via `mcp__playwright__browser_evaluate` BEFORE first user interaction
// on each new page (after navigate). Idempotent — safe to call multiple times.
//
// Mirrors the scan-side overrides from prompts/shared/_anti-fingerprint.md
// so form-filler and scan present the same device fingerprint when needed.
//
// Returns: {ok: bool, applied: [list of overrides], skipped: [reasons]}

(() => {
  const applied = [];
  const skipped = [];

  // 1. webdriver flag (critical — every anti-bot checks it first)
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
    applied.push('webdriver');
  } catch (e) { skipped.push('webdriver:' + e.message); }

  // 2. Hardware (Samsung Galaxy A16 5G profile — matches scan)
  try {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 4, configurable: true });
    applied.push('hardware');
  } catch (e) { skipped.push('hardware:' + e.message); }

  // 3. WebGL: Qualcomm Adreno 610 (budget Samsung GPU)
  try {
    const patchWebGL = (proto) => {
      if (!proto) return;
      const orig = proto.getParameter;
      proto.getParameter = function (param) {
        if (param === 37445) return 'Qualcomm';       // UNMASKED_VENDOR_WEBGL
        if (param === 37446) return 'Adreno (TM) 610'; // UNMASKED_RENDERER_WEBGL
        return orig.call(this, param);
      };
    };
    patchWebGL(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') {
      patchWebGL(WebGL2RenderingContext.prototype);
    }
    applied.push('webgl');
  } catch (e) { skipped.push('webgl:' + e.message); }

  // 4. Network: Indian/EU 4G connection
  try {
    if (navigator.connection) {
      Object.defineProperty(navigator.connection, 'effectiveType', { get: () => '4g', configurable: true });
      Object.defineProperty(navigator.connection, 'downlink', { get: () => 5.65, configurable: true });
      Object.defineProperty(navigator.connection, 'rtt', { get: () => 100, configurable: true });
      applied.push('connection');
    } else {
      skipped.push('connection:no_navigator_connection_api');
    }
  } catch (e) { skipped.push('connection:' + e.message); }

  // 5. Plugins: Chrome Mobile has minimal plugins
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [{ name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' }],
      configurable: true,
    });
    applied.push('plugins');
  } catch (e) { skipped.push('plugins:' + e.message); }

  // 6. Clean Playwright/patchright trace globals (idempotent)
  try {
    delete window.__playwright__binding__;
    delete window.__pwInitScripts;
    delete window.__playwright_run__;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    applied.push('trace_cleanup');
  } catch (e) { skipped.push('trace_cleanup:' + e.message); }

  // 7. Chrome runtime (anti-bots check window.chrome.runtime)
  try {
    if (!window.chrome) {
      window.chrome = {};
    }
    if (!window.chrome.runtime) {
      Object.defineProperty(window.chrome, 'runtime', {
        get: () => ({
          OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
          PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
          id: undefined,
        }),
        configurable: true,
      });
      applied.push('chrome_runtime');
    } else {
      skipped.push('chrome_runtime:already_present');
    }
  } catch (e) { skipped.push('chrome_runtime:' + e.message); }

  // 8. Permissions API (some anti-bots use unusual permissions queries)
  try {
    if (navigator.permissions && navigator.permissions.query) {
      const origQuery = navigator.permissions.query.bind(navigator.permissions);
      navigator.permissions.query = (parameters) => {
        if (parameters.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission, onchange: null });
        }
        return origQuery(parameters);
      };
      applied.push('permissions');
    }
  } catch (e) { skipped.push('permissions:' + e.message); }

  return { ok: true, applied, skipped, ts: Date.now() };
})();
