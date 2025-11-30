import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { toast } from "sonner";
import { apiGet, apiPost, apiPut, apiDelete, ApiClientError, buildApiUrl } from "../api/client";
import Toggle from "../components/Toggle";
import RadioGroup from "../components/RadioGroup";
import { VolumePickerModal } from "../components/VolumePickerModal";
import { BulkActionsBar } from "../components/BulkActionsBar";
import { SelectionControls } from "../components/SelectionControls";
import { MultiSelectFilter } from "../components/MultiSelectFilter";
import { MapPinPlus, MapPinX, MessageCircleCode, LayoutList, Activity, RotateCcw } from "lucide-react";
import "./ImportPage.css";

interface Library {
    id: string;
    name: string;
    library_root: string;
    default: boolean;
    enabled: boolean;
}

interface ImportJob {
    id: string;
    library_id: string;
    scan_type: "root_folders" | "external_folder";
    folder_path: string | null;
    link_files: boolean;
    status: "scanning" | "pending_review" | "processing" | "completed" | "cancelled";
    scanned_files: number;
    total_files: number;
    processed_files: number;
    matched_count: number;
    unmatched_count: number;
    approved_count: number;
    skipped_count: number;
    error: string | null;
    created_at: number;
    updated_at: number;
    completed_at: number | null;
}

interface ImportJobListResponse {
    jobs: ImportJob[];
    total: number;
}

interface ImportPendingFile {
    id: string;
    import_job_id: string;
    file_path: string;
    file_name: string;
    file_size: number;
    file_extension: string;
    status: "pending" | "import" | "skipped" | "processed";
    comicvine_match_type: "auto" | "manual" | null;
    matched_volume_id: string | null;
    matched_issue_id: string | null;
    matched_confidence: number | null;
    comicvine_volume_id: number | null;
    comicvine_issue_id: number | null;
    comicvine_volume_name: string | null;
    comicvine_issue_name: string | null;
    comicvine_issue_number: string | null;
    comicvine_issue_image: string | null;
    comicvine_confidence: number | null;
    cv_search_query: string | null;
    cv_results_count: number | null;
    cv_results_sample: string | null;
    cv_issue_filter: string | null;
    action: "link" | "create_volume" | "skip" | "move" | null;
    target_volume_id: string | null;
    target_issue_id: string | null;
    preview_rename_to: string | null;
    preview_convert_to: string | null;
    preview_metatag: boolean;
    extracted_series: string | null;
    extracted_issue_number: string | null;
    extracted_year: number | null;
    extracted_volume: string | null;
    notes: string | null;
    created_at: number;
    updated_at: number;
}

interface ImportPendingFileListResponse {
    pending_files: ImportPendingFile[];
    total: number;
    library_match: number;  // Files with library match
    comicvine_match: number;  // Files with ComicVine match
    pending: number;  // Status: pending
    import: number;  // Status: import (queued for import)
    skipped: number;  // Status: skipped
}

function formatDate(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

// Wrapper component to fetch cover image URL
function VolumePickerModalWithCover({ entry, onClose, onSelect, getIssueCoverUrl }: {
    entry: ImportPendingFile;
    onClose: () => void;
    onSelect: (volumeId: number) => Promise<void>;
    getIssueCoverUrl: (entryId: string, volumeId: number, issueNumber: string) => string;
}) {
    const [coverImageUrl, setCoverImageUrl] = useState<string | undefined>(undefined);

    useEffect(() => {
        // Always try to get the local file cover from the cover-image endpoint
        // This will extract the first page from the file
        const localCoverUrl = buildApiUrl(`/import/pending-files/${entry.id}/cover-image`);

        // Check if the file exists and is valid by trying to fetch the cover
        // We'll set the URL and let the image's onError handle failures
        setCoverImageUrl(localCoverUrl);
    }, [entry.id]);

    return (
        <VolumePickerModal
            entry={entry}
            onClose={onClose}
            onSelect={onSelect}
            coverImageUrl={coverImageUrl}
            getIssueCoverUrl={getIssueCoverUrl}
        />
    );
}

// Component to display ComicVine search results with scoring breakdown
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

function formatBytes(bytes: number): string {
    if (bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export default function ImportPage() {
    const [jobs, setJobs] = useState<ImportJob[]>([]);
    const [libraries, setLibraries] = useState<Library[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
    const [pendingFiles, setPendingFiles] = useState<ImportPendingFile[]>([]);
    const [pendingFilesLoading, setPendingFilesLoading] = useState(false);
    const [pendingFilesStats, setPendingFilesStats] = useState({ total: 0, library_match: 0, comicvine_match: 0, pending: 0, import: 0, skipped: 0 });
    // Filter state - using MultiSelectFilter approach like WeeklyReleasesPage
    type StatusFilter = "pending" | "import" | "skipped" | "processed";
    const [statusFilters, setStatusFilters] = useState<Set<StatusFilter>>(new Set());
    const [matchedFilters, setMatchedFilters] = useState<Set<string>>(new Set());
    const [publisherFilters, setPublisherFilters] = useState<Set<string>>(new Set());
    const [searchTerm, setSearchTerm] = useState("");
    const [volumePickerPendingFile, setVolumePickerPendingFile] = useState<ImportPendingFile | null>(null);
    const [diagnosticPendingFile, setDiagnosticPendingFile] = useState<ImportPendingFile | null>(null);
    const [diagnosticData, setDiagnosticData] = useState<any>(null);
    const [diagnosticLoading, setDiagnosticLoading] = useState(false);
    const [processConfirmJobId, setProcessConfirmJobId] = useState<string | null>(null);
    const [processPreview, setProcessPreview] = useState<any>(null);
    const [processPreviewLoading, setProcessPreviewLoading] = useState(false);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createLibraryId, setCreateLibraryId] = useState<string>("");
    const [createScanType, setCreateScanType] = useState<"root_folders" | "external_folder">("root_folders");
    const [createFolderPath, setCreateFolderPath] = useState("");
    const [createLinkFiles, setCreateLinkFiles] = useState(false);
    const [creating, setCreating] = useState(false);
    const [browserOpen, setBrowserOpen] = useState(false);
    const [browserPath, setBrowserPath] = useState<string | null>(null);
    const [browserParent, setBrowserParent] = useState<string | null>(null);
    const [browserEntries, setBrowserEntries] = useState<Array<{ path: string; name: string; readable: boolean; is_symlink: boolean }>>([]);
    const [browserLoading, setBrowserLoading] = useState(false);
    const [browserError, setBrowserError] = useState<string | null>(null);
    const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
    const [scanningJob, setScanningJob] = useState<{ progress: { current: number, total: number }, status: string } | null>(null);
    const [processingJob, setProcessingJob] = useState<{ progress: { current: number, total: number }, status: string } | null>(null);
    const scanningPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const processingPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        loadJobs();
        loadLibraries();
    }, []);

    // Poll for scanning job status
    const startPollingScanningJob = useCallback((jobId: string) => {
        if (scanningPollIntervalRef.current) {
            clearInterval(scanningPollIntervalRef.current);
        }
        
        const pollOnce = async () => {
            try {
                const response = await fetch(buildApiUrl(`/api/import/jobs/${jobId}/scanning/status`), {
                    method: "GET",
                    headers: { "Content-Type": "application/json" },
                });
                if (response.ok) {
                    const statusData = await response.json();
                    console.log("Scanning job status:", statusData);
                    if (statusData.status === "processing" || statusData.status === "queued" || statusData.status === "paused") {
                        setScanningJob({
                            progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
                            status: statusData.status,
                        });
                    } else if (statusData.status === "none") {
                        // Job not found yet, but ImportJob status is "scanning", so keep showing "Scanning..."
                        // Don't set to null, keep existing state or set a placeholder
                        console.log("Scanning job not found yet, but ImportJob is scanning");
                    } else if (statusData.status === "completed" || statusData.status === "failed") {
                        setScanningJob(null);
                    } else {
                        // Keep existing state if status is something else
                        console.log("Unexpected scanning job status:", statusData.status);
                    }
                } else {
                    console.error("Failed to fetch scanning job status:", response.status, response.statusText);
                }
            } catch (err) {
                console.error("Error polling scanning job status:", err);
            }
        };
        pollOnce();
        
        const pollInterval = setInterval(pollOnce, 2000);
        scanningPollIntervalRef.current = pollInterval;
    }, []);
    
    // Poll for processing job status
    const startPollingProcessingJob = useCallback((jobId: string) => {
        if (processingPollIntervalRef.current) {
            clearInterval(processingPollIntervalRef.current);
        }
        
        const pollOnce = async () => {
            try {
                const response = await fetch(buildApiUrl(`/api/import/jobs/${jobId}/processing/status`), {
                    method: "GET",
                    headers: { "Content-Type": "application/json" },
                });
                if (response.ok) {
                    const statusData = await response.json();
                    if (statusData.status === "processing" || statusData.status === "queued" || statusData.status === "paused") {
                        setProcessingJob({
                            progress: { current: statusData.progress?.current || 0, total: statusData.progress?.total || 0 },
                            status: statusData.status,
                        });
                    } else {
                        setProcessingJob(null);
                    }
                }
            } catch (err) {
                console.error("Error polling processing job status:", err);
            }
        };
        pollOnce();
        
        const pollInterval = setInterval(pollOnce, 2000);
        processingPollIntervalRef.current = pollInterval;
    }, []);

    useEffect(() => {
        if (selectedJobId) {
            // Reset filters when selecting a new job
            setStatusFilters(new Set());
            setMatchedFilters(new Set());
            setPublisherFilters(new Set());
            setSearchTerm("");
            setSelectedFileIds(new Set()); // Clear selection when switching jobs
            loadPendingFiles(selectedJobId);
            
            // Start polling for job status
            const job = jobs.find((j) => j.id === selectedJobId);
            if (job) {
                if (job.status === "scanning") {
                    startPollingScanningJob(selectedJobId);
                } else if (job.status === "processing") {
                    startPollingProcessingJob(selectedJobId);
                } else {
                    // Clear polling if job is not in scanning/processing state
                    if (scanningPollIntervalRef.current) {
                        clearInterval(scanningPollIntervalRef.current);
                        scanningPollIntervalRef.current = null;
                        setScanningJob(null);
                    }
                    if (processingPollIntervalRef.current) {
                        clearInterval(processingPollIntervalRef.current);
                        processingPollIntervalRef.current = null;
                        setProcessingJob(null);
                    }
                }
            } else {
                // Job not in list yet, try polling anyway (might be a new job)
                // We'll check the status endpoint to see if it's scanning/processing
                startPollingScanningJob(selectedJobId);
                startPollingProcessingJob(selectedJobId);
            }
            
            // Also poll for job updates
            const interval = setInterval(() => {
                if (selectedJobId) {
                    const job = jobs.find((j) => j.id === selectedJobId);
                    if (job && (job.status === "scanning" || job.status === "processing")) {
                        loadJobs();
                        loadPendingFiles(selectedJobId);
                    }
                }
            }, 3000);
            
            return () => {
                clearInterval(interval);
                if (scanningPollIntervalRef.current) {
                    clearInterval(scanningPollIntervalRef.current);
                    scanningPollIntervalRef.current = null;
                }
                if (processingPollIntervalRef.current) {
                    clearInterval(processingPollIntervalRef.current);
                    processingPollIntervalRef.current = null;
                }
                setScanningJob(null);
                setProcessingJob(null);
            };
        }
    }, [selectedJobId, jobs, startPollingScanningJob, startPollingProcessingJob]);

    async function loadJobs() {
        try {
            setLoading(true);
            const data = await apiGet<ImportJobListResponse>("/import/jobs");
            setJobs(data.jobs ?? []);
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to load import jobs";
            toast.error(message);
        } finally {
            setLoading(false);
        }
    }

    async function loadLibraries() {
        try {
            const data = await apiGet<{ libraries: Library[] }>("/libraries");
            const enabledLibraries = (data.libraries ?? []).filter((lib) => lib.enabled);
            setLibraries(enabledLibraries);
            if (enabledLibraries.length > 0 && !createLibraryId) {
                const defaultLib = enabledLibraries.find((lib) => lib.default) || enabledLibraries[0];
                setCreateLibraryId(defaultLib.id);
            }
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to load libraries";
            toast.error(message);
        }
    }

    async function loadPendingFiles(jobId: string) {
        try {
            setPendingFilesLoading(true);
            const data = await apiGet<ImportPendingFileListResponse>(`/import/jobs/${jobId}/pending-files`);
            setPendingFiles(data.pending_files ?? []);
            setPendingFilesStats({
                total: data.total,
                library_match: data.library_match || 0,
                comicvine_match: data.comicvine_match || 0,
                pending: data.pending,
                import: data.import || 0,
                skipped: data.skipped || 0,
            });
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to load pendingFiles";
            toast.error(message);
        } finally {
            setPendingFilesLoading(false);
        }
    }

    async function handleCreateJob() {
        if (!createLibraryId) {
            toast.error("Please select a library");
            return;
        }
        if (createScanType === "external_folder" && !createFolderPath.trim()) {
            toast.error("Folder path is required for external folder scans");
            return;
        }

        try {
            setCreating(true);
            const payload = {
                library_id: createLibraryId,
                scan_type: createScanType,
                folder_path: createScanType === "external_folder" ? createFolderPath.trim() : null,
                link_files: createLinkFiles,
            };
            const job = await apiPost<ImportJob>("/import/jobs", payload);
            toast.success("Import job created");
            setShowCreateModal(false);
            setCreateFolderPath("");
            setCreateLinkFiles(false);
            setCreateScanType("root_folders");
            await loadJobs();
            setSelectedJobId(job.id);
            // Start polling immediately if job is scanning
            if (job.status === "scanning") {
                startPollingScanningJob(job.id);
            } else if (job.status === "processing") {
                startPollingProcessingJob(job.id);
            }
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to create import job";
            toast.error(message);
        } finally {
            setCreating(false);
        }
    }

    async function handleProcessJobClick(jobId: string) {
        // Show confirmation modal with preview
        setProcessConfirmJobId(jobId);
        setProcessPreviewLoading(true);
        setProcessPreview(null);

        try {
            const preview = await apiGet(`/import/jobs/${jobId}/preview`);
            setProcessPreview(preview);
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to load preview";
            toast.error(message);
            setProcessConfirmJobId(null);
            setProcessPreview(null);
        } finally {
            setProcessPreviewLoading(false);
        }
    }

    async function handleProcessJobConfirm() {
        if (!processConfirmJobId) return;

        const jobId = processConfirmJobId;
        setProcessConfirmJobId(null);
        setProcessPreview(null);

        try {
            await apiPost(`/import/jobs/${jobId}/process`);
            toast.success("Processing started");
            await loadJobs();
            await loadPendingFiles(jobId);

            // Poll for updates while processing
            const pollInterval = setInterval(async () => {
                await loadJobs();
                const updatedJob = jobs.find((j) => j.id === jobId);
                if (updatedJob && updatedJob.status !== "processing") {
                    clearInterval(pollInterval);
                    if (updatedJob.status === "completed") {
                        toast.success("Import processing completed");
                    } else if (updatedJob.status === "pending_review" && updatedJob.error) {
                        toast.error(`Processing failed: ${updatedJob.error}`);
                    }
                    await loadPendingFiles(jobId);
                }
            }, 2000); // Poll every 2 seconds

            // Stop polling after 5 minutes
            setTimeout(() => clearInterval(pollInterval), 5 * 60 * 1000);
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to start processing";
            toast.error(message);
        }
    }

    async function handleIdentifyPendingFile(pendingFile: ImportPendingFile) {
        setDiagnosticPendingFile(pendingFile);
        setDiagnosticLoading(true);
        setDiagnosticData(null);

        try {
            const data = await apiPost<any>(`/import/pending-files/${pendingFile.id}/identify`);
            setDiagnosticData(data);
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to identify file";
            toast.error(message);
            setDiagnosticData({ error: message });
        } finally {
            setDiagnosticLoading(false);
        }
    }

    async function handleDeleteJob(jobId: string) {
        if (!confirm("Are you sure you want to delete this import job? This action cannot be undone.")) {
            return;
        }

        try {
            await apiDelete(`/import/jobs/${jobId}`);
            toast.success("Import job deleted");
            if (selectedJobId === jobId) {
                setSelectedJobId(null);
                setPendingFiles([]);
            }
            await loadJobs();
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to delete import job";
            toast.error(message);
            console.error("Delete job error:", err);
        }
    }

    async function handleUpdatePendingFile(jobId: string, pendingFileId: string, updates: Partial<ImportPendingFile>) {
        try {
            await apiPut<ImportPendingFile>(`/import/jobs/${jobId}/pending-files/${pendingFileId}`, updates);
            toast.success(updates.status === "skipped" ? "File skipped" : "File updated");
            await loadPendingFiles(jobId);
            await loadJobs();
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to update pending file";
            toast.error(message);
        }
    }

    async function handleBulkUpdatePendingFiles(jobId: string, fileIds: string[], updates: Partial<ImportPendingFile>) {
        if (fileIds.length === 0) {
            toast.error("No files selected");
            return;
        }

        try {
            // Update all selected files
            const promises = fileIds.map((fileId) =>
                apiPut<ImportPendingFile>(`/import/jobs/${jobId}/pending-files/${fileId}`, updates)
            );
            await Promise.all(promises);
            toast.success(`Updated ${fileIds.length} file${fileIds.length > 1 ? "s" : ""}`);
            setSelectedFileIds(new Set()); // Clear selection
            await loadPendingFiles(jobId);
            await loadJobs();
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to update files";
            toast.error(message);
        }
    }

    async function handleBulkUnapprovePendingFiles(jobId: string, fileIds: string[]) {
        if (fileIds.length === 0) {
            toast.error("No files selected");
            return;
        }

        try {
            // For each file, determine the appropriate status based on whether it has a match
            const promises = fileIds.map((fileId) => {
                const file = pendingFiles.find((f) => f.id === fileId);
                if (!file) {
                    return Promise.resolve();
                }

                // Set status to "pending" (unqueue from import)
                const newStatus = "pending";

                return apiPut<ImportPendingFile>(`/import/jobs/${jobId}/pending-files/${fileId}`, {
                    status: newStatus,
                    action: null,
                });
            });
            await Promise.all(promises);
            toast.success(`Set ${fileIds.length} file${fileIds.length > 1 ? "s" : ""} to pending`);
            setSelectedFileIds(new Set()); // Clear selection
            await loadPendingFiles(jobId);
            await loadJobs();
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to unapprove files";
            toast.error(message);
        }
    }

    function handleToggleFileSelection(fileId: string) {
        setSelectedFileIds((prev) => {
            const next = new Set(prev);
            if (next.has(fileId)) {
                next.delete(fileId);
            } else {
                next.add(fileId);
            }
            return next;
        });
    }


    function handleDeselectAllFiles() {
        setSelectedFileIds(new Set());
    }

    async function loadBrowserPath(path?: string | null) {
        setBrowserLoading(true);
        setBrowserError(null);
        try {
            const endpoint = path ? `/media/browse?path=${encodeURIComponent(path)}` : "/media/browse";
            const data = await apiGet<{
                path: string;
                parent: string | null;
                entries: Array<{ path: string; name: string; readable: boolean; is_symlink: boolean }>;
            }>(endpoint);
            setBrowserPath(data.path);
            setBrowserParent(data.parent);
            setBrowserEntries(data.entries);
        } catch (err) {
            const message = err instanceof ApiClientError ? err.message : "Failed to load directory";
            setBrowserError(message);
            setBrowserEntries([]);
        } finally {
            setBrowserLoading(false);
        }
    }

    function openFolderBrowser() {
        setBrowserOpen(true);
        void loadBrowserPath();
    }

    function closeFolderBrowser() {
        setBrowserOpen(false);
        setBrowserError(null);
        setBrowserEntries([]);
    }

    function applySelectedFolder() {
        if (!browserPath) {
            closeFolderBrowser();
            return;
        }
        setCreateFolderPath(browserPath);
        closeFolderBrowser();
    }

    function navigateToEntry(entryPath: string) {
        void loadBrowserPath(entryPath);
    }

    const selectedJob = selectedJobId ? jobs.find((j) => j.id === selectedJobId) : null;

    // Get unique publishers from pending files (unused for now)
    // @ts-expect-error - unused variable, may be used in future
    const _uniquePublishers = useMemo(() => {
        const publishers = new Set<string>();
        pendingFiles.forEach((file) => {
            // Extract publisher from ComicVine volume name if available
            // Or from extracted series if it contains publisher info
            // For now, we'll use ComicVine volume name as a proxy
            if (file.comicvine_volume_name) {
                // Publisher might be in the volume name, but we don't have it directly
                // We'll need to add publisher field to ImportPendingFile if available
            }
        });
        return Array.from(publishers).sort();
    }, [pendingFiles]);

    // Filter and sort pending files
    const filteredPendingFiles = useMemo(() => {
        let filtered = [...pendingFiles];

        // Status filters (multi-select)
        if (statusFilters.size > 0) {
            filtered = filtered.filter((f) => statusFilters.has(f.status as StatusFilter));
        }

        // Matched filters (multi-select) - check for library and ComicVine matches
        if (matchedFilters.size > 0) {
            filtered = filtered.filter((f) => {
                const hasLibrary = !!(f.matched_volume_id || f.matched_issue_id);
                const hasComicvine = !!(f.comicvine_volume_id || f.comicvine_issue_id);
                const hasNone = !hasLibrary && !hasComicvine;

                if (matchedFilters.has("none") && hasNone) return true;
                if (matchedFilters.has("library") && hasLibrary) return true;
                if (matchedFilters.has("comicvine") && hasComicvine) return true;
                return false;
            });
        }

        // Publisher filters (multi-select) - placeholder for now
        if (publisherFilters.size > 0) {
            // Will implement when publisher data is available
        }

        // Search term
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            filtered = filtered.filter(
                (f) =>
                    f.file_name.toLowerCase().includes(term) ||
                    f.file_path.toLowerCase().includes(term) ||
                    f.comicvine_volume_name?.toLowerCase().includes(term) ||
                    f.extracted_series?.toLowerCase().includes(term)
            );
        }

        // Sort by status (pending first), then filename
        filtered.sort((a, b) => {
            const statusOrder: Record<string, number> = { 
                pending: 0, 
                import: 1, 
                skipped: 2,
                processed: 3
            };
            const statusDiff = (statusOrder[a.status] || 99) - (statusOrder[b.status] || 99);
            if (statusDiff !== 0) return statusDiff;
            return a.file_name.localeCompare(b.file_name);
        });

        return filtered;
    }, [pendingFiles, statusFilters, matchedFilters, publisherFilters, searchTerm]);

    if (loading) {
        return (
            <div className="import-page">
                <div className="import-page__loading">
                    <p>Loading import jobs…</p>
                </div>
            </div>
        );
    }

    return (
        <div className="import-page">
            <div className="settings-header">
                <p>
                    Scan and import comic files into your library. Review matches, approve files, and organize your collection.
                </p>
            </div>

            {/* Panel 1: Import Jobs - Always visible */}
            <section className="section-card">
                <h2>Import Jobs</h2>
                <div className="section-card-content">
                    {/* Row 1: Job selector and navigation */}
                    <div className="section-row">
                        <div className="week-selector-group">
                            <label htmlFor="job-select" className="week-select-label">
                                Import Job:
                            </label>
                            <select
                                id="job-select"
                                value={selectedJobId || ""}
                                onChange={(e) => setSelectedJobId(e.target.value || null)}
                                className="week-select"
                                disabled={loading}
                            >
                                <option value="">{jobs.length === 0 ? "No import jobs yet..." : "Select an import job..."}</option>
                                {jobs.map((job) => (
                                    <option key={job.id} value={job.id}>
                                        {formatDate(job.created_at)} - {job.scan_type === "root_folders"
                                            ? `Root Folders Scan: ${libraries.find((lib) => lib.id === job.library_id)?.name || job.library_id}`
                                            : `External Folder: ${job.folder_path}`}
                                        {job.status === "scanning" || job.status === "processing" ? " ⏳" : ""}
                                        {job.status === "pending_review" ? " ✓" : ""}
                                        {job.status === "completed" ? " ✅" : ""}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="week-navigation">
                            <button
                                type="button"
                                className="btn btn-primary btn-small"
                                onClick={() => setShowCreateModal(true)}
                                title="Create a new import job"
                                disabled={loading}
                            >
                                New Import
                            </button>
                        </div>
                    </div>

                    {/* Row 2: Job actions */}
                    {selectedJob && (
                        <div className="section-row">
                            <div className="week-actions">
                                <button
                                    type="button"
                                    className="btn btn-danger btn-small"
                                    onClick={() => void handleDeleteJob(selectedJob.id)}
                                    title="Delete this import job"
                                >
                                    Delete
                                </button>
                                {selectedJob.status === "pending_review" && (
                                    <button
                                        type="button"
                                        className="btn btn-primary btn-small"
                                        onClick={async () => {
                                            await handleProcessJobClick(selectedJob.id);
                                        }}
                                        title="Process all files queued for import - create/update library issues"
                                    >
                                        Process
                                    </button>
                                )}
                                {(selectedJob.status === "scanning" || selectedJob.status === "processing") && (
                                    <>
                                        <div className="bulk-progress-indicator" style={{ marginLeft: "0.5rem", flex: 1, maxWidth: "300px" }}>
                                            <span className="bulk-progress-text">
                                                {selectedJob.status === "processing" && processingJob && processingJob.progress.total > 0
                                                    ? `Processing: ${processingJob.progress.current}/${processingJob.progress.total}`
                                                    : selectedJob.status === "scanning" && scanningJob && scanningJob.progress.total > 0
                                                        ? `Scanning: ${scanningJob.progress.current}/${scanningJob.progress.total}`
                                                        : selectedJob.status === "scanning" && scanningJob && scanningJob.progress.current > 0
                                                            ? `Scanning: ${scanningJob.progress.current} files`
                                                            : selectedJob.status === "processing"
                                                                ? "Processing..."
                                                                : "Scanning..."}
                                            </span>
                                            {((selectedJob.status === "processing" && processingJob) ||
                                              (selectedJob.status === "scanning" && scanningJob)) && (
                                                <div className="bulk-progress-bar">
                                                    <div
                                                        className="bulk-progress-fill"
                                                        style={{ 
                                                            width: `${selectedJob.status === "processing" && processingJob && processingJob.progress.total > 0
                                                                ? (processingJob.progress.current / processingJob.progress.total) * 100
                                                                : scanningJob && scanningJob.progress.total > 0
                                                                    ? (scanningJob.progress.current / scanningJob.progress.total) * 100
                                                                    : 0}%` 
                                                        }}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    </>
                                )}
                            </div>
                            {selectedJob.error && (
                                <div className="import-page__job-summary__error" style={{ width: "100%", marginTop: "0.5rem" }}>
                                    <strong>Error:</strong> {selectedJob.error}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </section>

            {/* Panel 2: Filters */}
            {selectedJob && (
                <section className="section-card">
                            <h2>Pending Files for {formatDate(selectedJob.created_at)}</h2>
                            <div className="section-card-content">
                                {/* Filter summary */}
                                <div className="filter-summary">
                                    Showing {filteredPendingFiles.length} of {pendingFiles.length} files
                                    {pendingFilesStats.total > 0 && ` (Total: ${pendingFilesStats.total})`}
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

                                    {/* Row 2: Status, Matched filters */}
                                    <div className="filter-row">
                                        <MultiSelectFilter
                                            label="Status"
                                            options={[
                                                { value: 'pending', label: 'Pending' },
                                                { value: 'import', label: 'Import' },
                                                { value: 'skipped', label: 'Skipped' },
                                                { value: 'processed', label: 'Processed' },
                                            ]}
                                            selected={statusFilters as Set<string>}
                                            onChange={(selected) => setStatusFilters(selected as Set<StatusFilter>)}
                                            placeholder="Statuses (All)"
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
                                    </div>

                                    {/* Row 3: Reset filters button */}
                                    <div className="filter-row">
                                        <button
                                            className="btn btn-secondary btn-small"
                                            onClick={() => {
                                                setStatusFilters(new Set());
                                                setMatchedFilters(new Set());
                                                setPublisherFilters(new Set());
                                                setSearchTerm("");
                                            }}
                                            disabled={statusFilters.size === 0 && matchedFilters.size === 0 && publisherFilters.size === 0 && searchTerm === ""}
                                        >
                                            Reset Filters
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </section>
            )}

            {/* Panel 3: Files Grid/List */}
            {selectedJob && (
                <section className="section-card">
                            <h2>Files</h2>
                            <div className="section-card-content">
                                {/* Bulk actions */}
                                <BulkActionsBar
                                    selectedCount={selectedFileIds.size}
                                    actions={[
                                        {
                                            label: "Mark as Skipped",
                                            onClick: () => handleBulkUpdatePendingFiles(selectedJob.id, Array.from(selectedFileIds), { status: "skipped", action: "skip" }),
                                        },
                                        {
                                            label: "Queue for Import",
                                            onClick: () => handleBulkUpdatePendingFiles(selectedJob.id, Array.from(selectedFileIds), { status: "import", action: "link" }),
                                        },
                                        {
                                            label: "Unapprove",
                                            onClick: () => handleBulkUnapprovePendingFiles(selectedJob.id, Array.from(selectedFileIds)),
                                        },
                                    ]}
                                />

                                {pendingFilesLoading ? (
                                    <div className="import-pending-files__loading">
                                        <p>Loading pending files…</p>
                                    </div>
                                ) : filteredPendingFiles.length === 0 ? (
                                    <div className="import-pending-files__empty">
                                        <p>No files found.</p>
                                    </div>
                                ) : (
                                    <>
                                        {/* Selection controls */}
                                        <SelectionControls
                                            selectedCount={selectedFileIds.size}
                                            totalCount={filteredPendingFiles.length}
                                            onSelectAll={() => {
                                                setSelectedFileIds(new Set(filteredPendingFiles.map((f) => f.id)));
                                            }}
                                            onSelectNone={handleDeselectAllFiles}
                                            onInvertSelection={() => {
                                                const newSelection = new Set<string>();
                                                filteredPendingFiles.forEach((file) => {
                                                    if (!selectedFileIds.has(file.id)) {
                                                        newSelection.add(file.id);
                                                    }
                                                });
                                                setSelectedFileIds(newSelection);
                                            }}
                                        />

                                        {/* Files grid list */}
                                        <div className="entries-grid">
                                            {filteredPendingFiles.map((pendingFile) => {
                                                // Get library root to strip from path
                                                const library = selectedJob ? libraries.find((lib) => lib.id === selectedJob.library_id) : null;
                                                const libraryRoot = library?.library_root || "";
                                                const displayPath = libraryRoot && pendingFile.file_path.startsWith(libraryRoot)
                                                    ? pendingFile.file_path.slice(libraryRoot.length).replace(/^\//, "")
                                                    : pendingFile.file_path;
                                                // Remove filename from path - show only directory
                                                const pathParts = displayPath.split('/');
                                                pathParts.pop(); // Remove filename
                                                const directoryPath = pathParts.join('/');

                                                return (
                                                    <div key={pendingFile.id} className={`entry-item status-${pendingFile.status}`}>
                                                        <div className="entry-checkbox">
                                                            <input
                                                                type="checkbox"
                                                                checked={selectedFileIds.has(pendingFile.id)}
                                                                onChange={() => handleToggleFileSelection(pendingFile.id)}
                                                                title="Select file"
                                                            />
                                                        </div>
                                                        <div className="entry-main">
                                                            <div className="entry-title">
                                                                {pendingFile.file_name}
                                                                <span className="entry-size" style={{ marginLeft: "0.5rem", fontWeight: "normal", color: "var(--color-text-muted, #666)" }}>
                                                                    {formatBytes(pendingFile.file_size)}
                                                                </span>
                                                            </div>
                                                            {(pendingFile.extracted_series || pendingFile.extracted_volume || pendingFile.extracted_issue_number) && (
                                                                <div className={`entry-meta ${(pendingFile.matched_volume_id || pendingFile.matched_issue_id) ? "entry-meta-library-match" : ""}`}>
                                                                    <span className="meta-item">
                                                                        {(() => {
                                                                            let series = pendingFile.extracted_series || "";
                                                                            let volume = pendingFile.extracted_volume;
                                                                            if (series && !volume) {
                                                                                const volumeMatch = series.match(/\b(?:v|vol\.?|volume)\s*(\d{4})\b/i);
                                                                                if (volumeMatch) {
                                                                                    volume = volumeMatch[1];
                                                                                    series = series.replace(/\b(?:v|vol\.?|volume)\s*\d{4}\b/gi, "").trim();
                                                                                    series = series.replace(/\s*[-_]\s*$/, "").trim();
                                                                                }
                                                                            }
                                                                            const parts: string[] = [];
                                                                            if (series) parts.push(series);
                                                                            if (volume) parts.push(`v${volume}`);
                                                                            if (pendingFile.extracted_issue_number) parts.push(`#${pendingFile.extracted_issue_number}`);
                                                                            return parts.length > 0 ? parts.join(" ") : null;
                                                                        })()}
                                                                    </span>
                                                                    {pendingFile.file_size < 1024 * 1024 && (
                                                                        <span className="meta-item" title="File is suspiciously small (< 1MB) and may be corrupted">
                                                                            ⚠️ Small
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            )}
                                                            {pendingFile.comicvine_volume_name && (
                                                                <div className="entry-comicvine">
                                                                    Matched: {pendingFile.comicvine_volume_name}
                                                                    {pendingFile.comicvine_issue_number && ` #${pendingFile.comicvine_issue_number}`}
                                                                </div>
                                                            )}
                                                            {directoryPath && (
                                                                <div className="entry-path" title={pendingFile.file_path}>
                                                                    <code>{directoryPath}/</code>
                                                                </div>
                                                            )}
                                                            {pendingFile.notes && pendingFile.notes.includes("⚠️") && (
                                                                <div className="entry-warning">
                                                                    {pendingFile.notes}
                                                                </div>
                                                            )}
                                                        </div>
                                                        <div className="entry-actions">
                                                            {(() => {
                                                                // Check if file has ComicVine results
                                                                let hasCvResults = false;
                                                                if (pendingFile.cv_results_sample) {
                                                                    try {
                                                                        const results = JSON.parse(pendingFile.cv_results_sample);
                                                                        hasCvResults = Array.isArray(results) && results.length > 0;
                                                                    } catch (e) {
                                                                        // Invalid JSON, ignore
                                                                    }
                                                                }
                                                                const hasComicvine = hasCvResults || !!pendingFile.comicvine_volume_id;
                                                                const hasLibrary = !!(pendingFile.matched_volume_id || pendingFile.matched_issue_id);
                                                                const hasMatch = hasComicvine || hasLibrary;
                                                                
                                                                return (
                                                                    <>
                                                                        {/* Import (MapPinPlus) - enabled if has match and not already imported */}
                                                                        <button
                                                                            type="button"
                                                                            className="btn btn-secondary btn-small btn-icon btn-status"
                                                                            onClick={() =>
                                                                                handleUpdatePendingFile(selectedJob.id, pendingFile.id, { status: "import", action: "link" })
                                                                            }
                                                                            title="Queue for import"
                                                                            disabled={!hasMatch || pendingFile.status === "import"}
                                                                        >
                                                                            <MapPinPlus size={16} />
                                                                        </button>

                                                                        {/* Skip (MapPinX) - enabled if not already skipped */}
                                                                        <button
                                                                            type="button"
                                                                            className="btn btn-secondary btn-small btn-icon btn-status"
                                                                            onClick={() =>
                                                                                handleUpdatePendingFile(selectedJob.id, pendingFile.id, { status: "skipped", action: "skip" })
                                                                            }
                                                                            title="Skip"
                                                                            disabled={pendingFile.status === "skipped"}
                                                                        >
                                                                            <MapPinX size={16} />
                                                                        </button>

                                                                        {/* Match CV (MessageCircleCode) - enabled if no ComicVine match, opens volume picker */}
                                                                        <button
                                                                            type="button"
                                                                            className="btn btn-secondary btn-small btn-icon btn-match"
                                                                            onClick={() => setVolumePickerPendingFile(pendingFile)}
                                                                            title="Match ComicVine"
                                                                            disabled={!!pendingFile.comicvine_volume_id}
                                                                        >
                                                                            <MessageCircleCode size={16} />
                                                                        </button>

                                                                        {/* Volume Picker (LayoutList) - enabled if has ComicVine results or match */}
                                                                        <button
                                                                            type="button"
                                                                            className="btn btn-secondary btn-small btn-icon btn-match"
                                                                            onClick={() => setVolumePickerPendingFile(pendingFile)}
                                                                            title="Pick Volume"
                                                                            disabled={!hasComicvine}
                                                                        >
                                                                            <LayoutList size={16} />
                                                                        </button>

                                                                        {/* Diagnostics (Activity) - always enabled */}
                                                                        <button
                                                                            type="button"
                                                                            className="btn btn-secondary btn-small btn-icon btn-utility"
                                                                            onClick={() => handleIdentifyPendingFile(pendingFile)}
                                                                            title="Identify file and show diagnostic information"
                                                                        >
                                                                            <Activity size={16} />
                                                                        </button>

                                                                        {/* Reset (RotateCcw) - enabled if status is import or has matches to clear */}
                                                                        <button
                                                                            type="button"
                                                                            className="btn btn-secondary btn-small btn-icon btn-utility"
                                                                            onClick={() =>
                                                                                handleUpdatePendingFile(selectedJob.id, pendingFile.id, { status: "pending", action: null })
                                                                            }
                                                                            title="Reset status to pending"
                                                                            disabled={pendingFile.status === "pending" && !hasMatch}
                                                                        >
                                                                            <RotateCcw size={16} />
                                                                        </button>
                                                                    </>
                                                                );
                                                            })()}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </>
                                )}
                            </div>
                        </section>
            )}

            {showCreateModal && (
                <div className="import-create-modal" role="dialog" aria-modal="true">
                    <div
                        className="import-create-modal__backdrop"
                        onClick={() => {
                            setShowCreateModal(false);
                            setCreateFolderPath("");
                            setCreateLinkFiles(false);
                            setCreateScanType("root_folders");
                        }}
                    />
                    <div className="import-create-modal__dialog">
                        <div className="import-create-modal__header">
                            <h2>Create Import Job</h2>
                        </div>
                        <div className="import-create-modal__body">
                            <div className="form-field">
                                <label htmlFor="library-select">Library</label>
                                <select
                                    id="library-select"
                                    value={createLibraryId}
                                    onChange={(e) => setCreateLibraryId(e.target.value)}
                                    disabled={creating || libraries.length === 0}
                                >
                                    {libraries.length === 0 ? (
                                        <option value="">No enabled libraries available</option>
                                    ) : (
                                        libraries.map((lib) => (
                                            <option key={lib.id} value={lib.id}>
                                                {lib.name} {lib.default ? "(Default)" : ""}
                                            </option>
                                        ))
                                    )}
                                </select>
                            </div>
                            <div className="form-field">
                                <label>Scan Type</label>
                                <RadioGroup
                                    name="scan_type"
                                    value={createScanType}
                                    options={[
                                        { value: "root_folders", label: "Root Folders", description: "Scan all root folders for this library" },
                                        { value: "external_folder", label: "External Folder", description: "Scan a specific folder outside the library" },
                                    ]}
                                    onChange={(value) => {
                                        setCreateScanType(value as "root_folders" | "external_folder");
                                        // Reset link_files when switching to root_folders (not applicable)
                                        if (value === "root_folders") {
                                            setCreateLinkFiles(false);
                                        }
                                    }}
                                    disabled={creating}
                                />
                            </div>
                            {createScanType === "external_folder" && (
                                <div className="form-field">
                                    <label htmlFor="folder-path">Folder Path</label>
                                    <div className="root-folder-add__controls">
                                        <input
                                            id="folder-path"
                                            type="text"
                                            placeholder="/path/to/folder"
                                            value={createFolderPath}
                                            onChange={(e) => setCreateFolderPath(e.target.value)}
                                            disabled={creating}
                                        />
                                        <button
                                            type="button"
                                            className="secondary"
                                            onClick={openFolderBrowser}
                                            disabled={creating}
                                        >
                                            Browse…
                                        </button>
                                    </div>
                                </div>
                            )}
                            {createScanType === "external_folder" && (
                                <div className="form-field">
                                    <Toggle
                                        id="create-link-files"
                                        label="Link files instead of moving them"
                                        checked={createLinkFiles}
                                        onChange={setCreateLinkFiles}
                                        disabled={creating}
                                    />
                                    <p style={{ fontSize: "0.875rem", color: "var(--color-text-muted)", marginTop: "0.5rem" }}>
                                        When enabled, symbolic links will be created in the library pointing to the original files.
                                    </p>
                                </div>
                            )}
                        </div>
                        <div className="import-create-modal__footer">
                            <button
                                type="button"
                                className="button secondary"
                                onClick={() => {
                                    setShowCreateModal(false);
                                    setCreateFolderPath("");
                                    setCreateLinkFiles(false);
                                    setCreateScanType("root_folders");
                                }}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                className="button primary"
                                onClick={handleCreateJob}
                                disabled={creating || !createLibraryId || (createScanType === "external_folder" && !createFolderPath.trim())}
                            >
                                {creating ? "Creating…" : "Create"}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {browserOpen && (
                <div className="folder-browser" role="dialog" aria-modal="true">
                    <div className="folder-browser__backdrop" onClick={closeFolderBrowser} />
                    <div className="folder-browser__dialog">
                        <div className="folder-browser__header">
                            <h2>Select Folder</h2>
                            <button type="button" className="secondary" onClick={closeFolderBrowser}>
                                Close
                            </button>
                        </div>
                        <div className="folder-browser__body">
                            <div className="folder-browser__path">
                                <label>Current Path</label>
                                <p>{browserPath || "—"}</p>
                            </div>
                            <div className="folder-browser__controls">
                                {browserParent && (
                                    <button
                                        type="button"
                                        className="secondary"
                                        onClick={() => navigateToEntry(browserParent)}
                                        disabled={browserLoading}
                                    >
                                        ← Parent
                                    </button>
                                )}
                                <button
                                    type="button"
                                    className="primary"
                                    onClick={applySelectedFolder}
                                    disabled={!browserPath || browserLoading}
                                >
                                    Select
                                </button>
                            </div>
                            {browserError ? (
                                <p className="status error">{browserError}</p>
                            ) : null}
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
            )}

            {/* Volume Picker Modal */}
            {volumePickerPendingFile && (
                <VolumePickerModalWithCover
                    entry={volumePickerPendingFile}
                    onClose={() => {
                        setVolumePickerPendingFile(null);
                    }}
                    onSelect={async (volumeId: number) => {
                        if (!volumePickerPendingFile) return;

                        try {
                            await apiPost(`/import/pending-files/${volumePickerPendingFile.id}/match`, {
                                comicvine_volume_id: volumeId,
                                action: "create_volume",
                            });

                            toast.success("Volume matched successfully");

                            // Reload pendingFiles
                            if (selectedJobId) {
                                await loadPendingFiles(selectedJobId);
                            }
                        } catch (err) {
                            const message = err instanceof ApiClientError ? err.message : "Failed to match volume";
                            toast.error(message);
                            throw err;
                        }
                    }}
                    getIssueCoverUrl={(entryId: string, volumeId: number, issueNumber: string) => {
                        return buildApiUrl(`/import/pending-files/${entryId}/issue-cover?volume_id=${volumeId}&issue_number=${encodeURIComponent(issueNumber)}`);
                    }}
                />
            )}

            {/* Diagnostic Modal */}
            {diagnosticPendingFile && (
                <div className="import-diagnostic-modal__overlay" onClick={() => setDiagnosticPendingFile(null)}>
                    <div className="import-diagnostic-modal__dialog" onClick={(e) => e.stopPropagation()}>
                        <div className="import-diagnostic-modal__header">
                            <h2>File Identification Diagnostic</h2>
                            <button className="import-diagnostic-modal__close" onClick={() => setDiagnosticPendingFile(null)}>
                                ×
                            </button>
                        </div>
                        <div className="import-diagnostic-modal__file-info">
                            <strong>{diagnosticPendingFile.file_name}</strong>
                            <code className="import-diagnostic-modal__path">{diagnosticPendingFile.file_path}</code>
                        </div>
                        {diagnosticLoading ? (
                            <div className="import-diagnostic-modal__loading">
                                <p>Identifying file...</p>
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
                                                <strong>Library Match Found:</strong> {diagnosticData.summary.library_match_found ? "✓ Yes" : "✗ No"}
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
                            <button className="button primary" onClick={() => setDiagnosticPendingFile(null)}>
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Process Confirmation Modal */}
            {processConfirmJobId && (
                <div className="modal-overlay" onClick={() => setProcessConfirmJobId(null)}>
                    <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>Confirm Import Processing</h2>
                            <button
                                type="button"
                                className="modal-close"
                                onClick={() => setProcessConfirmJobId(null)}
                            >
                                ×
                            </button>
                        </div>
                        <div className="modal-body">
                            {processPreviewLoading ? (
                                <p>Loading preview...</p>
                            ) : processPreview ? (
                                <div>
                                    <p>This will process <strong>{processPreview.total_files}</strong> file{processPreview.total_files !== 1 ? "s" : ""} queued for import.</p>
                                    <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                                        {processPreview.volumes_to_create > 0 && (
                                            <div>
                                                <strong>{processPreview.volumes_to_create}</strong> new volume{processPreview.volumes_to_create !== 1 ? "s" : ""} will be created
                                            </div>
                                        )}
                                        {processPreview.existing_volumes > 0 && (
                                            <div>
                                                <strong>{processPreview.existing_volumes}</strong> file{processPreview.existing_volumes !== 1 ? "s" : ""} will be added to existing volume{processPreview.existing_volumes !== 1 ? "s" : ""}
                                            </div>
                                        )}
                                        {processPreview.files_to_move > 0 && (
                                            <div>
                                                <strong>{processPreview.files_to_move}</strong> file{processPreview.files_to_move !== 1 ? "s" : ""} will be moved to the library
                                            </div>
                                        )}
                                        {processPreview.files_to_link > 0 && (
                                            <div>
                                                <strong>{processPreview.files_to_link}</strong> file{processPreview.files_to_link !== 1 ? "s" : ""} will be
                                                {(() => {
                                                    const selectedJob = jobs.find(j => j.id === processConfirmJobId);
                                                    if (selectedJob && selectedJob.scan_type === "root_folders") {
                                                        return "registered in the library (files are already in library root)";
                                                    } else if (selectedJob && selectedJob.link_files) {
                                                        return "linked to the library (symbolic links will be created)";
                                                    }
                                                    return "registered in the library";
                                                })()}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                <p>Failed to load preview.</p>
                            )}
                        </div>
                        <div className="modal-footer">
                            <button
                                type="button"
                                className="button secondary"
                                onClick={() => setProcessConfirmJobId(null)}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                className="button primary"
                                onClick={() => void handleProcessJobConfirm()}
                                disabled={processPreviewLoading || !processPreview}
                            >
                                Confirm & Process
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
