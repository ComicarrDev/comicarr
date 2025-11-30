import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { buildApiUrl } from '../api/client';
import Toggle from '../components/Toggle';
import './SettingsPage.css';
import './ReadingSettingsPage.css';

interface ReadingSettings {
  enabled: boolean;
  reading_mode?: 'single' | 'double';
  double_page_gap?: number; // Gap between pages in 2-page mode (pixels, 0 = pages touch)
  // Future settings (prepared for later implementation)
  // zoom_mode?: 'fit_width' | 'fit_height' | 'fit_both' | 'original';
  // track_progress?: boolean;
  // auto_mark_read?: boolean;
}

export default function ReadingSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<ReadingSettings>({ enabled: true, reading_mode: 'single', double_page_gap: 0 });
  const [hasChanges, setHasChanges] = useState(false);
  const [originalSettings, setOriginalSettings] = useState<ReadingSettings>({ enabled: true, reading_mode: 'single', double_page_gap: 0 });

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        setLoading(true);
        const response = await fetch(buildApiUrl('/api/settings/reading'), {
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error('Failed to load reading settings');
        }

        const data = await response.json() as { settings: ReadingSettings };
        setSettings(data.settings);
        setOriginalSettings(data.settings);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to load reading settings');
      } finally {
        setLoading(false);
      }
    };

    fetchSettings();
  }, []);

  // Track changes
  useEffect(() => {
    const changed = JSON.stringify(settings) !== JSON.stringify(originalSettings);
    setHasChanges(changed);
  }, [settings, originalSettings]);

  const handleEnabledChange = (checked: boolean) => {
    setSettings({ ...settings, enabled: checked });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(buildApiUrl('/api/settings/reading'), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(settings),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to save settings' }));
        throw new Error(errorData.detail || 'Failed to save reading settings');
      }

      const data = await response.json() as { settings: ReadingSettings };
      setSettings(data.settings);
      setOriginalSettings(data.settings);
      toast.success('Reading settings saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save reading settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSettings(originalSettings);
  };

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <p>Loading reading settings…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <p>
          Configure reading functionality, display modes, and viewing preferences.
        </p>
      </div>

      <div className="settings-content">
        <div className="settings-section">
          <h2>General</h2>
          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="reading-enabled">Enable Reading</label>
              <p className="settings-field-description">
                Enable or disable the reading functionality. When disabled, the Read button will not be available.
              </p>
            </div>
            <div className="settings-field-control">
              <Toggle
                id="reading-enabled"
                checked={settings.enabled}
                onChange={handleEnabledChange}
              />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Reading Mode</h2>
          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="reading-mode">Page Display</label>
              <p className="settings-field-description">
                Choose how pages are displayed: single page or two pages side by side. The cover (first page) is always shown alone.
              </p>
            </div>
            <div className="settings-field-control">
              <select
                id="reading-mode"
                value={settings.reading_mode || 'single'}
                onChange={(e) => setSettings({ ...settings, reading_mode: e.target.value as 'single' | 'double' })}
              >
                <option value="single">Single Page</option>
                <option value="double">Two Pages</option>
              </select>
            </div>
          </div>
          {settings.reading_mode === 'double' && (
            <div className="settings-field">
              <div className="settings-field-label">
                <label htmlFor="double-page-gap">Page Gap (2-page mode only)</label>
                <p className="settings-field-description">
                  Gap between pages when viewing in 2-page mode (in pixels). Set to 0 for pages to touch edge-to-edge (useful for two-page spreads).
                </p>
              </div>
              <div className="settings-field-control">
                <input
                  id="double-page-gap"
                  type="number"
                  min="0"
                  max="50"
                  step="1"
                  value={settings.double_page_gap ?? 0}
                  onChange={(e) => setSettings({ ...settings, double_page_gap: parseInt(e.target.value, 10) || 0 })}
                  style={{ width: '100px' }}
                />
                <span style={{ marginLeft: '0.5rem', color: 'var(--text-secondary)' }}>px</span>
              </div>
            </div>
          )}
        </div>

        {/* Future settings sections - prepared for later implementation */}
        {/*

        <div className="settings-section">
          <h2>Zoom Settings</h2>
          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="zoom-mode">Zoom Mode</label>
              <p className="settings-field-description">
                How pages should be zoomed by default.
              </p>
            </div>
            <div className="settings-field-control">
              <select
                id="zoom-mode"
                value={settings.zoom_mode || 'fit_width'}
                onChange={(e) => setSettings({ ...settings, zoom_mode: e.target.value as any })}
              >
                <option value="fit_width">Fit to Width</option>
                <option value="fit_height">Fit to Height</option>
                <option value="fit_both">Fit to Screen</option>
                <option value="original">Original Size</option>
              </select>
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Progress Tracking</h2>
          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="track-progress">Track Reading Progress</label>
              <p className="settings-field-description">
                Automatically track which pages you have read.
              </p>
            </div>
            <div className="settings-field-control">
              <Toggle
                id="track-progress"
                checked={settings.track_progress ?? true}
                onChange={(checked) => setSettings({ ...settings, track_progress: checked })}
              />
            </div>
          </div>
          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="auto-mark-read">Auto Mark as Read</label>
              <p className="settings-field-description">
                Automatically mark issues as read when you finish reading them.
              </p>
            </div>
            <div className="settings-field-control">
              <Toggle
                id="auto-mark-read"
                checked={settings.auto_mark_read ?? false}
                onChange={(checked) => setSettings({ ...settings, auto_mark_read: checked })}
              />
            </div>
          </div>
        </div>
        */}
      </div>

      <div className="settings-actions">
        <button
          type="button"
          className="button secondary"
          onClick={handleReset}
          disabled={!hasChanges || saving}
        >
          Reset
        </button>
        <button
          type="button"
          className="button primary"
          onClick={handleSave}
          disabled={!hasChanges || saving}
        >
          {saving ? 'Saving…' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

