import { expect, test } from 'vitest';
import { WISHLIST_MAX, normalizeWishlist, toggleWishlist } from './wishlist';

test('toggle adds first, removes on second call', () => {
  expect(toggleWishlist([], 'a')).toEqual(['a']);
  expect(toggleWishlist(['a', 'b'], 'a')).toEqual(['b']);
});

test('normalize drops junk, duplicates and caps size', () => {
  expect(normalizeWishlist('nope')).toEqual([]);
  expect(normalizeWishlist(['a', 'a', 3, '', null, 'b'])).toEqual(['a', 'b']);
  expect(normalizeWishlist(Array.from({ length: 80 }, (_, i) => `s${i}`))).toHaveLength(WISHLIST_MAX);
});

test('adding past the cap drops the oldest', () => {
  const full = Array.from({ length: WISHLIST_MAX }, (_, i) => `s${i}`);
  const next = toggleWishlist(full, 'new');
  expect(next).toHaveLength(WISHLIST_MAX);
  expect(next[0]).toBe('new');
});
