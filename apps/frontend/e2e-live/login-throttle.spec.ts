import { expect, test } from '@playwright/test';
import { live } from './live';

// #67: run last, in its own invocation: it deliberately locks this client out of
// admin sign-in for 15 minutes.
test('repeated failed sign-ins are throttled, even for the correct key', async ({ request }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Runs once.');
  const signIn = (key: string, headers: Record<string, string> = {}) =>
    request.post('/api/admin/session', { data: { key }, headers: { Origin: live.site, ...headers } });

  for (let attempt = 1; attempt <= 5; attempt += 1) expect((await signIn(`wrong-${attempt}`)).status()).toBe(401);
  const throttled = await signIn(live.adminKey);
  expect(throttled.status()).toBe(429);
  expect(Number(throttled.headers()['retry-after'])).toBeGreaterThan(0);
  expect(throttled.headers()['set-cookie']).toBeUndefined();

  // A forged X-Forwarded-For is overwritten by the proxy, so it cannot reset the throttle.
  expect((await signIn(live.adminKey, { 'X-Forwarded-For': '198.51.100.23' })).status()).toBe(429);
  expect(JSON.stringify(await throttled.json())).not.toContain(live.adminKey);
});
