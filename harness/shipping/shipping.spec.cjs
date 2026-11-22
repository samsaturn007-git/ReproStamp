const { expect, test } = require('./test.cjs');

async function assertFee(page, testInfo, subtotal, id, expected) {
  await page.goto('/');
  await page.getByLabel('Order subtotal (USD)').fill(subtotal);
  const actual = await page.getByLabel('Shipping fee').textContent({ timeout: 3_000 });
  try {
    expect(actual).toBe(expected);
  } catch (error) {
    testInfo.annotations.push({
      type: 'reprostamp.assertion',
      description: JSON.stringify({ id, actual, expected }),
    });
    throw error;
  }
}

test('shipping.free-at-threshold', async ({ page }, testInfo) => {
  await assertFee(page, testInfo, '50.00', 'threshold_fee', '$0.00');
});

test('shipping.paid-below-threshold', async ({ page }, testInfo) => {
  await assertFee(page, testInfo, '49.99', 'standard_fee', '$6.00');
});
