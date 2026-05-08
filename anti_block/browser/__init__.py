"""Browser modules — anti-detect Chromium (CloakBrowser) + DOM helpers.

Modules:
- cloak: open URL via CloakBrowser (open-source Dolphin-Anty alternative)
- inspect_form.js: JS snippet to dump all form inputs (visible + hidden)

inspect_form.js usage (Playwright/Puppeteer):
    const inputs = await page.evaluate(fs.readFileSync(\"path/to/inspect_form.js\", \"utf8\"));
"""
