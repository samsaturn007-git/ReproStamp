const { expect, test } = require('./test.cjs');

test('checkout.mixed', async ({ page }, testInfo) => {
  await page.goto('/');
  // Deliberately use browser entropy outside the owner profile's seeded Math.random.
  const actual = await page.evaluate(() => String(crypto.getRandomValues(new Uint8Array(1))[0] % 2));
  try {
    expect(actual).toBe('0');
  } catch (error) {
    testInfo.annotations.push({
      type: 'reprostamp.assertion',
      description: JSON.stringify({ id: 'intermittent_bit', actual, expected: '0' }),
    });
    throw error;
  }
});
