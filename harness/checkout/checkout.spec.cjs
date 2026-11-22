const { expect, test } = require('@playwright/test');

async function assertTotal(page, testInfo, id, expected) {
  const actual = await page.getByLabel('Order total').textContent({ timeout: 3_000 });
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

test('checkout.discount', async ({ page }, testInfo) => {
  await page.goto('/');
  await page.getByLabel('Promo code').fill('SAVE10');
  await page.getByRole('button', { name: 'Apply' }).click();
  await page.getByText('Promo code applied', { exact: true }).waitFor({ state: 'visible' });
  await assertTotal(page, testInfo, 'discounted_total', '$90.00');
});

test('checkout.full-price', async ({ page }, testInfo) => {
  await page.goto('/');
  await assertTotal(page, testInfo, 'ordinary_total', '$100.00');
});
