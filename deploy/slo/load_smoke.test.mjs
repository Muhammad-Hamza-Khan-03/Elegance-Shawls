// Run with: node --test deploy/slo/load_smoke.test.mjs
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { p95, run } from './load_smoke.mjs';

const slos = JSON.parse(readFileSync(new URL('./slos.json', import.meta.url), 'utf8'));

test('slos.json is well formed', () => {
  assert.equal(slos.version, 1);
  for (const o of slos.objectives) {
    assert.match(o.path, /^\//);
    assert.ok(o.p95_ms > 0 && o.max_error_rate >= 0 && o.max_error_rate < 1, o.name);
  }
});

test('p95 picks the 95th percentile and an empty sample fails', () => {
  assert.equal(p95(Array.from({ length: 100 }, (_, i) => i + 1)), 95);
  assert.equal(p95([]), Infinity);
});

test('passes against a healthy stub and fails against a failing one', async () => {
  const serve = (status) => new Promise((resolve) => { const s = createServer((_, res) => { res.statusCode = status; res.end('{}'); }).listen(0, () => resolve(s)); });
  for (const [status, expected] of [[200, true], [500, false]]) {
    const server = await serve(status);
    try {
      const results = await run(`http://127.0.0.1:${server.address().port}`, slos.objectives, 10, 2);
      assert.equal(results.every((r) => r.ok), expected);
    } finally { server.close(); }
  }
});
