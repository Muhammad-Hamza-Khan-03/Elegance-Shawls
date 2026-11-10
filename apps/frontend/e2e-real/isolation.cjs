// Test-database isolation and subprocess environment hygiene for the real-stack suite.
// CommonJS so the Playwright config (loaded as CJS) and the ESM scripts (prepare.mjs, launch.mjs) share one implementation.
// eslint-disable-next-line @typescript-eslint/no-require-imports -- CommonJS on purpose (see header)
const path = require('node:path');

const LOOPBACK = new Set(['127.0.0.1', 'localhost', '::1']);
// A disposable database is DESIGNATED by name (an `e2e` token) AND acknowledged by naming it in E2E_DISPOSABLE_DATABASE.
const DESIGNATED = /^(?:[a-z0-9]+_)*e2e(?:_[a-z0-9]+)*$/;
// Child processes get only these inherited variables. Provider keys, DATABASE_URL, ADMIN_API_KEY etc. are never forwarded.
const INHERITED = ['PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'TMPDIR', 'TERM', 'TZ', 'CI'];

function assertDisposableDatabase(raw, env = process.env) {
  const fail = (why) => { throw new Error(`Refusing to run the real-stack suite: ${why}`); };
  if (!raw) fail('E2E_DATABASE_URL is not set.');
  // postgresql://user@/db?host=/dir (empty host = unix socket) is not parseable by URL: give it a placeholder host first.
  const emptyHost = /^[^:]+:\/\/(?:[^@/]*@)?\//.test(raw);
  let url;
  try { url = new URL(emptyHost ? raw.replace(/^([^:]+:\/\/(?:[^@/]*@)?)\//, '$1socket.invalid/') : raw); } catch { fail('E2E_DATABASE_URL is not a valid URL.'); }
  if (!url.protocol.startsWith('postgres')) fail('E2E_DATABASE_URL must be a PostgreSQL URL.');
  if (url.searchParams.has('hostaddr')) fail('hostaddr is not allowed.');
  const host = emptyHost ? '' : url.hostname.replace(/^\[|\]$/g, '').toLowerCase();
  const socketDir = url.searchParams.get('host');
  // A unix-socket directory (host=/abs/path with no hostname) is local by construction; any network host must be loopback.
  const loopback = host ? LOOPBACK.has(host) : Boolean(socketDir && path.isAbsolute(socketDir));
  if (!loopback) fail(`database host "${host || socketDir || ''}" is not loopback.`);
  const name = decodeURIComponent(url.pathname.replace(/^\//, ''));
  if (!DESIGNATED.test(name)) fail(`database "${name}" is not designated as a test database (its name needs an "e2e" token, e.g. elegance_e2e).`);
  if (env.E2E_DISPOSABLE_DATABASE !== name) fail(`set E2E_DISPOSABLE_DATABASE=${name} to confirm this database may be reset.`);
  return { host: host || socketDir, name };
}

/** Allowlisted environment for a child process: a few inherited basics plus the explicit values given. */
function sanitizedEnv(extra = {}, source = process.env) {
  const env = {};
  for (const key of INHERITED) if (source[key] !== undefined) env[key] = source[key];
  return { ...env, ...extra };
}

module.exports = { assertDisposableDatabase, sanitizedEnv };
