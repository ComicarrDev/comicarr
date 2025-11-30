import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from './SettingsPage';
import * as apiClient from '../api/client';

// Mock the API client
vi.mock('../api/client');

// Mock toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('SettingsPage', () => {
  const mockWeeklyReleasesSettings = {
    auto_fetch_enabled: false,
    auto_fetch_interval_hours: 24,
    sources: {
      previewsworld: { enabled: false },
      comicgeeks: { enabled: false },
      readcomicsonline: { enabled: false },
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    // Mock delayed responses
    vi.mocked(apiClient.apiGet).mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({}), 1000);
        }) as Promise<unknown>,
    );

    render(<SettingsPage />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('displays host settings when loaded successfully', async () => {
    const mockHostSettings = {
      bind_address: '127.0.0.1',
      port: 8000,
      base_url: '',
    };

    const mockSecuritySettings = {
      auth_method: 'none',
      username: null,
      has_password: false,
      api_key: null,
      has_api_key: false,
    };

    const mockExternalApis = {
      comicvine: {
        api_key: null,
        base_url: 'https://comicvine.gamespot.com/api',
        enabled: false,
      },
    };

    vi.mocked(apiClient.apiGet)
      .mockResolvedValueOnce(mockHostSettings) // /settings/host
      .mockResolvedValueOnce(mockSecuritySettings) // /settings/security
      .mockResolvedValueOnce(mockExternalApis) // /settings/external-apis
      .mockResolvedValueOnce(mockWeeklyReleasesSettings); // /settings/weekly-releases

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Check Host section
    expect(screen.getByText('Host')).toBeInTheDocument();
    expect(screen.getByLabelText(/bind address/i)).toHaveValue('127.0.0.1');
    expect(screen.getByLabelText(/port/i)).toHaveValue(8000);
    expect(screen.getByLabelText(/base url/i)).toHaveValue('');

    // Check Security section
    expect(screen.getByText('Security')).toBeInTheDocument();

    // Check External APIs section
    expect(screen.getByText('External APIs')).toBeInTheDocument();
  });

  it('displays security settings with forms auth', async () => {
    const mockHostSettings = {
      bind_address: '127.0.0.1',
      port: 8000,
      base_url: '',
    };

    const mockSecuritySettings = {
      auth_method: 'forms',
      username: 'admin',
      has_password: true,
      api_key: 'test-key',
      has_api_key: true,
    };

    const mockExternalApis = {
      comicvine: {
        api_key: null,
        base_url: 'https://comicvine.gamespot.com/api',
        enabled: false,
      },
    };

    vi.mocked(apiClient.apiGet)
      .mockResolvedValueOnce(mockHostSettings)
      .mockResolvedValueOnce(mockSecuritySettings)
      .mockResolvedValueOnce(mockExternalApis)
      .mockResolvedValueOnce(mockWeeklyReleasesSettings);

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Check auth method is set to forms
    const authToggle = screen.getByLabelText(/forms authentication enabled/i);
    expect(authToggle).toBeChecked();

    // Check username field is visible and has value
    expect(screen.getByLabelText(/username/i)).toHaveValue('admin');
  });

  it('displays external APIs settings with Comicvine enabled', async () => {
    const mockHostSettings = {
      bind_address: '127.0.0.1',
      port: 8000,
      base_url: '',
    };

    const mockSecuritySettings = {
      auth_method: 'none',
      username: null,
      has_password: false,
      api_key: null,
      has_api_key: false,
    };

    const mockExternalApis = {
      comicvine: {
        api_key: 'test-api-key',
        base_url: 'https://comicvine.gamespot.com/api',
        enabled: true,
      },
    };

    vi.mocked(apiClient.apiGet)
      .mockResolvedValueOnce(mockHostSettings)
      .mockResolvedValueOnce(mockSecuritySettings)
      .mockResolvedValueOnce(mockExternalApis)
      .mockResolvedValueOnce(mockWeeklyReleasesSettings);

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Check Comicvine toggle is enabled
    const comicvineToggle = screen.getByLabelText(/enable comicvine integration/i);
    expect(comicvineToggle).toBeChecked();

    // Check API key field is visible and has value (use ID to be specific to Comicvine)
    expect(screen.getByLabelText(/comicvine api key/i)).toHaveValue('test-api-key');
  });

  it('saves host settings when save button is clicked', async () => {
    const user = userEvent.setup();

    const mockHostSettings = {
      bind_address: '127.0.0.1',
      port: 8000,
      base_url: '',
    };

    const mockSecuritySettings = {
      auth_method: 'none',
      username: null,
      has_password: false,
      api_key: null,
      has_api_key: false,
    };

    const mockExternalApis = {
      comicvine: {
        api_key: null,
        base_url: 'https://comicvine.gamespot.com/api',
        enabled: false,
      },
    };

    vi.mocked(apiClient.apiGet)
      .mockResolvedValueOnce(mockHostSettings)
      .mockResolvedValueOnce(mockSecuritySettings)
      .mockResolvedValueOnce(mockExternalApis)
      .mockResolvedValueOnce(mockWeeklyReleasesSettings);

    vi.mocked(apiClient.apiPut).mockResolvedValue({
      bind_address: '0.0.0.0',
      port: 9000,
      base_url: '/comicarr',
    });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Change bind address
    const bindAddressInput = screen.getByLabelText(/bind address/i);
    await user.clear(bindAddressInput);
    await user.type(bindAddressInput, '0.0.0.0');

    // Change port
    const portInput = screen.getByLabelText(/port/i);
    await user.clear(portInput);
    await user.type(portInput, '9000');

    // Find and click save button (should be enabled after changes)
    const saveButtons = screen.getAllByRole('button', { name: /save/i });
    const hostSaveButton = saveButtons[0]; // First save button is for Host section

    await user.click(hostSaveButton);

    await waitFor(() => {
      expect(apiClient.apiPut).toHaveBeenCalledWith('/settings/host', {
        bind_address: '0.0.0.0',
        port: 9000,
        base_url: '',
      });
    });
  });

  it('disables save buttons when no changes are made', async () => {
    const mockHostSettings = {
      bind_address: '127.0.0.1',
      port: 8000,
      base_url: '',
    };

    const mockSecuritySettings = {
      auth_method: 'none',
      username: null,
      has_password: false,
      api_key: null,
      has_api_key: false,
    };

    const mockExternalApis = {
      comicvine: {
        api_key: null,
        base_url: 'https://comicvine.gamespot.com/api',
        enabled: false,
      },
    };

    vi.mocked(apiClient.apiGet)
      .mockResolvedValueOnce(mockHostSettings)
      .mockResolvedValueOnce(mockSecuritySettings)
      .mockResolvedValueOnce(mockExternalApis)
      .mockResolvedValueOnce(mockWeeklyReleasesSettings);

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // All save buttons should be disabled (except weekly releases which is always enabled unless saving)
    expect(screen.getByRole('button', { name: /save changes/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /save security settings/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /save comicvine settings/i })).toBeDisabled();
    // Weekly releases save button is always enabled (not based on changes), so we don't check it
  });

  it('tests Comicvine connection', async () => {
    const user = userEvent.setup();

    const mockHostSettings = {
      bind_address: '127.0.0.1',
      port: 8000,
      base_url: '',
    };

    const mockSecuritySettings = {
      auth_method: 'none',
      username: null,
      has_password: false,
      api_key: null,
      has_api_key: false,
    };

    const mockExternalApis = {
      comicvine: {
        api_key: null,
        base_url: 'https://comicvine.gamespot.com/api',
        enabled: false,
      },
    };

    vi.mocked(apiClient.apiGet)
      .mockResolvedValueOnce(mockHostSettings)
      .mockResolvedValueOnce(mockSecuritySettings)
      .mockResolvedValueOnce(mockExternalApis)
      .mockResolvedValueOnce(mockWeeklyReleasesSettings);

    vi.mocked(apiClient.apiPost).mockResolvedValue({
      success: true,
      message: 'Connection successful',
    });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Enable Comicvine
    const comicvineToggle = screen.getByLabelText(/enable comicvine integration/i);
    await user.click(comicvineToggle);

    // Enter API key (use Comicvine-specific label)
    const apiKeyInput = screen.getByLabelText(/comicvine api key/i);
    await user.type(apiKeyInput, 'test-key');

    // Click test button
    const testButton = screen.getByRole('button', { name: /test comicvine connection/i });
    await user.click(testButton);

    await waitFor(() => {
      expect(apiClient.apiPost).toHaveBeenCalledWith('/settings/external-apis/test', {
        comicvine: {
          api_key: 'test-key',
          base_url: 'https://comicvine.gamespot.com/api',
          enabled: true,
        },
      });
    });
  });

  it('handles API errors gracefully', async () => {
    vi.mocked(apiClient.apiGet)
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'));

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    // Should show error state (component should handle errors)
    // The exact error display depends on implementation
  });
});
