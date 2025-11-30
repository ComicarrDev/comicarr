import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useTheme } from '../contexts/ThemeContext';
import { ThemeMode, ThemeName } from '../themes/theme';
import Toggle from '../components/Toggle';
import './SettingsPage.css';
import './UISettingsPage.css';

const UI_SETTINGS_STORAGE_KEY = 'comicarr-ui-settings';

interface UISettings {
  themeName: ThemeName;
  defaultTheme: ThemeMode;
  toastNotificationsEnabled: boolean;
}

const defaultSettings: UISettings = {
  themeName: 'default',
  defaultTheme: 'dark',
  toastNotificationsEnabled: true,
};

function loadUISettings(): UISettings {
  try {
    const saved = localStorage.getItem(UI_SETTINGS_STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      return {
        themeName: ['default', 'A', 'B', 'C', 'D'].includes(parsed.themeName) 
          ? parsed.themeName as ThemeName 
          : 'default',
        defaultTheme: parsed.defaultTheme === 'light' ? 'light' : 'dark',
        toastNotificationsEnabled: parsed.toastNotificationsEnabled !== false,
      };
    }
  } catch (err) {
    console.warn('Failed to load UI settings:', err);
  }
  return defaultSettings;
}

function saveUISettings(settings: UISettings): void {
  try {
    localStorage.setItem(UI_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch (err) {
    console.warn('Failed to save UI settings:', err);
  }
}

export default function UISettingsPage() {
  const { themeName, themeMode, setThemeName, setThemeMode } = useTheme();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<UISettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const loaded = loadUISettings();
    setSettings(loaded);
    setLoading(false);
  }, []);

  // Track changes by comparing with current theme
  useEffect(() => {
    const hasThemeChanges = settings.themeName !== themeName || settings.defaultTheme !== themeMode;
    setHasChanges(hasThemeChanges);
  }, [settings, themeName, themeMode]);

  const handleThemeNameChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newThemeName = event.target.value as ThemeName;
    const newSettings = { ...settings, themeName: newThemeName };
    setSettings(newSettings);
    setHasChanges(true);
  };

  const handleDefaultThemeChange = (checked: boolean) => {
    const newTheme: ThemeMode = checked ? 'light' : 'dark';
    const newSettings = { ...settings, defaultTheme: newTheme };
    setSettings(newSettings);
    setHasChanges(true);
  };

  const handleToastNotificationsChange = (checked: boolean) => {
    const newSettings = { ...settings, toastNotificationsEnabled: checked };
    setSettings(newSettings);
    setHasChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      saveUISettings(settings);
      
      // Apply theme changes if different from current
      if (settings.themeName !== themeName) {
        setThemeName(settings.themeName);
      }
      if (settings.defaultTheme !== themeMode) {
        setThemeMode(settings.defaultTheme);
      }
      
      // Dispatch event to notify other components of settings change
      window.dispatchEvent(new Event('ui-settings-changed'));
      
      toast.success('UI settings saved successfully');
      setHasChanges(false);
    } catch (err) {
      toast.error('Failed to save UI settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <p>Loading UI settings…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <p>
          Configure user interface preferences, themes, and notification settings.
        </p>
      </div>

      <div className="settings-content">
        <div className="settings-section">
          <h2>Theme</h2>
          <p className="settings-section-description">
            Choose your preferred theme and color scheme. You can always toggle between light and dark modes using the button in the header.
          </p>

          <div className="settings-form">
            <div className="settings-field">
              <label htmlFor="theme-name" className="settings-label">
                Theme
              </label>
              <select
                id="theme-name"
                value={settings.themeName}
                onChange={handleThemeNameChange}
                disabled={saving}
              >
                <option value="default">Default</option>
                <option value="A">Theme A</option>
                <option value="B">Theme B</option>
                <option value="C">Theme C</option>
                <option value="D">Theme D</option>
              </select>
              <p className="settings-field-help">
                Select a color theme for the application.
              </p>
            </div>

            <div className="settings-field">
              <Toggle
                id="default-theme-light"
                checked={settings.defaultTheme === 'light'}
                onChange={handleDefaultThemeChange}
                disabled={saving}
                label="Use light mode as default"
              />
              <p className="settings-field-help">
                When enabled, the light mode will be used by default. When disabled, the dark mode is used.
              </p>
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Notifications</h2>
          <p className="settings-section-description">
            Control how notifications are displayed in the application.
          </p>

          <div className="settings-form">
            <div className="settings-field">
              <Toggle
                id="toast-notifications"
                checked={settings.toastNotificationsEnabled}
                onChange={handleToastNotificationsChange}
                disabled={saving}
                label="Enable toast notifications"
              />
              <p className="settings-field-help">
                When enabled, toast notifications will appear for actions and events. When disabled, notifications are hidden.
              </p>
            </div>
          </div>
        </div>

        <div className="settings-actions">
          <button
            type="button"
            className="settings-save-button"
            onClick={handleSave}
            disabled={saving || !hasChanges}
          >
            {saving ? 'Saving...' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

