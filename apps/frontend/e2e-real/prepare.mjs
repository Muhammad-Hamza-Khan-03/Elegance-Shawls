// Prepares a DISPOSABLE PostgreSQL for the real-stack suite: migrations, owner account, synthetic catalogue.
// Needs E2E_DATABASE_URL (postgresql+asyncpg://...), E2E_DISPOSABLE_DATABASE=<its name> and the backend Python environment
// (E2E_PYTHON, default "python"). See isolation.cjs for what is refused.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { assertDisposableDatabase, sanitizedEnv } from './isolation.cjs';

const backend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../backend');
const url = process.env.E2E_DATABASE_URL;
try { assertDisposableDatabase(url); } catch (error) { console.error(error.message); process.exit(2); }
const python = process.env.E2E_PYTHON || 'python';
const env = sanitizedEnv({ DATABASE_URL: url, ENVIRONMENT: 'development', ADMIN_ACCOUNT_PASSWORD: 'e2e-owner-Passw0rd-fixture' });
const run = (args) => { const r = spawnSync(python, args, { cwd: backend, env, stdio: 'inherit' }); if (r.status !== 0) process.exit(r.status ?? 1); };
run(['-m', 'alembic', 'upgrade', 'head']);
run(['scripts/admin_accounts.py', 'bootstrap-owner', '--email', 'owner@e2e.test']);
run(['scripts/seed_e2e.py']);
