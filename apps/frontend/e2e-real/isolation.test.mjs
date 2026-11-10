import assert from 'node:assert/strict';
import test from 'node:test';
import { assertDisposableDatabase, sanitizedEnv } from './isolation.cjs';

const ok = (url, db = 'elegance_e2e') => assertDisposableDatabase(url, { E2E_DISPOSABLE_DATABASE: db });
const refused = (url, env = { E2E_DISPOSABLE_DATABASE: 'elegance_e2e' }) => assert.throws(() => assertDisposableDatabase(url, env), /Refusing/);

test('accepts a loopback host with a designated, acknowledged database', () => {
  assert.equal(ok('postgresql+asyncpg://e2e:pw@127.0.0.1:5432/elegance_e2e').name, 'elegance_e2e');
  assert.equal(ok('postgresql+asyncpg://e2e:pw@localhost/e2e', 'e2e').name, 'e2e');
  assert.equal(ok('postgresql+asyncpg://postgres@/elegance_e2e?host=/tmp/pg', 'elegance_e2e').host, '/tmp/pg');
});
test('refuses non-loopback hosts, even with a designated name', () => {
  refused('postgresql+asyncpg://u:p@db.example.com:5432/elegance_e2e');
  refused('postgresql+asyncpg://u:p@10.0.0.5/elegance_e2e');
  refused('postgresql+asyncpg://u:p@127.0.0.1.evil.example/elegance_e2e');
  refused('postgresql+asyncpg://u:p@127.0.0.1/elegance_e2e?hostaddr=10.0.0.5');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=relative/dir');
});
test('refuses query parameters that could redirect the connection', () => {
  for (const q of ['host=db.example.com', 'host=/tmp/pg', 'HostAddr=10.0.0.5', 'HOSTADDR=10.0.0.5', 'dbname=postgres', 'Host=/tmp/pg', 'port=6543', 'service=prod', 'options=-c%20x=1', 'sslmode=require']) {
    refused(`postgresql+asyncpg://u:p@127.0.0.1/elegance_e2e?${q}`);
  }
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=/tmp/pg&dbname=postgres');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=/tmp/pg&HOST=/tmp/other');
});
test('refuses repeated or comma-listed hosts and whitespace the URL parser would strip', () => {
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=/tmp/pg&host=evil.com');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=evil.com&host=/tmp/pg');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=/tmp/pg&host=/tmp/pg');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=/tmp/pg,10.0.0.5');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=/tmp/pg/,evil.com');
  refused('postgresql+asyncpg://u:p@/elegance_e2e?host=');
  refused(' postgresql+asyncpg://u:p@127.0.0.1/elegance_e2e');
  refused('postgresql+asyncpg://u:p@127.0.0.1/elegance_e2e\n');
  refused('postgresql+asyncpg://u:p@127.0.0.1/ele\tgance_e2e');
  assert.equal(ok('postgresql+asyncpg://u:p@/elegance_e2e?host=%2Ftmp%2Fpg').host, '/tmp/pg');     // encoded single socket dir stays valid
});
test('refuses databases that are not designated or not acknowledged', () => {
  refused('postgresql+asyncpg://u:p@127.0.0.1/postgres', { E2E_DISPOSABLE_DATABASE: 'postgres' });
  refused('postgresql+asyncpg://u:p@127.0.0.1/elegance_shawls', { E2E_DISPOSABLE_DATABASE: 'elegance_shawls' });
  refused('postgresql+asyncpg://u:p@127.0.0.1/elegance_e2e', {});
  refused('postgresql+asyncpg://u:p@127.0.0.1/elegance_e2e', { E2E_DISPOSABLE_DATABASE: 'other' });
  refused('postgresql+asyncpg://u:p@127.0.0.1/note2e', { E2E_DISPOSABLE_DATABASE: 'note2e' });
  refused(undefined);
  refused('not a url');
  refused('mysql://u:p@127.0.0.1/elegance_e2e');
});
test('child environment is an allowlist: credentials and production settings never pass through', () => {
  const source = { PATH: '/bin', HOME: '/h', GROQ_API_KEY: 'k', OPENAI_API_KEY: 'k', GEMINI_API_KEY: 'k', DATABASE_URL: 'prod', ADMIN_API_KEY: 'a', REDIS_URL: 'r', LLM_CHAIN_DEFAULT: 'x' };
  const env = sanitizedEnv({ DATABASE_URL: 'disposable' }, source);
  assert.deepEqual(Object.keys(env).sort(), ['DATABASE_URL', 'HOME', 'PATH']);
  assert.equal(env.DATABASE_URL, 'disposable');
});
