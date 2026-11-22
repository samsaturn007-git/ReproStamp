// Local dashboard acceptance checks. The worker still runs browsers in the pinned Linux runner.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../tools/runner-smoke/node_modules/playwright");

const [origin, evidence, ownerFile] = process.argv.slice(2);
const mark = (name, value = "") => fs.writeFileSync(path.join(evidence, name), value);
const ready = (name) => fs.existsSync(path.join(evidence, name));

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
    recordVideo: { dir: evidence, size: { width: 1152, height: 800 } },
  });
  const page = await context.newPage();
  try {
    const cursors = [];
    page.on("request", async (request) => {
      if (request.url().endsWith("/events")) {
        cursors.push((await request.allHeaders())["last-event-id"] ?? "");
      }
    });
    await page.goto(origin);
    await page.getByLabel("Owner password").fill(fs.readFileSync(ownerFile, "utf8").trim());
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByRole("button", { name: "New run", exact: true }).first().click();
    await page.getByLabel("Repository").selectOption("checkout");
    await page.getByLabel("Profile").selectOption("checkout");
    await page.getByRole("button", { name: "Start run", exact: true }).click();
    await page.getByRole("heading", { name: "Discount checkout", exact: true }).waitFor();
    const id = new URL(page.url()).searchParams.get("run");
    assert.match(id, /^[a-f0-9-]{36}$/);
    await page.getByText("Attempt started", { exact: true }).first().waitFor();
    mark("browser-run-id", id);

    await page.getByText("Reconnecting", { exact: true }).waitFor({ timeout: 30_000 });
    mark("browser-disconnected");

    await page.getByText("Worker lease expired", { exact: true }).waitFor({ timeout: 45_000 });
    await page.getByText("Recovery started", { exact: true }).waitFor();
    await page.getByRole("link", { name: "Download receipt", exact: true }).waitFor({ timeout: 150_000 });
    await page.getByText("Complete", { exact: true }).waitFor();
    assert.ok(cursors.some((cursor) => Number(cursor) >= 3), cursors);
    const sequences = await page.locator("[data-sequence]").evaluateAll((items) =>
      items.map((item) => Number(item.dataset.sequence)));
    assert.deepEqual(sequences, sequences.map((_, index) => index + 1));
    mark("browser-timeline.json", JSON.stringify({ sequences, cursors }));

    const matrix = page.getByRole("table", { name: "Browser verification matrix" });
    assert.equal(await matrix.getByText("Assertion failed", { exact: true }).count(), 6);
    assert.equal(await matrix.getByText("Passed", { exact: true }).count(), 18);
    await page.screenshot({ path: path.join(evidence, "recovered-run.png"), fullPage: true });
    for (const [target, filename] of [
      [page.getByRole("link", { name: "Download receipt", exact: true }), "ui-receipt.zip"],
      [matrix.getByRole("link", { name: "Trace", exact: true }).first(), "ui-trace.zip"],
    ]) {
      const [download] = await Promise.all([page.waitForEvent("download"), target.click()]);
      await download.saveAs(path.join(evidence, filename));
    }
    await page.locator("details").filter({ hasText: "Generation 2" }).first().locator("summary").click();
    const log = page.getByRole("button", { name: "View app log", exact: true }).first();
    await page.route("**/artifacts/*", (route) => route.fulfill({
      contentType: "text/plain",
      body: '<img src="x" onerror="window.logExecuted = true">',
    }));
    await log.click();
    const dialog = page.getByRole("dialog");
    await dialog.locator("pre").getByText('<img src="x" onerror="window.logExecuted = true">', { exact: true }).waitFor();
    assert.equal(await dialog.locator("img").count(), 0);
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    mark("browser-recovered");
    console.log(`PASS browser submitted run, reconnected with Last-Event-ID ${cursors.find((value) => Number(value) >= 3)}, recovered ${sequences.length} ordered events and downloaded both ZIPs`);

    for (let count = 0; !ready("evidence-expired"); count++) {
      if (count >= 160) throw new Error("Test did not expire the run evidence");
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    await page.reload();
    await page.getByText(/^Evidence expired /).waitFor();
    assert.equal(await page.getByRole("link", { name: "Download receipt", exact: true }).count(), 0);
    assert.equal(await page.getByRole("link", { name: "Trace", exact: true }).count(), 0);
    console.log("PASS browser shows expired evidence and removes download links");
  } finally {
    await context.close();
    const video = page.video();
    if (video) {
      await video.saveAs(path.join(evidence, "worker-recovery.webm"));
      await video.delete();
    }
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
