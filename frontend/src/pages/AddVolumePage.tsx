import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { buildApiUrl, apiGet, ApiClientError } from "../api/client";
import { VolumeFilters, type SortOption } from "../components/VolumeFilters";
import Toggle from "../components/Toggle";
import "../components/Card.css";
import "./AddVolumePage.css";

interface ComicvineResult {
  id: number;
  name: string;
  start_year?: number;
  publisher?: string | null;
  publisher_country?: string | null;
  volume_tag?: string | null;
  count_of_issues?: number;
  description?: string;
  site_url?: string;
  image?: string;
  language?: string | null;
}

interface SearchResponse {
  results: ComicvineResult[];
  total: number;
  limit: number;
  page: number;
}

interface Library {
  id: string;
  name: string;
  library_root: string;
  default: boolean;
  enabled: boolean;
}

interface LibraryListResponse {
  libraries: Library[];
}

interface VolumeRecord {
  id: string;
  comicvine_id: number;
  title: string;
  year?: number;
  publisher?: string;
  folder_name: string;
}

const PAGE_SIZE = 12;

const SORT_OPTIONS: SortOption[] = [
  { value: "relevance", label: "Relevance" },
  { value: "title-asc", label: "Title (A–Z)" },
  { value: "title-desc", label: "Title (Z–A)" },
  { value: "year-desc", label: "Year (Newest)" },
  { value: "year-asc", label: "Year (Oldest)" },
  { value: "issues-desc", label: "Issues (Most)" },
  { value: "issues-asc", label: "Issues (Fewest)" }
];

type SortValue = (typeof SORT_OPTIONS)[number]["value"];

function truncate(text: string | undefined, length = 240): string {
  if (!text) {
    return "";
  }
  const clean = text.replace(/<[^>]+>/g, "").trim();
  if (clean.length <= length) {
    return clean;
  }
  return `${clean.slice(0, length)}…`;
}

function formatPublisherLabel(value?: string | null): string {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : "Unknown publisher";
}

type AddVolumeModalProps = {
  volume: ComicvineResult | null;
  libraries: Library[];
  libraryLoading: boolean;
  libraryId: string;
  onLibraryChange: (value: string) => void;
  monitored: boolean;
  onMonitoredChange: (value: boolean) => void;
  monitorNewIssues: boolean;
  onMonitorNewIssuesChange: (value: boolean) => void;
  onClose: () => void;
  onSubmit: () => void;
  submitting: boolean;
  errorMessage: string | null;
};

function AddVolumeModal({
  volume,
  libraries,
  libraryLoading,
  libraryId,
  onLibraryChange,
  monitored,
  onMonitoredChange,
  monitorNewIssues,
  onMonitorNewIssuesChange,
  onClose,
  onSubmit,
  submitting,
  errorMessage
}: AddVolumeModalProps) {
  if (!volume) {
    return null;
  }

  const yearLabel = volume.start_year ? ` (${volume.start_year})` : "";

  return (
    <div className="add-volume__modal-backdrop" onClick={onClose} data-testid="add-volume-modal-backdrop">
      <div
        className="add-volume__modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-volume-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="add-volume__modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        <header className="add-volume__modal-header">
          <h2 id="add-volume-modal-title">
            {volume.site_url ? (
              <a
                href={volume.site_url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={{ color: "inherit", textDecoration: "none" }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.textDecoration = "underline";
                  e.currentTarget.style.color = "var(--color-primary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.textDecoration = "none";
                  e.currentTarget.style.color = "inherit";
                }}
              >
                {volume.name || "Untitled volume"}
                {yearLabel}
              </a>
            ) : (
              <>
                {volume.name || "Untitled volume"}
                {yearLabel}
              </>
            )}
          </h2>
          <p className="muted">
            {volume.publisher ? `${volume.publisher} • ` : ""}
            {typeof volume.count_of_issues === "number" ? `${volume.count_of_issues} issues` : "Issues unknown"}
            {volume.publisher_country ? ` • ${volume.publisher_country}` : ""}
          </p>
        </header>

        <div className="add-volume__modal-body">
          <div className="add-volume__modal-cover">
            {volume.image ? (
              volume.site_url ? (
                <a
                  href={volume.site_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  style={{ display: "block", cursor: "pointer" }}
                  title="View on ComicVine"
                >
                  <img src={volume.image} alt={`${volume.name ?? "Comicvine cover"}`} />
                </a>
              ) : (
                <img src={volume.image} alt={`${volume.name ?? "Comicvine cover"}`} />
              )
            ) : (
              <div className="cover-placeholder">No cover available</div>
            )}
          </div>

          <form
            className="add-volume__modal-form"
            onSubmit={(event) => {
              event.preventDefault();
              onSubmit();
            }}
          >
            <div className="modal-row">
              <span className="modal-label">Library</span>
              {libraries.length > 0 ? (
                <select
                  id="modal-library"
                  value={libraryId}
                  disabled={submitting || libraryLoading}
                  onChange={(event) => onLibraryChange(event.target.value)}
                >
                  {libraries.map((library) => (
                    <option key={library.id} value={library.id}>
                      {library.name} {library.default && "(Default)"} - {library.library_root}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="status error inline">No enabled libraries available. Create one in Library → Libraries.</p>
              )}
            </div>

            <div className="modal-row">
              <span className="modal-label">Monitor Volume</span>
              <Toggle
                id="modal-monitor-volume"
                checked={monitored}
                onChange={onMonitoredChange}
                disabled={submitting}
              />
            </div>

            <div className="modal-row">
              <div className="modal-label-group">
                <span className="modal-label">Monitor New Issues</span>
                <p className="muted caption">When new issues come out, automatically monitor them.</p>
              </div>
              <Toggle
                id="modal-monitor-new-issues"
                checked={monitorNewIssues}
                onChange={onMonitorNewIssuesChange}
                disabled={submitting}
              />
            </div>

            {errorMessage ? <p className="status error">{errorMessage}</p> : null}

            <div className="modal-actions">
              <button type="button" className="secondary" onClick={onClose} disabled={submitting}>
                Cancel
              </button>
              <button type="submit" className="primary" disabled={submitting || libraries.length === 0}>
                {submitting ? "Adding…" : "Add Volume"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function AddVolumePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [hasSearched, setHasSearched] = useState(false);
  const [sortOption, setSortOption] = useState<SortValue>("relevance");
  const [rawResults, setRawResults] = useState<ComicvineResult[]>([]);
  const [totalResults, setTotalResults] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [libraries, setLibraries] = useState<Library[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  const [recentlyAdded, setRecentlyAdded] = useState<VolumeRecord[]>([]);
  const [globalStatus, setGlobalStatus] = useState<string | null>(null);

  const [publisherFilter, setPublisherFilter] = useState("All");
  const [volumeFilter, setVolumeFilter] = useState("All");
  const [yearMin, setYearMin] = useState("");
  const [yearMax, setYearMax] = useState("");
  const [issueMin, setIssueMin] = useState("");
  const [issueMax, setIssueMax] = useState("");

  const [modalVolume, setModalVolume] = useState<ComicvineResult | null>(null);
  const [modalLibraryId, setModalLibraryId] = useState<string>("");
  const [modalMonitored, setModalMonitored] = useState(true);
  const [modalMonitorNewIssues, setModalMonitorNewIssues] = useState(true);
  const [modalError, setModalError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    loadLibraries();
  }, []);

  async function loadLibraries() {
    try {
      setLibraryLoading(true);
      setLibraryError(null);
      const data = await apiGet<LibraryListResponse>("/libraries");
      const enabledLibraries = (data.libraries ?? []).filter((lib) => lib.enabled);
      setLibraries(enabledLibraries);
      
      if (enabledLibraries.length > 0) {
        const defaultLibrary = enabledLibraries.find((lib) => lib.default);
        setModalLibraryId(defaultLibrary ? defaultLibrary.id : enabledLibraries[0].id);
      }
    } catch (err) {
      setLibraryError(err instanceof ApiClientError ? err.message : String(err));
    } finally {
      setLibraryLoading(false);
    }
  }

  useEffect(() => {
    if (modalVolume && libraries.length > 0) {
      setModalLibraryId((current) => {
        if (current && libraries.some((lib) => lib.id === current)) {
          return current;
        }
        const defaultLibrary = libraries.find((lib) => lib.default);
        return defaultLibrary ? defaultLibrary.id : libraries[0].id;
      });
    }
  }, [modalVolume, libraries]);

  useEffect(() => {
    if (!modalVolume) {
      document.body.style.removeProperty("overflow");
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setModalVolume(null);
      }
    };

    window.addEventListener("keydown", handleKeydown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeydown);
    };
  }, [modalVolume]);

  useEffect(() => {
    setPage(1);
  }, [publisherFilter, volumeFilter, yearMin, yearMax, issueMin, issueMax, sortOption]);

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setSearchError("Enter at least one character before searching.");
      setRawResults([]);
      setTotalResults(null);
      setHasSearched(false);
      return;
    }

    setSearching(true);
    setSearchError(null);
    setGlobalStatus(null);
    setHasSearched(true);
    setPublisherFilter("All");
    setVolumeFilter("All");
    setYearMin("");
    setYearMax("");
    setIssueMin("");
    setIssueMax("");
    setSortOption("relevance");
    setModalVolume(null);
    setModalError(null);
    setPage(1);
    setViewMode("list");

    try {
      const response = await fetch(
        buildApiUrl(`/api/comicvine/volumes/search?query=${encodeURIComponent(trimmed)}&page=1&limit=50`),
        {
          credentials: "include"
        }
      );

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const data = (await response.json()) as SearchResponse;
      const results = data.results ?? [];
      setRawResults(results);
      setTotalResults(data.total ?? results.length ?? 0);
      if (results.length === 0) {
        setSearchError("Comicvine did not return any volumes for that query.");
      }
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : String(err));
      setRawResults([]);
      setTotalResults(null);
    } finally {
      setSearching(false);
    }
  };

  const publisherOptions = useMemo(() => {
    const values = new Set<string>();
    rawResults.forEach((item) => {
      values.add(formatPublisherLabel(item.publisher));
    });
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [rawResults]);

  const volumeOptions = useMemo(() => {
    const values = new Set<string>();
    rawResults.forEach((item) => {
      const tag = item.volume_tag ?? (typeof item.start_year === "number" ? `V${item.start_year}` : null);
      if (tag) {
        values.add(tag);
      }
    });
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [rawResults]);

  const filteredResults = useMemo(() => {
    const minYear = yearMin ? Number.parseInt(yearMin, 10) : null;
    const maxYear = yearMax ? Number.parseInt(yearMax, 10) : null;
    const minIssues = issueMin ? Number.parseInt(issueMin, 10) : null;
    const maxIssues = issueMax ? Number.parseInt(issueMax, 10) : null;

    return rawResults.filter((item) => {
      const publisherLabel = formatPublisherLabel(item.publisher);
      if (publisherFilter !== "All" && publisherLabel !== publisherFilter) {
        return false;
      }

      if (minYear !== null && (item.start_year ?? 0) < minYear) {
        return false;
      }
      if (maxYear !== null && (item.start_year ?? 0) > maxYear) {
        return false;
      }

      if (minIssues !== null && (item.count_of_issues ?? 0) < minIssues) {
        return false;
      }
      if (maxIssues !== null && (item.count_of_issues ?? 0) > maxIssues) {
        return false;
      }

      if (volumeFilter !== "All") {
        const tag = item.volume_tag ?? (typeof item.start_year === "number" ? `V${item.start_year}` : null);
        if (tag !== volumeFilter) {
          return false;
        }
      }

      return true;
    });
  }, [
    rawResults,
    publisherFilter,
    volumeFilter,
    yearMin,
    yearMax,
    issueMin,
    issueMax
  ]);

  const sortedResults = useMemo(() => {
    if (sortOption === "relevance") {
      return filteredResults;
    }

    const sorted = [...filteredResults];
    sorted.sort((a, b) => {
      const titleA = (a.name || "").toLocaleLowerCase();
      const titleB = (b.name || "").toLocaleLowerCase();
      const yearA = a.start_year ?? 0;
      const yearB = b.start_year ?? 0;
      const issuesA = a.count_of_issues ?? 0;
      const issuesB = b.count_of_issues ?? 0;

      switch (sortOption) {
        case "title-asc":
          return titleA.localeCompare(titleB);
        case "title-desc":
          return titleB.localeCompare(titleA);
        case "year-asc":
          return yearA - yearB;
        case "year-desc":
          return yearB - yearA;
        case "issues-asc":
          return issuesA - issuesB;
        case "issues-desc":
          return issuesB - issuesA;
        default:
          return 0;
      }
    });
    return sorted;
  }, [filteredResults, sortOption]);

  const totalFiltered = sortedResults.length;
  const pageCount = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));

  useEffect(() => {
    if (page > pageCount) {
      setPage(pageCount);
    }
  }, [page, pageCount]);

  const pagedResults = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return sortedResults.slice(start, start + PAGE_SIZE);
  }, [sortedResults, page]);

  const openModal = (volume: ComicvineResult) => {
    setModalVolume(volume);
  };

  const closeModal = () => {
    if (adding) {
      return;
    }
    setModalVolume(null);
    setModalError(null);
  };

  const handleAddVolume = async () => {
    if (!modalVolume) {
      return;
    }
    if (!modalLibraryId) {
      setModalError("Select a library before adding this volume.");
      return;
    }

    setAdding(true);
    setModalError(null);

    try {
      const response = await fetch(buildApiUrl("/api/volumes"), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          comicvine_id: modalVolume.id,
          library_id: modalLibraryId,
        })
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const record = (await response.json()) as VolumeRecord;
      setRecentlyAdded((prev) => [record, ...prev].slice(0, 5));
      setGlobalStatus(`Added "${record.title}"${record.year ? ` (${record.year})` : ""} to library.`);
      setModalVolume(null);
      toast.success("Volume added successfully");
      navigate(`/volumes/${record.id}`);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const noLibraries = !libraryLoading && libraries.length === 0;

  return (
    <div className="add-volume">
      <form className="card add-volume__search" onSubmit={handleSearch}>
        <div className="search-row">
          <input
            type="text"
            placeholder='Search Comicvine (e.g., "Saga", "Batman", "cv:4050-2127")'
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            disabled={searching}
          />
          <button type="submit" className="primary" disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
        </div>

        {hasSearched && rawResults.length > 0 ? (
          <div className="filter-row">
            <VolumeFilters
              publisherFilter={publisherFilter}
              volumeFilter={volumeFilter}
              yearMin={yearMin}
              yearMax={yearMax}
              minIssues={issueMin}
              maxIssues={issueMax}
              sortValue={sortOption}
              onPublisherChange={setPublisherFilter}
              onVolumeChange={setVolumeFilter}
              onYearMinChange={setYearMin}
              onYearMaxChange={setYearMax}
              onMinIssuesChange={setIssueMin}
              onMaxIssuesChange={setIssueMax}
              onSortChange={(value) => setSortOption(value as SortValue)}
              publisherOptions={["All", ...publisherOptions]}
              volumeOptions={volumeOptions}
              sortOptions={SORT_OPTIONS}
              idPrefix="filter"
            />
            <div className="view-toggle">
              <button
                type="button"
                className={viewMode === "list" ? "secondary active" : "secondary"}
                onClick={() => setViewMode("list")}
                disabled={sortedResults.length === 0}
                title="List view"
                aria-label="List view"
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
                className={viewMode === "grid" ? "secondary active" : "secondary"}
                onClick={() => setViewMode("grid")}
                disabled={sortedResults.length === 0}
                title="Grid view"
                aria-label="Grid view"
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
          </div>
        ) : null}

        {searchError ? <p className="status error">{searchError}</p> : null}
        {globalStatus ? <p className="status success">{globalStatus}</p> : null}

        {hasSearched && !searching ? (
          <div className="search-footer">
            <p className="muted">
              {totalFiltered} result{totalFiltered === 1 ? "" : "s"}
              {typeof totalResults === "number" ? ` (Comicvine reported ${totalResults})` : ""}
            </p>
          </div>
        ) : null}
      </form>

      {noLibraries ? (
        <section className="card add-volume__notice">
          <p className="status error">
            No enabled libraries configured yet. Create one in Library → Libraries before importing volumes.
          </p>
        </section>
      ) : null}

      {libraryError ? (
        <section className="card add-volume__notice">
          <p className="status error">{libraryError}</p>
        </section>
      ) : null}

      {recentlyAdded.length > 0 ? (
        <section className="card add-volume__recent">
          <h2>Recently Added</h2>
          <ul>
            {recentlyAdded.map((volume) => (
              <li key={volume.id}>
                <span>
                  {volume.title}
                  {volume.year ? ` (${volume.year})` : ""}
                </span>
                <span className="muted">{volume.folder_name}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={`add-volume__results ${viewMode}`}>
        {pagedResults.map((result) => {
          const issueCountLabel =
            typeof result.count_of_issues === "number"
              ? `${result.count_of_issues} ${result.count_of_issues === 1 ? "issue" : "issues"}`
              : null;
          const volumeTag = result.volume_tag ?? (typeof result.start_year === "number" ? `V${result.start_year}` : null);

          return (
            <article key={result.id} className="card add-volume__result">
              <div className="result-cover">
                {result.image ? (
                  <img src={result.image} alt={`${result.name ?? "Comicvine cover"}`} />
                ) : (
                  <div className="cover-placeholder">No cover</div>
                )}
              </div>
              <div className="result-content">
                <div className="result-header">
                  <div>
                    <h3>
                      {result.name || "Untitled volume"}
                      {result.start_year ? ` (${result.start_year})` : ""}
                    </h3>
                    <div className="result-badges">
                      {volumeTag ? <span className="badge">{volumeTag}</span> : null}
                      {result.publisher ? <span className="badge">{result.publisher}</span> : null}
                      {result.publisher_country ? <span className="badge">{result.publisher_country}</span> : null}
                      {issueCountLabel ? <span className="badge">{issueCountLabel}</span> : null}
                      {result.language ? <span className="badge">{result.language}</span> : null}
                      {result.site_url ? (
                        <a href={result.site_url} target="_blank" rel="noreferrer" className="badge badge--link">
                          Comicvine
                        </a>
                      ) : null}
                    </div>
                  </div>
                  <div className="result-actions">
                    <button
                      type="button"
                      className="primary"
                      onClick={() => openModal(result)}
                      disabled={libraryLoading || libraries.length === 0}
                      title={libraries.length === 0 ? "Add at least one library first" : undefined}
                    >
                      Add volume
                    </button>
                  </div>
                </div>
                <p className="result-summary">{truncate(result.description)}</p>
              </div>
            </article>
          );
        })}
      </section>

      {totalFiltered > PAGE_SIZE ? (
        <footer className="add-volume__pagination">
          <button
            type="button"
            className="secondary"
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            disabled={page === 1}
          >
            Previous
          </button>
          <span className="muted">
            Page {page} of {pageCount}
          </span>
          <button
            type="button"
            className="secondary"
            onClick={() => setPage((prev) => Math.min(pageCount, prev + 1))}
            disabled={page === pageCount}
          >
            Next
          </button>
        </footer>
      ) : null}

      <AddVolumeModal
        volume={modalVolume}
        libraries={libraries}
        libraryLoading={libraryLoading}
        libraryId={modalLibraryId}
        onLibraryChange={setModalLibraryId}
        monitored={modalMonitored}
        onMonitoredChange={setModalMonitored}
        monitorNewIssues={modalMonitorNewIssues}
        onMonitorNewIssuesChange={setModalMonitorNewIssues}
        onClose={closeModal}
        onSubmit={handleAddVolume}
        submitting={adding}
        errorMessage={modalError}
      />
    </div>
  );
}

export default AddVolumePage;
