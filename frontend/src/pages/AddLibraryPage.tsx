import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { apiGet, apiPost, ApiClientError } from "../api/client";
import Toggle from "../components/Toggle";
import "./AddLibraryPage.css";

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

interface LibraryCreatePayload {
  name: string;
  library_root: string;
  default: boolean;
  enabled: boolean;
}

export default function AddLibraryPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [libraryRoot, setLibraryRoot] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [rootFolders, setRootFolders] = useState<RootFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingRootFolders, setLoadingRootFolders] = useState(true);

  useEffect(() => {
    loadRootFolders();
  }, []);

  async function loadRootFolders() {
    try {
      setLoadingRootFolders(true);
      const data = await apiGet<RootFolderResponse>("/media/root-folders");
      setRootFolders(data.root_folders ?? []);
      // Pre-select first root folder if available
      if (data.root_folders && data.root_folders.length > 0) {
        setLibraryRoot(data.root_folders[0].folder);
      }
    } catch (err) {
      // Don't show error if root folders endpoint doesn't exist yet
      console.warn("Failed to load root folders:", err);
    } finally {
      setLoadingRootFolders(false);
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Library name is required");
      return;
    }

    if (!libraryRoot.trim()) {
      toast.error("Library root path is required");
      return;
    }

    setLoading(true);
    try {
      const payload: LibraryCreatePayload = {
        name: name.trim(),
        library_root: libraryRoot.trim(),
        default: isDefault,
        enabled: enabled,
      };

      await apiPost("/libraries", payload);
      toast.success(`Library "${name}" created successfully`);
      navigate("/library");
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Failed to create library";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="add-library-page">
      <form className="add-library-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="library-name">
            Library Name <span className="required">*</span>
          </label>
          <input
            id="library-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Comics, Mangas"
            required
            disabled={loading}
          />
          <p className="form-field-help">A descriptive name for this library (e.g., "Comics", "Mangas")</p>
        </div>

        <div className="form-field">
          <label htmlFor="library-root">
            Library Root Path <span className="required">*</span>
          </label>
          {loadingRootFolders ? (
            <p className="form-field-help">Loading root folders...</p>
          ) : rootFolders.length > 0 ? (
            <select
              id="library-root"
              value={libraryRoot}
              onChange={(e) => setLibraryRoot(e.target.value)}
              required
              disabled={loading}
            >
              <option value="">Select a root folder...</option>
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
              placeholder="/path/to/library"
              required
              disabled={loading}
            />
          )}
          <p className="form-field-help">
            The base directory where files for this library will be organized
          </p>
        </div>

        <div className="form-field">
          <Toggle
            id="library-default"
            checked={isDefault}
            onChange={setIsDefault}
            disabled={loading}
            label="Set as default library"
          />
          <p className="form-field-help">
            New volumes will be added to the default library if no library is specified
          </p>
        </div>

        <div className="form-field">
          <Toggle
            id="library-enabled"
            checked={enabled}
            onChange={setEnabled}
            disabled={loading}
            label="Enable library"
          />
          <p className="form-field-help">Disabled libraries won't be used for new volumes</p>
        </div>

        <div className="form-actions">
          <button type="submit" className="button primary" disabled={loading}>
            {loading ? "Creating..." : "Create Library"}
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => navigate("/library")}
            disabled={loading}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

