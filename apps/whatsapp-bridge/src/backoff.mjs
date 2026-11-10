// Exponential reconnect delay in ms, capped at 5 minutes.
export const backoffMs = (attempt) => Math.min(1000 * 2 ** Math.max(0, attempt), 5 * 60 * 1000);
