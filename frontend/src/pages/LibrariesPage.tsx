import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { apiGet, apiDelete, ApiClientError } from "../api/client";
import "./LibrariesPage.css";

export type Library = {
  id: string;
  name: string;
  library_root: string;
  default: boolean;
  enabled: boolean;
  settings: Record<string, unknown>;
  created_at: number;
  updated_at: number;
  volume_count: number;
};

interface LibraryListResponse {
  libraries: Library[];
}

// @ts-expect-error - unused function, may be used in future
function _formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString();
}

export default function LibrariesPage() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadLibraries();
  }, []);

  async function loadLibraries() {
    try {
      setLoading(true);
      setError(null);
      const data = await apiGet<LibraryListResponse>("/libraries");
      setLibraries(data.libraries ?? []);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to load libraries";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(libraryId: string, libraryName: string) {
    if (!confirm(`Are you sure you want to delete "${libraryName}"? This action cannot be undone.`)) {
      return;
    }

    try {
      await apiDelete(`/libraries/${libraryId}`);
      toast.success(`Library "${libraryName}" deleted`);
      await loadLibraries();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to delete library";
      toast.error(message);
    }
  }

  if (loading) {
    return (
      <div className="libraries-page">
        <div className="libraries-page__loading">
          <p>Loading libraries…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="libraries-page">
        <div className="libraries-page__error">
          <p>Error: {error}</p>
          <button onClick={loadLibraries}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="libraries-page">
      <div className="settings-header">
        <p>
          Manage your libraries and configure include paths for organizing volumes.
        </p>
      </div>
      <div className="libraries-page__header">
        <Link to="/library/add" className="button primary">
          Add Library
        </Link>
      </div>
      <div className="libraries-page__content">
        {libraries.length === 0 ? (
          <div className="libraries-page__empty">
            <p>No libraries configured yet.</p>
            <Link to="/library/add" className="button primary">
              Create your first library
            </Link>
          </div>
        ) : (
          <div className="libraries-table-wrapper">
            <table className="libraries-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Root Path</th>
                  <th>Volumes</th>
                  <th>Status</th>
                  <th>Default</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {libraries.map((library) => (
                  <tr key={library.id}>
                    <td>
                      <strong>{library.name}</strong>
                    </td>
                    <td>
                      <code>{library.library_root}</code>
                    </td>
                    <td className="number-column">{library.volume_count}</td>
                    <td>
                      {library.enabled ? (
                        <span className="status-badge status-badge--enabled">Enabled</span>
                      ) : (
                        <span className="status-badge status-badge--disabled">Disabled</span>
                      )}
                    </td>
                    <td>
                      {library.default && <span className="default-badge">Default</span>}
                    </td>
                    <td className="action-column">
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => navigate(`/library/${library.id}`)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => handleDelete(library.id, library.name)}
                        disabled={library.volume_count > 0}
                        title={library.volume_count > 0 ? "Cannot delete library with volumes" : "Delete library"}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

