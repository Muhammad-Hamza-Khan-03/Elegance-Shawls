export function assertDisposableDatabase(raw: string | undefined, env?: Record<string, string | undefined>): { host: string | null; name: string };
export function sanitizedEnv(extra?: Record<string, string>, source?: Record<string, string | undefined>): Record<string, string>;
