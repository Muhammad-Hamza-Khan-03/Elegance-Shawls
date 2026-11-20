import { expect, test } from 'vitest';
import { imgSrc, parseImageHosts, remoteImagePatterns } from './image-hosts';

test('unset keeps the open default', () => {
  expect(remoteImagePatterns(parseImageHosts(undefined))).toEqual([{ protocol: 'https', hostname: '**' }]);
  expect(imgSrc([])).toContain('https:');
});

test('a list restricts both Next image optimisation and CSP', () => {
  const hosts = parseImageHosts('cdn.example.com, *.shopify.com');
  expect(remoteImagePatterns(hosts)).toEqual([{ protocol: 'https', hostname: 'cdn.example.com' }, { protocol: 'https', hostname: '*.shopify.com' }]);
  expect(imgSrc(hosts)).toBe("img-src 'self' data: blob: https://cdn.example.com https://*.shopify.com");
});

test('junk, schemes, paths and bare wildcards are dropped', () => {
  expect(parseImageHosts('**, https://evil.com, a.com/x, localhost, ;drop, good.example.com')).toEqual(['good.example.com']);
});
