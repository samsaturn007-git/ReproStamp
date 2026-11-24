const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('../tools/runner-smoke/node_modules/playwright');

const [origin, evidence, passwordPath, action, runId] = process.argv.slice(2);

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  try {
    await page.goto(`${origin}/?run=${runId}`);
    await page.getByLabel('Owner password').fill(fs.readFileSync(passwordPath, 'utf8').trim());
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const review = page.locator('.route-review').filter({ has: page.getByRole('heading', { name: '/review', exact: true }) });
    await review.waitFor();
    for (const name of ['Baseline', 'Candidate', 'Pixel diff']) {
      const image = review.getByRole('img', { name: `${name} screenshot for /review` });
      await image.waitFor();
      await image.evaluate(element => element.decode());
      assert.equal(await image.evaluate(element => element.naturalWidth), 1100);
    }
    const approve = review.getByRole('button', { name: 'Approve candidate screenshot' });
    await approve.waitFor();
    if (action === 'approve') {
      await approve.focus();
      await page.keyboard.press('Enter');
      await review.getByText(/^Approved by owner/).waitFor();
      assert.equal(await approve.count(), 0);
    }
    if (action === 'regression') {
      const findings = review.getByRole('table', { name: 'New accessibility findings for /review' });
      const label = findings.getByRole('row').filter({ hasText: 'label' });
      await label.getByText('#promo', { exact: true }).waitFor();
      await label.getByText('critical', { exact: true }).waitFor();
    } else {
      await review.getByText('Approval history (1)', { exact: true }).click();
      await review.getByRole('link', { name: 'Source run', exact: true }).waitFor();
    }
    await review.screenshot({ path: path.join(evidence, `${action}-desktop.png`) });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await review.screenshot({ path: path.join(evidence, `${action}-mobile.png`) });
    console.log(`PASS ${action} review in dashboard with loaded evidence images and mobile layout`);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
