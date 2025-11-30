import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { buildApiUrl } from "../api/client";
import "./HistoryPage.css";

type ActivityTask = {
  id: string;
  type: string;
  volume_id?: string | null;
  volume_title?: string | null;
  issue_id?: string | null;
  issue_number?: string | null;
  issue_file_path?: string | null;
  status: string;
  source?: string;
  source_path?: string | null;
  source_filename?: string | null;
  file_filename?: string | null;
  file_path?: string | null;
  file_size?: number | null;
  updated_at: number;
  created_at: number;
  error?: string | null;
};

function formatBytes(bytes?: number | null): string {
  if (!bytes || Number.isNaN(bytes)) {
    return "—";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  const formatted = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${formatted} ${units[index]}`;
}

function formatTimestamp(seconds?: number | null): string {
  if (!seconds || Number.isNaN(seconds)) {
    return "—";
  }
  return new Date(seconds * 1000).toLocaleString();
}

function formatStatus(status: string): { label: string; className: string } {
  switch (status.toLowerCase()) {
    case "completed":
      return { label: "Completed", className: "download-status--completed" };
    case "failed":
      return { label: "Failed", className: "download-status--failed" };
    case "queued":
      return { label: "Queued", className: "download-status--queued" };
    case "downloading":
      return { label: "Downloading", className: "download-status--active" };
    default:
      return { label: status, className: "download-status--queued" };
  }
}

export default function HistoryPage() {
  const [tasks, setTasks] = useState<ActivityTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      try {
        const params = new URLSearchParams();
        if (typeFilter !== "all") {
          params.set("type", typeFilter);
        }
        if (statusFilter !== "all") {
          params.set("status", statusFilter);
        }
        params.set("limit", "100");
        const url = buildApiUrl(`/api/activity?${params.toString()}`);
        const response = await fetch(url, { credentials: "include" });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const payload = (await response.json()) as { tasks?: ActivityTask[] };
        if (!ignore) {
          setTasks(payload.tasks ?? []);
          setError(null);
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
    };

    void load();
    return () => {
      ignore = true;
    };
  }, [typeFilter, statusFilter]);

  return (
    <div className="history-page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem" }}>
        <h1>History</h1>
        <div className="history-page__filters">
          <div>
            <label htmlFor="type-filter">Filter by type:</label>
            <select
              id="type-filter"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="all">All Types</option>
              <option value="download">Downloads</option>
              <option value="metatag_issue">Metatag Issue</option>
              <option value="metatag_volume">Metatag Volume</option>
              <option value="rename_file">Rename File</option>
              <option value="convert_file">Convert File</option>
            </select>
          </div>
          <div>
            <label htmlFor="status-filter">Filter by status:</label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Status</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="app__loading">
          <p>Loading activity…</p>
        </div>
      ) : null}

      {error ? <p className="status error">{error}</p> : null}

      {!loading && tasks.length === 0 ? (
        <p className="muted">No activity yet.</p>
      ) : (
        <ul className="history-list">
          {tasks.map((task) => {
            const info = formatStatus(task.status);
            return (
              <li key={task.id}>
                <div className="history-list__row">
                  <div className="history-list__title">
                    <strong>
                      {task.type === "download" && task.issue_number
                        ? `Issue ${task.issue_number}`
                        : task.type === "metatag_issue" && task.issue_number
                        ? `Metatag Issue ${task.issue_number}`
                        : task.type === "metatag_volume"
                        ? "Metatag Volume"
                        : task.type === "rename_file" && task.issue_number
                        ? `Rename Issue ${task.issue_number}`
                        : task.type === "convert_file" && task.issue_number
                        ? `Convert Issue ${task.issue_number}`
                        : `${task.type} task`}
                    </strong>
                    <span className={`download-status ${info.className}`}>{info.label}</span>
                  </div>
                  <div className="history-list__meta">
                    <span>Type: {task.type}</span>
                    {task.volume_id ? (
                      <span>
                        Volume:{" "}
                        {task.volume_title ? (
                          <Link to={`/volumes/${task.volume_id}`} style={{ color: "var(--primary-color)", textDecoration: "underline" }}>
                            {task.volume_title}
                          </Link>
                        ) : (
                          task.volume_id
                        )}
                      </span>
                    ) : null}
                    {task.issue_id && task.issue_number ? (
                      <span>
                        Issue:{" "}
                        <Link to={`/volumes/${task.volume_id}/issues/${task.issue_id}`} style={{ color: "var(--primary-color)", textDecoration: "underline" }}>
                          {task.issue_number}
                        </Link>
                      </span>
                    ) : null}
                    {(task.source_filename || task.file_filename) ? (
                      <span>File: {task.source_filename || task.file_filename}</span>
                    ) : null}
                    <span>Completed: {formatTimestamp(task.updated_at)}</span>
                    {task.file_size ? <span>Size: {formatBytes(task.file_size)}</span> : null}
                  </div>
                  {task.error ? <p className="history-list__error">Error: {task.error}</p> : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}



