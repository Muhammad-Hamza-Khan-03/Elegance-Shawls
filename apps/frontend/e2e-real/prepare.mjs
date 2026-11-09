// Prepares a DISPOSABLE PostgreSQL for the real-stack suite: migrations, owner account, synthetic catalogue.
// Needs E2E_DATABASE_URL (postgresql+asyncpg://...) and the backend Python environment (E2E_PYTHON, default "python").
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const backend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../backend');
const url = process.env.E2E_DATABASE_URL;
if (!url) { console.error('E2E_DATABASE_URL is required (a disposable database).'); process.exit(2); }
if (/amazonaws|neon\.tech|supabase|render\.com|prod/i.test(url)) { console.error('Refusing a database URL that looks hosted.'); process.exit(2); }
const python = process.env.E2E_PYTHON || 'python';
const env = { ...process.env, DATABASE_URL: url, ENVIRONMENT: 'development', ADMIN_ACCOUNT_PASSWORD: 'e2e-owner-Passw0rd-fixture' };
const run = (args) => { const r = spawnSync(python, args, { cwd: backend, env, stdio: 'inherit' }); if (r.status !== 0) process.exit(r.status ?? 1); };
run(['-m', 'alembic', 'upgrade', 'head']);
run(['scripts/admin_accounts.py', 'bootstrap-owner', '--email', 'owner@e2e.test']);
run(['scripts/seed_e2e.py']);
