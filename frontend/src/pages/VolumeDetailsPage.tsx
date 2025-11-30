import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Trash2, BookOpen } from 'lucide-react';
import { toast } from 'sonner';
import { buildApiUrl, apiDelete, ApiClientError } from '../api/client';
import './VolumeDetailsPage.css';

export type VolumeDetails = {
  id: string;
  library_id: string;
  comicvine_id: number | null;
  title: string;
  year: number | null;
  publisher: string | null;
  publisher_country: string | null;
  description: string | null;
  site_url: string | null;
  count_of_issues: number | null;
  image: string | null;
  monitored: boolean;
  monitor_new_issues: boolean;
  folder_name: string | null;
  custom_folder: boolean;
  date_last_updated: string | null;
  is_ended: boolean;
  created_at: number;
  updated_at: number;
  progress: {
    downloaded: number;
    total: number;
  };
};

export type IssueSummary = {
  id: string;
  title?: string | null;
  number?: string | null;
  release_date?: string | null;
  monitored?: boolean | null;
  site_url?: string | null;
  image?: string | null;
  status?: string | null;
  file_path?: string | null;
  file_size?: number | null;
};

export default function VolumeDetailsPage() {
  const { volumeId } = useParams<{ volumeId: string }>();
  const navigate = useNavigate();
  const [volume, setVolume] = useState<VolumeDetails | null>(null);
  const [issues, setIssues] = useState<IssueSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteFiles, setDeleteFiles] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [readingEnabled, setReadingEnabled] = useState(true);

  useEffect(() => {
    if (!volumeId) {
      setError('Volume ID is required');
      setLoading(false);
      return;
    }

    const fetchVolume = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(buildApiUrl(`/api/volumes/${volumeId}`), {
          credentials: 'include',
        });

        if (!response.ok) {
          if (response.status === 404) {
            setError('Volume not found');
          } else {
            setError(`Failed to load volume: ${response.statusText}`);
          }
          setLoading(false);
          return;
        }

        const payload = await response.json() as { volume: VolumeDetails; issues: IssueSummary[] };
        setVolume(payload.volume);
        setIssues(payload.issues ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load volume');
      } finally {
        setLoading(false);
      }
    };

    fetchVolume();
  }, [volumeId]);

  // Fetch reading settings
  useEffect(() => {
    const fetchReadingSettings = async () => {
      try {
        const response = await fetch(buildApiUrl('/api/settings/reading'), {
          credentials: 'include',
        });
        if (response.ok) {
          const data = await response.json() as { settings: { enabled: boolean } };
          setReadingEnabled(data.settings.enabled ?? true);
        }
      } catch (err) {
        // Default to enabled if fetch fails
        console.warn('Failed to fetch reading settings:', err);
      }
    };

    fetchReadingSettings();
  }, []);

  function handleDeleteClick() {
    setDeleteFiles(false);
    setDeleteModalOpen(true);
  }

  function handleDeleteCancel() {
    setDeleteModalOpen(false);
    setDeleteFiles(false);
  }

  async function handleDeleteConfirm() {
    if (!volume || !volumeId) {
      return;
    }

    try {
      setDeleting(true);
      const url = `/volumes/${volumeId}${deleteFiles ? '?delete_files=true' : ''}`;
      await apiDelete(url);
      toast.success(`Volume "${volume.title}" deleted`);
      navigate('/volumes');
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : 'Failed to delete volume';
      toast.error(message);
      setDeleting(false);
      setDeleteModalOpen(false);
    }
  }

  if (loading) {
    return (
      <div className="volume-details-page">
        <div className="volume-details-loading">
          <p>Loading volume details…</p>
        </div>
      </div>
    );
  }

  if (error || !volume) {
    return (
      <div className="volume-details-page">
        <div className="volume-details-error">
          <p>{error || 'Volume not found'}</p>
          <Link to="/volumes" className="button primary">
            Back to Volumes
          </Link>
        </div>
      </div>
    );
  }

  const progressPercentage =
    volume.progress.total > 0
      ? Math.round((volume.progress.downloaded / volume.progress.total) * 100)
      : 0;

  return (
    <div className="volume-details-page">
      <div className="volume-details-header">
        <Link to="/volumes" className="volume-details-back">
          ← Back to Volumes
        </Link>
        <button
          type="button"
          className="volume-details-delete"
          onClick={handleDeleteClick}
          disabled={deleting}
          title="Delete volume"
        >
          <Trash2 size={18} />
          Delete
        </button>
      </div>

      <div className="volume-details-content">
        <div className="volume-details-main">
          <div className="volume-details-cover">
            {volume.image ? (
              <img src={volume.image} alt={volume.title} />
            ) : (
              <div className="volume-details-cover-placeholder">
                <span>No Cover</span>
              </div>
            )}
          </div>

          <div className="volume-details-info">
            <h1>{volume.title}</h1>
            <div className="volume-details-meta">
              {volume.publisher && (
                <span className="volume-details-meta-item">
                  <strong>Publisher:</strong> {volume.publisher}
                  {volume.publisher_country && ` (${volume.publisher_country})`}
                </span>
              )}
              {volume.year && (
                <span className="volume-details-meta-item">
                  <strong>Year:</strong> {volume.year}
                </span>
              )}
              {volume.count_of_issues !== null && (
                <span className="volume-details-meta-item">
                  <strong>Issues:</strong> {volume.count_of_issues}
                </span>
              )}
              {volume.is_ended && (
                <span className="volume-details-meta-item">
                  <strong>Status:</strong> Ended
                </span>
              )}
            </div>

            {volume.description && (
              <div className="volume-details-description">
                <h2>Description</h2>
                <p>{volume.description}</p>
              </div>
            )}

            <div className="volume-details-progress">
              <h2>Progress</h2>
              <div className="volume-details-progress-bar">
                <div
                  className="volume-details-progress-fill"
                  style={{ width: `${progressPercentage}%` }}
                />
              </div>
              <p className="volume-details-progress-text">
                {volume.progress.downloaded} of {volume.progress.total} issues downloaded ({progressPercentage}%)
              </p>
            </div>

            <div className="volume-details-issues">
              <h2>Issues</h2>
              {issues.length === 0 ? (
                <p className="volume-details-empty">No issues imported yet.</p>
              ) : (
                <ul className="volume-details-issues-list">
                  {issues.map((issue) => {
                    const statusLabel = issue.status === 'ready' || issue.status === 'processed' 
                      ? 'Downloaded' 
                      : issue.status === 'wanted' 
                      ? 'Wanted' 
                      : 'Missing';
                    const statusClass = issue.status === 'ready' || issue.status === 'processed'
                      ? 'ready'
                      : issue.status === 'wanted'
                      ? 'wanted'
                      : 'missing';

                    return (
                      <li key={issue.id} className="volume-details-issue-item">
                        <div className="volume-details-issue-info">
                          <strong>#{issue.number ?? '?'}</strong> {issue.title ?? 'Untitled'}
                        </div>
                        <div className="volume-details-issue-status">
                          <span className={`issue-status issue-status--${statusClass}`}>
                            {statusLabel}
                          </span>
                          {readingEnabled && (issue.status === 'ready' || issue.status === 'processed') && issue.file_path && (
                            <Link
                              to={`/reading/${issue.id}`}
                              className="button primary"
                              style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem', fontSize: '0.875rem', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                            >
                              <BookOpen size={14} />
                              Read
                            </Link>
                          )}
                          {issue.file_path && (
                            <span className="volume-details-issue-file" title={issue.file_path}>
                              {issue.file_path.split('/').pop()}
                            </span>
                          )}
                          {issue.release_date && (
                            <span className="volume-details-issue-date">
                              {new Date(issue.release_date).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="volume-details-sidebar">
          <div className="volume-details-card">
            <h3>Details</h3>
            <dl className="volume-details-details-list">
              <dt>ComicVine ID</dt>
              <dd>{volume.comicvine_id || '—'}</dd>

              <dt>Library ID</dt>
              <dd>{volume.library_id}</dd>

              <dt>Folder Name</dt>
              <dd>{volume.folder_name || '—'}</dd>

              <dt>Monitored</dt>
              <dd>{volume.monitored ? 'Yes' : 'No'}</dd>

              <dt>Monitor New Issues</dt>
              <dd>{volume.monitor_new_issues ? 'Yes' : 'No'}</dd>

              {volume.site_url && (
                <>
                  <dt>ComicVine</dt>
                  <dd>
                    <a
                      href={volume.site_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="volume-details-link"
                    >
                      View on ComicVine
                    </a>
                  </dd>
                </>
              )}
            </dl>
          </div>
        </div>
      </div>

      {deleteModalOpen ? (
        <div
          className="volume-delete-modal__backdrop"
          onClick={handleDeleteCancel}
          role="presentation"
        >
          <div
            className="volume-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-volume-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="volume-delete-modal__close"
              onClick={handleDeleteCancel}
              aria-label="Close"
              disabled={deleting}
            >
              ×
            </button>
            <header className="volume-delete-modal__header">
              <h2 id="delete-volume-modal-title">Delete Volume</h2>
              <p className="muted">Are you sure you want to delete "{volume.title}"?</p>
              <p className="status status--warning">
                This will permanently delete the volume and all {issues.length} associated issues from the database.
              </p>
            </header>
            <div className="volume-delete-modal__body">
              <label className="volume-delete-modal__checkbox">
                <input
                  type="checkbox"
                  checked={deleteFiles}
                  onChange={(e) => setDeleteFiles(e.target.checked)}
                  disabled={deleting}
                />
                <span>Also delete all files from disk</span>
              </label>
              {deleteFiles && (
                <p className="status status--error">
                  Warning: This will permanently delete the folder and all files for this volume from disk. This action cannot be undone.
                </p>
              )}
            </div>
            <footer className="volume-delete-modal__actions">
              <button
                type="button"
                className="secondary"
                onClick={handleDeleteCancel}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger"
                onClick={handleDeleteConfirm}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete volume'}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}

