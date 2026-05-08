#!/usr/bin/env node
// warmup_browser.js — Playwright script that opens URL via CDP, simulates
// human-like browsing for 30-60 seconds, then closes. Refreshes cookies
// (cf_clearance, dd_session, _abck, h_token) so WAF treats the profile as
// "trusted" on next production use.
//
// Usage:
//   node warmup_browser.js --cdp ws://127.0.0.1:NNNN --url https://example.com
//
// Requires: npm install playwright (or playwright-core if Chromium binary is
// already managed by the anti-detect browser).

const { chromium } = require('playwright');

async function main() {
    const args = process.argv.slice(2);
    let cdp = null;
    let url = null;
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--cdp') cdp = args[i + 1];
        if (args[i] === '--url') url = args[i + 1];
    }
    if (!cdp || !url) {
        console.error('usage: node warmup_browser.js --cdp <ws-endpoint> --url <homepage>');
        process.exit(2);
    }

    const browser = await chromium.connectOverCDP(cdp);
    const context = browser.contexts()[0] || await browser.newContext();
    const page = await context.newPage();

    try {
        console.log(`[warmup] navigating ${url}`);
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });

        // Wait for any anti-bot challenge to settle
        await page.waitForTimeout(8000);

        // Simulate scroll
        await page.evaluate(() => {
            window.scrollTo({ top: 400, behavior: 'smooth' });
        });
        await page.waitForTimeout(3000);

        await page.evaluate(() => {
            window.scrollTo({ top: 800, behavior: 'smooth' });
        });
        await page.waitForTimeout(3000);

        // Random small mouse jitter (humanize)
        for (let i = 0; i < 5; i++) {
            const x = 100 + Math.random() * 600;
            const y = 100 + Math.random() * 400;
            await page.mouse.move(x, y, { steps: 10 });
            await page.waitForTimeout(500 + Math.random() * 1000);
        }

        // Final dwell
        await page.waitForTimeout(5000);

        const cookies = await context.cookies();
        const interesting = cookies.filter(c => /cf_clearance|dd_session|_abck|h_token|datadome/i.test(c.name));
        console.log(`[warmup] cookies refreshed: ${interesting.map(c => c.name).join(', ') || '(none of interest)'}`);

    } catch (err) {
        console.error(`[warmup] ERROR: ${err.message}`);
        process.exitCode = 1;
    } finally {
        await page.close();
        // Don't close browser — Dolphin profile stays alive, we just disconnect
        await browser.close();
    }
}

main();
