import { FormEvent, useEffect, useState, useMemo, useRef } from "react";
import { toast } from "sonner";
import { apiGet, apiPost, apiPut, apiDelete, ApiClientError } from "../api/client";
import Toggle from "../components/Toggle";
import PlaceholderPickerModal from "../components/PlaceholderPickerModal";
import "./SettingsPage.css";
import "./MediaManagementSettingsPage.css";

interface RootFolder {
  id: string;
  folder: string;
  stats?: {
    free_bytes?: number;
    used_bytes?: number;
    total_bytes?: number;
  };
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

type BrowserTarget =
  | { type: "new" }
  | { type: "existing"; id: string };

interface MediaSettings {
  rename_downloaded_files: boolean;
  replace_illegal_characters: boolean;
  volume_folder_naming: string;
  file_naming: string;
  file_naming_empty: string;
  file_naming_special_version: string;
  file_naming_vai: string;
  long_special_version: boolean;
  create_empty_volume_folders: boolean;
  delete_empty_folders: boolean;
  unmonitor_deleted_issues: boolean;
  convert: boolean;
  extract_issue_ranges: boolean;
  format_preference: string[];
}

interface MediaSettingsResponse {
  settings: MediaSettings;
  format_options: string[];
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) {
    return "—";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export default function MediaManagementSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [renamingSaving, setRenamingSaving] = useState(false);
  const [namingSaving, setNamingSaving] = useState(false);
  const [conversionSaving, setConversionSaving] = useState(false);
  const [mediaSettings, setMediaSettings] = useState<MediaSettings | null>(null);
  const [formatOptions, setFormatOptions] = useState<string[]>([]);
  const [rootFolders, setRootFolders] = useState<RootFolder[]>([]);
  const [addFolderPath, setAddFolderPath] = useState("");
  const [rootBusy, setRootBusy] = useState(false);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [browserPath, setBrowserPath] = useState<string | null>(null);
  const [browserParent, setBrowserParent] = useState<string | null>(null);
  const [browserEntries, setBrowserEntries] = useState<DirectoryEntry[]>([]);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerField, setPickerField] = useState<keyof MediaSettings | null>(null);
  const [pickerInitialValue, setPickerInitialValue] = useState('');

  // Track initial state for change detection
  const renamingInitialRef = useRef<Partial<MediaSettings> | null>(null);
  const namingInitialRef = useRef<Partial<MediaSettings> | null>(null);
  const conversionInitialRef = useRef<Partial<MediaSettings> | null>(null);

  const ISSUE_TOKENS = useMemo(
    () => new Set(["issue", "issuenumber", "volume", "volumenumber"]),
    []
  );

  const ISSUE_TOKEN_PATTERN = useMemo(() => /\{([^{}:]+)(?::[^{}]+)?\}/g, []);

  const templateHasIssueToken = useMemo(() => {
    if (!mediaSettings) {
      return true;
    }
    const template = mediaSettings.file_naming ?? "";
    const matcher = template.matchAll(ISSUE_TOKEN_PATTERN);
    for (const match of matcher) {
      const raw = match[1]?.trim() ?? "";
      if (!raw) continue;
      const canonical = raw.toLowerCase().replace(/[^a-z0-9]/g, "");
      if (ISSUE_TOKENS.has(canonical)) {
        return true;
      }
    }
    return false;
  }, [ISSUE_TOKEN_PATTERN, ISSUE_TOKENS, mediaSettings]);

  const availableFormats = useMemo(() => {
    if (!mediaSettings) {
      return formatOptions;
    }
    const current = new Set(mediaSettings.format_preference);
    return formatOptions.filter((option) => !current.has(option));
  }, [formatOptions, mediaSettings]);

  useEffect(() => {
    loadMediaSettings();
    loadRootFolders();
  }, []);

  async function loadMediaSettings() {
    try {
      setLoading(true);
      const data = await apiGet<MediaSettingsResponse>("/settings/media-management");
      setMediaSettings(data.settings);
      setFormatOptions(data.format_options);
      
      // Set initial refs for change detection
      if (data.settings) {
        renamingInitialRef.current = {
          rename_downloaded_files: data.settings.rename_downloaded_files,
          replace_illegal_characters: data.settings.replace_illegal_characters,
          long_special_version: data.settings.long_special_version,
          create_empty_volume_folders: data.settings.create_empty_volume_folders,
          delete_empty_folders: data.settings.delete_empty_folders,
          unmonitor_deleted_issues: data.settings.unmonitor_deleted_issues,
        };
        namingInitialRef.current = {
          volume_folder_naming: data.settings.volume_folder_naming,
          file_naming: data.settings.file_naming,
          file_naming_empty: data.settings.file_naming_empty,
          file_naming_special_version: data.settings.file_naming_special_version,
          file_naming_vai: data.settings.file_naming_vai,
        };
        conversionInitialRef.current = {
          convert: data.settings.convert,
          extract_issue_ranges: data.settings.extract_issue_ranges,
          format_preference: [...data.settings.format_preference],
        };
      }
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to load media settings";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  // Change detection helpers
  const renamingHasChanges = renamingInitialRef.current && mediaSettings ? (
    mediaSettings.rename_downloaded_files !== renamingInitialRef.current.rename_downloaded_files ||
    mediaSettings.replace_illegal_characters !== renamingInitialRef.current.replace_illegal_characters ||
    mediaSettings.long_special_version !== renamingInitialRef.current.long_special_version ||
    mediaSettings.create_empty_volume_folders !== renamingInitialRef.current.create_empty_volume_folders ||
    mediaSettings.delete_empty_folders !== renamingInitialRef.current.delete_empty_folders ||
    mediaSettings.unmonitor_deleted_issues !== renamingInitialRef.current.unmonitor_deleted_issues
  ) : false;

  const namingHasChanges = namingInitialRef.current && mediaSettings ? (
    mediaSettings.volume_folder_naming !== namingInitialRef.current.volume_folder_naming ||
    mediaSettings.file_naming !== namingInitialRef.current.file_naming ||
    mediaSettings.file_naming_empty !== namingInitialRef.current.file_naming_empty ||
    mediaSettings.file_naming_special_version !== namingInitialRef.current.file_naming_special_version ||
    mediaSettings.file_naming_vai !== namingInitialRef.current.file_naming_vai
  ) : false;

  const conversionHasChanges = conversionInitialRef.current && mediaSettings ? (
    mediaSettings.convert !== conversionInitialRef.current.convert ||
    mediaSettings.extract_issue_ranges !== conversionInitialRef.current.extract_issue_ranges ||
    JSON.stringify(mediaSettings.format_preference) !== JSON.stringify(conversionInitialRef.current.format_preference)
  ) : false;

  async function loadRootFolders() {
    try {
      setLoading(true);
      const data = await apiGet<RootFolderResponse>("/media/root-folders");
      setRootFolders(data.root_folders);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to load root folders";
      toast.error(message);
    } finally {
      setLoading(false);
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

  function openFolderBrowser(target: BrowserTarget) {
    setBrowserTarget(target);
    setBrowserOpen(true);
    const initialPath =
      target.type === "existing"
        ? rootFolders.find((f) => f.id === target.id)?.folder
        : addFolderPath;
    const normalized = initialPath && initialPath.trim().length > 0 ? initialPath : null;
    void loadBrowserPath(normalized);
  }

  function closeFolderBrowser() {
    setBrowserOpen(false);
    setBrowserError(null);
    setBrowserEntries([]);
    setBrowserTarget(null);
  }

  function applySelectedFolder() {
    if (!browserTarget || !browserPath) {
      closeFolderBrowser();
      return;
    }
    if (browserTarget.type === "new") {
      setAddFolderPath(browserPath);
    } else {
      // Update existing folder
      handleUpdateRootFolder(browserTarget.id, browserPath);
    }
    closeFolderBrowser();
  }

  function navigateToEntry(entryPath: string) {
    void loadBrowserPath(entryPath);
  }

  async function handleAddRootFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!addFolderPath.trim()) return;
    setRootBusy(true);
    try {
      await apiPost("/media/root-folders", { folder: addFolderPath.trim() });
      setAddFolderPath("");
      toast.success("Root folder added");
      await loadRootFolders();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to add root folder";
      toast.error(message);
    } finally {
      setRootBusy(false);
    }
  }

  async function handleUpdateRootFolder(folderId: string, folderPath: string) {
    setRootBusy(true);
    try {
      await apiPut(`/media/root-folders/${folderId}`, { folder: folderPath });
      toast.success("Root folder updated");
      await loadRootFolders();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to update root folder";
      toast.error(message);
    } finally {
      setRootBusy(false);
    }
  }

  async function handleDeleteRootFolder(folderId: string) {
    if (!confirm("Are you sure you want to remove this root folder?")) {
      return;
    }
    setRootBusy(true);
    try {
      await apiDelete(`/media/root-folders/${folderId}`);
      toast.success("Root folder removed");
      await loadRootFolders();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to delete root folder";
      toast.error(message);
    } finally {
      setRootBusy(false);
    }
  }

  const handleBooleanChange = (field: keyof MediaSettings) => (checked: boolean) => {
    if (!mediaSettings) return;
    setMediaSettings({ ...mediaSettings, [field]: checked });
  };

  const handleStringChange = (field: keyof MediaSettings) => (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!mediaSettings) return;
    setMediaSettings({ ...mediaSettings, [field]: event.target.value });
  };

  // @ts-expect-error - unused function, may be used in future
  const _handleNumberChange = (field: keyof MediaSettings) => (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!mediaSettings) return;
    setMediaSettings({ ...mediaSettings, [field]: Number(event.target.value) });
  };

  const handleAddFormat = (format: string) => {
    if (!mediaSettings || !format) return;
    setMediaSettings({
      ...mediaSettings,
      format_preference: [...mediaSettings.format_preference, format]
    });
  };

  const handleRemoveFormat = (index: number) => {
    if (!mediaSettings) return;
    const next = mediaSettings.format_preference.filter((_, idx) => idx !== index);
    setMediaSettings({ ...mediaSettings, format_preference: next });
  };

  const handleMoveFormat = (index: number, direction: -1 | 1) => {
    if (!mediaSettings) return;
    const next = [...mediaSettings.format_preference];
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= next.length) {
      return;
    }
    const [entry] = next.splice(index, 1);
    next.splice(targetIndex, 0, entry);
    setMediaSettings({ ...mediaSettings, format_preference: next });
  };

  const handleOpenPicker = (fieldName: keyof MediaSettings) => {
    if (!mediaSettings) return;
    setPickerField(fieldName);
    setPickerInitialValue(mediaSettings[fieldName] as string || '');
    setPickerOpen(true);
  };

  const handleApplyTemplate = (value: string) => {
    if (!mediaSettings || !pickerField) return;
    setMediaSettings({ ...mediaSettings, [pickerField]: value });
  };

  async function handleSaveRenaming() {
    if (!mediaSettings) return;
    setRenamingSaving(true);
    try {
      const payload = {
        rename_downloaded_files: mediaSettings.rename_downloaded_files,
        replace_illegal_characters: mediaSettings.replace_illegal_characters,
        long_special_version: mediaSettings.long_special_version,
        create_empty_volume_folders: mediaSettings.create_empty_volume_folders,
        delete_empty_folders: mediaSettings.delete_empty_folders,
        unmonitor_deleted_issues: mediaSettings.unmonitor_deleted_issues,
      };
      const updated = await apiPut<MediaSettings>("/settings/media-management", payload);
      setMediaSettings(updated);
      renamingInitialRef.current = {
        rename_downloaded_files: updated.rename_downloaded_files,
        replace_illegal_characters: updated.replace_illegal_characters,
        long_special_version: updated.long_special_version,
        create_empty_volume_folders: updated.create_empty_volume_folders,
        delete_empty_folders: updated.delete_empty_folders,
        unmonitor_deleted_issues: updated.unmonitor_deleted_issues,
      };
      toast.success("Renaming & cleanup settings saved");
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to save settings";
      toast.error(message);
    } finally {
      setRenamingSaving(false);
    }
  }

  async function handleSaveNaming() {
    if (!mediaSettings) return;
    setNamingSaving(true);
    try {
      const payload = {
        volume_folder_naming: mediaSettings.volume_folder_naming,
        file_naming: mediaSettings.file_naming,
        file_naming_empty: mediaSettings.file_naming_empty,
        file_naming_special_version: mediaSettings.file_naming_special_version,
        file_naming_vai: mediaSettings.file_naming_vai,
      };
      const updated = await apiPut<MediaSettings>("/settings/media-management", payload);
      setMediaSettings(updated);
      namingInitialRef.current = {
        volume_folder_naming: updated.volume_folder_naming,
        file_naming: updated.file_naming,
        file_naming_empty: updated.file_naming_empty,
        file_naming_special_version: updated.file_naming_special_version,
        file_naming_vai: updated.file_naming_vai,
      };
      toast.success("File naming settings saved");
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to save settings";
      toast.error(message);
    } finally {
      setNamingSaving(false);
    }
  }

  async function handleSaveConversion() {
    if (!mediaSettings) return;
    setConversionSaving(true);
    try {
      const payload = {
        convert: mediaSettings.convert,
        extract_issue_ranges: mediaSettings.extract_issue_ranges,
        format_preference: mediaSettings.format_preference,
      };
      const updated = await apiPut<MediaSettings>("/settings/media-management", payload);
      setMediaSettings(updated);
      conversionInitialRef.current = {
        convert: updated.convert,
        extract_issue_ranges: updated.extract_issue_ranges,
        format_preference: [...updated.format_preference],
      };
      toast.success("Conversion settings saved");
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to save settings";
      toast.error(message);
    } finally {
      setConversionSaving(false);
    }
  }

  if (loading || !mediaSettings) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <p>Loading root folders…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <p>
          Configure how Comicarr organises, renames, and maintains your library after downloads finish.
        </p>
      </div>

      <div className="settings-content">
        <section className="card settings-section">
          <h2>Renaming & Cleanup</h2>
          <div className="settings-media__grid settings-media__grid--two-column">
            <div className="settings-media__column">
              <Toggle
                id="rename-downloaded-files"
                label="Rename downloaded files"
                checked={mediaSettings.rename_downloaded_files}
                onChange={handleBooleanChange("rename_downloaded_files")}
              />
              <Toggle
                id="replace-illegal-characters"
                label="Replace illegal characters"
                checked={mediaSettings.replace_illegal_characters}
                onChange={handleBooleanChange("replace_illegal_characters")}
              />
              <Toggle
                id="long-special-version"
                label="Use long special version format"
                checked={mediaSettings.long_special_version}
                onChange={handleBooleanChange("long_special_version")}
              />
            </div>
            <div className="settings-media__column">
              <Toggle
                id="create-empty-volume-folders"
                label="Create empty volume folders"
                checked={mediaSettings.create_empty_volume_folders}
                onChange={handleBooleanChange("create_empty_volume_folders")}
              />
              <Toggle
                id="delete-empty-folders"
                label="Delete empty folders"
                checked={mediaSettings.delete_empty_folders}
                onChange={handleBooleanChange("delete_empty_folders")}
              />
              <Toggle
                id="unmonitor-deleted-issues"
                label="Unmonitor deleted issues"
                checked={mediaSettings.unmonitor_deleted_issues}
                onChange={handleBooleanChange("unmonitor_deleted_issues")}
              />
            </div>
          </div>
          <div className="settings-actions">
            <button
              type="button"
              className="settings-save-button"
              onClick={handleSaveRenaming}
              disabled={renamingSaving || !renamingHasChanges}
            >
              {renamingSaving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </section>

        <section className="card settings-section">
          <h2>File Naming</h2>
          <div className="settings-media__grid settings-media__grid--single-column">
            <div className="form-field">
              <label htmlFor="volume-folder-naming">Volume folder naming</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  id="volume-folder-naming"
                  type="text"
                  value={mediaSettings.volume_folder_naming}
                  onChange={handleStringChange("volume_folder_naming")}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => handleOpenPicker('volume_folder_naming')}
                  title="Open placeholder picker"
                >
                  ...
                </button>
              </div>
            </div>
            <div className="form-field">
              <label htmlFor="file-naming">File naming</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  id="file-naming"
                  type="text"
                  value={mediaSettings.file_naming}
                  onChange={handleStringChange("file_naming")}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => handleOpenPicker('file_naming')}
                  title="Open placeholder picker"
                >
                  ...
                </button>
              </div>
              {!templateHasIssueToken ? (
                <p className="placeholder-warning">
                  Consider including an issue placeholder such as <code>{"{Issue}"}</code> or <code>{"{Issue:000}"}</code> so rescans can match files.
                </p>
              ) : null}
            </div>
            <div className="form-field">
              <label htmlFor="file-naming-empty">File naming (empty volumes)</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  id="file-naming-empty"
                  type="text"
                  value={mediaSettings.file_naming_empty}
                  onChange={handleStringChange("file_naming_empty")}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => handleOpenPicker('file_naming_empty')}
                  title="Open placeholder picker"
                >
                  ...
                </button>
              </div>
            </div>
            <div className="form-field">
              <label htmlFor="file-naming-sv">File naming (special version)</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  id="file-naming-sv"
                  type="text"
                  value={mediaSettings.file_naming_special_version}
                  onChange={handleStringChange("file_naming_special_version")}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => handleOpenPicker('file_naming_special_version')}
                  title="Open placeholder picker"
                >
                  ...
                </button>
              </div>
            </div>
            <div className="form-field">
              <label htmlFor="file-naming-vai">File naming (volume alternate issue)</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  id="file-naming-vai"
                  type="text"
                  value={mediaSettings.file_naming_vai}
                  onChange={handleStringChange("file_naming_vai")}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => handleOpenPicker('file_naming_vai')}
                  title="Open placeholder picker"
                >
                  ...
                </button>
              </div>
            </div>
          </div>
          
          <div className="settings-actions">
            <button
              type="button"
              className="settings-save-button"
              onClick={handleSaveNaming}
              disabled={namingSaving || !namingHasChanges}
            >
              {namingSaving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </section>

        <section className="card settings-section">
          <h2>Conversion</h2>
          <div className="settings-media__grid">
            <Toggle
              id="convert-to-preferred-formats"
              label="Convert to preferred formats"
              checked={mediaSettings.convert}
              onChange={handleBooleanChange("convert")}
            />
            <Toggle
              id="extract-issue-ranges"
              label="Extract issue ranges from archives"
              checked={mediaSettings.extract_issue_ranges}
              onChange={handleBooleanChange("extract_issue_ranges")}
            />
          </div>

          <div className="format-preference">
            <h3>Format preference</h3>
            <p className="muted">
              Arrange formats in the order Comicarr should attempt conversions. Items at the top have highest priority.
            </p>
            <ul className="format-preference__list">
              {mediaSettings.format_preference.map((format, index) => (
                <li key={format} className="format-preference__item">
                  <span>{index + 1}. {format}</span>
                  <div className="format-preference__actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => handleMoveFormat(index, -1)}
                      disabled={index === 0}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => handleMoveFormat(index, 1)}
                      disabled={index === mediaSettings.format_preference.length - 1}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => handleRemoveFormat(index)}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <div className="format-preference__add">
              <label htmlFor="format-add">Add format</label>
              <div className="format-preference__add-controls">
                <select
                  id="format-add"
                  value=""
                  onChange={(event) => handleAddFormat(event.target.value)}
                >
                  <option value="" disabled>
                    Select a format…
                  </option>
                  {availableFormats.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="settings-actions">
            <button
              type="button"
              className="settings-save-button"
              onClick={handleSaveConversion}
              disabled={conversionSaving || !conversionHasChanges}
            >
              {conversionSaving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </section>

      <section className="card settings-section">
        <h2>Root Folders</h2>
        <p className="muted">
          Define the base directories Comicarr uses when importing and organising volumes. Stats update on page load.
        </p>

        <form className="root-folder-add" onSubmit={handleAddRootFolder}>
          <label htmlFor="root-folder-path">Add root folder</label>
          <div className="root-folder-add__controls">
            <input
              id="root-folder-path"
              type="text"
              placeholder="/path/to/library"
              value={addFolderPath}
              onChange={(event) => setAddFolderPath(event.target.value)}
              disabled={rootBusy}
            />
            <button
              type="button"
              className="secondary"
              onClick={() => openFolderBrowser({ type: "new" })}
              disabled={rootBusy}
            >
              Browse…
            </button>
            <button type="submit" className="primary" disabled={rootBusy || !addFolderPath.trim()}>
              Add
            </button>
          </div>
        </form>

        <div className="root-folder-table-wrapper">
          <table className="root-folder-table">
            <thead>
              <tr>
                <th>Folder</th>
                <th>Free</th>
                <th>Total</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rootFolders.length === 0 ? (
                <tr>
                  <td colSpan={4} className="muted">
                    No root folders configured yet.
                  </td>
                </tr>
              ) : (
                rootFolders.map((folder) => (
                  <tr key={folder.id}>
                    <td>
                      <code>{folder.folder}</code>
                    </td>
                    <td className="number-column">{formatBytes(folder.stats?.free_bytes)}</td>
                    <td className="number-column">{formatBytes(folder.stats?.total_bytes)}</td>
                    <td className="action-column">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => openFolderBrowser({ type: "existing", id: folder.id })}
                        disabled={rootBusy}
                      >
                        Browse…
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void handleDeleteRootFolder(folder.id)}
                        disabled={rootBusy}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

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

      <PlaceholderPickerModal
        isOpen={pickerOpen}
        initialValue={pickerInitialValue}
        onClose={() => setPickerOpen(false)}
        onApply={handleApplyTemplate}
        title="File Naming Tokens"
      />
    </div>
  );
}

