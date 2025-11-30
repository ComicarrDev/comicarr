import { useState, FormEvent, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../contexts/AuthContext';
import './LoginPage.css';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, authMethod, authenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (authMethod === 'none') {
      navigate('/', { replace: true });
    } else if (authenticated) {
      navigate('/', { replace: true });
    }
  }, [authMethod, authenticated, navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const loginPromise = login(username, password);

    toast.promise(loginPromise, {
      loading: 'Signing in...',
      success: () => {
        navigate('/', { replace: true });
        return 'Signed in successfully';
      },
      error: (err) => {
        const message = err instanceof Error ? err.message : 'Login failed. Please try again.';
        return message;
      },
    });

    try {
      await loginPromise;
    } catch {
      // Error handled by toast.promise
    } finally {
      setLoading(false);
    }
  };

  if (authMethod === 'none' || authenticated) {
    return null;
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>Comicarr</h1>
          <p>Please sign in to continue</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              disabled={loading}
            />
          </div>
          <button type="submit" className="login-button" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}