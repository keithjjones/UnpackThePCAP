#!/usr/bin/env node
/*
 * Screenshot the landing page at phone, tablet, and desktop widths.
 *
 * Renders with playwright-chromium, which is already a devDependency for the
 * slide checker, so there is nothing extra to install.
 *
 *   npm run shots:landing                       # build, shoot, print paths
 *   node tools/shoot-landing.js <index.html> <outdir>
 *
 * Also reports horizontal overflow per width: anything above 0 means the page
 * scrolls sideways, which is the failure mode that matters on a phone.
 */

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright-chromium');

const pageFile = path.resolve(process.argv[2] || 'dist/index.html');
const outDir = path.resolve(process.argv[3] || 'output/screenshots');

// fullPage for the small widths, where seeing the whole column is the point;
// viewport-only for desktop, where a full-page shot of a long list is useless.
const SHOTS = [
  { name: 'phone',         width: 390,  height: 844,  scheme: 'dark',  fullPage: true },
  { name: 'phone-light',   width: 390,  height: 844,  scheme: 'light', fullPage: true },
  { name: 'tablet',        width: 768,  height: 1024, scheme: 'dark',  fullPage: true },
  { name: 'desktop',       width: 1280, height: 900,  scheme: 'dark',  fullPage: false },
  { name: 'desktop-light', width: 1280, height: 900,  scheme: 'light', fullPage: false },
];

(async () => {
  if (!fs.existsSync(pageFile)) {
    console.error(`shoot-landing: no such page: ${pageFile}`);
    console.error('Build it first, e.g. python3 tools/build_landing.py --out dist');
    process.exit(2);
  }
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch();
  const problems = [];

  for (const shot of SHOTS) {
    const ctx = await browser.newContext({
      viewport: { width: shot.width, height: shot.height },
      deviceScaleFactor: 2,          // retina, so text is legible when zoomed
      colorScheme: shot.scheme,
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => problems.push(`${shot.name}: JS error: ${e.message}`));

    await page.goto(`file://${pageFile}`, { waitUntil: 'load' });
    await page.waitForTimeout(250);   // let the banner decode

    const file = path.join(outDir, `${shot.name}.png`);
    await page.screenshot({ path: file, fullPage: shot.fullPage });

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 0) problems.push(`${shot.name}: ${overflow}px horizontal overflow`);

    console.log(`  ${path.relative(process.cwd(), file).padEnd(36)} ` +
                `${shot.width}x${shot.height} ${shot.scheme}, overflow ${overflow}px`);
    await ctx.close();
  }

  await browser.close();

  if (problems.length) {
    console.error('\nshoot-landing: problems found:');
    for (const p of problems) console.error(`  ${p}`);
    process.exit(1);
  }
  console.log('\nshoot-landing: no horizontal overflow, no JS errors.');
})();
