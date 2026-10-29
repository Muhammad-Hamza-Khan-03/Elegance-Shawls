import { describe, expect, it } from 'vitest';
import { traceHeaders } from './trace';

const PARENT = '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01';

describe('traceHeaders', () => {
  it('keeps the trace ID and creates a new span ID', () => {
    const [, trace, span] = traceHeaders(PARENT).traceparent.split('-');
    expect(trace).toBe('4bf92f3577b34da6a3ce929d0e0e4736');
    expect(span).not.toBe('00f067aa0ba902b7');
  });

  it.each([[null], [undefined], [''], ['garbage'], ['00-00000000000000000000000000000000-00f067aa0ba902b7-01']])(
    'starts a new valid trace for %s',
    (incoming) => {
      const value = traceHeaders(incoming).traceparent;
      expect(value).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
      expect(value).not.toContain('00000000000000000000000000000000');
    },
  );

  it('produces a different trace each time', () => {
    expect(traceHeaders().traceparent).not.toBe(traceHeaders().traceparent);
  });
});
