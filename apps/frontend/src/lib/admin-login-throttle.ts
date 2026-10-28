// In-process throttle for failed admin sign-ins. It protects a single server
// instance; edge/proxy rate limits should supplement it in production.
export const LOGIN_FAILURE_LIMIT = 5;
export const LOGIN_FAILURE_WINDOW_MS = 15 * 60 * 1000;
const MAX_TRACKED_CLIENTS = 10_000;

const failures = new Map<string, number[]>();

// Use the right-most X-Forwarded-For entry: it is the address seen by the
// nearest trusted proxy, whereas earlier entries can be supplied by the client.
export const getLoginClientKey = (request: Request) => {
  const forwarded = request.headers.get('x-forwarded-for')?.split(',').map((part) => part.trim()).filter(Boolean);
  return forwarded?.at(-1) || request.headers.get('x-real-ip')?.trim() || 'unknown';
};

const recentFailures = (key: string, now: number) => {
  const recent = (failures.get(key) || []).filter((at) => at > now - LOGIN_FAILURE_WINDOW_MS);
  if (recent.length) failures.set(key, recent);
  else failures.delete(key);
  return recent;
};

export const loginRetryAfterSeconds = (key: string, now = Date.now()) => {
  const recent = recentFailures(key, now);
  if (recent.length < LOGIN_FAILURE_LIMIT) return 0;
  return Math.max(1, Math.ceil((recent[0] + LOGIN_FAILURE_WINDOW_MS - now) / 1000));
};

export const recordLoginFailure = (key: string, now = Date.now()) => {
  const recent = recentFailures(key, now);
  failures.delete(key);
  failures.set(key, [...recent, now]);
  // Map preserves insertion order, so the first key is the least recently failed client.
  while (failures.size > MAX_TRACKED_CLIENTS) {
    failures.delete(failures.keys().next().value!);
  }
};

export const clearLoginFailures = (key: string) => {
  failures.delete(key);
};

export const resetLoginThrottle = () => {
  failures.clear();
};
