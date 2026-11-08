import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'lcov', 'json-summary'],
      include: ['src/lib/cart.ts', 'src/lib/whatsapp.ts', 'src/lib/api.ts', 'src/lib/admin-session.ts', 'src/lib/admin-backend.ts'],
      thresholds: { lines: 75, functions: 70, branches: 60, statements: 75 },
    },
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
});
