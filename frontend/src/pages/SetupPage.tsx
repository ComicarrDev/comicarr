import { useState, FormEvent, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../contexts/AuthContext';
import { apiPost, ApiClientError } from '../api/client';
import './SetupPage.css';

export default function SetupPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { setupRequired, authMethod, authenticated, loading: authLoading, checkSession } = useAuth();
  const navigate = useNavigate();

  // Redirect if setup is not required (auth is already configured)
  useEffect(() => {
    if (!authLoading && !setupRequired) {
      // Auth is already configured, redirect appropriately
      if (authMethod === 'forms' && !authenticated) {
        navigate('/login', { replace: true });
      } else {
        navigate('/', { replace: true });
      }
    }
  }, [setupRequired, authMethod, authenticated, authLoading, navigate]);

  // Don't render if setup is not required (will redirect)
  if (authLoading || !setupRequired) {
    return null;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    // Validation
    if (!username.trim()) {
      toast.error('Username is required');
      return;
    }

    if (password.length < 1) {
      toast.error('Password is required');
      return;
    }

    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }

    setLoading(true);

    const setupPromise = (async () => {
      const response = await apiPost<{
        success: boolean;
        message: string;
      }>('/auth/setup', {
        username: username.trim(),
        password,
      });

      if (!response.success) {
        throw new Error(response.message || 'Setup failed');
      }

      // Re-check session to update auth state
      await checkSession();

      // Redirect to login page (user needs to login with new credentials)
      navigate('/login', { replace: true });
      
      return response.message || 'Setup completed successfully';
    })();

    toast.promise(setupPromise, {
      loading: 'Creating account...',
      success: (message) => {
        return message;
      },
      error: (err) => {
        // Handle ApiClientError with better error messages
        if (err instanceof ApiClientError) {
          // If 409 Conflict, auth is already configured - redirect to login
          if (err.status === 409) {
            // Refresh auth state and redirect
            checkSession().then(() => {
              navigate('/login', { replace: true });
            });
            return 'Authentication is already configured. Redirecting to login...';
          }
          
          // Extract detail from ApiClientError
          let errorMessage = 'Setup failed. Please try again.';
          if (typeof err.detail === 'string') {
            errorMessage = err.detail;
          } else if (Array.isArray(err.detail)) {
            errorMessage = err.detail.map((e) => e.msg || String(e)).join(', ');
          } else if (err.detail) {
            errorMessage = String(err.detail);
          }
          return errorMessage;
        } else if (err instanceof Error) {
          return err.message || 'Setup failed. Please try again.';
        }
        return 'Setup failed. Please try again.';
      },
    });

    try {
      await setupPromise;
    } catch {
      // Error handled by toast.promise
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="setup-page">
      <div className="setup-container">
        <div className="setup-header">
          <h1>Welcome to Comicarr</h1>
          <p>Create your administrator account to get started</p>
        </div>
        <form onSubmit={handleSubmit} className="setup-form">
          <div className="setup-field">
            <label htmlFor="setup-username">Username</label>
            <input
              id="setup-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              disabled={loading}
              placeholder="Enter username"
            />
          </div>
          <div className="setup-field">
            <label htmlFor="setup-password">Password</label>
            <input
              id="setup-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              disabled={loading}
              placeholder="Enter password"
            />
          </div>
          <div className="setup-field">
            <label htmlFor="setup-confirm-password">Confirm Password</label>
            <input
              id="setup-confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              disabled={loading}
              placeholder="Confirm password"
            />
          </div>
          <button type="submit" className="setup-button" disabled={loading}>
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  );
}