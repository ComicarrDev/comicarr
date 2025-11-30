import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface RequireAuthProps {
  children: React.ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const { authenticated, authMethod, loading, setupRequired } = useAuth();

  // Show nothing while loading
  if (loading) {
    return <div>Loading...</div>;
  }

  // If setup is required, redirect to setup page
  if (setupRequired) {
    return <Navigate to="/setup" replace />;
  }

  // If auth method is 'none', allow access
  if (authMethod === 'none') {
    return <>{children}</>;
  }

  // If authenticated, allow access
  if (authenticated) {
    return <>{children}</>;
  }

  // Otherwise, redirect to login
  return <Navigate to="/login" replace />;
}

