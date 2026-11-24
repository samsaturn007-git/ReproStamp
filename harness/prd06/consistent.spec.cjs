const { test } = require('./test.cjs');

test('checkout.full-price', async ({ page }, testInfo) => {
  await page.goto('/');
  try {
    await page.evaluate(async () => (await import('/src/checkout.ts')).reviewOrdinaryTotal());
  } catch (error) {
    const match = /Ordinary total was (\d+)/.exec(error.message);
    if (match) {
      testInfo.annotations.push({
        type: 'reprostamp.assertion',
        description: JSON.stringify({ id: 'ordinary_total', actual: match[1], expected: '10000' }),
      });
    }
    throw error;
  }
});
