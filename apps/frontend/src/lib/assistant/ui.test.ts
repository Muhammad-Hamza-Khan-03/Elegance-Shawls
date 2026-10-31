import { describe, expect, it } from 'vitest';
import { isAssistantEnabled, isAssistantRoute, SUGGESTED_PROMPTS } from './ui';

describe('assistant UI gating', () => {
  it('is off unless the flag is "1" or "true"', () => {
    for (const off of [undefined, '', '0', 'false', 'yes']) expect(isAssistantEnabled(off)).toBe(false);
    for (const on of ['1', 'true']) expect(isAssistantEnabled(on)).toBe(true);
  });
  it('excludes admin and cart routes only', () => {
    for (const p of ['/', '/products', '/product/x', '/cartography', '/memory', '/account']) expect(isAssistantRoute(p)).toBe(true);
    for (const p of ['/admin', '/admin/login', '/cart', '/cart/']) expect(isAssistantRoute(p)).toBe(false);
    expect(isAssistantRoute(null)).toBe(false);
  });
  it('offers a few short prompts', () => {
    expect(SUGGESTED_PROMPTS.length).toBeGreaterThanOrEqual(3);
    for (const p of SUGGESTED_PROMPTS) expect(p.length).toBeLessThanOrEqual(40);
  });
});
