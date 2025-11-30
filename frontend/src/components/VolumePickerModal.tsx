import { useEffect, useState } from "react";
import "./VolumePickerModal.css";

type VolumeResult = {
  name: string;
  start_year?: number;
  publisher?: string;
  cv_volume_id?: number;
  image_url?: string;
  issue_image_url?: string;
  volume_image_url?: string;
  rank: number;
  is_best_match?: boolean;
  confidence?: number;
  count_of_issues?: number | null;
};

type ComicVineEntry = {
  id: string;
  cv_results_sample?: string | null;
  comicvine_volume_id?: number | null;
  comicvine_issue_id?: number | null;
  comicvine_issue_image?: string | null;
  extracted_issue_number?: string | null;
  comicvine_issue_number?: string | null;
  file_name?: string;
  title?: string;
};

type VolumePickerModalProps = {
  entry: ComicVineEntry | null;
  onClose: () => void;
  onSelect: (volumeId: number) => Promise<void>;
  coverImageUrl?: string;
  issueCoverUrl?: string;
  getIssueCoverUrl?: (entryId: string, volumeId: number, issueNumber: string) => string;
};

export function VolumePickerModal({
  entry,
  onClose,
  onSelect,
  coverImageUrl,
  issueCoverUrl: initialIssueCoverUrl,
  getIssueCoverUrl,
}: VolumePickerModalProps) {
  const [volumePickerIndex, setVolumePickerIndex] = useState(0);
  const [issueCoverUrl, setIssueCoverUrl] = useState<string | null>(initialIssueCoverUrl || null);
  const [loadingIssueCover, setLoadingIssueCover] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);

  useEffect(() => {
    if (entry) {
      setVolumePickerIndex(0);
    }
  }, [entry?.id]);

  useEffect(() => {
    if (!entry || volumePickerIndex < 0) {
      setIssueCoverUrl(null);
      return;
    }

    let volumeResults: VolumeResult[] = [];
    try {
      if (entry.cv_results_sample) {
        volumeResults = JSON.parse(entry.cv_results_sample);
      }
    } catch (e) {
      // Invalid JSON, ignore
    }

    volumeResults.sort((a, b) => {
      if (a.is_best_match && !b.is_best_match) return -1;
      if (!a.is_best_match && b.is_best_match) return 1;
      
      const aConf = a.confidence ?? -1;
      const bConf = b.confidence ?? -1;
      if (aConf !== bConf) {
        return bConf - aConf;
      }
      
      return (a.rank ?? 0) - (b.rank ?? 0);
    });

    const currentVolume = volumeResults[volumePickerIndex];

    if (!currentVolume?.cv_volume_id) {
      setIssueCoverUrl(null);
      return;
    }

    const issueNumber = entry.extracted_issue_number || entry.comicvine_issue_number || null;

    if (!issueNumber) {
      setIssueCoverUrl(null);
      return;
    }

    if (currentVolume.issue_image_url) {
      setIssueCoverUrl(currentVolume.issue_image_url);
      setLoadingIssueCover(false);
      return;
    }

    const hasMatchingIssueId =
      entry.comicvine_volume_id === currentVolume.cv_volume_id && entry.comicvine_issue_id;

    if (hasMatchingIssueId && entry.comicvine_issue_image) {
      setIssueCoverUrl(entry.comicvine_issue_image);
      setLoadingIssueCover(false);
      return;
    }

    if (!getIssueCoverUrl) {
      setIssueCoverUrl(null);
      return;
    }

    const fetchIssueCover = async () => {
      setLoadingIssueCover(true);
      setIssueCoverUrl(null);

      try {
        if (currentVolume.cv_volume_id === undefined) {
          setIssueCoverUrl(null);
          return;
        }
        const url = getIssueCoverUrl(entry.id, currentVolume.cv_volume_id, issueNumber);
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          setIssueCoverUrl(data.issue_image_url || null);
        } else {
          setIssueCoverUrl(null);
        }
      } catch (err) {
        console.error("Error fetching issue cover:", err);
        setIssueCoverUrl(null);
      } finally {
        setLoadingIssueCover(false);
      }
    };

    fetchIssueCover();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry?.id, entry?.cv_results_sample, entry?.extracted_issue_number, entry?.comicvine_issue_number, entry?.comicvine_volume_id, entry?.comicvine_issue_id, entry?.comicvine_issue_image, volumePickerIndex]);

  if (!entry) {
    return null;
  }

  let volumeResults: VolumeResult[] = [];
  try {
    if (entry.cv_results_sample) {
      volumeResults = JSON.parse(entry.cv_results_sample);
    }
  } catch (e) {
    // Invalid JSON, ignore
  }

  volumeResults.sort((a, b) => {
    if (a.is_best_match && !b.is_best_match) return -1;
    if (!a.is_best_match && b.is_best_match) return 1;
    
    const aConf = a.confidence ?? -1;
    const bConf = b.confidence ?? -1;
    if (aConf !== bConf) {
      return bConf - aConf;
    }
    
    return (a.rank ?? 0) - (b.rank ?? 0);
  });

  if (volumeResults.length === 0) {
    return (
      <div className="volume-picker-modal__overlay" onClick={onClose}>
        <div className="volume-picker-modal__dialog" onClick={(e) => e.stopPropagation()}>
          <h2>No Volume Results</h2>
          <p>No volume results available for this entry.</p>
          <button className="button primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    );
  }

  const currentVolume = volumeResults[volumePickerIndex];
  if (!currentVolume) {
    setVolumePickerIndex(0);
    return null;
  }

  const hasPrevious = volumePickerIndex > 0;
  const hasNext = volumePickerIndex < volumeResults.length - 1;

  const cvCoverUrl =
    issueCoverUrl || currentVolume.issue_image_url || currentVolume.image_url || currentVolume.volume_image_url;

  const handleAccept = async () => {
    if (!currentVolume?.cv_volume_id || isSelecting) return;

    setIsSelecting(true);
    try {
      await onSelect(currentVolume.cv_volume_id);
      onClose();
      setIssueCoverUrl(null);
    } catch (err) {
      console.error("Error selecting volume:", err);
    } finally {
      setIsSelecting(false);
    }
  };

  const displayName = entry.file_name || entry.title || "Unknown";

  return (
    <div className="volume-picker-modal__overlay" onClick={onClose}>
      <div className="volume-picker-modal__dialog" onClick={(e) => e.stopPropagation()}>
        <div className="volume-picker-modal__header">
          <h2>Select ComicVine Volume</h2>
          <button className="volume-picker-modal__close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="volume-picker-modal__file-info">
          {entry.file_name ? `File: ${displayName}` : `Entry: ${displayName}`}
        </div>

        <div className="volume-picker-modal__content">
          <div className="volume-picker-modal__sidebar">
            <h3>Volumes ({volumeResults.length})</h3>
            <div className="volume-picker-modal__volume-list">
              {volumeResults.map((vol, idx) => (
                <div
                  key={idx}
                  className={`volume-picker-modal__volume-item ${idx === volumePickerIndex ? "volume-picker-modal__volume-item--active" : ""}`}
                  onClick={() => setVolumePickerIndex(idx)}
                >
                  <div className="volume-picker-modal__volume-name">
                    {idx === volumePickerIndex && <span className="volume-picker-modal__selected-indicator">✓</span>}
                    {vol.name || "Unknown Volume"}
                    {vol.is_best_match && <span className="volume-picker-modal__best-match">✓ Best</span>}
                  </div>
                  <div className="volume-picker-modal__volume-details">
                    {vol.publisher && (
                      <div>
                        <strong>Publisher:</strong> {vol.publisher}
                      </div>
                    )}
                    {vol.start_year && (
                      <div>
                        <strong>Year:</strong> {vol.start_year}
                      </div>
                    )}
                    {vol.count_of_issues !== null && vol.count_of_issues !== undefined && (
                      <div>
                        <strong>Issues:</strong> {vol.count_of_issues}
                      </div>
                    )}
                    {vol.cv_volume_id && (
                      <div>
                        <strong>CV ID:</strong> {vol.cv_volume_id}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="volume-picker-modal__main">
            {currentVolume ? (
              <>
                <div className="volume-picker-modal__covers">
                  {coverImageUrl && (
                    <div className="volume-picker-modal__cover-section">
                      <h3>Local File</h3>
                      <img
                        src={coverImageUrl}
                        alt="Local file cover"
                        className="volume-picker-modal__cover-image"
                        onError={(e) => {
                          const target = e.target as HTMLImageElement;
                          target.style.display = "none";
                          if (target.nextElementSibling) {
                            (target.nextElementSibling as HTMLElement).style.display = "flex";
                          }
                        }}
                      />
                      <div className="volume-picker-modal__cover-placeholder">
                        <span>No cover available</span>
                      </div>
                    </div>
                  )}

                  <div className="volume-picker-modal__cover-section">
                    <h3>
                      ComicVine {loadingIssueCover ? "Issue" : "Volume"}
                      {currentVolume.is_best_match && (
                        <span className="volume-picker-modal__best-match-badge">
                          (Best Match: {currentVolume.confidence ? `score ${currentVolume.confidence.toFixed(1)}` : "N/A"})
                        </span>
                      )}
                      {loadingIssueCover && <span className="volume-picker-modal__loading">Loading...</span>}
                    </h3>
                    {cvCoverUrl ? (
                      <img
                        src={cvCoverUrl}
                        alt={currentVolume.name || "Volume cover"}
                        className="volume-picker-modal__cover-image volume-picker-modal__cover-image--cv"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="volume-picker-modal__cover-placeholder">
                        <span>No cover available</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="volume-picker-modal__actions">
                  <div className="volume-picker-modal__navigation">
                    <button
                      className="button secondary"
                      onClick={() => setVolumePickerIndex(Math.max(0, volumePickerIndex - 1))}
                      disabled={!hasPrevious}
                    >
                      Previous
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => setVolumePickerIndex(Math.min(volumeResults.length - 1, volumePickerIndex + 1))}
                      disabled={!hasNext}
                    >
                      Next
                    </button>
                    <span className="volume-picker-modal__counter">
                      {volumePickerIndex + 1} of {volumeResults.length}
                    </span>
                  </div>
                  <button
                    className="button primary"
                    onClick={handleAccept}
                    disabled={isSelecting}
                  >
                    {isSelecting ? "Selecting..." : "Select This Volume"}
                  </button>
                </div>
              </>
            ) : (
              <div className="volume-picker-modal__empty">
                <p>No volume selected</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}



