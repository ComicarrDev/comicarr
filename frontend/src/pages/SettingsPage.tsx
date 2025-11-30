import { useEffect, useState, useRef } from 'react';
import { toast } from 'sonner';
import { Check, X, RefreshCw } from 'lucide-react';
import { apiGet, apiPut, apiPost, ApiClientError } from '../api/client';
import Toggle from '../components/Toggle';
import './SettingsPage.css';

interface HostSettings {
  bind_address: string;
  port: number;
  base_url: string;
}

interface SecuritySettings {
  auth_method: 'none' | 'forms';
  username: string | null;
  has_password: boolean;
  api_key: string | null;
  has_api_key: boolean;
}

interface ComicvineSettings {
  api_key: string | null;
  base_url: string;
  enabled: boolean;
  rate_limit?: number;
  rate_limit_period?: number;
  max_retries?: number;
  cache_enabled?: boolean;
  burst_prevention_enabled?: boolean;
  min_gap_seconds?: number | null;
}

interface ExternalApisResponse {
  comicvine: ComicvineSettings;
}

interface WeeklyReleasesSettings {
  auto_fetch_enabled: boolean;
  auto_fetch_interval_hours: number;
  sources: {
    previewsworld: { enabled: boolean };
    comicgeeks: { enabled: boolean };
    readcomicsonline: { enabled: boolean };
  };
}

export default function SettingsPage() {
  // Host settings
  const [hostLoading, setHostLoading] = useState(true);
  const [hostSaving, setHostSaving] = useState(false);
  const [bindAddress, setBindAddress] = useState('');
  const [port, setPort] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  // Initialize ref with default values - will be updated when data loads
  const hostInitialRef = useRef<{ bind_address: string; port: number; base_url: string } | null>(null);

  // Security settings
  const [securitySettings, setSecuritySettings] = useState<SecuritySettings | null>(null);
  const [securityLoading, setSecurityLoading] = useState(true);
  const [securitySaving, setSecuritySaving] = useState(false);
  const [authMethod, setAuthMethod] = useState<'none' | 'forms'>('none');
  const [securityUsername, setSecurityUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [apiKey, setApiKey] = useState('');
  // Initialize ref - will be updated when data loads
  const securityInitialRef = useRef<{ auth_method: string; username: string | null; api_key: string | null } | null>(null);

  // External APIs (Comicvine)
  const [externalApisLoading, setExternalApisLoading] = useState(true);
  const [externalApisSaving, setExternalApisSaving] = useState(false);
  const [externalApisTesting, setExternalApisTesting] = useState(false);
  const [comicvineTestResult, setComicvineTestResult] = useState<'success' | 'error' | null>(null);
  const [comicvineEnabled, setComicvineEnabled] = useState(false);
  const [comicvineApiKey, setComicvineApiKey] = useState('');
  const [comicvineBaseUrl, setComicvineBaseUrl] = useState('https://comicvine.gamespot.com/api');
  const [comicvineRateLimit, setComicvineRateLimit] = useState(40);
  const [comicvineRateLimitPeriod, setComicvineRateLimitPeriod] = useState(60);
  const [comicvineMaxRetries, setComicvineMaxRetries] = useState(3);
  const [comicvineCacheEnabled, setComicvineCacheEnabled] = useState(true);
  const [comicvineBurstPreventionEnabled, setComicvineBurstPreventionEnabled] = useState(true);
  const [comicvineMinGapSeconds, setComicvineMinGapSeconds] = useState<number | null>(null);
  // Initialize ref - will be updated when data loads
  const externalApisInitialRef = useRef<{ enabled: boolean; api_key: string | null; base_url: string; rate_limit?: number; rate_limit_period?: number; max_retries?: number; cache_enabled?: boolean; burst_prevention_enabled?: boolean; min_gap_seconds?: number | null } | null>(null);

  // Weekly Releases settings
  const [weeklyReleasesLoading, setWeeklyReleasesLoading] = useState(true);
  const [weeklyReleasesSaving, setWeeklyReleasesSaving] = useState(false);
  const [weeklyReleasesSettings, setWeeklyReleasesSettings] = useState<WeeklyReleasesSettings | null>(null);

  useEffect(() => {
    loadHostSettings();
    loadSecuritySettings();
    loadExternalApis();
    loadWeeklyReleasesSettings();
  }, []);

  // Helper to check if host settings have changed
  const hostHasChanges = hostInitialRef.current ? (
    bindAddress.trim() !== (hostInitialRef.current.bind_address || '').trim() ||
    (port.trim() !== '' && Number(port) !== hostInitialRef.current.port) ||
    baseUrl.trim() !== (hostInitialRef.current.base_url || '').trim()
  ) : false;

  // Helper to check if security settings have changed
  const securityHasChanges = securityInitialRef.current ? (
    authMethod !== securityInitialRef.current.auth_method ||
    securityUsername.trim() !== (securityInitialRef.current.username || 'admin').trim() ||
    password.length > 0 ||
    (apiKey || '').trim() !== (securityInitialRef.current.api_key || '').trim()
  ) : false;

  // Helper to check if external APIs have changed
  const externalApisHasChanges = externalApisInitialRef.current ? (
    comicvineEnabled !== externalApisInitialRef.current.enabled ||
    (comicvineApiKey || '').trim() !== (externalApisInitialRef.current.api_key || '').trim() ||
    (comicvineBaseUrl || '').trim() !== (externalApisInitialRef.current.base_url || '').trim() ||
    comicvineRateLimit !== (externalApisInitialRef.current.rate_limit ?? 40) ||
    comicvineRateLimitPeriod !== (externalApisInitialRef.current.rate_limit_period ?? 60) ||
    comicvineMaxRetries !== (externalApisInitialRef.current.max_retries ?? 3) ||
    comicvineCacheEnabled !== (externalApisInitialRef.current.cache_enabled ?? true) ||
    comicvineBurstPreventionEnabled !== (externalApisInitialRef.current.burst_prevention_enabled ?? true) ||
    comicvineMinGapSeconds !== (externalApisInitialRef.current.min_gap_seconds ?? null)
  ) : false;

  async function loadHostSettings() {
    try {
      setHostLoading(true);
      const data = await apiGet<HostSettings>('/settings/host');
      setBindAddress(data.bind_address);
      setPort(String(data.port));
      setBaseUrl(data.base_url);
      hostInitialRef.current = { ...data };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load host settings';
      toast.error(message);
      // Set initial ref to current state values (exactly as they are, even if empty)
      // This gives us a baseline to detect changes from
      // For port, if empty we'll use 8000 as the baseline since that's the default
      const currentPort = port.trim() !== '' ? Number(port) : 8000;
      hostInitialRef.current = {
        bind_address: bindAddress,
        port: currentPort,
        base_url: baseUrl,
      };
      // Also update state to match the baseline for port if it was empty
      if (port.trim() === '') {
        setPort('8000');
      }
    } finally {
      setHostLoading(false);
    }
  }

  async function loadSecuritySettings() {
    try {
      setSecurityLoading(true);
      const data = await apiGet<SecuritySettings>('/settings/security');
      setSecuritySettings(data);
      setAuthMethod(data.auth_method);
      setSecurityUsername(data.username || 'admin');
      setApiKey(data.api_key || '');
      securityInitialRef.current = {
        auth_method: data.auth_method,
        username: data.username,
        api_key: data.api_key,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load security settings';
      toast.error(message);
      // Don't set ref on error - we can't know the actual backend state
      // This ensures buttons stay disabled until we successfully load data
    } finally {
      setSecurityLoading(false);
    }
  }

  async function loadExternalApis() {
    try {
      setExternalApisLoading(true);
      const response = await apiGet<ExternalApisResponse>('/settings/external-apis');
      const comicvine = response.comicvine;
      setComicvineEnabled(comicvine.enabled);
      setComicvineApiKey(comicvine.api_key ?? '');
      setComicvineBaseUrl(comicvine.base_url);
      setComicvineRateLimit(comicvine.rate_limit ?? 40);
      setComicvineRateLimitPeriod(comicvine.rate_limit_period ?? 60);
      setComicvineMaxRetries(comicvine.max_retries ?? 3);
      setComicvineCacheEnabled(comicvine.cache_enabled ?? true);
      setComicvineBurstPreventionEnabled(comicvine.burst_prevention_enabled ?? true);
      setComicvineMinGapSeconds(comicvine.min_gap_seconds ?? null);
      externalApisInitialRef.current = { ...comicvine };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load external API settings';
      toast.error(message);
      // Don't set ref on error - we can't know the actual backend state
      // This ensures buttons stay disabled until we successfully load data
    } finally {
      setExternalApisLoading(false);
    }
  }

  async function loadWeeklyReleasesSettings() {
    try {
      setWeeklyReleasesLoading(true);
      const response = await apiGet<WeeklyReleasesSettings>('/settings/weekly-releases');
      setWeeklyReleasesSettings(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load weekly releases settings';
      toast.error(message);
    } finally {
      setWeeklyReleasesLoading(false);
    }
  }

  async function saveWeeklyReleasesSettings() {
    if (!weeklyReleasesSettings) return;
    
    setWeeklyReleasesSaving(true);
    try {
      await apiPut('/settings/weekly-releases', weeklyReleasesSettings);
      toast.success('Weekly releases settings saved. Scheduler will be updated on next restart.');
    } catch (err) {
      let errorMessage = 'Failed to save weekly releases settings';
      if (err instanceof ApiClientError) {
        if (typeof err.detail === 'string') {
          errorMessage = err.detail;
        } else if (Array.isArray(err.detail)) {
          errorMessage = err.detail.map((e) => e.msg || String(e)).join(', ');
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      toast.error(errorMessage);
    } finally {
      setWeeklyReleasesSaving(false);
    }
  }

  async function handleHostSubmit() {
    setHostSaving(true);

    try {
      const payload = {
        bind_address: bindAddress.trim() || '127.0.0.1',
        port: Number(port),
        base_url: baseUrl.trim(),
      };

      const updated = await apiPut<HostSettings & { restart_required?: boolean; message?: string }>('/settings/host', payload);
      setBindAddress(updated.bind_address);
      setPort(String(updated.port));
      setBaseUrl(updated.base_url);
      hostInitialRef.current = { ...updated };

      if (updated.restart_required) {
        toast.success(updated.message || 'Settings saved. Please restart the server.', {
          duration: 5000,
        });
      } else {
        toast.success('Host settings saved.');
      }
    } catch (err) {
      let errorMessage = 'Failed to save host settings';
      if (err instanceof ApiClientError) {
        if (typeof err.detail === 'string') {
          errorMessage = err.detail;
        } else if (Array.isArray(err.detail)) {
          errorMessage = err.detail.map((e) => e.msg || String(e)).join(', ');
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      toast.error(errorMessage);
    } finally {
      setHostSaving(false);
    }
  }

  async function handleSecuritySubmit() {
    setSecuritySaving(true);

    try {
      if (authMethod === 'forms') {
        if (!securitySettings?.has_password && password.trim().length === 0) {
          throw new Error('Set a password before enabling Forms authentication.');
        }

        if (password && password !== confirmPassword) {
          throw new Error('Passwords do not match.');
        }
      }

      const payload: any = {
        auth_method: authMethod,
        username: securityUsername.trim() || 'admin',
      };

      if (password) {
        payload.password = password;
      }

      // Include API key (empty string to clear, or the value)
      payload.api_key = apiKey.trim() || null;

      await apiPut('/settings/security', payload);

      // Determine what changed to show appropriate messages
      const authMethodChanged = securityInitialRef.current &&
        authMethod !== securityInitialRef.current.auth_method;
      const apiKeyChanged = securityInitialRef.current &&
        (apiKey || '').trim() !== (securityInitialRef.current.api_key || '').trim();
      const usernameChanged = securityInitialRef.current &&
        securityUsername.trim() !== (securityInitialRef.current.username || 'admin').trim();
      const passwordChanged = password.length > 0;

      // Show multiple toasts if multiple things changed
      if (authMethodChanged) {
        toast.success(
          authMethod === 'forms'
            ? 'Forms authentication enabled. Changes take effect immediately.'
            : 'Authentication disabled.'
        );
      }

      if (apiKeyChanged) {
        toast.success('API key updated.');
      }

      if (usernameChanged && !authMethodChanged) {
        toast.success('Username updated.');
      }

      if (passwordChanged && !authMethodChanged) {
        toast.success('Password updated.');
      }

      // If nothing specific changed but we saved, show generic message
      if (!authMethodChanged && !apiKeyChanged && !usernameChanged && !passwordChanged) {
        toast.success('Security settings saved.');
      }

      // Reload security settings
      await loadSecuritySettings();
      setPassword('');
      setConfirmPassword('');
      // API key is loaded from server, so no need to clear it
    } catch (err) {
      let errorMessage = 'Failed to save security settings';
      if (err instanceof ApiClientError) {
        if (typeof err.detail === 'string') {
          errorMessage = err.detail;
        } else if (Array.isArray(err.detail)) {
          errorMessage = err.detail.map((e) => e.msg || String(e)).join(', ');
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      toast.error(errorMessage);
    } finally {
      setSecuritySaving(false);
    }
  }

  async function handleExternalApisSubmit() {
    setExternalApisSaving(true);

    try {
      const response = await apiPut<ExternalApisResponse>('/settings/external-apis', {
        comicvine: {
          enabled: comicvineEnabled,
          api_key: comicvineApiKey.trim() ? comicvineApiKey.trim() : null,
          base_url: comicvineBaseUrl.trim(),
          rate_limit: comicvineRateLimit,
          rate_limit_period: comicvineRateLimitPeriod,
          max_retries: comicvineMaxRetries,
          cache_enabled: comicvineCacheEnabled,
          burst_prevention_enabled: comicvineBurstPreventionEnabled,
          min_gap_seconds: comicvineMinGapSeconds,
        },
      });

      const comicvine = response.comicvine;
      setComicvineEnabled(comicvine.enabled);
      setComicvineApiKey(comicvine.api_key ?? '');
      setComicvineBaseUrl(comicvine.base_url);
      setComicvineRateLimit(comicvine.rate_limit ?? 40);
      setComicvineRateLimitPeriod(comicvine.rate_limit_period ?? 60);
      setComicvineMaxRetries(comicvine.max_retries ?? 3);
      setComicvineCacheEnabled(comicvine.cache_enabled ?? true);
      setComicvineBurstPreventionEnabled(comicvine.burst_prevention_enabled ?? true);
      setComicvineMinGapSeconds(comicvine.min_gap_seconds ?? null);
      externalApisInitialRef.current = { ...comicvine };
      toast.success('Comicvine settings saved.');
    } catch (err) {
      let errorMessage = 'Failed to save external API settings';
      if (err instanceof ApiClientError) {
        if (typeof err.detail === 'string') {
          errorMessage = err.detail;
        } else if (Array.isArray(err.detail)) {
          errorMessage = err.detail.map((e) => e.msg || String(e)).join(', ');
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      toast.error(errorMessage);
    } finally {
      setExternalApisSaving(false);
    }
  }

  async function handleTestComicvine() {
    setExternalApisTesting(true);
    setComicvineTestResult(null);

    try {
      const response = await apiPost<{ comicvine: { status: string; ok: boolean } }>(
        '/settings/external-apis/test',
        {
          comicvine: {
            enabled: comicvineEnabled,
            // Always send form values - backend will use these if non-empty, otherwise fall back to saved
            api_key: comicvineApiKey.trim() || null,
            base_url: comicvineBaseUrl.trim() || null,
          },
        }
      );

      if (response.comicvine.ok) {
        toast.success(response.comicvine.status);
        setComicvineTestResult('success');
      } else {
        toast.error(response.comicvine.status);
        setComicvineTestResult('error');
      }
    } catch (err) {
      let errorMessage = 'Failed to test Comicvine connection';
      if (err instanceof ApiClientError) {
        if (typeof err.detail === 'string') {
          errorMessage = err.detail;
        } else if (Array.isArray(err.detail)) {
          errorMessage = err.detail.map((e) => e.msg || String(e)).join(', ');
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      toast.error(errorMessage);
      setComicvineTestResult('error');
    } finally {
      setExternalApisTesting(false);
    }
  }

  if (hostLoading || securityLoading || externalApisLoading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <p>Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <p>
          Configure host settings, authentication, and external API integrations for Comicarr.
        </p>
      </div>
      <div className="settings-content">
        {/* Host Settings */}
        <div className="settings-section">
          <h2>Host</h2>
          <p className="settings-section-description">
            Configure how Comicarr binds to the network interface. Changes take effect the next time the backend starts.
          </p>
          <div className="settings-form">
            <div className="settings-field">
              <label htmlFor="bind-address">Bind address</label>
              <input
                id="bind-address"
                type="text"
                value={bindAddress}
                onChange={(e) => setBindAddress(e.target.value)}
                disabled={hostSaving || hostLoading}
                placeholder="127.0.0.1"
              />
              <p className="settings-field-help">
                Use 0.0.0.0 to listen on all interfaces.
              </p>
            </div>

            <div className="settings-field">
              <label htmlFor="port">Port</label>
              <input
                id="port"
                type="number"
                min="1"
                max="65535"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                disabled={hostSaving || hostLoading}
                placeholder="8000"
              />
            </div>

            <div className="settings-field">
              <label htmlFor="base-url">Base URL</label>
              <input
                id="base-url"
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                disabled={hostSaving || hostLoading}
                placeholder="/comicarr"
              />
              <p className="settings-field-help">
                Leave blank unless running behind a reverse proxy.
              </p>
            </div>
          </div>

          <div className="settings-actions">
            <button
              type="button"
              className="settings-save-button"
              onClick={handleHostSubmit}
              disabled={hostSaving || hostLoading || !hostHasChanges}
            >
              {hostSaving ? 'Saving...' : 'Save changes'}
            </button>
          </div>
        </div>

        {/* Security Settings */}
        <div className="settings-section">
          <h2>Security</h2>
          <p className="settings-section-description">
            Control how Comicarr authenticates access to the web interface.
          </p>

          <div className="settings-form">
            <div className="settings-field">
              <Toggle
                id="auth-method-toggle"
                checked={authMethod === 'forms'}
                onChange={(checked) => setAuthMethod(checked ? 'forms' : 'none')}
                disabled={securitySaving || securityLoading}
                label={authMethod === 'forms' ? 'Forms authentication enabled' : 'Authentication disabled'}
              />
            </div>
            {authMethod === 'forms' && (
              <div className="settings-field">
                <p className="settings-field-help">
                  Users sign in with a username and password managed by Comicarr.
                </p>
              </div>
            )}

            {authMethod === 'forms' && (
              <>
                <div className="settings-field">
                  <label htmlFor="security-username">Username</label>
                  <input
                    id="security-username"
                    type="text"
                    value={securityUsername}
                    onChange={(e) => setSecurityUsername(e.target.value)}
                    disabled={securitySaving || securityLoading}
                    placeholder="admin"
                  />
                </div>

                <div className="settings-field">
                  <label htmlFor="security-password">Password</label>
                  <input
                    id="security-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    disabled={securitySaving || securityLoading}
                    placeholder={securitySettings?.has_password ? 'Leave blank to keep current password' : 'Enter a password'}
                  />
                </div>

                <div className="settings-field">
                  <label htmlFor="security-confirm-password">Confirm password</label>
                  <input
                    id="security-confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    disabled={securitySaving || securityLoading}
                  />
                </div>
              </>
            )}

            <div className="settings-field">
              <label htmlFor="api-key">API Key</label>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  id="api-key"
                  type="text"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={securitySaving || securityLoading}
                  placeholder="Enter API key for external applications"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  onClick={() => {
                    // Generate a random 40-character API key
                    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
                    const array = new Uint8Array(40);
                    crypto.getRandomValues(array);
                    const randomKey = Array.from(array, (byte) => chars[byte % chars.length]).join('');
                    setApiKey(randomKey);
                  }}
                  disabled={securitySaving || securityLoading}
                  title="Regenerate API key"
                  aria-label="Regenerate API key"
                  style={{
                    padding: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <RefreshCw size={18} />
                </button>
              </div>
              <p className="settings-field-help">
                API key for external applications to authenticate with Comicarr's API. Leave blank to clear.
              </p>
            </div>
          </div>

          <div className="settings-actions">
            <button
              type="button"
              className="settings-save-button"
              onClick={handleSecuritySubmit}
              disabled={securitySaving || securityLoading || !securityHasChanges}
            >
              {securitySaving ? 'Saving...' : 'Save security settings'}
            </button>
          </div>
          <p className="settings-section-help">
            {authMethod === 'forms'
              ? 'Credentials take effect immediately. Existing sessions are preserved.'
              : 'Authentication is disabled; the UI is accessible without login.'}
          </p>
        </div>

        {/* External APIs */}
        <div className="settings-section">
          <h2>External APIs</h2>
          <p className="settings-section-description">
            Configure third-party services used by Comicarr. Comicvine powers volume and issue metadata lookups.
          </p>

          {externalApisLoading ? (
            <p className="settings-section-help">Loading Comicvine settings…</p>
          ) : (
            <>
              <div className="settings-form">
                <div className="settings-field">
                  <Toggle
                    id="comicvine-enabled"
                    checked={comicvineEnabled}
                    onChange={setComicvineEnabled}
                    disabled={externalApisSaving || externalApisTesting}
                    label="Enable Comicvine integration"
                  />
                </div>

                {comicvineEnabled && (
                  <>
                    <div className="settings-field">
                      <label htmlFor="comicvine-api-key">Comicvine API key</label>
                      <input
                        id="comicvine-api-key"
                        type="text"
                        value={comicvineApiKey}
                        onChange={(e) => {
                          setComicvineApiKey(e.target.value);
                          setComicvineTestResult(null);
                        }}
                        disabled={externalApisSaving || externalApisTesting}
                        placeholder="Enter the API key provided by Comicvine"
                      />
                      <p className="settings-field-help">
                        Request an API key at{' '}
                        <a
                          href="https://comicvine.gamespot.com/api/"
                          target="_blank"
                          rel="noreferrer"
                        >
                          comicvine.gamespot.com/api
                        </a>
                        .
                      </p>
                    </div>

                    <div className="settings-field">
                      <label htmlFor="comicvine-base-url">Comicvine base URL</label>
                      <input
                        id="comicvine-base-url"
                        type="text"
                        value={comicvineBaseUrl}
                        onChange={(e) => {
                          setComicvineBaseUrl(e.target.value);
                          setComicvineTestResult(null);
                        }}
                        disabled={externalApisSaving || externalApisTesting}
                      />
                      <p className="settings-field-help">
                        Override this if you proxy Comicvine internally.
                      </p>
                    </div>

                    <div className="settings-field">
                      <label htmlFor="comicvine-rate-limit">Rate limit (requests per period)</label>
                      <input
                        id="comicvine-rate-limit"
                        type="number"
                        min="1"
                        max="100"
                        value={comicvineRateLimit}
                        onChange={(e) => setComicvineRateLimit(Number(e.target.value))}
                        disabled={externalApisSaving || externalApisTesting}
                      />
                      <p className="settings-field-help">
                        Maximum number of requests allowed per rate limit period. Default: 40
                      </p>
                    </div>

                    <div className="settings-field">
                      <label htmlFor="comicvine-rate-limit-period">Rate limit period (seconds)</label>
                      <input
                        id="comicvine-rate-limit-period"
                        type="number"
                        min="1"
                        max="3600"
                        value={comicvineRateLimitPeriod}
                        onChange={(e) => setComicvineRateLimitPeriod(Number(e.target.value))}
                        disabled={externalApisSaving || externalApisTesting}
                      />
                      <p className="settings-field-help">
                        Time window in seconds for rate limiting. Default: 60
                      </p>
                    </div>

                    <div className="settings-field">
                      <label htmlFor="comicvine-max-retries">Max retries</label>
                      <input
                        id="comicvine-max-retries"
                        type="number"
                        min="0"
                        max="10"
                        value={comicvineMaxRetries}
                        onChange={(e) => setComicvineMaxRetries(Number(e.target.value))}
                        disabled={externalApisSaving || externalApisTesting}
                      />
                      <p className="settings-field-help">
                        Maximum number of retry attempts on rate limit errors (HTTP 420, 429). Default: 3
                      </p>
                    </div>

                    <div className="settings-field">
                      <Toggle
                        id="comicvine-cache-enabled"
                        checked={comicvineCacheEnabled}
                        onChange={setComicvineCacheEnabled}
                        disabled={externalApisSaving || externalApisTesting}
                        label="Enable response caching"
                      />
                      <p className="settings-field-help">
                        Cache ComicVine API responses to disk to reduce API calls and improve performance.
                      </p>
                    </div>

                    <div className="settings-field">
                      <Toggle
                        id="comicvine-burst-prevention-enabled"
                        checked={comicvineBurstPreventionEnabled}
                        onChange={setComicvineBurstPreventionEnabled}
                        disabled={externalApisSaving || externalApisTesting}
                        label="Enable burst prevention"
                      />
                      <p className="settings-field-help">
                        Prevents bursts of requests at startup by spacing requests during the first 50% of the rate limit window.
                      </p>
                    </div>

                    {comicvineBurstPreventionEnabled && (
                      <div className="settings-field">
                        <label htmlFor="comicvine-min-gap-seconds">Minimum gap (seconds)</label>
                        <input
                          type="number"
                          id="comicvine-min-gap-seconds"
                          min="0"
                          step="0.1"
                          value={comicvineMinGapSeconds ?? ''}
                          onChange={(e) => {
                            const val = e.target.value;
                            setComicvineMinGapSeconds(val === '' ? null : Number(val));
                          }}
                          disabled={externalApisSaving || externalApisTesting}
                          placeholder="Auto-calculate"
                        />
                        <p className="settings-field-help">
                          Minimum gap between requests during burst prevention. Leave empty to auto-calculate (rate_limit_period / rate_limit).
                        </p>
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="settings-actions">
                <button
                  type="button"
                  className="settings-save-button"
                  onClick={handleExternalApisSubmit}
                  disabled={externalApisSaving || !externalApisHasChanges}
                >
                  {externalApisSaving ? 'Saving...' : 'Save Comicvine settings'}
                </button>
                <button
                  type="button"
                  className="settings-cancel-button"
                  onClick={handleTestComicvine}
                  disabled={externalApisSaving || externalApisTesting}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
                >
                  {externalApisTesting ? (
                    'Testing...'
                  ) : (
                    <>
                      Test Comicvine connection
                      {comicvineTestResult === 'success' && <Check size={16} />}
                      {comicvineTestResult === 'error' && <X size={16} />}
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>

        {/* Weekly Releases */}
        <div className="settings-section">
          <h2>Weekly Releases</h2>
          <p className="settings-section-description">
            Configure automatic fetching of weekly comic releases from enabled sources.
          </p>
          
          {weeklyReleasesLoading ? (
            <p className="settings-section-help">Loading weekly releases settings…</p>
          ) : weeklyReleasesSettings ? (
            <div className="settings-form">
              <div className="settings-field">
                <Toggle
                  id="auto-fetch-enabled"
                  label="Enable automatic fetching"
                  checked={weeklyReleasesSettings.auto_fetch_enabled}
                  onChange={(checked) =>
                    setWeeklyReleasesSettings({
                      ...weeklyReleasesSettings,
                      auto_fetch_enabled: checked,
                    })
                  }
                  disabled={weeklyReleasesSaving}
                />
                <p className="settings-field-help">
                  Automatically fetch releases from enabled sources on a schedule.
                </p>
              </div>
              
              {weeklyReleasesSettings.auto_fetch_enabled && (
                <>
                  <div className="settings-field">
                    <label htmlFor="fetch-interval" className="settings-label">
                      Fetch interval (hours)
                    </label>
                    <input
                      id="fetch-interval"
                      type="number"
                      min="1"
                      max="168"
                      value={weeklyReleasesSettings.auto_fetch_interval_hours}
                      onChange={(e) =>
                        setWeeklyReleasesSettings({
                          ...weeklyReleasesSettings,
                          auto_fetch_interval_hours: parseInt(e.target.value) || 12,
                        })
                      }
                      className="settings-input"
                      disabled={weeklyReleasesSaving}
                    />
                    <p className="settings-field-help">
                      How often to fetch releases (1-168 hours, default: 12).
                    </p>
                  </div>
                  
                  <div className="settings-field">
                    <label className="settings-label">Sources</label>
                    <div className="settings-checkbox-group">
                      <div className="settings-checkbox-item">
                        <Toggle
                          id="source-previewsworld"
                          label="PreviewsWorld"
                          checked={weeklyReleasesSettings.sources.previewsworld.enabled}
                          onChange={(checked) =>
                            setWeeklyReleasesSettings({
                              ...weeklyReleasesSettings,
                              sources: {
                                ...weeklyReleasesSettings.sources,
                                previewsworld: { enabled: checked },
                              },
                            })
                          }
                          disabled={weeklyReleasesSaving}
                        />
                      </div>
                      <div className="settings-checkbox-item">
                        <Toggle
                          id="source-comicgeeks"
                          label="League of Comic Geeks"
                          checked={weeklyReleasesSettings.sources.comicgeeks.enabled}
                          onChange={(checked) =>
                            setWeeklyReleasesSettings({
                              ...weeklyReleasesSettings,
                              sources: {
                                ...weeklyReleasesSettings.sources,
                                comicgeeks: { enabled: checked },
                              },
                            })
                          }
                          disabled={weeklyReleasesSaving}
                        />
                      </div>
                      <div className="settings-checkbox-item">
                        <Toggle
                          id="source-readcomicsonline"
                          label="ReadComicsOnline"
                          checked={weeklyReleasesSettings.sources.readcomicsonline.enabled}
                          onChange={(checked) =>
                            setWeeklyReleasesSettings({
                              ...weeklyReleasesSettings,
                              sources: {
                                ...weeklyReleasesSettings.sources,
                                readcomicsonline: { enabled: checked },
                              },
                            })
                          }
                          disabled={weeklyReleasesSaving}
                        />
                      </div>
                    </div>
                    <p className="settings-field-help">
                      Select which sources to fetch from automatically.
                    </p>
                  </div>
                </>
              )}
              
              <div className="settings-actions">
                <button
                  type="button"
                  className="settings-save-button"
                  onClick={saveWeeklyReleasesSettings}
                  disabled={weeklyReleasesSaving}
                >
                  {weeklyReleasesSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          ) : (
            <p className="settings-section-help">Failed to load settings.</p>
          )}
        </div>
      </div>
    </div>
  );
}
