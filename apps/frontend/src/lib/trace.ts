// W3C trace context for same-origin storefront -> API calls made by Next.js route handlers.
// The browser never talks to the API with these headers: handlers continue an incoming
// `traceparent` (new span, same trace) or start a trace, so one storefront action is one trace.
const TRACEPARENT = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/;

const hex = (bytes: number) =>
  Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (b) => b.toString(16).padStart(2, '0')).join('');

export const traceHeaders = (incoming?: string | null): { traceparent: string } => {
  const match = incoming ? TRACEPARENT.exec(incoming) : null;
  const traceId = match && !/^0+$/.test(match[1]) ? match[1] : hex(16);
  return { traceparent: `00-${traceId}-${hex(8)}-01` };
};
