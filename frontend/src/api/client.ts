/**
 * API client for Comicarr backend.
 */

// Base URL detection
// Don't auto-detect from pathname - always fetch from server config
// This prevents issues when navigating to /comicarr/ when base_url is actually empty
function detectBaseUrlFromPath(): string {
  // Always return empty - let the server config determine the base_url
  // This prevents false detection when user navigates to a path that looks like base_url
  return '';
}

// Initialize with detected base_url (will be updated by config if available)
let BASE_URL = detectBaseUrlFromPath();
let API_BASE = BASE_URL ? `${BASE_URL}/api` : '/api';

// Debug logging
if (typeof window !== 'undefined') {
  console.log('[API Client] Detected base_url:', BASE_URL, 'from pathname:', window.location.pathname);
  console.log('[API Client] API_BASE:', API_BASE);
}
let configInitialized = false;
let configInitPromise: Promise<void> | null = null;

// Fetch config to get base_url (this will override detection if server says different)
export async function initApiConfig(): Promise<void> {
  if (configInitPromise) {
    return configInitPromise;
  }

  configInitPromise = (async () => {
    try {
      // Always try /api/config first (works when base_url is empty)
      // If that fails, try with detected base_url as fallback
      let configUrl = '/api/config';
      console.log('[API Client] Fetching config from:', configUrl);
      let response = await fetch(configUrl, { credentials: 'include' });
      
      // If 404, try with detected base_url (for backwards compatibility)
      if (!response.ok && BASE_URL) {
        configUrl = `${BASE_URL}/api/config`;
        console.log('[API Client] Retrying config from:', configUrl);
        response = await fetch(configUrl, { credentials: 'include' });
      }
      
      if (response.ok) {
        const config = await response.json();
        // Update with server-provided base_url
        BASE_URL = config.base_url || '';
        API_BASE = BASE_URL ? `${BASE_URL}/api` : '/api';
        console.log('[API Client] Config loaded, base_url:', BASE_URL, 'API_BASE:', API_BASE);
      } else {
        console.warn('[API Client] Config fetch failed:', response.status, 'using empty base_url');
        BASE_URL = '';
        API_BASE = '/api';
      }
    } catch (error) {
      // If config fetch fails, use empty base_url
      console.warn('[API Client] Config fetch error:', error, 'using empty base_url');
      BASE_URL = '';
      API_BASE = '/api';
    } finally {
      configInitialized = true;
    }
  })();

  return configInitPromise;
}

// Ensure config is initialized before making API calls
async function ensureConfigInitialized(): Promise<void> {
  // Don't re-detect from pathname - always trust server config
  if (!configInitialized && !configInitPromise) {
    await initApiConfig();
  } else if (configInitPromise) {
    await configInitPromise;
  }
}

export function getApiBase(): string {
  return API_BASE;
}

export function getBaseUrl(): string {
  return BASE_URL;
}

export interface ApiError {
  detail: string | Array<{ msg: string; loc: string[] }>;
}

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public detail: ApiError['detail'],
    message?: string,
  ) {
    super(message || `API error: ${status}`);
    this.name = 'ApiClientError';
  }

  get message(): string {
    // Return a more user-friendly message
    if (typeof this.detail === 'string') {
      return this.detail;
    }
    if (Array.isArray(this.detail)) {
      return this.detail.map((e) => e.msg || String(e)).join(', ');
    }
    return super.message;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: ApiError['detail'] = response.statusText;
    try {
      const errorData = await response.json();
      detail = errorData.detail || detail;
    } catch {
      // Not JSON, use status text
    }
    throw new ApiClientError(response.status, detail);
  }

  // Handle 204 No Content responses (no body)
  if (response.status === 204) {
    return {} as T;
  }

  // Handle empty responses
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }

  // Return text for non-JSON responses
  const text = await response.text();
  return (text ? JSON.parse(text) : {}) as T;
}

export async function apiGet<T>(endpoint: string): Promise<T> {
  await ensureConfigInitialized();
  const response = await fetch(`${getApiBase()}${endpoint}`, {
    credentials: 'include', // Include cookies for session management
  });
  return handleResponse<T>(response);
}

export async function apiPost<T>(
  endpoint: string,
  data?: unknown,
): Promise<T> {
  await ensureConfigInitialized();
  const url = `${getApiBase()}${endpoint}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: data ? JSON.stringify(data) : undefined,
    credentials: 'include', // Include cookies for session management
  });

  // Log for debugging (remove in production)
  if (!response.ok) {
    console.error('API POST failed:', {
      url,
      status: response.status,
      statusText: response.statusText,
    });
  }

  return handleResponse<T>(response);
}

export async function apiPut<T>(
  endpoint: string,
  data?: unknown,
): Promise<T> {
  await ensureConfigInitialized();
  const response = await fetch(`${getApiBase()}${endpoint}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: data ? JSON.stringify(data) : undefined,
    credentials: 'include', // Include cookies for session management
  });
  return handleResponse<T>(response);
}

export async function apiDelete<T>(endpoint: string): Promise<T> {
  await ensureConfigInitialized();
  const response = await fetch(`${getApiBase()}${endpoint}`, {
    method: 'DELETE',
    credentials: 'include', // Include cookies for session management
  });
  return handleResponse<T>(response);
}

// Helper function to build API URLs (for use with fetch directly)
export function buildApiUrl(endpoint: string): string {
  // Remove leading /api if present (we'll add it via getApiBase)
  const cleanEndpoint = endpoint.startsWith('/api') ? endpoint : `/api${endpoint}`;
  // getApiBase already includes /api, so we need to handle this carefully
  if (cleanEndpoint.startsWith('/api')) {
    const path = cleanEndpoint.substring(4); // Remove '/api'
    return `${getApiBase()}${path}`;
  }
  return `${getApiBase()}${cleanEndpoint}`;
}

