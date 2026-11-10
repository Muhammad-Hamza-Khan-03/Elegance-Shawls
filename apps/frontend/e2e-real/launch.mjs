// Starts the backend or the frontend dev server with an ALLOWLISTED environment (see isolation.cjs).
// Playwright's webServer would otherwise merge the whole parent environment (provider keys, DATABASE_URL, ...) into the servers.
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertDisposableDatabase, sanitizedEnv } from './isolation.cjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const apiPort = process.env.E2E_REAL_API_PORT || '4300';
const webPort = process.env.E2E_REAL_WEB_PORT || '3300';
const web = `http://127.0.0.1:${webPort}`;
const role = process.argv[2];
const database = process.env.E2E_DATABASE_URL;
assertDisposableDatabase(database);

const backend = {
  cwd: path.resolve(here, '../../backend'),
  command: process.env.E2E_PYTHON || 'python',
  args: ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', apiPort],
  env: {
    DATABASE_URL: database, ENVIRONMENT: 'development', ALLOWED_ORIGINS: web, ASSISTANT_CATALOGUE: 'true', ASSISTANT_LLM: 'false',
    PUBLIC_RATE_LIMIT_PER_MINUTE: '100000', ADMIN_RATE_LIMIT_PER_MINUTE: '100000', ADMIN_API_KEY: '', ADMIN_LEGACY_KEY_EXPIRES_AT: '',
    EMBEDDING_ENABLED: 'false', LOCAL_SEMANTIC_SEARCH_ENABLED: 'false', REDIS_URL: '',
  },
};
const frontend = {
  cwd: path.resolve(here, '..'),
  command: 'npm',
  args: ['run', 'dev', '--', '--hostname', '127.0.0.1', '--port', webPort],
  env: {
    NEXT_PUBLIC_API_URL: `http://127.0.0.1:${apiPort}`, NEXT_PUBLIC_SITE_URL: web, NEXT_PUBLIC_WHATSAPP_NUMBER: '923001234567',
    NEXT_PUBLIC_ASSISTANT_ENABLED: '1', ADMIN_API_KEY: '',
  },
};
const target = { backend, frontend }[role];
if (!target) { console.error('usage: launch.mjs backend|frontend'); process.exit(2); }

const child = spawn(target.command, target.args, { cwd: target.cwd, env: sanitizedEnv(target.env), stdio: 'inherit' });
for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(signal, () => child.kill(signal));
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
