import { afterEach, expect, test, vi } from 'vitest';
import { reportError, setErrorReporter } from './report-error';

afterEach(() => setErrorReporter(null));

test('is a no-op without a reporter', () => {
  expect(() => reportError(new Error('x'), '/a')).not.toThrow();
});

test('reports name, digest and route only, never the message', () => {
  const seen = vi.fn();
  setErrorReporter(seen);
  const e = Object.assign(new Error('call 0300-1234567'), { digest: 'd1' });
  reportError(e, '/products');
  expect(seen).toHaveBeenCalledWith({ name: 'Error', digest: 'd1', route: '/products' });
  expect(JSON.stringify(seen.mock.calls)).not.toContain('0300');
});

test('a throwing reporter does not propagate', () => {
  setErrorReporter(() => { throw new Error('down'); });
  expect(() => reportError(new Error('x'), '/a')).not.toThrow();
});
