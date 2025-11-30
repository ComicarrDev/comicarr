import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

const TOAST_SETTINGS_KEY = 'comicarr-ui-settings';

interface ToastContextType {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabledState] = useState<boolean>(() => {
    try {
      const uiSettings = localStorage.getItem(TOAST_SETTINGS_KEY);
      if (uiSettings) {
        const parsed = JSON.parse(uiSettings);
        return parsed.toastNotificationsEnabled !== false; // Default to true
      }
    } catch (err) {
      // Ignore errors
    }
    return true; // Default to enabled
  });

  const setEnabled = (value: boolean) => {
    setEnabledState(value);
    // Update localStorage
    try {
      const existing = localStorage.getItem(TOAST_SETTINGS_KEY);
      const settings = existing ? JSON.parse(existing) : {};
      settings.toastNotificationsEnabled = value;
      localStorage.setItem(TOAST_SETTINGS_KEY, JSON.stringify(settings));
    } catch (err) {
      console.warn('Failed to save toast settings:', err);
    }
  };

  // Listen for changes to UI settings
  useEffect(() => {
    const handleStorageChange = () => {
      try {
        const uiSettings = localStorage.getItem(TOAST_SETTINGS_KEY);
        if (uiSettings) {
          const parsed = JSON.parse(uiSettings);
          setEnabledState(parsed.toastNotificationsEnabled !== false);
        }
      } catch (err) {
        // Ignore errors
      }
    };

    window.addEventListener('storage', handleStorageChange);
    // Also listen for custom events (for same-tab updates)
    window.addEventListener('ui-settings-changed', handleStorageChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('ui-settings-changed', handleStorageChange);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ enabled, setEnabled }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}



