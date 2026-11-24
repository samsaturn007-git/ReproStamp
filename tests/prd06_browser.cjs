const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../tools/runner-smoke/node_modules/playwright");

const [origin, evidence, ownerFile, sourceId, mixedReplay] = process.argv.slice(2);

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1370, height: 980 } });
  try {
    await page.goto(`${origin}/?run=${sourceId}`);
    await page.getByLabel("Owner password").fill(fs.readFileSync(ownerFile, "utf8").trim());
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByRole("heading", { name: "Repository failure history" }).waitFor();
    await page.getByRole("heading", { name: "Application assertions" }).waitFor();
    await page.getByRole("heading", { name: "Runner and dependency failures" }).waitFor();
    const group = page.locator(".failure-groups details").filter({ hasText: "ordinary_total" });
    await group.locator("summary").click();
    await group.getByText(/^First seen .*Last seen .*Chromium, Firefox$/).waitFor();
    assert.equal(await group.getByRole("link", { name: /^Receipt / }).count(), 2);

    const original = page.locator("#attempt-chromium-head-1");
    await original.locator("summary").click();
    await original.getByRole("button", { name: "Replay failing case", exact: true }).click();
    await page.getByRole("heading", { name: "Case replay · checkout.full-price" }).waitFor();
    await page.getByText("Consistent failure", { exact: true }).waitFor({ timeout: 75_000 });
    const results = page.getByRole("table", { name: "Case replay outcomes" });
    await results.getByRole("link", { name: "Trace", exact: true }).nth(4).waitFor();
    assert.equal(await results.getByText(/^[1-9]\d* ms$/).count(), 5);
    assert.equal(await results.getByText("Assertion failed", { exact: true }).count(), 5);
    await page.getByRole("link", { name: "Original run and attempt", exact: true }).click();
    await original.getByText("Assertion failed", { exact: true }).waitFor();
    await page.getByRole("heading", { name: "Case replays", exact: true }).waitFor();

    await page.goto(`${origin}/?run=${mixedReplay}`);
    await page.getByText("Suspected flaky", { exact: true }).waitFor();
    await page.getByText("Sample size 5", { exact: true }).waitFor();
    const mixed = page.getByRole("table", { name: "Case replay outcomes" });
    assert.ok(await mixed.getByText("Passed", { exact: true }).count() > 0);
    assert.ok(await mixed.getByText("Assertion failed", { exact: true }).count() > 0);
    assert.equal(await mixed.getByRole("link", { name: "Trace", exact: true }).count(), 5);
    await page.screenshot({ path: path.join(evidence, "mixed-replay.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.ok(await mixed.evaluate((table) => table.parentElement.scrollWidth <= table.parentElement.clientWidth));
    await page.screenshot({ path: path.join(evidence, "mixed-replay-mobile.png"), fullPage: true });
    await page.getByRole("link", { name: "Original run and attempt", exact: true }).click();
    await page.locator("details[open]").getByText("checkout.mixed", { exact: true }).waitFor();
    assert.ok(await page.locator("details[open]").getByText("Assertion failed", { exact: true }).count() > 0);
    console.log("PASS dashboard replay action, five timed outcomes and trace links, source failure links, grouped receipts, and mobile layout");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
