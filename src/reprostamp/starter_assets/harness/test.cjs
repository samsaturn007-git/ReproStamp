const { expect, test: base } = require('@playwright/test');

const { seed } = JSON.parse(process.env.REPROSTAMP_BROWSER_SETTINGS);

const test = base.extend({
  browserEvidence: [async ({ browser, browserName, context }, use, testInfo) => {
    testInfo.annotations.push({
      type: 'reprostamp.browser',
      description: JSON.stringify({
        engine: browserName,
        version: browser.version(),
        platform: `${process.platform}/${process.arch}`,
      }),
    });
    await context.addInitScript(initialSeed => {
      let state = initialSeed;
      Math.random = () => {
        state = (Math.imul(1664525, state) + 1013904223) >>> 0;
        return state / 2 ** 32;
      };
    }, seed);
    await use();
  }, { auto: true }],
});

module.exports = { expect, test };
