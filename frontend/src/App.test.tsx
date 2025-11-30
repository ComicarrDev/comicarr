import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { apiGet } from './api/client';

// Mock the API client
vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof import('./api/client')>('./api/client');
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPut: vi.fn(),
    apiDelete: vi.fn(),
    getBaseUrl: vi.fn(() => ''),
  };
});

const routerConfig = {
  future: {
    v7_startTransition: true,
    v7_relativeSplatPath: true,
  },
};

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock session check to return 'none' auth by default
    vi.mocked(apiGet).mockResolvedValue({
      authenticated: true,
      auth_method: 'none',
      setup_required: false,
    });
  });

  it('renders navigation with Comicarr brand', async () => {
    render(
      <BrowserRouter {...routerConfig}>
        <App />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Comicarr')).toBeInTheDocument();
    });
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('renders home page by default', async () => {
    render(
      <BrowserRouter {...routerConfig}>
        <App />
      </BrowserRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Overview of your comic library'),
    ).toBeInTheDocument();
  });

  it('has working navigation links', async () => {
    render(
      <BrowserRouter {...routerConfig}>
        <App />
      </BrowserRouter>,
    );

    await waitFor(() => {
      // Settings is in a nested menu, so we look for the "General" child link
      const settingsLink = screen.getByRole('link', { name: 'General' });
      expect(settingsLink).toHaveAttribute('href', '/settings/general');
    });
  });
});
