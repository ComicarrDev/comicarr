import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { apiGet, apiPost, apiPut, apiDelete, ApiClientError } from "../api/client";
import Toggle from "../components/Toggle";
import "./SettingsPage.css";
import "./MediaManagementSettingsPage.css";
import "./EditLibraryPage.css";

interface Library {
  id: string;
  name: string;
  library_root: string;
  default: boolean;
  enabled: boolean;
  settings: Record<string, unknown>;
  created_at: number;
  updated_at: number;
  volume_count: number;
}

interface IncludePath {
  id: string;
  library_id: string;
  path: string;
  enabled: boolean;
  created_at: number;
  updated_at: number;
}

interface IncludePathListResponse {
  include_paths: IncludePath[];
}

interface RootFolder {
  id: string;
  folder: string;
}

interface RootFolderResponse {
  root_folders: RootFolder[];
}

interface DirectoryEntry {
  name: string;
  path: string;
  readable: boolean;
  is_symlink: boolean;
}

interface DirectoryBrowseResponse {
  path: string;
  parent: string | null;
  entries: DirectoryEntry[];
}

export default function EditLibraryPage() {
  const { libraryId } = useParams<{ libraryId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [library, setLibrary] = useState<Library | null>(null);
  const [includePaths, setIncludePaths] = useState<IncludePath[]>([]);
  const [rootFolders, setRootFolders] = useState<RootFolder[]>([]);
  
  // Form state
  const [name, setName] = useState("");
  const [libraryRoot, setLibraryRoot] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [enabled, setEnabled] = useState(true);
  
  // Track original values for change detection
  const [originalName, setOriginalName] = useState("");
  const [originalLibraryRoot, setOriginalLibraryRoot] = useState("");
  const [originalIsDefault, setOriginalIsDefault] = useState(false);
  const [originalEnabled, setOriginalEnabled] = useState(true);
  
  // Include path form state
  const [addPath, setAddPath] = useState("");
  const [addingPath, setAddingPath] = useState(false);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [browserPath, setBrowserPath] = useState<string | null>(null);
  const [browserParent, setBrowserParent] = useState<string | null>(null);
  const [browserEntries, setBrowserEntries] = useState<DirectoryEntry[]>([]);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  useEffect(() => {
    if (libraryId) {
      loadLibrary();
      loadIncludePaths();
      loadRootFolders();
    }
  }, [libraryId]);

  async function loadLibrary() {
    if (!libraryId) return;
    try {
      setLoading(true);
      const data = await apiGet<Library>(`/libraries/${libraryId}`);
      setLibrary(data);
      setName(data.name);
      setLibraryRoot(data.library_root);
      setIsDefault(data.default);
      setEnabled(data.enabled);
      // Store original values for change detection
      setOriginalName(data.name);
      setOriginalLibraryRoot(data.library_root);
      setOriginalIsDefault(data.default);
      setOriginalEnabled(data.enabled);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to load library";
      toast.error(message);
      navigate("/library");
    } finally {
      setLoading(false);
    }
  }

  async function loadIncludePaths() {
    if (!libraryId) return;
    try {
      const data = await apiGet<IncludePathListResponse>(`/libraries/${libraryId}/include-paths`);
      setIncludePaths(data.include_paths ?? []);
    } catch (err) {
      console.warn("Failed to load include paths:", err);
      setIncludePaths([]);
    }
  }

  async function loadRootFolders() {
    try {
      const data = await apiGet<RootFolderResponse>("/media/root-folders");
      setRootFolders(data.root_folders ?? []);
    } catch (err) {
      console.warn("Failed to load root folders:", err);
      setRootFolders([]);
    }
  }

  async function loadBrowserPath(path?: string | null) {
    setBrowserLoading(true);
    setBrowserError(null);
    try {
      const endpoint = path ? `/media/browse?path=${encodeURIComponent(path)}` : "/media/browse";
      const data = await apiGet<DirectoryBrowseResponse>(endpoint);
      setBrowserPath(data.path);
      setBrowserParent(data.parent);
      setBrowserEntries(data.entries);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to browse directory";
      setBrowserError(message);
      setBrowserEntries([]);
    } finally {
      setBrowserLoading(false);
    }
  }

  function openFolderBrowser() {
    setBrowserOpen(true);
    const initialPath = addPath && addPath.trim().length > 0 ? addPath : libraryRoot;
    void loadBrowserPath(initialPath);
  }

  function closeFolderBrowser() {
    setBrowserOpen(false);
    setBrowserError(null);
    setBrowserEntries([]);
  }

  function applySelectedFolder() {
    if (browserPath) {
      setAddPath(browserPath);
    }
    closeFolderBrowser();
  }

  function navigateToEntry(entryPath: string) {
    void loadBrowserPath(entryPath);
  }

  async function handleSaveLibrary(e: FormEvent) {
    e.preventDefault();
    if (!libraryId) return;

    setSaving(true);
    try {
      await apiPut(`/libraries/${libraryId}`, {
        name: name.trim(),
        library_root: libraryRoot.trim(),
        default: isDefault,
        enabled: enabled,
      });
      toast.success("Library updated successfully");
      await loadLibrary();
      // Reset original values after successful save
      setOriginalName(name.trim());
      setOriginalLibraryRoot(libraryRoot.trim());
      setOriginalIsDefault(isDefault);
      setOriginalEnabled(enabled);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to update library";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  async function handleAddIncludePath(e: FormEvent) {
    e.preventDefault();
    if (!libraryId || !addPath.trim()) return;

    setAddingPath(true);
    try {
      await apiPost(`/libraries/${libraryId}/include-paths`, {
        library_id: libraryId,
        path: addPath.trim(),
        enabled: true,
      });
      toast.success("Include path added");
      setAddPath("");
      await loadIncludePaths();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to add include path";
      toast.error(message);
    } finally {
      setAddingPath(false);
    }
  }

  async function handleDeleteIncludePath(includePathId: string, path: string) {
    if (!confirm(`Remove include path "${path}"?`)) {
      return;
    }

    try {
      await apiDelete(`/include-paths/${includePathId}`);
      toast.success("Include path removed");
      await loadIncludePaths();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to remove include path";
      toast.error(message);
    }
  }

  async function handleToggleIncludePath(includePath: IncludePath) {
    try {
      await apiPut(`/include-paths/${includePath.id}`, {
        enabled: !includePath.enabled,
      });
      toast.success(`Include path ${includePath.enabled ? "disabled" : "enabled"}`);
      await loadIncludePaths();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to update include path";
      toast.error(message);
    }
  }

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <p>Loading library…</p>
        </div>
      </div>
    );
  }

  if (!library) {
    return null;
  }

  // Check if form has changes
  const hasChanges =
    name.trim() !== originalName ||
    libraryRoot.trim() !== originalLibraryRoot ||
    isDefault !== originalIsDefault ||
    enabled !== originalEnabled;

  return (
    <div className="settings-page edit-library-page">
      <div className="settings-header">
        <button
          type="button"
          className="secondary"
          onClick={() => navigate("/library")}
        >
          Back to Libraries
        </button>
      </div>

      <div className="edit-library-page__content">
        {/* Library Settings Form */}
        <section className="card settings-section">
          <h2>Library Settings</h2>
          <form className="library-form" onSubmit={handleSaveLibrary}>
            <div className="form-field">
              <label htmlFor="library-name">
                Library Name <span className="required">*</span>
              </label>
              <input
                id="library-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                disabled={saving}
              />
            </div>

            <div className="form-field">
              <label htmlFor="library-root">
                Library Root Path <span className="required">*</span>
              </label>
              {rootFolders.length > 0 ? (
                <select
                  id="library-root"
                  value={libraryRoot}
                  onChange={(e) => setLibraryRoot(e.target.value)}
                  required
                  disabled={saving}
                >
                  {rootFolders.map((folder) => (
                    <option key={folder.id} value={folder.folder}>
                      {folder.folder}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="library-root"
                  type="text"
                  value={libraryRoot}
                  onChange={(e) => setLibraryRoot(e.target.value)}
                  required
                  disabled={saving}
                />
              )}
              <p className="form-field-help">
                The base directory where files for this library will be organized
              </p>
            </div>

            <div className="settings-field">
              <Toggle
                id="library-default"
                checked={isDefault}
                onChange={setIsDefault}
                disabled={saving}
                label="Set as default library"
              />
            </div>

            <div className="settings-field">
              <Toggle
                id="library-enabled"
                checked={enabled}
                onChange={setEnabled}
                disabled={saving}
                label="Enable library"
              />
            </div>

            <div className="form-actions">
              <button type="submit" className="primary" disabled={saving || !hasChanges}>
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </form>
        </section>

        {/* Include Paths Section */}
        <section className="card settings-section">
          <h2>Include Paths</h2>
          <p className="settings-section-description">
            {includePaths.length === 0
              ? "No include paths configured. The library will manage all files under the library root path."
              : "Include paths limit the library scope to specific folders. When include paths are configured, only these paths will be scanned and managed."}
          </p>

          <form className="root-folder-add" onSubmit={handleAddIncludePath}>
            <label htmlFor="include-path">Add include path</label>
            <div className="root-folder-add__controls">
              <input
                id="include-path"
                type="text"
                placeholder="/comics/DC"
                value={addPath}
                onChange={(e) => setAddPath(e.target.value)}
                disabled={addingPath}
              />
              <button
                type="button"
                className="secondary"
                onClick={openFolderBrowser}
                disabled={addingPath}
              >
                Browse…
              </button>
              <button type="submit" className="primary" disabled={addingPath || !addPath.trim()}>
                {addingPath ? "Adding..." : "Add"}
              </button>
            </div>
          </form>

          {includePaths.length > 0 && (
            <div className="root-folder-table-wrapper">
              <table className="root-folder-table">
                <thead>
                  <tr>
                    <th>Path</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {includePaths.map((ip) => (
                    <tr key={ip.id}>
                      <td>
                        <code>{ip.path}</code>
                      </td>
                      <td>
                        {ip.enabled ? (
                          <span className="status-badge status-badge--enabled">Enabled</span>
                        ) : (
                          <span className="status-badge status-badge--disabled">Disabled</span>
                        )}
                      </td>
                      <td className="action-column">
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleToggleIncludePath(ip)}
                        >
                          {ip.enabled ? "Disable" : "Enable"}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleDeleteIncludePath(ip.id, ip.path)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* Folder Browser Modal */}
      {browserOpen ? (
        <div className="folder-browser" role="dialog" aria-modal="true">
          <div className="folder-browser__backdrop" onClick={closeFolderBrowser} />
          <div className="folder-browser__dialog">
            <header className="folder-browser__header">
              <h2>Select Folder</h2>
              <button type="button" className="secondary" onClick={closeFolderBrowser}>
                Close
              </button>
            </header>
            <div className="folder-browser__body">
              <div className="folder-browser__path">
                <label>Current path</label>
                <p>{browserPath ?? "…"}</p>
              </div>
              <div className="folder-browser__controls">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => browserParent && navigateToEntry(browserParent)}
                  disabled={!browserParent || browserLoading}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={applySelectedFolder}
                  disabled={!browserPath || browserLoading}
                >
                  Use this folder
                </button>
              </div>
              {browserError ? <p className="status error">{browserError}</p> : null}
              <div className="folder-browser__entries">
                {browserLoading ? (
                  <p className="muted">Loading directories…</p>
                ) : browserEntries.length === 0 ? (
                  <p className="muted">No readable subdirectories.</p>
                ) : (
                  <ul>
                    {browserEntries.map((entry) => (
                      <li key={entry.path}>
                        <button
                          type="button"
                          className="secondary"
                          disabled={!entry.readable || browserLoading}
                          onClick={() => navigateToEntry(entry.path)}
                        >
                          {entry.name}
                          {!entry.readable ? " (unreadable)" : entry.is_symlink ? " (symlink)" : ""}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

