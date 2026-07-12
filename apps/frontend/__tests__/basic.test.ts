import { describe, it, expect } from 'vitest';

describe('Frontend Basic Tests', () => {
  it('should pass basic tests', () => {
    expect(true).toBe(true);
  });

  it('should have environment variables', () => {
    expect(process.env.NODE_ENV).toBeDefined();
  });
});