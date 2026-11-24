const { expect, test } = require('./test.cjs');

test('checkout.keyboard', async ({ page }) => {
  await page.goto('/review');
  await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();
  const promo = page.locator('#promo');
  const apply = page.getByRole('button', { name: 'Apply' });
  await page.keyboard.press('Tab');
  await expect(promo).toBeFocused();
  await expect(promo).toHaveCSS('outline-style', 'auto');
  await page.keyboard.type('SAVE10');
  await page.keyboard.press('Tab');
  await expect(apply).toBeFocused();
  await expect(apply).toHaveCSS('outline-style', 'auto');
  await page.keyboard.press('Shift+Tab');
  await expect(promo).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(apply).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('status').filter({ hasText: 'Promo code applied' })).toBeVisible();
});
