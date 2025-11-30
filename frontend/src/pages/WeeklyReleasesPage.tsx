import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { MapPinPlus, MapPinX, MessageCircleCode, BookOpen, LayoutList, RotateCcw, Activity, Pause, Play } from "lucide-react";
import { buildApiUrl } from "../api/client";
import { VolumePickerModal } from "../components/VolumePickerModal";
import { BulkActionsBar } from "../components/BulkActionsBar";
import { SelectionControls } from "../components/SelectionControls";
import { MultiSelectFilter } from "../components/MultiSelectFilter";
import "./WeeklyReleasesPage.css";

// ComicVine Search Result Display Component (from ImportPage)
function ComicVineSearchResultDisplay({ result }: { result: any }) {
  const resultsSample = result.results_sample || [];
  const selectedVolumeId = result.volume_id;

  return (
    <div className="comicvine-search-result">
      <div className="comicvine-search-result__header">
        <div className="comicvine-search-result__query">
          <div><strong>Search Query:</strong> {result.search_query || "N/A"}</div>
          {result.api_query && result.api_query !== result.search_query && (
            <div><strong>API Query:</strong> {result.api_query}</div>
          )}
        </div>
        <div className="comicvine-search-result__summary">
          <div><strong>Results Found:</strong> {result.results_count || 0}</div>
          {result.volume_id && (
            <div className="comicvine-search-result__match">
              <strong>Selected Match:</strong> {result.volume_name || `Volume ID: ${result.volume_id}`}
              {result.confidence !== null && result.confidence !== undefined && (
                <span className="comicvine-search-result__confidence">
                  {" "}(Confidence: {(result.confidence * 100).toFixed(1)}%)
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {resultsSample.length > 0 && (
        <div className="comicvine-search-result__volumes">
          <h4>Volume Candidates (sorted by score):</h4>
          <div className="comicvine-search-result__volumes-list">
            {resultsSample.map((volume: any, idx: number) => {
              const isSelected = volume.cv_volume_id === selectedVolumeId;
              const matchDetails = volume.match_details || [];
              const isRejected = volume.rejected === true;

              return (
                <div
                  key={volume.cv_volume_id || idx}
                  className={`comicvine-search-result__volume ${isSelected ? "comicvine-search-result__volume--selected" : ""} ${volume.is_best_match ? "comicvine-search-result__volume--best-match" : ""} ${isRejected ? "comicvine-search-result__volume--rejected" : ""}`}
                >
                  <div className="comicvine-search-result__volume-header">
                    <div className="comicvine-search-result__volume-name">
                      <strong>{volume.name}</strong>
                      {volume.start_year && <span className="comicvine-search-result__volume-year"> ({volume.start_year})</span>}
                      {isSelected && <span className="comicvine-search-result__volume-badge">✓ Selected</span>}
                      {volume.is_best_match && !isSelected && <span className="comicvine-search-result__volume-badge">Best Match</span>}
                      {isRejected && <span className="comicvine-search-result__volume-badge comicvine-search-result__volume-badge--rejected">Rejected</span>}
                    </div>
                    <div className="comicvine-search-result__volume-scores">
                      <span className="comicvine-search-result__score">
                        Raw Score: <strong>{volume.raw_score?.toFixed(2) || "0.00"}</strong>
                      </span>
                      <span className="comicvine-search-result__confidence-badge">
                        Confidence: <strong>{(volume.confidence * 100).toFixed(1)}%</strong>
                      </span>
                      <span className={`comicvine-search-result__classification comicvine-search-result__classification--${volume.match_classification || "no_match"}`}>
                        {volume.match_classification || "no_match"}
                      </span>
                    </div>
                  </div>

                  {volume.publisher && (
                    <div className="comicvine-search-result__volume-meta">
                      <strong>Publisher:</strong> {volume.publisher}
                    </div>
                  )}

                  {isRejected && volume.rejection_reason && (
                    <div className="comicvine-search-result__volume-rejection">
                      <strong>Rejection Reason:</strong> {volume.rejection_reason}
                    </div>
                  )}

                  {matchDetails.length > 0 && (
                    <div className="comicvine-search-result__volume-details">
                      <strong>Match Breakdown:</strong>
                      <ul className="comicvine-search-result__match-details">
                        {matchDetails.map((detail: string, detailIdx: number) => (
                          <li key={detailIdx}>{detail}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!result.volume_id && result.results_count === 0 && (
        <div className="comicvine-search-result__no-results">
          No results found in ComicVine.
        </div>
      )}
    </div>
  );
}

type WeeklyReleaseWeek = {
  id: string;
  week_start: string;
  fetched_at: number;
  status: string;
  counts: {
    total: number;
    pending: number;
    import: number;
    skipped: number;
    processed: number;
  };
};

type WeeklyReleaseItem = {
  id: string;
  week_id: string;
  week_start?: string | null;
  source: string;
  issue_key?: string | null;
  title: string;
  publisher?: string | null;
  release_date?: string | null;
  url?: string | null;
  status: "pending" | "import" | "skipped" | "processed";
  notes?: string | null;
  matched_volume_id?: string | null;
  matched_issue_id?: string | null;
  comicvine_volume_id?: number | null;
  comicvine_issue_id?: number | null;
  comicvine_volume_name?: string | null;
  comicvine_issue_name?: string | null;
  comicvine_issue_number?: string | null;
  comicvine_site_url?: string | null;
  comicvine_cover_date?: string | null;
  comicvine_confidence?: number | null;
  cv_search_query?: string | null;
  cv_results_count?: number | null;
  cv_results_sample?: string | null;
  metadata?: Record<string, unknown> | null;
  library_volume?: {
    id: string;
    title: string;
    comicvine_id: number;
    publisher?: string | null;
    year?: number | null;
  } | null;
  library_issue?: {
    id: string;
    number: string;
    title?: string | null;
    status?: string | null;
    release_date?: string | null;
    file_path?: string | null;
  } | null;
};

type StatusFilter = "pending" | "import" | "skipped" | "processed";
type SourceFilter = "previewsworld" | "comicgeeks" | "readcomicsonline" | "combined";

const SOURCE_LABELS: Record<string, string> = {
  previewsworld: "PreviewsWorld",
  comicgeeks: "League of Comic Geeks",
  readcomicsonline: "ReadComicsOnline",
  combined: "Multiple sources",
};

function formatSourceLabel(source: string): string {
  return SOURCE_LABELS[source] || source.replace(/_/g, " ");
}

function formatDate(date: string | null | undefined): string {
  if (!date) return "—";
  try {
    return new Date(date).toLocaleDateString();
  } catch {
    return date;
  }
}

export default function WeeklyReleasesPage() {
  const [weeks, setWeeks] = useState<WeeklyReleaseWeek[]>([]);
  const [selectedWeekId, setSelectedWeekId] = useState<string | null>(null);
  const [entries, setEntries] = useState<WeeklyReleaseItem[]>([]);
  const [loadingWeeks, setLoadingWeeks] = useState(false);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilters, setStatusFilters] = useState<Set<StatusFilter>>(new Set());
  const [sourceFilters, setSourceFilters] = useState<Set<SourceFilter>>(new Set());
  const [publisherFilters, setPublisherFilters] = useState<Set<string>>(new Set());
  const [matchedFilters, setMatchedFilters] = useState<Set<string>>(new Set());
  const [inLibraryFilter, setInLibraryFilter] = useState<boolean | null>(null);
  const [pullModalOpen, setPullModalOpen] = useState(false);
  const [bulkStatusValue, setBulkStatusValue] = useState<string>("pending");
  const [searchTerm, setSearchTerm] = useState("");
  const [fetchingSource, setFetchingSource] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    // Default to today if Wednesday, otherwise previous Wednesday
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayOfWeek = today.getDay();

    let defaultDate: Date;
    if (dayOfWeek === 3) {
      // Today is Wednesday, use today
      defaultDate = today;
    } else {
      // Go to previous Wednesday
      const daysToSubtract = (dayOfWeek - 3 + 7) % 7;
      defaultDate = new Date(today);
      defaultDate.setDate(today.getDate() - daysToSubtract);
    }

    // Format date as YYYY-MM-DD
    const year = defaultDate.getFullYear();
    const month = String(defaultDate.getMonth() + 1).padStart(2, "0");
    const day = String(defaultDate.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  });
  // Track matching jobs per week: Map<weekId, { type: 'cv' | 'library', progress: { current: number, total: number }, paused: boolean }>
  const [matchingJobs, setMatchingJobs] = useState<Map<string, { type: 'cv' | 'library', progress: { current: number, total: number }, paused: boolean }>>(new Map());
  const matchingPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track processing jobs per week: Map<weekId, { progress: { current: number, total: number }, paused: boolean }>
  const [processingJobs, setProcessingJobs] = useState<Map<string, { progress: { current: number, total: number }, paused: boolean }>>(new Map());
  const processingPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [deletingWeekId, setDeletingWeekId] = useState<string | null>(null);
  const [diagnosticEntry, setDiagnosticEntry] = useState<WeeklyReleaseItem | null>(null);
  const [diagnosticData, setDiagnosticData] = useState<any>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);
  const [selectedEntryIds, setSelectedEntryIds] = useState<Set<string>>(new Set());
  const [volumePickerEntry, setVolumePickerEntry] = useState<WeeklyReleaseItem | null>(null);

  // Load weeks list
  const loadWeeks = useCallback(async () => {
    setLoadingWeeks(true);
    setError(null);
    try {
      const response = await fetch(buildApiUrl("/api/releases"));
      if (!response.ok) {
        throw new Error(`Failed to load weeks: ${response.statusText}`);
      }
      const data = await response.json();
      setWeeks(data.weeks || []);
      // Auto-select first week if available
      if (data.weeks && data.weeks.length > 0 && !selectedWeekId) {
        setSelectedWeekId(data.weeks[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load weeks");
    } finally {
      setLoadingWeeks(false);
    }
  }, [selectedWeekId]);

  // Load entries for selected week
  const loadEntries = useCallback(async (weekId: string) => {
    setLoadingEntries(true);
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}`));
      if (!response.ok) {
        throw new Error(`Failed to load entries: ${response.statusText}`);
      }
      const data = await response.json();
      setEntries(data.entries || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load entries");
    } finally {
      setLoadingEntries(false);
    }
  }, []);

  // Helper function to check if a date is a Wednesday

  // Helper function to format date as YYYY-MM-DD
  const formatDateForInput = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  const isWednesday = (date: Date): boolean => {
    return date.getDay() === 3;
  };

  // Helper function to get the nearest past Wednesday from a given date
  // If date is today and today is Wednesday, use today
  // Otherwise, always goes to previous Wednesday (no future dates allowed)
  const getNearestWednesday = (date: Date): Date => {
    const targetDate = new Date(date);
    targetDate.setHours(0, 0, 0, 0);

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const dayOfWeek = date.getDay(); // 0 = Sunday, 1 = Monday, ..., 6 = Saturday

    // If the date is today and today is Wednesday, use today
    if (targetDate.getTime() === today.getTime() && dayOfWeek === 3) {
      return targetDate;
    }

    // Calculate days to subtract to get to previous Wednesday
    let daysToSubtract = (dayOfWeek - 3 + 7) % 7;
    if (daysToSubtract === 0 && !isWednesday(date)) {
      daysToSubtract = 7; // If not Wednesday, go back 7 days to previous Wednesday
    } else if (daysToSubtract === 0) {
      // If it's already Wednesday but not today, go back 7 days to previous Wednesday
      daysToSubtract = 7;
    }

    const nearestWednesday = new Date(date);
    nearestWednesday.setDate(date.getDate() - daysToSubtract);
    return nearestWednesday;
  };

  // Handle date change - ensure it's a Wednesday
  const handleDateChange = (dateString: string) => {
    if (!dateString) {
      setSelectedDate("");
      return;
    }

    const date = new Date(dateString + "T00:00:00"); // Add time to avoid timezone issues
    if (isWednesday(date)) {
      setSelectedDate(dateString);
    } else {
      // If not a Wednesday, find the nearest Wednesday
      const nearestWed = getNearestWednesday(date);
      const formatted = formatDateForInput(nearestWed);
      setSelectedDate(formatted);
      // Show a brief message that we adjusted the date
      setTimeout(() => {
        toast.info(`Date adjusted to previous Wednesday: ${formatted}`);
      }, 100);
    }
  };

  // Get min date (12 months ago) for date picker
  const getMinDate = (): string => {
    const today = new Date();
    const twelveMonthsAgo = new Date(today);
    twelveMonthsAgo.setMonth(today.getMonth() - 12);
    // Find the first Wednesday on or before this date
    const dayOfWeek = twelveMonthsAgo.getDay();
    const daysToSubtract = (dayOfWeek - 3 + 7) % 7; // 3 = Wednesday
    twelveMonthsAgo.setDate(twelveMonthsAgo.getDate() - daysToSubtract);
    return formatDateForInput(twelveMonthsAgo);
  };

  // Get max date (today if Wednesday, otherwise most recent past Wednesday)
  const getMaxDate = (): string => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayOfWeek = today.getDay();

    // If today is Wednesday, use today
    if (dayOfWeek === 3) {
      return formatDateForInput(today);
    }

    // Otherwise, go back to the previous Wednesday
    let daysToSubtract = (dayOfWeek - 3 + 7) % 7;
    const lastWednesday = new Date(today);
    lastWednesday.setDate(today.getDate() - daysToSubtract);
    return formatDateForInput(lastWednesday);
  };

  // Fetch releases from a source
  const fetchReleases = useCallback(async (source: string) => {
    setFetchingSource(source);
    setError(null);
    try {
      const body: Record<string, string> = { source };
      if (selectedDate && selectedDate.trim() !== "") {
        body.week_start = selectedDate.trim();
      }

      const requestBody = JSON.stringify(body);
      console.log("Fetching releases with body:", requestBody);
      console.log("Request body parsed:", JSON.parse(requestBody));

      const url = buildApiUrl("/api/releases/fetch");
      console.log("Request URL:", url);

      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: requestBody,
      });

      console.log("Response status:", response.status, response.statusText);

      if (!response.ok) {
        let errorMessage = `Failed to fetch releases: ${response.statusText}`;
        try {
          const errorData = await response.json();
          console.error("Error response data:", JSON.stringify(errorData, null, 2));
          // Handle different error response formats
          if (typeof errorData.detail === "string") {
            errorMessage = errorData.detail;
          } else if (Array.isArray(errorData.detail)) {
            // Pydantic validation errors
            errorMessage = errorData.detail
              .map((e: any) => {
                if (e.loc && e.msg) {
                  return `${e.loc.join(".")}: ${e.msg}`;
                }
                return e.msg || String(e);
              })
              .join(", ");
          } else if (errorData.detail && typeof errorData.detail === "object") {
            errorMessage = JSON.stringify(errorData.detail);
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        } catch (parseError) {
          // If JSON parsing fails, use the status text
          console.error("Failed to parse error response:", parseError);
        }
        throw new Error(errorMessage);
      }
      const data = await response.json();
      // Reload weeks to show new week
      await loadWeeks();
      // If a week_id was returned, select it
      if (data.week_id) {
        setSelectedWeekId(data.week_id);
      }
      // Show toast notification with entry count
      const count = data.count || 0;
      if (count > 0) {
        toast.success(`Added ${count} ${count === 1 ? 'entry' : 'entries'} from ${source}`);
      } else {
        toast.info(`No new entries found from ${source}`);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    } finally {
      setFetchingSource(null);
    }
  }, [loadWeeks, selectedDate]);

  // Update entry status
  const updateEntryStatus = useCallback(async (
    weekId: string,
    entryId: string,
    status: "pending" | "import" | "skipped" | "processed"
  ) => {
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/entries/${entryId}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        throw new Error(`Failed to update entry: ${response.statusText}`);
      }
      // Reload entries
      await loadEntries(weekId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update entry");
    }
  }, [loadEntries]);

  // Match week to ComicVine

  // Navigate to previous/next week
  const navigateWeek = useCallback((direction: "prev" | "next") => {
    if (weeks.length === 0) return;

    const currentIndex = selectedWeekId
      ? weeks.findIndex((w) => w.id === selectedWeekId)
      : -1;

    if (direction === "prev") {
      if (currentIndex > 0) {
        setSelectedWeekId(weeks[currentIndex - 1].id);
      } else if (weeks.length > 0) {
        setSelectedWeekId(weeks[weeks.length - 1].id);
      }
    } else {
      if (currentIndex >= 0 && currentIndex < weeks.length - 1) {
        setSelectedWeekId(weeks[currentIndex + 1].id);
      } else if (weeks.length > 0) {
        setSelectedWeekId(weeks[0].id);
      }
    }
  }, [weeks, selectedWeekId]);

  // Match single entry to ComicVine
  const matchEntryToComicvine = useCallback(async (entry: WeeklyReleaseItem) => {
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${entry.week_id}/entries/${entry.id}/match-comicvine`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to match to ComicVine: ${response.statusText}`);
      }
      const updatedEntry = await response.json();
      // Reload entries to show updated data
      await loadEntries(entry.week_id);
      return updatedEntry;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to match to ComicVine");
      toast.error(`Error: ${err instanceof Error ? err.message : "Failed to match to ComicVine"}`);
      throw err;
    }
  }, [loadEntries]);

  // Match single entry to library
  const matchEntryToLibrary = useCallback(async (entry: WeeklyReleaseItem) => {
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${entry.week_id}/entries/${entry.id}/match-library`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to match to library: ${response.statusText}`);
      }
      // Reload entries to show updated data
      await loadEntries(entry.week_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to match to library");
      toast.error(`Error: ${err instanceof Error ? err.message : "Failed to match to library"}`);
    }
  }, [loadEntries]);

  // Handle volume picker selection
  const handleVolumePickerSelect = useCallback(async (entry: WeeklyReleaseItem, volumeId: number) => {
    setError(null);
    try {
      // Update entry with selected volume
      const response = await fetch(buildApiUrl(`/api/releases/${entry.week_id}/entries/${entry.id}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          comicvine_volume_id: volumeId,
          status: "manual_match",
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to update entry: ${response.statusText}`);
      }
      setVolumePickerEntry(null);
      // Reload entries to show updated data
      await loadEntries(entry.week_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update entry");
      toast.error(`Error: ${err instanceof Error ? err.message : "Failed to update entry"}`);
    }
  }, [loadEntries]);

  // Identify entry (troubleshooting)
  const identifyEntry = useCallback(async (entry: WeeklyReleaseItem) => {
    setDiagnosticEntry(entry);
    setDiagnosticLoading(true);
    setDiagnosticData(null);

    try {
      const response = await fetch(buildApiUrl(`/api/releases/${entry.week_id}/entries/${entry.id}/identify`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to identify entry: ${response.statusText}`);
      }
      const data = await response.json();
      setDiagnosticData(data);
      // Reload entries to show updated ComicVine data
      await loadEntries(entry.week_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to identify entry");
      setDiagnosticData({ error: err instanceof Error ? err.message : "Failed to identify entry" });
    } finally {
      setDiagnosticLoading(false);
    }
  }, [loadEntries]);

  // Reset matches for entry
  const resetEntryMatches = useCallback(async (entry: WeeklyReleaseItem) => {
    // Confirmation removed - proceed directly

    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${entry.week_id}/entries/${entry.id}/reset-matches`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to reset matches: ${response.statusText}`);
      }
      // Reload entries to show updated data
      await loadEntries(entry.week_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset matches");
    }
  }, [loadEntries]);

  // Start polling for matching job status (only polls for selected week)
  const startPollingMatchingJobStatus = useCallback((weekId: string, matchType: 'cv' | 'library') => {
    // Only poll if this is the selected week
    if (weekId !== selectedWeekId) {
      return;
    }

    // Clear any existing polling interval
    if (matchingPollIntervalRef.current) {
      clearInterval(matchingPollIntervalRef.current);
      matchingPollIntervalRef.current = null;
    }

    // Map frontend match type to backend match type
    const backendMatchType = matchType === 'cv' ? 'comicvine' : matchType;

    // Poll immediately to get current status (don't wait for first interval)
    const pollOnce = async () => {
      try {
        const statusResponse = await fetch(buildApiUrl(`/api/releases/${weekId}/match-bulk/status?match_type=${backendMatchType}`), {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });
        if (statusResponse.ok) {
          const statusData = await statusResponse.json();
          if (statusData.status === "processing" || statusData.status === "queued" || statusData.status === "paused") {
            setMatchingJobs(prev => {
              const next = new Map(prev);
              next.set(weekId, {
                type: matchType,
                progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
                paused: statusData.status === "paused",
              });
              return next;
            });
          }
        }
      } catch (err) {
        console.error("Error polling matching job status:", err);
      }
    };
    pollOnce();

    // Start polling for job status
    const pollInterval = setInterval(async () => {
      // Only continue polling if this is still the selected week
      if (weekId !== selectedWeekId) {
        clearInterval(pollInterval);
        matchingPollIntervalRef.current = null;
        return;
      }

      try {
        const statusResponse = await fetch(buildApiUrl(`/api/releases/${weekId}/match-bulk/status?match_type=${backendMatchType}`), {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });
        if (!statusResponse.ok) {
          clearInterval(pollInterval);
          setMatchingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          matchingPollIntervalRef.current = null;
          return;
        }
        const statusData = await statusResponse.json();

        if (statusData.status === "processing" || statusData.status === "queued") {
          setMatchingJobs(prev => {
            const next = new Map(prev);
            next.set(weekId, {
              type: matchType,
              progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
              paused: false,
            });
            return next;
          });
        } else if (statusData.status === "paused") {
          setMatchingJobs(prev => {
            const next = new Map(prev);
            const existing = next.get(weekId);
            next.set(weekId, {
              type: matchType,
              progress: existing?.progress || { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
              paused: true,
            });
            return next;
          });
        } else if (statusData.status === "completed") {
          clearInterval(pollInterval);
          setMatchingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          matchingPollIntervalRef.current = null;
          // Reload entries and weeks
          await loadEntries(weekId);
          await loadWeeks();
          const matched = statusData.matched_count || 0;
          const errors = statusData.error_count || 0;
          if (matched > 0 && errors > 0) {
            toast.info(`${matched} matched, ${errors} not found`);
          } else if (matched > 0) {
            toast.success(`${matched} matched`);
          } else if (errors > 0) {
            toast.error(`${errors} not found`);
          }
        } else if (statusData.status === "failed") {
          clearInterval(pollInterval);
          setMatchingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          matchingPollIntervalRef.current = null;
          const errorMsg = statusData.error || "Matching failed";
          setError(errorMsg);
          toast.error(`Matching failed: ${errorMsg}`);
        } else if (statusData.status === "none") {
          // No active job, stop polling and remove from map
          clearInterval(pollInterval);
          setMatchingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          matchingPollIntervalRef.current = null;
        }
      } catch (err) {
        console.error("Error polling matching job status:", err);
      }
    }, 2000); // Poll every 2 seconds

    matchingPollIntervalRef.current = pollInterval;

    // Stop polling after 10 minutes
    setTimeout(() => {
      if (matchingPollIntervalRef.current === pollInterval) {
        clearInterval(pollInterval);
        matchingPollIntervalRef.current = null;
      }
    }, 10 * 60 * 1000);
  }, [selectedWeekId, loadEntries, loadWeeks]);

  // Check for active matching job and restore progress
  const checkActiveMatchingJob = useCallback(async (weekId: string, matchType: 'cv' | 'library') => {
    try {
      // Map frontend match type to backend match type
      const backendMatchType = matchType === 'cv' ? 'comicvine' : matchType;
      const statusResponse = await fetch(buildApiUrl(`/api/releases/${weekId}/match-bulk/status?match_type=${backendMatchType}`), {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (!statusResponse.ok) {
        return;
      }
      const statusData = await statusResponse.json();

      if (statusData.status === "processing" || statusData.status === "queued") {
        // Restore progress state to map
        setMatchingJobs(prev => {
          const next = new Map(prev);
          next.set(weekId, {
            type: matchType,
            progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
            paused: false,
          });
          return next;
        });
        // Start polling if this is the selected week
        if (weekId === selectedWeekId) {
          startPollingMatchingJobStatus(weekId, matchType);
        }
      } else if (statusData.status === "paused") {
        // Restore paused state to map
        setMatchingJobs(prev => {
          const next = new Map(prev);
          next.set(weekId, {
            type: matchType,
            progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
            paused: true,
          });
          return next;
        });
        // Start polling if this is the selected week
        if (weekId === selectedWeekId) {
          startPollingMatchingJobStatus(weekId, matchType);
        }
      }
    } catch (err) {
      console.error("Error checking active matching job:", err);
    }
  }, [selectedWeekId, startPollingMatchingJobStatus]);

  // Bulk match to ComicVine (now uses background job)
  const bulkMatchToComicvine = useCallback(async (entryIds: string[]) => {
    if (entryIds.length === 0) {
      toast.info("No entries selected for ComicVine match.");
      return;
    }
    if (!selectedWeekId) {
      toast.error("No week selected.");
      return;
    }

    setError(null);

    // Set initial progress immediately (will be updated by polling)
    setMatchingJobs(prev => {
      const next = new Map(prev);
      next.set(selectedWeekId, {
        type: 'cv',
        progress: { current: 0, total: entryIds.length },
        paused: false,
      });
      return next;
    });

    try {
      // Start the matching job
      const response = await fetch(buildApiUrl(`/api/releases/${selectedWeekId}/match-bulk`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          match_type: "comicvine",
          entry_ids: entryIds,
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to start matching: ${response.statusText}`);
      }
      const data = await response.json();

      if (!data.job_id) {
        throw new Error("No job ID returned from server");
      }

      // Update progress from job creation response if available
      if (data.progress) {
        setMatchingJobs(prev => {
          const next = new Map(prev);
          next.set(selectedWeekId, {
            type: 'cv',
            progress: { current: data.progress.current || 0, total: data.progress.total || entryIds.length },
            paused: false,
          });
          return next;
        });
      }

      // Start polling for job status (only if this is the selected week)
      if (selectedWeekId) {
        startPollingMatchingJobStatus(selectedWeekId, 'cv');
      }

      toast.info("Matching started");
    } catch (err) {
      // Remove job from map on error
      setMatchingJobs(prev => {
        const next = new Map(prev);
        next.delete(selectedWeekId);
        return next;
      });
      const errorMessage = err instanceof Error ? err.message : "Failed to start matching";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, [selectedWeekId, startPollingMatchingJobStatus]);

  // Bulk match to library (now uses background job)
  const bulkMatchToLibrary = useCallback(async (entryIds: string[]) => {
    if (entryIds.length === 0) {
      toast.info("No entries selected for library match.");
      return;
    }
    if (!selectedWeekId) {
      toast.error("No week selected.");
      return;
    }

    setError(null);

    // Set initial progress immediately (will be updated by polling)
    setMatchingJobs(prev => {
      const next = new Map(prev);
      next.set(selectedWeekId, {
        type: 'library',
        progress: { current: 0, total: entryIds.length },
        paused: false,
      });
      return next;
    });

    try {
      // Start the matching job
      const response = await fetch(buildApiUrl(`/api/releases/${selectedWeekId}/match-bulk`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          match_type: "library",
          entry_ids: entryIds,
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to start matching: ${response.statusText}`);
      }
      const data = await response.json();

      if (!data.job_id) {
        throw new Error("No job ID returned from server");
      }

      // Update progress from job creation response if available
      if (data.progress) {
        setMatchingJobs(prev => {
          const next = new Map(prev);
          next.set(selectedWeekId, {
            type: 'library',
            progress: { current: data.progress.current || 0, total: data.progress.total || entryIds.length },
            paused: false,
          });
          return next;
        });
      }

      // Start polling for job status (only if this is the selected week)
      if (selectedWeekId) {
        startPollingMatchingJobStatus(selectedWeekId, 'library');
      }

      toast.info("Matching started");
    } catch (err) {
      // Remove job from map on error
      setMatchingJobs(prev => {
        const next = new Map(prev);
        next.delete(selectedWeekId);
        return next;
      });
      const errorMessage = err instanceof Error ? err.message : "Failed to start matching";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, [selectedWeekId, startPollingMatchingJobStatus]);

  // Bulk reset matches
  const bulkResetMatches = useCallback(async (entryIds: string[]) => {
    if (entryIds.length === 0) {
      toast.info("No entries selected");
      return;
    }
    // Confirmation removed - proceed directly

    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${selectedWeekId}/entries/bulk-reset-matches`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_ids: entryIds }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to reset matches: ${response.statusText}`);
      }
      // Reload entries to show updated data
      await loadEntries(selectedWeekId!);
      setSelectedEntryIds(new Set());
      // Success message removed - user can see the results in the UI
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset matches");
      toast.error(`Error: ${err instanceof Error ? err.message : "Failed to reset matches"}`);
    }
  }, [selectedWeekId, loadEntries]);

  // Bulk update status
  const bulkUpdateStatus = useCallback(async (entryIds: string[], status: "pending" | "import" | "skipped" | "processed") => {
    if (entryIds.length === 0) {
      toast.info("No entries selected");
      return;
    }

    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${selectedWeekId}/entries/bulk-update-status`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_ids: entryIds, status }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to update status: ${response.statusText}`);
      }
      // Reload entries to show updated data
      await loadEntries(selectedWeekId!);
      setSelectedEntryIds(new Set());
      toast.success(`Updated status to ${status} for ${entryIds.length} entry(ies)`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
      toast.error(`Error: ${err instanceof Error ? err.message : "Failed to update status"}`);
    }
  }, [selectedWeekId, loadEntries]);

  // Toggle entry selection
  const toggleEntrySelection = useCallback((entryId: string) => {
    setSelectedEntryIds((prev) => {
      const next = new Set(prev);
      if (next.has(entryId)) {
        next.delete(entryId);
      } else {
        next.add(entryId);
      }
      return next;
    });
  }, []);

  // Start polling for job status (only polls for selected week)
  const startPollingJobStatus = useCallback((weekId: string) => {
    // Only poll if this is the selected week
    if (weekId !== selectedWeekId) {
      return;
    }

    // Clear any existing polling interval
    if (processingPollIntervalRef.current) {
      clearInterval(processingPollIntervalRef.current);
      processingPollIntervalRef.current = null;
    }

    // Start polling for job status
    const pollInterval = setInterval(async () => {
      // Only continue polling if this is still the selected week
      if (weekId !== selectedWeekId) {
        clearInterval(pollInterval);
        processingPollIntervalRef.current = null;
        return;
      }

      try {
        const statusResponse = await fetch(buildApiUrl(`/api/releases/${weekId}/process/status`), {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });
        if (!statusResponse.ok) {
          clearInterval(pollInterval);
          setProcessingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          processingPollIntervalRef.current = null;
          return;
        }
        const statusData = await statusResponse.json();

        if (statusData.status === "processing" || statusData.status === "queued") {
          setProcessingJobs(prev => {
            const next = new Map(prev);
            next.set(weekId, {
              progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
              paused: false,
            });
            return next;
          });
        } else if (statusData.status === "paused") {
          setProcessingJobs(prev => {
            const next = new Map(prev);
            const existing = next.get(weekId);
            next.set(weekId, {
              progress: existing?.progress || { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
              paused: true,
            });
            return next;
          });
        } else if (statusData.status === "completed") {
          clearInterval(pollInterval);
          setProcessingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          processingPollIntervalRef.current = null;
          // Reload entries and weeks
          await loadEntries(weekId);
          await loadWeeks();
          const processed = statusData.progress?.current || 0;
          const errors = statusData.error_count || 0;
          if (errors > 0) {
            const errorMsg = statusData.error || `${errors} item(s) failed to process`;
            toast.warning(`Processing completed with errors: ${processed} processed, ${errors} failed. ${errorMsg}`);
          } else {
            toast.success(`Processing completed: ${processed} items processed`);
          }
        } else if (statusData.status === "failed") {
          clearInterval(pollInterval);
          setProcessingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          processingPollIntervalRef.current = null;
          const errorMsg = statusData.error || "Processing failed";
          setError(errorMsg);
          toast.error(`Processing failed: ${errorMsg}`);
        } else if (statusData.status === "none") {
          // No active job, stop polling and remove from map
          clearInterval(pollInterval);
          setProcessingJobs(prev => {
            const next = new Map(prev);
            next.delete(weekId);
            return next;
          });
          processingPollIntervalRef.current = null;
        }
      } catch (err) {
        console.error("Error polling job status:", err);
      }
    }, 2000); // Poll every 2 seconds

    processingPollIntervalRef.current = pollInterval;

    // Stop polling after 10 minutes
    setTimeout(() => {
      if (processingPollIntervalRef.current === pollInterval) {
        clearInterval(pollInterval);
        processingPollIntervalRef.current = null;
      }
    }, 10 * 60 * 1000);
  }, [selectedWeekId, loadEntries, loadWeeks]);

  // Check for active processing job and restore progress
  const checkActiveJob = useCallback(async (weekId: string) => {
    try {
      const statusResponse = await fetch(buildApiUrl(`/api/releases/${weekId}/process/status`), {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (!statusResponse.ok) {
        return;
      }
      const statusData = await statusResponse.json();

      if (statusData.status === "processing" || statusData.status === "queued") {
        // Restore progress state to map
        setProcessingJobs(prev => {
          const next = new Map(prev);
          next.set(weekId, {
            progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
            paused: false,
          });
          return next;
        });
        // Start polling if this is the selected week
        if (weekId === selectedWeekId) {
          startPollingJobStatus(weekId);
        }
      } else if (statusData.status === "paused") {
        // Restore paused state to map
        setProcessingJobs(prev => {
          const next = new Map(prev);
          next.set(weekId, {
            progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
            paused: true,
          });
          return next;
        });
        // Start polling if this is the selected week
        if (weekId === selectedWeekId) {
          startPollingJobStatus(weekId);
        }
      }
    } catch (err) {
      console.error("Error checking active job:", err);
    }
  }, [selectedWeekId, startPollingJobStatus]);

  // Process week (now uses background job)
  const processWeek = useCallback(async (weekId: string) => {
    setError(null);

    try {
      // Start the processing job
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/process`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to start processing: ${response.statusText}`);
      }
      const data = await response.json();

      if (!data.job_id) {
        throw new Error("No job ID returned from server");
      }

      // Set initial progress in map
      if (data.progress) {
        setProcessingJobs(prev => {
          const next = new Map(prev);
          next.set(weekId, {
            progress: { current: data.progress.current || 0, total: data.progress.total || 0 },
            paused: false,
          });
          return next;
        });
      }

      // Start polling for job status (only if this is the selected week)
      if (weekId === selectedWeekId) {
        startPollingJobStatus(weekId);
      }

      toast.info("Processing started");
    } catch (err) {
      // Remove job from map on error
      setProcessingJobs(prev => {
        const next = new Map(prev);
        next.delete(weekId);
        return next;
      });
      const errorMessage = err instanceof Error ? err.message : "Failed to start processing";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, [selectedWeekId, startPollingJobStatus]);

  // Pause processing job
  const pauseProcessing = useCallback(async (weekId: string) => {
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/process/pause`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to pause processing: ${response.statusText}`);
      }
      setProcessingJobs(prev => {
        const next = new Map(prev);
        const existing = next.get(weekId);
        if (existing) {
          next.set(weekId, { ...existing, paused: true });
        }
        return next;
      });
      toast.info("Processing paused");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to pause processing";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, []);

  // Resume processing job
  const resumeProcessing = useCallback(async (weekId: string) => {
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/process/resume`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to resume processing: ${response.statusText}`);
      }
      setProcessingJobs(prev => {
        const next = new Map(prev);
        const existing = next.get(weekId);
        if (existing) {
          next.set(weekId, { ...existing, paused: false });
        }
        return next;
      });
      toast.info("Processing resumed");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to resume processing";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, []);

  // Pause matching job
  const pauseMatching = useCallback(async (weekId: string, matchType: 'cv' | 'library') => {
    setError(null);
    try {
      const backendMatchType = matchType === 'cv' ? 'comicvine' : matchType;
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/match-bulk/pause?match_type=${backendMatchType}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to pause matching: ${response.statusText}`);
      }
      setMatchingJobs(prev => {
        const next = new Map(prev);
        const existing = next.get(weekId);
        if (existing && existing.type === matchType) {
          next.set(weekId, { ...existing, paused: true });
        }
        return next;
      });
      toast.info("Matching paused");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to pause matching";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, []);

  // Resume matching job
  const resumeMatching = useCallback(async (weekId: string, matchType: 'cv' | 'library') => {
    setError(null);
    try {
      const backendMatchType = matchType === 'cv' ? 'comicvine' : matchType;
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/match-bulk/resume?match_type=${backendMatchType}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to resume matching: ${response.statusText}`);
      }
      setMatchingJobs(prev => {
        const next = new Map(prev);
        const existing = next.get(weekId);
        if (existing && existing.type === matchType) {
          next.set(weekId, { ...existing, paused: false });
        }
        return next;
      });
      toast.info("Matching resumed");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to resume matching";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, []);

  // Restart processing job
  const restartProcessing = useCallback(async (weekId: string) => {
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/process/restart`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to restart processing: ${response.statusText}`);
      }
      // Update job in map
      const data = await response.json();
      setProcessingJobs(prev => {
        const next = new Map(prev);
        next.set(weekId, {
          progress: { current: data.progress?.current || 0, total: data.progress?.total || 0 },
          paused: false,
        });
        return next;
      });
      // Start polling
      if (weekId === selectedWeekId) {
        startPollingJobStatus(weekId);
      }
      toast.info("Processing restarted");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to restart processing";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, [selectedWeekId, startPollingJobStatus]);

  // Restart matching job
  const restartMatching = useCallback(async (weekId: string, matchType: 'cv' | 'library') => {
    setError(null);
    try {
      const backendMatchType = matchType === 'cv' ? 'comicvine' : matchType;
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}/match-bulk/restart?match_type=${backendMatchType}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to restart matching: ${response.statusText}`);
      }
      // Update job in map
      const data = await response.json();
      setMatchingJobs(prev => {
        const next = new Map(prev);
        next.set(weekId, {
          type: matchType,
          progress: { current: data.progress?.current || 0, total: data.progress?.total || 0 },
          paused: false,
        });
        return next;
      });
      // Start polling
      if (weekId === selectedWeekId) {
        startPollingMatchingJobStatus(weekId, matchType);
      }
      toast.info("Matching restarted");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to restart matching";
      setError(errorMessage);
      toast.error(`Error: ${errorMessage}`);
    }
  }, [selectedWeekId, startPollingMatchingJobStatus]);

  // Delete week
  const deleteWeek = useCallback(async (weekId: string) => {
    // Confirmation removed - proceed directly
    setDeletingWeekId(weekId);
    setError(null);
    try {
      const response = await fetch(buildApiUrl(`/api/releases/${weekId}`), {
        method: "DELETE",
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete week: ${response.statusText}`);
      }
      // Reload weeks
      await loadWeeks();
      // Clear selection if deleted week was selected
      if (selectedWeekId === weekId) {
        setSelectedWeekId(null);
        setEntries([]);
      }
      // Success message removed - user can see the week is gone from the list
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete week");
      toast.error(`Error: ${err instanceof Error ? err.message : "Failed to delete week"}`);
    } finally {
      setDeletingWeekId(null);
    }
  }, [loadWeeks, selectedWeekId]);

  // Load weeks on mount
  useEffect(() => {
    loadWeeks();
  }, [loadWeeks]);

  // Load entries when week is selected
  useEffect(() => {
    if (selectedWeekId) {
      loadEntries(selectedWeekId);
      setSelectedEntryIds(new Set()); // Clear selection when switching weeks
      // Check for active processing job and restore progress
      checkActiveJob(selectedWeekId);
      // Check for active matching jobs and restore progress
      checkActiveMatchingJob(selectedWeekId, 'cv');
      checkActiveMatchingJob(selectedWeekId, 'library');
    } else {
      // Stop polling when no week is selected
      if (processingPollIntervalRef.current) {
        clearInterval(processingPollIntervalRef.current);
        processingPollIntervalRef.current = null;
      }
      if (matchingPollIntervalRef.current) {
        clearInterval(matchingPollIntervalRef.current);
        matchingPollIntervalRef.current = null;
      }
      // Note: Don't clear maps - jobs continue in background
    }
  }, [selectedWeekId, loadEntries, checkActiveJob, checkActiveMatchingJob]);

  // Start polling for selected week's jobs (separate effect, only when selectedWeekId changes)
  // This effect should NOT depend on matchingJobs/processingJobs to avoid re-running when Maps update
  useEffect(() => {
    if (!selectedWeekId) return;

    // Use a small delay to let checkActiveJob/checkActiveMatchingJob populate the maps first
    const timeoutId = setTimeout(() => {
      const matchingJob = matchingJobs.get(selectedWeekId);
      if (matchingJob) {
        startPollingMatchingJobStatus(selectedWeekId, matchingJob.type);
      }
      const processingJob = processingJobs.get(selectedWeekId);
      if (processingJob) {
        startPollingJobStatus(selectedWeekId);
      }
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [selectedWeekId, startPollingMatchingJobStatus, startPollingJobStatus]);


  // Cleanup polling intervals on unmount
  useEffect(() => {
    return () => {
      if (processingPollIntervalRef.current) {
        clearInterval(processingPollIntervalRef.current);
        processingPollIntervalRef.current = null;
      }
      if (matchingPollIntervalRef.current) {
        clearInterval(matchingPollIntervalRef.current);
        matchingPollIntervalRef.current = null;
      }
    };
  }, []);

  // Close dropdowns when clicking outside
  // Dropdown closing is now handled by MultiSelectFilter components internally

  // Get unique publishers from entries
  const uniquePublishers = useMemo(() => {
    const publishers = new Set<string>();
    entries.forEach((entry) => {
      if (entry.publisher) {
        publishers.add(entry.publisher);
      }
    });
    return Array.from(publishers).sort();
  }, [entries]);

  // Helper: Get matching job for selected week
  const selectedWeekMatchingJob = useMemo(() => {
    if (!selectedWeekId) return null;
    return matchingJobs.get(selectedWeekId) || null;
  }, [selectedWeekId, matchingJobs]);

  // Helper: Get processing job for selected week
  const selectedWeekProcessingJob = useMemo(() => {
    if (!selectedWeekId) return null;
    return processingJobs.get(selectedWeekId) || null;
  }, [selectedWeekId, processingJobs]);

  // Check if any bulk operation is active for the selected week
  const isOperationActive = useMemo(() => {
    return selectedWeekMatchingJob !== null || selectedWeekProcessingJob !== null;
  }, [selectedWeekMatchingJob, selectedWeekProcessingJob]);

  // Filter and sort entries

  const filteredEntries = useMemo(() => {
    let filtered = [...entries];

    // Status filters (multi-select)
    if (statusFilters.size > 0) {
      filtered = filtered.filter((e) => statusFilters.has(e.status as StatusFilter));
    }

    // Source filters (multi-select)
    if (sourceFilters.size > 0) {
      filtered = filtered.filter((e) => {
        if (sourceFilters.has("combined")) {
          return e.source === "combined" || sourceFilters.has(e.source as SourceFilter);
        }
        return sourceFilters.has(e.source as SourceFilter);
      });
    }

    // Publisher filters (multi-select)
    if (publisherFilters.size > 0) {
      filtered = filtered.filter((e) => e.publisher && publisherFilters.has(e.publisher));
    }

    // Matched filters (multi-select)
    if (matchedFilters.size > 0) {
      filtered = filtered.filter((e) => {
        const hasComicvine = (e.comicvine_volume_id !== null && e.comicvine_volume_id !== undefined) ||
          (e.comicvine_issue_id !== null && e.comicvine_issue_id !== undefined);
        const hasLibrary = (e.matched_volume_id !== null && e.matched_volume_id !== undefined) ||
          (e.matched_issue_id !== null && e.matched_issue_id !== undefined);
        const hasNone = !hasComicvine && !hasLibrary;

        if (matchedFilters.has("none") && hasNone) return true;
        if (matchedFilters.has("library") && hasLibrary) return true;
        if (matchedFilters.has("comicvine") && hasComicvine) return true;
        return false;
      });
    }

    // Library filter (toggle)
    if (inLibraryFilter === true) {
      filtered = filtered.filter((e) => e.matched_issue_id !== null && e.matched_issue_id !== undefined);
    } else if (inLibraryFilter === false) {
      filtered = filtered.filter((e) => e.matched_issue_id === null || e.matched_issue_id === undefined);
    }

    // Search term
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (e) =>
          e.title.toLowerCase().includes(term) ||
          e.publisher?.toLowerCase().includes(term) ||
          e.comicvine_volume_name?.toLowerCase().includes(term)
      );
    }

    // Sort by status (pending first), then title
    filtered.sort((a, b) => {
      const statusOrder: Record<string, number> = { pending: 0, import: 1, skipped: 2, processed: 3 };
      const statusDiff = (statusOrder[a.status] || 99) - (statusOrder[b.status] || 99);
      if (statusDiff !== 0) return statusDiff;
      return a.title.localeCompare(b.title);
    });

    return filtered;
  }, [entries, statusFilters, sourceFilters, publisherFilters, matchedFilters, inLibraryFilter, searchTerm]);

  // Toggle all entries selection (defined after filteredEntries)
  const toggleAllEntries = useCallback(() => {
    if (selectedEntryIds.size === filteredEntries.length) {
      setSelectedEntryIds(new Set());
    } else {
      setSelectedEntryIds(new Set(filteredEntries.map((e) => e.id)));
    }
  }, [filteredEntries, selectedEntryIds.size]);

  const selectNoneEntries = useCallback(() => {
    setSelectedEntryIds(new Set());
  }, []);

  const invertSelection = useCallback(() => {
    const allIds = new Set(filteredEntries.map((e) => e.id));
    const newSelection = new Set<string>();
    allIds.forEach((id) => {
      if (!selectedEntryIds.has(id)) {
        newSelection.add(id);
      }
    });
    setSelectedEntryIds(newSelection);
  }, [filteredEntries, selectedEntryIds]);

  const selectedWeek = weeks.find((w) => w.id === selectedWeekId);

  return (
    <div className="weekly-releases-page">
      {error && (
        <div className="alert alert-error">
          {error}
        </div>
      )}

      {/* Process weekly releases */}
      <section className="section-card">
        <h2>Process weekly releases</h2>
        <div className="section-card-content">
          {/* Row 1: Week selector and navigation */}
          <div className="section-row">
            <div className="week-selector-group">
              <label htmlFor="week-select" className="week-select-label">
                Week:
              </label>
              <select
                id="week-select"
                value={selectedWeekId || ""}
                onChange={(e) => setSelectedWeekId(e.target.value || null)}
                className="week-select"
                disabled={loadingWeeks}
              >
                <option value="">Select a week...</option>
                {weeks.map((week) => (
                  <option key={week.id} value={week.id}>
                    {formatDate(week.week_start)} ({week.counts.total} total, {week.counts.pending} pending, {week.counts.import} import, {week.counts.skipped} skipped, {week.counts.processed} processed)
                  </option>
                ))}
              </select>
            </div>
            <div className="week-navigation">
              <button
                className="btn btn-secondary btn-small"
                onClick={() => navigateWeek("prev")}
                disabled={weeks.length === 0}
                title="Previous week"
              >
                ← Prev
              </button>
              <button
                className="btn btn-secondary btn-small"
                onClick={() => navigateWeek("next")}
                disabled={weeks.length === 0}
                title="Next week"
              >
                Next →
              </button>
              <button
                className="btn btn-primary btn-small"
                onClick={() => setPullModalOpen(true)}
                title="Manual weekly data pull"
              >
                Manual Pull
              </button>
            </div>
          </div>

          {/* Row 2: Week actions */}
          {selectedWeekId && (
            <div className="section-row">
              <div className="week-actions">
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => deleteWeek(selectedWeekId)}
                  disabled={selectedWeekMatchingJob !== null || deletingWeekId === selectedWeekId || selectedWeekProcessingJob !== null}
                  title="Delete this week and all its entries"
                >
                  {deletingWeekId === selectedWeekId ? "Deleting..." : "Delete"}
                </button>
                <button
                  className="btn btn-primary btn-small"
                  onClick={() => processWeek(selectedWeekId)}
                  disabled={selectedWeekMatchingJob !== null || deletingWeekId === selectedWeekId || selectedWeekProcessingJob !== null}
                  title="Process all items with status 'import' - create/update library issues"
                >
                  {selectedWeekProcessingJob ? "Processing..." : "Process"}
                </button>
                {selectedWeekProcessingJob && (
                  <>
                    <div className="bulk-progress-indicator" style={{ marginLeft: "0.5rem", flex: 1, maxWidth: "300px" }}>
                      <span className="bulk-progress-text">
                        {selectedWeekProcessingJob.paused ? "Paused: " : "Processing: "}{selectedWeekProcessingJob.progress.current}/{selectedWeekProcessingJob.progress.total}
                      </span>
                      <div className="bulk-progress-bar">
                        <div
                          className="bulk-progress-fill"
                          style={{ width: `${selectedWeekProcessingJob.progress.total > 0 ? (selectedWeekProcessingJob.progress.current / selectedWeekProcessingJob.progress.total) * 100 : 0}%` }}
                        />
                      </div>
                    </div>
                    <button
                      className="btn btn-secondary btn-small"
                      onClick={() => restartProcessing(selectedWeekId)}
                      title="Restart processing"
                      style={{ marginLeft: "0.5rem" }}
                    >
                      <RotateCcw size={14} style={{ marginRight: "0.25rem" }} />
                      Restart
                    </button>
                    {selectedWeekProcessingJob.paused ? (
                      <button
                        className="btn btn-secondary btn-small"
                        onClick={() => resumeProcessing(selectedWeekId)}
                        title="Resume processing"
                        style={{ marginLeft: "0.5rem" }}
                      >
                        <Play size={14} style={{ marginRight: "0.25rem" }} />
                        Resume
                      </button>
                    ) : (
                      <button
                        className="btn btn-secondary btn-small"
                        onClick={() => pauseProcessing(selectedWeekId)}
                        title="Pause processing"
                        style={{ marginLeft: "0.5rem" }}
                      >
                        <Pause size={14} style={{ marginRight: "0.25rem" }} />
                        Pause
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Releases for selected week section */}
      {selectedWeekId && (
        <section className="section-card">
          <h2>Releases for {selectedWeek ? formatDate(selectedWeek.week_start) : "selected week"}</h2>
          <div className="section-card-content">
            {/* Filter summary */}
            <div className="filter-summary">
              Showing {filteredEntries.length} of {entries.length} entries
              {selectedWeek && ` (Total: ${selectedWeek.counts.total})`}
            </div>

            {/* Filter fields */}
            <div className="entries-filters">
              {/* Row 1: Search input */}
              <div className="filter-row">
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="search-input"
                />
              </div>

              {/* Row 2: Status, Sources, Publishers, Matched, In Library */}
              <div className="filter-row">
                <MultiSelectFilter
                  label="Status"
                  options={[
                    { value: 'pending', label: 'Pending' },
                    { value: 'import', label: 'Import' },
                    { value: 'skipped', label: 'Skipped' },
                  ]}
                  selected={statusFilters as Set<string>}
                  onChange={(selected) => setStatusFilters(selected as Set<StatusFilter>)}
                  placeholder="Statuses (All)"
                />
                <MultiSelectFilter
                  label="Source"
                  options={[
                    { value: 'previewsworld', label: formatSourceLabel('previewsworld') },
                    { value: 'comicgeeks', label: formatSourceLabel('comicgeeks') },
                    { value: 'readcomicsonline', label: formatSourceLabel('readcomicsonline') },
                    { value: 'combined', label: formatSourceLabel('combined') },
                  ]}
                  selected={sourceFilters as Set<string>}
                  onChange={(selected) => setSourceFilters(selected as Set<SourceFilter>)}
                  placeholder="Sources (All)"
                />
                <MultiSelectFilter
                  label="Publisher"
                  options={uniquePublishers.map((p) => ({ value: p, label: p }))}
                  selected={publisherFilters}
                  onChange={setPublisherFilters}
                  placeholder="Publishers (All)"
                />
                <MultiSelectFilter
                  label="Matched"
                  options={[
                    { value: 'none', label: 'None' },
                    { value: 'library', label: 'Library' },
                    { value: 'comicvine', label: 'ComicVine' },
                  ]}
                  selected={matchedFilters}
                  onChange={setMatchedFilters}
                  placeholder="Matched (All)"
                />
                <MultiSelectFilter
                  label="In Library"
                  options={[
                    { value: 'yes', label: 'Yes' },
                    { value: 'no', label: 'No' },
                  ]}
                  selected={inLibraryFilter === null ? new Set<string>() : inLibraryFilter ? new Set<string>(['yes']) : new Set<string>(['no'])}
                  onChange={(selected) => {
                    // Single-select behavior: only one option can be selected at a time
                    const wasYes = inLibraryFilter === true;
                    const wasNo = inLibraryFilter === false;
                    const nowYes = selected.has('yes');
                    const nowNo = selected.has('no');

                    // If clicking the same option that's already selected, deselect it (set to All)
                    if ((wasYes && nowYes && !nowNo) || (wasNo && nowNo && !nowYes)) {
                      setInLibraryFilter(null);
                    } else if (nowYes && !nowNo) {
                      setInLibraryFilter(true);
                    } else if (nowNo && !nowYes) {
                      setInLibraryFilter(false);
                    } else {
                      setInLibraryFilter(null);
                    }
                  }}
                  placeholder="In library (All)"
                />
              </div>

              {/* Row 3: Reset filters button */}
              <div className="filter-row">
                <button
                  className="btn btn-secondary btn-small"
                  onClick={() => {
                    setStatusFilters(new Set());
                    setSourceFilters(new Set());
                    setPublisherFilters(new Set());
                    setMatchedFilters(new Set());
                    setInLibraryFilter(null);
                    setSearchTerm("");
                  }}
                  disabled={statusFilters.size === 0 && sourceFilters.size === 0 && publisherFilters.size === 0 && matchedFilters.size === 0 && inLibraryFilter === null && searchTerm === ""}
                >
                  Reset Filters
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Issues section */}
      {selectedWeekId && (
        <section className="section-card">
          <h2>Issues</h2>
          <div className="section-card-content">
            {/* Bulk actions - shown when there's progress or selections (component handles visibility) */}
            <BulkActionsBar
              selectedCount={selectedEntryIds.size}
              progress={selectedWeekMatchingJob ? {
                current: selectedWeekMatchingJob.progress.current,
                total: selectedWeekMatchingJob.progress.total,
                label: selectedWeekMatchingJob.type === 'cv' ? 'Matching to ComicVine' : 'Matching to Library',
                paused: selectedWeekMatchingJob.paused,
              } : null}
              onPause={selectedWeekMatchingJob && selectedWeekId ? () => pauseMatching(selectedWeekId, selectedWeekMatchingJob.type) : undefined}
              onResume={selectedWeekMatchingJob && selectedWeekId ? () => resumeMatching(selectedWeekId, selectedWeekMatchingJob.type) : undefined}
              onRestart={selectedWeekMatchingJob && selectedWeekId ? () => restartMatching(selectedWeekId, selectedWeekMatchingJob.type) : undefined}
              actions={[
                {
                  label: selectedWeekMatchingJob?.type === 'cv' ? "Matching..." : "Match CV",
                  onClick: () => bulkMatchToComicvine(Array.from(selectedEntryIds)),
                  disabled: !selectedWeekId || selectedWeekMatchingJob !== null || deletingWeekId === selectedWeekId,
                  title: "Match selected items to ComicVine",
                },
                {
                  label: selectedWeekMatchingJob?.type === 'library' ? "Matching..." : "Match Library",
                  onClick: () => bulkMatchToLibrary(Array.from(selectedEntryIds)),
                  disabled: !selectedWeekId || selectedWeekMatchingJob !== null || deletingWeekId === selectedWeekId,
                  title: "Match selected items to your library",
                },
                {
                  label: "Reset Matches",
                  onClick: () => bulkResetMatches(Array.from(selectedEntryIds)),
                },
              ]}
            >
              {filteredEntries.length > 0 && selectedEntryIds.size > 0 && (
                <>
                  <label className="chip-select-label" style={{ marginRight: "0.5rem", display: "flex", alignItems: "center" }}>
                    Status:
                  </label>
                  <select
                    value={bulkStatusValue}
                    onChange={(e) => setBulkStatusValue(e.target.value)}
                    className="bulk-status-select"
                  >
                    <option value="pending">Pending</option>
                    <option value="import">Import</option>
                    <option value="processed">Processed</option>
                    <option value="skipped">Skipped</option>
                  </select>
                  <button
                    type="button"
                    className="btn btn-secondary btn-small"
                    onClick={() => bulkUpdateStatus(Array.from(selectedEntryIds), bulkStatusValue as "pending" | "import" | "skipped" | "processed")}
                  >
                    Set
                  </button>
                </>
              )}
            </BulkActionsBar>

            {loadingEntries ? (
              <div>Loading entries...</div>
            ) : filteredEntries.length === 0 ? (
              <div className="empty-state">No entries found.</div>
            ) : (
              <>
                {/* Selection controls */}
                <SelectionControls
                  selectedCount={selectedEntryIds.size}
                  totalCount={filteredEntries.length}
                  onSelectAll={toggleAllEntries}
                  onSelectNone={selectNoneEntries}
                  onInvertSelection={invertSelection}
                  disabled={isOperationActive}
                />

                {/* Issues grid list */}
                <div className="entries-grid">
                  {filteredEntries.map((entry) => (
                    <div key={entry.id} className={`entry-item status-${entry.status}`}>
                      <div className="entry-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedEntryIds.has(entry.id)}
                          onChange={() => toggleEntrySelection(entry.id)}
                          title="Select entry"
                          disabled={isOperationActive}
                        />
                      </div>
                      <div className="entry-main">
                        <div className="entry-title">{entry.title}</div>
                        <div className="entry-meta">
                          {entry.publisher && <span className="meta-item">{entry.publisher}</span>}
                          <span className="meta-item">{formatSourceLabel(entry.source)}</span>
                          {entry.release_date && (
                            <span className="meta-item">{formatDate(entry.release_date)}</span>
                          )}
                        </div>
                        {entry.comicvine_volume_name && (
                          <div className="entry-comicvine">
                            Matched: {entry.comicvine_volume_name}
                            {entry.comicvine_issue_number && ` #${entry.comicvine_issue_number}`}
                          </div>
                        )}
                        {entry.library_volume && (
                          <div className="entry-library">
                            Matched: {entry.library_volume.title}
                            {entry.library_issue && ` #${entry.library_issue.number}`}
                            {entry.library_issue?.file_path && " (with file)"}
                          </div>
                        )}
                      </div>
                      <div className="entry-actions">
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-status"
                          onClick={() => updateEntryStatus(entry.week_id, entry.id, "import")}
                          title="Import"
                          disabled={isOperationActive || !entry.comicvine_volume_id || entry.status === "import"}
                        >
                          <MapPinPlus size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-status"
                          onClick={() => updateEntryStatus(entry.week_id, entry.id, "skipped")}
                          title="Skip"
                          disabled={isOperationActive || entry.status === "skipped"}
                        >
                          <MapPinX size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-match"
                          onClick={() => matchEntryToComicvine(entry)}
                          title="Match CV"
                          disabled={isOperationActive || !!entry.comicvine_volume_id}
                        >
                          <MessageCircleCode size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-match"
                          onClick={() => matchEntryToLibrary(entry)}
                          title="Match Library"
                          disabled={isOperationActive || !!entry.matched_volume_id}
                        >
                          <BookOpen size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-match"
                          onClick={async () => {
                            // If no ComicVine results, search first
                            if (!entry.cv_results_sample && !entry.comicvine_volume_id) {
                              try {
                                const updatedEntry = await matchEntryToComicvine(entry);
                                // Use the updated entry from the response, which includes cv_results_sample
                                if (updatedEntry && updatedEntry.cv_results_sample) {
                                  setVolumePickerEntry(updatedEntry as WeeklyReleaseItem);
                                } else {
                                  // Fallback: reload and find the entry
                                  await loadEntries(entry.week_id);
                                  setTimeout(() => {
                                    const foundEntry = entries.find(e => e.id === entry.id);
                                    setVolumePickerEntry(foundEntry || entry);
                                  }, 100);
                                }
                              } catch (err) {
                                console.error("Failed to search ComicVine:", err);
                                // Still open the picker even if search fails
                                setVolumePickerEntry(entry);
                              }
                            } else {
                              setVolumePickerEntry(entry);
                            }
                          }}
                          title="Pick Volume"
                          disabled={isOperationActive || !!entry.comicvine_volume_id}
                        >
                          <LayoutList size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-utility"
                          onClick={() => identifyEntry(entry)}
                          title="Identify entry and show diagnostic information"
                          disabled={isOperationActive}
                        >
                          <Activity size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-small btn-icon btn-utility"
                          onClick={() => resetEntryMatches(entry)}
                          title="Reset ComicVine and library matches"
                          disabled={isOperationActive || (!entry.comicvine_volume_id && !entry.matched_volume_id)}
                        >
                          <RotateCcw size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </section>
      )}

      {!selectedWeekId && (
        <section className="section-card">
          <div className="empty-state">Select a week to view releases.</div>
        </section>
      )}

      {/* Volume Picker Modal */}
      {volumePickerEntry && (
        <VolumePickerModal
          entry={{
            id: volumePickerEntry.id,
            file_name: volumePickerEntry.title,
            comicvine_volume_id: volumePickerEntry.comicvine_volume_id || null,
            comicvine_issue_id: volumePickerEntry.comicvine_issue_id || null,
            extracted_issue_number: volumePickerEntry.comicvine_issue_number || null,
            comicvine_issue_number: volumePickerEntry.comicvine_issue_number || null,
            title: volumePickerEntry.title,
            cv_results_sample: volumePickerEntry.cv_results_sample || null,
          }}
          onClose={() => setVolumePickerEntry(null)}
          onSelect={(volumeId) => handleVolumePickerSelect(volumePickerEntry, volumeId)}
          coverImageUrl={undefined}
          getIssueCoverUrl={() => {
            // Return ComicVine issue image URL if available
            if (volumePickerEntry?.comicvine_issue_id) {
              return `https://comicvine.gamespot.com/a/uploads/scale_medium/0/4/1/5/415-${volumePickerEntry.comicvine_issue_id}.jpg`;
            }
            return "";
          }}
        />
      )}

      {/* Diagnostic Modal */}
      {diagnosticEntry && (
        <div className="import-diagnostic-modal__overlay" onClick={() => setDiagnosticEntry(null)}>
          <div className="import-diagnostic-modal__dialog" onClick={(e) => e.stopPropagation()}>
            <div className="import-diagnostic-modal__header">
              <h2>Entry Identification Diagnostic</h2>
              <button className="import-diagnostic-modal__close" onClick={() => setDiagnosticEntry(null)}>
                ×
              </button>
            </div>
            <div className="import-diagnostic-modal__file-info">
              <strong>{diagnosticEntry.title}</strong>
              {diagnosticEntry.publisher && (
                <code className="import-diagnostic-modal__path">{diagnosticEntry.publisher}</code>
              )}
            </div>
            {diagnosticLoading ? (
              <div className="import-diagnostic-modal__loading">
                <p>Identifying entry...</p>
              </div>
            ) : diagnosticData ? (
              <div className="import-diagnostic-modal__content">
                {diagnosticData.errors && diagnosticData.errors.length > 0 && (
                  <div className="import-diagnostic-modal__section import-diagnostic-modal__section--error">
                    <h3>Errors</h3>
                    <ul>
                      {diagnosticData.errors.map((error: string, idx: number) => (
                        <li key={idx}>{error}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {diagnosticData.warnings && diagnosticData.warnings.length > 0 && (
                  <div className="import-diagnostic-modal__section import-diagnostic-modal__section--warning">
                    <h3>Warnings</h3>
                    <ul>
                      {diagnosticData.warnings.map((warning: string, idx: number) => (
                        <li key={idx}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {diagnosticData.steps && diagnosticData.steps.length > 0 && (
                  <div className="import-diagnostic-modal__section">
                    <h3>Identification Steps</h3>
                    {diagnosticData.steps.map((step: any, idx: number) => (
                      <div key={idx} className={`import-diagnostic-modal__step ${step.success ? "import-diagnostic-modal__step--success" : "import-diagnostic-modal__step--failed"}`}>
                        <div className="import-diagnostic-modal__step-header">
                          <span className="import-diagnostic-modal__step-number">{idx + 1}</span>
                          <strong>{step.step}</strong>
                          {step.success ? (
                            <span className="import-diagnostic-modal__step-status import-diagnostic-modal__step-status--success">✓</span>
                          ) : (
                            <span className="import-diagnostic-modal__step-status import-diagnostic-modal__step-status--failed">✗</span>
                          )}
                        </div>
                        <p className="import-diagnostic-modal__step-description">{step.description}</p>
                        {step.result && (
                          <div className="import-diagnostic-modal__step-result">
                            {step.step === "search_comicvine" ? (
                              <ComicVineSearchResultDisplay result={step.result} />
                            ) : (
                              <pre>{JSON.stringify(step.result, null, 2)}</pre>
                            )}
                          </div>
                        )}
                        {step.reason && (
                          <div className="import-diagnostic-modal__step-reason">
                            <strong>Reason:</strong> {step.reason}
                          </div>
                        )}
                        {step.error && (
                          <div className="import-diagnostic-modal__step-error">
                            <strong>Error:</strong> {step.error}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {diagnosticData.summary && (
                  <div className="import-diagnostic-modal__section">
                    <h3>Summary</h3>
                    <div className="import-diagnostic-modal__summary">
                      <div className="import-diagnostic-modal__summary-item">
                        <strong>Metadata Extracted:</strong> {diagnosticData.summary.metadata_extracted ? "✓ Yes" : "✗ No"}
                      </div>
                      <div className="import-diagnostic-modal__summary-item">
                        <strong>ComicVine Match Found:</strong> {diagnosticData.summary.comicvine_match_found ? "✓ Yes" : "✗ No"}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : null}
            <div className="import-diagnostic-modal__footer">
              <button className="btn btn-primary" onClick={() => setDiagnosticEntry(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual weekly data pull modal */}
      {pullModalOpen && (
        <div className="volume-picker-modal__overlay" onClick={() => setPullModalOpen(false)}>
          <div className="volume-picker-modal__dialog pull-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="volume-picker-modal__header">
              <h2>Manual weekly data pull</h2>
              <button
                className="volume-picker-modal__close"
                onClick={() => setPullModalOpen(false)}
                title="Close"
              >
                ×
              </button>
            </div>
            <div className="section-card-content">
              {/* Row 1: Date picker */}
              <div className="section-row">
                <div className="date-picker-container">
                  <label htmlFor="week-date-picker" className="date-picker-label">
                    Week:
                  </label>
                  <input
                    id="week-date-picker"
                    type="date"
                    value={selectedDate}
                    onChange={(e) => handleDateChange(e.target.value)}
                    onBlur={(e) => {
                      // Validate on blur as well
                      if (e.target.value && !isWednesday(new Date(e.target.value + "T00:00:00"))) {
                        handleDateChange(e.target.value);
                      }
                    }}
                    min={getMinDate()}
                    max={getMaxDate()}
                    className="date-picker-input"
                    title="Select a Wednesday date for the release week (past Wednesdays only, last 12 months). Non-Wednesday dates will be adjusted to the previous Wednesday."
                  />
                </div>
              </div>

              {/* Row 2: Fetch buttons */}
              <div className="section-row">
                <div className="week-actions">
                  <button
                    onClick={() => fetchReleases("previewsworld")}
                    disabled={fetchingSource !== null}
                    className="btn btn-primary btn-small"
                    title="Fetch PreviewsWorld"
                  >
                    {fetchingSource === "previewsworld" ? (
                      <span className="icon-loading">⟳</span>
                    ) : (
                      "PreviewsWorld"
                    )}
                  </button>
                  <button
                    onClick={() => fetchReleases("comicgeeks")}
                    disabled={fetchingSource !== null}
                    className="btn btn-primary btn-small"
                    title="Fetch League of Comic Geeks"
                  >
                    {fetchingSource === "comicgeeks" ? (
                      <span className="icon-loading">⟳</span>
                    ) : (
                      "League of Comic Geeks"
                    )}
                  </button>
                  <button
                    onClick={() => fetchReleases("readcomicsonline")}
                    disabled={fetchingSource !== null}
                    className="btn btn-primary btn-small"
                    title="Fetch ReadComicsOnline"
                  >
                    {fetchingSource === "readcomicsonline" ? (
                      <span className="icon-loading">⟳</span>
                    ) : (
                      "ReadComicsOnline"
                    )}
                  </button>
                  <button
                    disabled={true}
                    className="btn btn-primary btn-small"
                    title="Fetch GetComics"
                  >
                    GetComics
                  </button>
                </div>
              </div>

              {/* OK button to close modal */}
              <div className="section-row" style={{ marginTop: "1rem", justifyContent: "flex-end" }}>
                <button
                  className="btn btn-primary btn-small"
                  onClick={() => setPullModalOpen(false)}
                >
                  OK
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

