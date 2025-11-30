import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  apiGet,
  apiPost,
  apiPut,
  apiDelete,
  ApiClientError,
} from './client';

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('apiGet', () => {
    it('makes GET request and returns JSON data', async () => {
      const mockData = { message: 'success', data: [1, 2, 3] };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockData,
      });

      const result = await apiGet('/test');

      expect(global.fetch).toHaveBeenCalledWith('/api/test', {
        credentials: 'include',
      });
      expect(result).toEqual(mockData);
    });

    it('handles empty JSON response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({}),
      });

      const result = await apiGet('/test');

      expect(result).toEqual({});
    });

    it('throws ApiClientError on HTTP error status', async () => {
      const errorResponse = { detail: 'Not found' };
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => errorResponse,
      });

      await expect(apiGet('/test')).rejects.toThrow(ApiClientError);
      await expect(apiGet('/test')).rejects.toMatchObject({
        status: 404,
        detail: errorResponse.detail,
      });
    });

    it('handles non-JSON error response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'text/plain' }),
        json: async () => {
          throw new Error('Not JSON');
        },
      });

      await expect(apiGet('/test')).rejects.toThrow(ApiClientError);
      await expect(apiGet('/test')).rejects.toMatchObject({
        status: 500,
        detail: 'Internal Server Error',
      });
    });
  });

  describe('apiPost', () => {
    it('makes POST request with JSON body', async () => {
      const requestData = { name: 'test', value: 123 };
      const responseData = { id: 1, ...requestData };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => responseData,
      });

      const result = await apiPost('/test', requestData);

      expect(global.fetch).toHaveBeenCalledWith('/api/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
        credentials: 'include',
      });
      expect(result).toEqual(responseData);
    });

    it('handles POST without body', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({}),
      });

      await apiPost('/test');

      expect(global.fetch).toHaveBeenCalledWith('/api/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: undefined,
        credentials: 'include',
      });
    });
  });

  describe('apiPut', () => {
    it('makes PUT request with JSON body', async () => {
      const requestData = { name: 'updated', value: 456 };
      const responseData = { id: 1, ...requestData };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => responseData,
      });

      const result = await apiPut('/test/1', requestData);

      expect(global.fetch).toHaveBeenCalledWith('/api/test/1', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
        credentials: 'include',
      });
      expect(result).toEqual(responseData);
    });
  });

  describe('apiDelete', () => {
    it('makes DELETE request', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({}),
      });

      await apiDelete('/test/1');

      expect(global.fetch).toHaveBeenCalledWith('/api/test/1', {
        method: 'DELETE',
        credentials: 'include',
      });
    });
  });

  describe('ApiClientError', () => {
    it('creates error with status and detail', () => {
      const error = new ApiClientError(404, 'Not found', 'Custom message');
      expect(error.status).toBe(404);
      expect(error.detail).toBe('Not found');
      expect(error.message).toBe('Custom message');
      expect(error.name).toBe('ApiClientError');
    });

    it('uses default message when not provided', () => {
      const error = new ApiClientError(500, 'Server error');
      expect(error.message).toBe('API error: 500');
    });
  });
});

