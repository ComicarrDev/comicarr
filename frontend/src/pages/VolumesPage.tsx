import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "./VolumesPage.css";
import { buildApiUrl } from "../api/client";

export type LibraryVolume = {
  id: string;
  library_id: string;
  comicvine_id: number | null;
  title: string;
  year?: number | null;
  publisher?: string | null;
  publisher_country?: string | null;
  description?: string | null;
  site_url?: string | null;
  count_of_issues?: number | null;
  image?: string | null;
  monitored: boolean;
  monitor_new_issues: boolean;
  folder_name?: string | null;
  custom_folder: boolean;
  date_last_updated?: string | null;
  is_ended: boolean;
  created_at: number;
  updated_at: number;
  progress: {
    downloaded: number;
    total: number;
  };
};

type ViewMode = "table" | "grid-small" | "grid-big";

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString();
}

function truncateText(text: string, maxLength: number): string {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength).trim() + "...";
}

function stripHtml(text?: string | null): string {
  if (!text) {
    return "";
  }
  return text.replace(/<[^>]+>/g, "").trim();
}

function VolumesPage() {
  const [allVolumes, setAllVolumes] = useState<LibraryVolume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("grid-big");

  useEffect(() => {
    let ignore = false;

    async function loadVolumes() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(buildApiUrl("/api/volumes"), { credentials: "include" });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const payload = (await response.json()) as { volumes: LibraryVolume[] };
        if (!ignore) {
          setAllVolumes(payload.volumes ?? []);
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    void loadVolumes();
    return () => {
      ignore = true;
    };
  }, []);

  const volumes = allVolumes;

  return (
    <div className="volumes-page">
      <div className="volumes-page__header">
        <Link to="/volumes/add" className="button primary">
          Add Volume
        </Link>
      </div>

      <div className="volumes-page__view-toggle">
        <button
          type="button"
          className={`secondary ${viewMode === "table" ? "active" : ""}`}
          onClick={() => setViewMode("table")}
          title="Table view"
          aria-label="Table view"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="currentColor"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M0 0h6v6H0V0zm7 0h11v6H7V0zM0 7h6v6H0V7zm7 0h11v6H7V7zM0 14h6v4H0v-4zm7 0h11v4H7v-4z" />
          </svg>
        </button>
        <button
          type="button"
          className={`secondary ${viewMode === "grid-small" ? "active" : ""}`}
          onClick={() => setViewMode("grid-small")}
          title="Grid small view"
          aria-label="Grid small view"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="currentColor"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M0 0h4v4H0V0zm5 0h4v4H5V0zm5 0h4v4h-4V0zm5 0h4v4h-4V0zM0 5h4v4H0V5zm5 0h4v4H5V5zm5 0h4v4h-4V5zm5 0h4v4h-4V5zM0 10h4v4H0v-4zm5 0h4v4H5v-4zm5 0h4v4h-4v-4zm5 0h4v4h-4v-4zM0 15h4v3H0v-3zm5 0h4v3H5v-3zm5 0h4v3h-4v-3zm5 0h4v3h-4v-3z" />
          </svg>
        </button>
        <button
          type="button"
          className={`secondary ${viewMode === "grid-big" ? "active" : ""}`}
          onClick={() => setViewMode("grid-big")}
          title="Grid big view"
          aria-label="Grid big view"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="currentColor"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M0 0h8v8H0V0zm10 0h8v8h-8V0zM0 10h8v8H0v-8zm10 0h8v8h-8v-8z" />
          </svg>
        </button>
      </div>

      {loading ? (
        <div className="volumes-page__state">
          <p className="muted">Loading volumes…</p>
        </div>
      ) : error ? (
        <div className="volumes-page__state">
          <p className="status error">{error}</p>
        </div>
      ) : volumes.length === 0 ? (
        <div className="volumes-page__state">
          <p className="muted">No volumes have been added yet.</p>
          <p>
            <Link to="/volumes/add" className="link">
              Add your first volume
            </Link>
          </p>
        </div>
      ) : (
        <div className="volumes-page__content-wrapper">
          <div className="volumes-page__main">
            {viewMode === "table" ? (
              <div className="volumes-table-wrapper">
                <table className="volumes-table">
                  <thead>
                    <tr>
                      <th>Volume Title</th>
                      <th>Year</th>
                      <th>ComicVine ID</th>
                      <th>Progress</th>
                      <th>Monitored</th>
                    </tr>
                  </thead>
                  <tbody>
                    {volumes.map((volume) => {
                      const progress = volume.progress || { downloaded: 0, total: 0 };
                      return (
                        <tr key={volume.id}>
                          <td>
                            <Link to={`/volumes/${volume.id}`} className="volumes-table__link">
                              {volume.title}
                            </Link>
                            {volume.is_ended ? (
                              <span className="volumes-table__badge volumes-table__badge--ended" title="Series has ended and all issues are downloaded">
                                Ended
                              </span>
                            ) : null}
                          </td>
                          <td>{volume.year || "—"}</td>
                          <td>{volume.comicvine_id || "—"}</td>
                          <td>
                            {progress.downloaded}/{progress.total}
                          </td>
                          <td>
                            <span className={`volumes-table__badge ${volume.monitored ? "monitored" : "unmonitored"}`}>
                              {volume.monitored ? "Yes" : "No"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : viewMode === "grid-small" ? (
              <div className="volumes-collection volumes-collection--small">
                {volumes.map((volume) => {
                  const progress = volume.progress || { downloaded: 0, total: 0 };
                  return (
                    <Link key={volume.id} to={`/volumes/${volume.id}`} className="volumes-card volumes-card--small">
                      <div className="volumes-card__cover volumes-card__cover--small">
                        {volume.image ? (
                          <img src={volume.image} alt={`${volume.title} cover`} />
                        ) : (
                          <div className="volumes-card__placeholder">No cover</div>
                        )}
                      </div>
                      <div className="volumes-card__content volumes-card__content--small">
                        <h3 className="volumes-card__title--small">{volume.title}</h3>
                        <div className="volumes-card__progress--small">
                          <div className="volumes-card__progress-bar">
                            <div
                              className="volumes-card__progress-fill"
                              style={{
                                width: `${progress.total > 0 ? (progress.downloaded / progress.total) * 100 : 0}%`,
                              }}
                            />
                          </div>
                          <span className="volumes-card__progress-text">
                            {progress.downloaded}/{progress.total}
                          </span>
                        </div>
                        <div className="volumes-card__tags--small">
                          {volume.site_url ? (
                            <a
                              href={volume.site_url}
                              target="_blank"
                              rel="noreferrer"
                              className="volumes-card__tag volumes-card__tag--comicvine"
                              onClick={(e) => e.stopPropagation()}
                            >
                              ComicVine
                            </a>
                          ) : null}
                          <span
                            className={`volumes-card__tag ${volume.monitored ? "volumes-card__tag--monitored" : "volumes-card__tag--unmonitored"}`}
                          >
                            {volume.monitored ? "Monitored" : "Unmonitored"}
                          </span>
                          {volume.is_ended ? (
                            <span className="volumes-card__tag volumes-card__tag--ended" title="Series has ended and all issues are downloaded">
                              Ended
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="volumes-collection volumes-collection--big">
                {volumes.map((volume) => {
                  const progress = volume.progress || { downloaded: 0, total: 0 };
                  const description = truncateText(stripHtml(volume.description || ""), 250);
                  const created = formatDate(volume.created_at);
                  return (
                    <Link key={volume.id} to={`/volumes/${volume.id}`} className="volumes-card volumes-card--big">
                      <div className="volumes-card__cover volumes-card__cover--big">
                        {volume.image ? (
                          <img src={volume.image} alt={`${volume.title} cover`} />
                        ) : (
                          <div className="volumes-card__placeholder">No cover</div>
                        )}
                      </div>
                      <div className="volumes-card__content volumes-card__content--big">
                        <h2 className="volumes-card__title--big">{volume.title}</h2>
                        <div className="volumes-card__tags--big">
                          {volume.publisher ? (
                            <span className="volumes-card__tag volumes-card__tag--publisher">{volume.publisher}</span>
                          ) : null}
                          {volume.year ? (
                            <span className="volumes-card__tag volumes-card__tag--year">{volume.year}</span>
                          ) : null}
                          <span className="volumes-card__tag volumes-card__tag--progress">
                            {progress.downloaded}/{progress.total}
                          </span>
                          {volume.site_url ? (
                            <a
                              href={volume.site_url}
                              target="_blank"
                              rel="noreferrer"
                              className="volumes-card__tag volumes-card__tag--comicvine"
                              onClick={(e) => e.stopPropagation()}
                            >
                              ComicVine
                            </a>
                          ) : null}
                          <span
                            className={`volumes-card__tag ${volume.monitored ? "volumes-card__tag--monitored" : "volumes-card__tag--unmonitored"}`}
                          >
                            {volume.monitored ? "Monitored" : "Unmonitored"}
                          </span>
                          {volume.is_ended ? (
                            <span className="volumes-card__tag volumes-card__tag--ended" title="Series has ended and all issues are downloaded">
                              Ended
                            </span>
                          ) : null}
                        </div>
                        {description ? (
                          <p className="volumes-card__description--big">{description}</p>
                        ) : null}
                        <div className="volumes-card__meta--big">
                          <span className="volumes-card__meta-item">Added: {created}</span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default VolumesPage;

