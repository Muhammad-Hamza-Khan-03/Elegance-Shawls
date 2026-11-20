#!/usr/bin/env node
// Dependency-free load smoke against the SLOs in slos.json (no k6 install needed).
// Usage: node deploy/slo/load_smoke.mjs <api-base-url> [requests-per-objective=50] [concurrency=5]
// Only hits the public, read-only endpoints listed in slos.json. Exit 1 when any objective is missed.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const p95 = (values) => {
  if (!values.length) return Infinity;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(0.95 * sorted.length) - 1)];
};

export async function run(base, objectives, total = 50, concurrency = 5) {
  const results = [];
  for (const o of objectives) {
    const times = [];
    let errors = 0;
    let next = 0;
    const worker = async () => {
      while (next++ < total) {
        const started = performance.now();
        try {
          const res = await fetch(base + o.path, {
            method: o.method ?? 'GET',
            headers: o.body ? { 'content-type': 'application/json' } : {},
            body: o.body ? JSON.stringify(o.body) : undefined,
            signal: AbortSignal.timeout(10_000),
          });
          if (!res.ok) errors++;
          await res.arrayBuffer();
        } catch {
          errors++;
        }
        times.push(performance.now() - started);
      }
    };
    await Promise.all(Array.from({ length: concurrency }, worker));
    const errorRate = errors / total;
    const p = p95(times);
    results.push({ name: o.name, p95_ms: Math.round(p), error_rate: errorRate, ok: p <= o.p95_ms && errorRate <= o.max_error_rate });
  }
  return results;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [base, n = '50', c = '5'] = process.argv.slice(2);
  if (!base) { console.error('usage: load_smoke.mjs <api-base-url> [requests] [concurrency]'); process.exit(2); }
  const { objectives } = JSON.parse(readFileSync(new URL('./slos.json', import.meta.url), 'utf8'));
  const results = await run(base.replace(/\/$/, ''), objectives, Number(n), Number(c));
  for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name} p95=${r.p95_ms}ms error_rate=${r.error_rate}`);
  process.exit(results.every((r) => r.ok) ? 0 : 1);
}
