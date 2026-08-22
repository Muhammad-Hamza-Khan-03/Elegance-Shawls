import { expect, test } from '@playwright/test';

test('shared cart supports multiple products, quantity editing and refresh persistence', async ({ page }) => {
  await page.goto('/product/classic-wool-shawl');
  await page.getByLabel('Increase quantity').click();
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('2');

  await page.goto('/product/light-silk-stole');
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('3');

  await page.goto('/cart');
  await expect(page.getByRole('heading', { name: 'Your cart' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Classic Wool Shawl' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Light Silk Stole' })).toBeVisible();
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('2');
  await page.getByLabel('Increase quantity for Classic Wool Shawl').click();
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('3');
  await expect(page.getByLabel('Increase quantity for Classic Wool Shawl')).toBeDisabled();

  await page.reload();
  await expect(page.getByLabel('Quantity for Classic Wool Shawl')).toHaveValue('3');
  await expect(page.getByLabel('Quantity for Light Silk Stole')).toHaveValue('1');
  await expect(page.getByRole('link', { name: /Cart/ }).last()).toContainText('4');
});
