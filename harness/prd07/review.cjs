const { renameSync, writeFileSync } = require('node:fs');
const playwright = require('@playwright/test');
const axe = require('axe-core');

const origin = 'http://127.0.0.1:4173';
const settings = JSON.parse(process.env.REPROSTAMP_BROWSER_SETTINGS);
const { engine, routes } = JSON.parse(process.env.REPROSTAMP_REVIEW);

function message(error) {
  return (error instanceof Error ? error.message : String(error)).slice(0, 512);
}

async function capture(browser, route) {
  const result = { id: route.id, visual_error: null, accessibility_error: null, findings: null };
  const context = await browser.newContext({
    viewport: { width: settings.viewport_width, height: settings.viewport_height },
    deviceScaleFactor: 1,
    locale: settings.locale,
    timezoneId: settings.timezone,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  });
  try {
    await context.addInitScript(initialSeed => {
      let state = initialSeed;
      Math.random = () => {
        state = (Math.imul(1664525, state) + 1013904223) >>> 0;
        return state / 2 ** 32;
      };
    }, settings.seed);
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    const response = await page.goto(new URL(route.path, origin).href, { waitUntil: 'load' });
    if (!response?.ok() || new URL(page.url()).origin !== origin) {
      throw new Error(`${route.path} did not load on the application origin.`);
    }
    await page.locator(route.ready).waitFor({ state: 'visible' });
    try {
      // Playwright waits for document fonts. The runner image pins installed font files and fontconfig.
      await page.screenshot({ path: `/evidence/review-${route.id}.png`, animations: 'disabled',
        caret: 'hide', scale: 'css' });
    } catch (error) {
      result.visual_error = message(error);
    }
    try {
      await page.addScriptTag({ content: axe.source });
      const observed = await page.evaluate(async () => {
        const scan = await window.axe.run({ resultTypes: ['violations'] });
        const findings = scan.violations.flatMap(rule => rule.nodes.map(node => ({
          rule: rule.id,
          impact: node.impact ?? rule.impact ?? null,
          target: node.target.map(selector => Array.isArray(selector) ? selector.join(' › ') : selector).join(' → '),
        })));
        return { version: scan.testEngine.version, findings };
      });
      if (observed.version !== axe.version || observed.findings.length > 200) {
        throw new Error('The axe scan returned an unexpected version or exceeded 200 findings.');
      }
      result.findings = observed.findings;
    } catch (error) {
      result.accessibility_error = message(error);
    }
  } catch (error) {
    result.visual_error = result.accessibility_error = message(error);
  } finally {
    await context.close();
  }
  return result;
}

async function main() {
  const browser = await playwright[engine].launch({ headless: true });
  try {
    const results = [];
    for (const route of routes) results.push(await capture(browser, route));
    const report = { browser: { engine, version: browser.version(), platform: `${process.platform}/${process.arch}` },
      axe_version: axe.version, routes: results };
    writeFileSync('/evidence/.review.json.tmp', JSON.stringify(report));
    renameSync('/evidence/.review.json.tmp', '/evidence/review.json');
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
