import { describe, it, expect } from 'vitest';

describe('Hello World', () => {
  it('should pass a simple test', () => {
    expect(true).toBe(true);
    expect('hello').toBe('hello');
    expect(1 + 1).toBe(2);
  });
});

