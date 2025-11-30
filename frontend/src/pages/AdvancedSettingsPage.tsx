import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { buildApiUrl } from '../api/client';
import Toggle from '../components/Toggle';
import './SettingsPage.css';
import './ReadingSettingsPage.css';

interface MatchingSettings {
  issue_number_exact_match: number;
  series_name_exact_match: number;
  series_name_prefix_match: number;
  series_name_substring_match: number;
  year_match: number;
  publisher_match: number;
  minimum_confidence: number;
  minimum_issue_match_score: number;
  max_volume_score: number;
  max_issue_score: number;
  minimum_series_name_length_for_rejection: number;
  issue_search_limit: number;
  volume_search_limit: number;
  comicvine_cache_enabled: boolean;
}

export default function AdvancedSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<MatchingSettings>({
    issue_number_exact_match: 5.0,
    series_name_exact_match: 3.0,
    series_name_prefix_match: 1.5,
    series_name_substring_match: 1.0,
    year_match: 0.5,
    publisher_match: 1.0,
    minimum_confidence: 0.3,
    minimum_issue_match_score: 5.0,
    max_volume_score: 3.5,
    max_issue_score: 8.5,
    minimum_series_name_length_for_rejection: 5,
    issue_search_limit: 30,
    volume_search_limit: 10,
    comicvine_cache_enabled: true,
  });
  const [hasChanges, setHasChanges] = useState(false);
  const [originalSettings, setOriginalSettings] = useState<MatchingSettings>(settings);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        setLoading(true);
        const response = await fetch(buildApiUrl('/api/settings/advanced'), {
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error('Failed to load advanced settings');
        }

        const data = await response.json() as { settings: MatchingSettings };
        setSettings(data.settings);
        setOriginalSettings(data.settings);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to load advanced settings');
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

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(buildApiUrl('/api/settings/advanced'), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(settings),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to save settings' }));
        throw new Error(errorData.detail || 'Failed to save advanced settings');
      }

      const data = await response.json() as { settings: MatchingSettings };
      setSettings(data.settings);
      setOriginalSettings(data.settings);
      toast.success('Advanced settings saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save advanced settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSettings(originalSettings);
  };

  const updateSetting = (key: keyof MatchingSettings, value: number | boolean) => {
    setSettings({ ...settings, [key]: value });
  };

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <p>Loading advanced settings…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <p>
          Configure matching parameters, scoring weights, and search limits for ComicVine integration.
        </p>
      </div>

      <div className="settings-content">
        <div className="settings-section">
          <h2>Scoring Weights</h2>
          <p className="settings-section-description">
            Adjust the weights used when matching files to ComicVine data. Higher values give more importance to that criterion.
          </p>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="issue-number-exact-match">Issue Number Exact Match</label>
              <p className="settings-field-description">
                Weight for when the issue number matches exactly (e.g., searching for #127 finds issue #127).
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="issue-number-exact-match"
                type="number"
                min="0"
                max="10"
                step="0.1"
                value={settings.issue_number_exact_match}
                onChange={(e) => updateSetting('issue_number_exact_match', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="series-name-exact-match">Series Name Exact Match</label>
              <p className="settings-field-description">
                Weight for when the series name matches exactly (e.g., "Batman" matches "Batman").
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="series-name-exact-match"
                type="number"
                min="0"
                max="10"
                step="0.1"
                value={settings.series_name_exact_match}
                onChange={(e) => updateSetting('series_name_exact_match', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="series-name-prefix-match">Series Name Prefix Match</label>
              <p className="settings-field-description">
                Weight for when the series name starts with the search term (e.g., "Batman" matches "Batman: The Dark Knight").
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="series-name-prefix-match"
                type="number"
                min="0"
                max="10"
                step="0.1"
                value={settings.series_name_prefix_match}
                onChange={(e) => updateSetting('series_name_prefix_match', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="series-name-substring-match">Series Name Substring Match</label>
              <p className="settings-field-description">
                Weight for when the series name contains the search term (e.g., "Batman" matches "The Batman").
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="series-name-substring-match"
                type="number"
                min="0"
                max="10"
                step="0.1"
                value={settings.series_name_substring_match}
                onChange={(e) => updateSetting('series_name_substring_match', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="year-match">Year Match</label>
              <p className="settings-field-description">
                Weight for when the volume start year matches the search year (e.g., searching for 2016 matches a volume from 2016).
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="year-match"
                type="number"
                min="0"
                max="10"
                step="0.1"
                value={settings.year_match}
                onChange={(e) => updateSetting('year_match', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="publisher-match">Publisher Match</label>
              <p className="settings-field-description">
                Weight for when the publisher matches (e.g., "DC Comics" matches "DC Comics").
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="publisher-match"
                type="number"
                min="0"
                max="10"
                step="0.1"
                value={settings.publisher_match}
                onChange={(e) => updateSetting('publisher_match', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Thresholds</h2>
          <p className="settings-section-description">
            Configure minimum scores and confidence levels required for matches.
          </p>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="minimum-confidence">Minimum Confidence</label>
              <p className="settings-field-description">
                Minimum confidence score (0.0-1.0) required for a match to be considered valid. Lower values allow more matches, higher values require stronger matches.
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="minimum-confidence"
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={settings.minimum_confidence}
                onChange={(e) => updateSetting('minimum_confidence', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="minimum-issue-match-score">Minimum Issue Match Score</label>
              <p className="settings-field-description">
                Minimum raw score required when searching for issues. Issues below this score will be rejected even if they match the issue number.
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="minimum-issue-match-score"
                type="number"
                min="0"
                max="20"
                step="0.1"
                value={settings.minimum_issue_match_score}
                onChange={(e) => updateSetting('minimum_issue_match_score', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Normalization</h2>
          <p className="settings-section-description">
            Maximum scores used to normalize raw scores to confidence values (0.0-1.0). These are typically calculated automatically but can be adjusted.
          </p>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="max-volume-score">Max Volume Score</label>
              <p className="settings-field-description">
                Maximum possible score for volume-only matches (typically: exact name + year = 3.0 + 0.5 = 3.5).
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="max-volume-score"
                type="number"
                min="0"
                max="20"
                step="0.1"
                value={settings.max_volume_score}
                onChange={(e) => updateSetting('max_volume_score', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="max-issue-score">Max Issue Score</label>
              <p className="settings-field-description">
                Maximum possible score for issue matches (typically: issue + exact name + year = 5.0 + 3.0 + 0.5 = 8.5).
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="max-issue-score"
                type="number"
                min="0"
                max="20"
                step="0.1"
                value={settings.max_issue_score}
                onChange={(e) => updateSetting('max_issue_score', parseFloat(e.target.value) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Validation</h2>
          <p className="settings-section-description">
            Configure validation rules for matching.
          </p>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="minimum-series-name-length-for-rejection">Minimum Series Name Length for Rejection</label>
              <p className="settings-field-description">
                When an issue number matches but the series name doesn't, only reject if the series name is longer than this value. This prevents false rejections for very short series names.
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="minimum-series-name-length-for-rejection"
                type="number"
                min="0"
                max="100"
                step="1"
                value={settings.minimum_series_name_length_for_rejection}
                onChange={(e) => updateSetting('minimum_series_name_length_for_rejection', parseInt(e.target.value, 10) || 0)}
                style={{ width: '120px' }}
              />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h2>Search Limits</h2>
          <p className="settings-section-description">
            Configure how many results to fetch from ComicVine API. Higher values may return more results but take longer.
          </p>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="issue-search-limit">Issue Search Limit</label>
              <p className="settings-field-description">
                Number of issues to fetch from ComicVine when searching for issues. Increase this if the correct issue isn't appearing in results (default: 30).
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="issue-search-limit"
                type="number"
                min="1"
                max="100"
                step="1"
                value={settings.issue_search_limit}
                onChange={(e) => updateSetting('issue_search_limit', parseInt(e.target.value, 10) || 30)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="volume-search-limit">Volume Search Limit</label>
              <p className="settings-field-description">
                Number of volumes to fetch from ComicVine when searching for volumes (fallback search). Default: 10.
              </p>
            </div>
            <div className="settings-field-control">
              <input
                id="volume-search-limit"
                type="number"
                min="1"
                max="100"
                step="1"
                value={settings.volume_search_limit}
                onChange={(e) => updateSetting('volume_search_limit', parseInt(e.target.value, 10) || 10)}
                style={{ width: '120px' }}
              />
            </div>
          </div>

          <div className="settings-field">
            <div className="settings-field-label">
              <label htmlFor="comicvine-cache-enabled">ComicVine Cache Enabled</label>
              <p className="settings-field-description">
                Enable caching of ComicVine API responses to speed up scans. Cached data is stored for 7 days. Disable if you want fresh data on every scan (slower but always up-to-date).
              </p>
            </div>
            <div className="settings-field-control">
              <Toggle
                id="comicvine-cache-enabled"
                checked={settings.comicvine_cache_enabled}
                onChange={(checked) => updateSetting('comicvine_cache_enabled', checked)}
              />
            </div>
          </div>
        </div>
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

