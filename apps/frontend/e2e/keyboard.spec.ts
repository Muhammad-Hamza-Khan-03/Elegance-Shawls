import { expect, test, type Locator, type Page } from '@playwright/test';

async function tabTo(page: Page, target: Locator, max = 80) {
  for (let index = 0; index < max; index += 1) {
    await page.keyboard.press('Tab');
    if (await target.evaluate((element) => element === document.activeElement).catch(() => false)) return;
  }
  throw new Error('target never received keyboard focus');
}

test('keyboard only: skip link, product quantity, add to cart, cart quantity', async ({ page, isMobile }) => {
  test.skip(isMobile, 'keyboard path is a desktop concern');
  await page.goto('/product/classic-wool-shawl');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main-content$/);
  await tabTo(page, page.getByLabel('Increase quantity'));
  await page.keyboard.press('Enter');
  await tabTo(page, page.getByRole('button', { name: 'Add to cart' }));
  await page.keyboard.press('Enter');
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('2');
  await page.goto('/cart');
  await expect(page.getByRole('heading', { name: 'Your cart' })).toBeVisible();
  await tabTo(page, page.getByLabel('Increase Classic Wool Shawl quantity'));
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('3');
});
