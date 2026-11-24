const { expect, test } = require('./test.cjs');

let primed = false;

test('checkout.primer', async () => {
  primed = true;
});

test('checkout.order-dependent', async ({ page }, testInfo) => {
  await page.goto('/');
  const actual = String(primed);
  try {
    expect(actual).toBe('false');
  } catch (error) {
    testInfo.annotations.push({
      type: 'reprostamp.assertion',
      description: JSON.stringify({ id: 'isolated_case', actual, expected: 'false' }),
    });
    throw error;
  }
});
