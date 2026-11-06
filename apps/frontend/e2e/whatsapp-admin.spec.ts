import { expect, test, type Page } from '@playwright/test';

const MOCK = 'http://127.0.0.1:4100';

async function signIn(page: Page) {
  await page.goto('/admin/login');
  await page.getByLabel('Email').fill('owner@example.test');
  await page.getByLabel('Password').fill('test-owner-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
}

test('owner pairs the number, links an unlinked chat and reads the enquiry timeline', async ({ page, request }) => {
  await request.get(`${MOCK}/__whatsapp-disabled?on=0`);
  await signIn(page);
  await page.getByRole('link', { name: 'WhatsApp', exact: true }).click();
  await expect(page.getByTestId('status-card')).toContainText('Needs reconnect');

  await page.getByRole('button', { name: 'Connect WhatsApp' }).click();
  await expect(page.getByRole('img', { name: 'WhatsApp pairing QR code' })).toBeVisible();
  await expect(page.getByTestId('status-card')).toContainText('Connected as +923001234567', { timeout: 10_000 });

  await expect(page.getByTestId('unlinked-chat')).toContainText('Sana');
  await page.getByLabel(/Enquiry reference for/).fill('es-mock42');
  await page.getByRole('button', { name: 'Link', exact: true }).click();
  await expect(page.getByText('No unlinked chats.')).toBeVisible();

  await page.getByRole('link', { name: 'Enquiries' }).click();
  await page.getByRole('button', { name: 'Show WhatsApp chat' }).click();
  await expect(page.getByText('Thank you for your enquiry ES-MOCK42.')).toBeVisible();
});

test('shows a one-line notice instead of an error while automation is off', async ({ page, request }) => {
  await signIn(page);
  await request.get(`${MOCK}/__whatsapp-disabled?on=1`);
  try {
    await page.goto('/admin/whatsapp');
    await expect(page.getByTestId('whatsapp-disabled')).toContainText('WhatsApp automation is off');
    await expect(page.locator('p[role="alert"]')).toHaveCount(0);
    await page.goto('/admin/enquiries');
    await page.getByRole('button', { name: 'Show WhatsApp chat' }).click();
    await expect(page.getByText('WhatsApp automation is off.')).toBeVisible();
  } finally {
    await request.get(`${MOCK}/__whatsapp-disabled?on=0`);
  }
});
