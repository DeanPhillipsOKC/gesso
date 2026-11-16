// Phone-size screenshots of an A/B page (#165), to check the layout at 390 px wide before the owner scores it.
//
//   node spike/experiments/bench/ab_screenshot.js <page.html> <out-prefix>
//
// Writes <out-prefix>-top.png (the first screen), <out-prefix>-step.png (after a swipe to step 2, scrolled to the
// words), <out-prefix>-rubric.png (the rubric, with a few scores tapped) and <out-prefix>-full.png (the whole first
// picture), and prints what the page saved through saveScores(). Needs Playwright with Chromium (require('playwright')).
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const [page_, prefix] = process.argv.slice(2);
  if (!page_ || !prefix) { console.error('usage: ab_screenshot.js <page.html> <out-prefix>'); process.exit(2); }
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true,
    hasTouch: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto('file://' + path.resolve(page_));
  await page.screenshot({ path: prefix + '-top.png' });
  await page.locator('section.pic.on button[aria-label="Next step"]').first().click();
  await page.locator('section.pic.on .sname').first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: prefix + '-step.png' });
  await page.locator('section.pic.on button.worst').first().click();
  const scale = page.locator('section.pic.on .scale').first();
  await scale.locator('button').nth(3).click();
  await page.locator('section.pic.on .scale').nth(1).locator('button').nth(2).click();
  await scale.scrollIntoViewIfNeeded();
  await page.screenshot({ path: prefix + '-rubric.png' });
  await page.screenshot({ path: prefix + '-full.png', fullPage: true });
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  const saved = await page.evaluate(() => {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith('gesso-ab:')) return localStorage.getItem(k);
    }
    return null;
  });
  console.log(JSON.stringify({ scrollWidth: width, errors, saved: saved && JSON.parse(saved).pictures[0] }, null, 1));
  await browser.close();
})();
