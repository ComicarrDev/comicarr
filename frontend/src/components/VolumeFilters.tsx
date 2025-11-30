import "./VolumeFilters.css";

export interface SortOption {
  value: string;
  label: string;
}

export interface VolumeFiltersProps {
  // Filter values
  publisherFilter: string;
  volumeFilter?: string;
  yearMin?: string;
  yearMax?: string;
  minIssues?: string;
  maxIssues?: string;
  sortValue: string;

  // Filter setters
  onPublisherChange: (value: string) => void;
  onVolumeChange?: (value: string) => void;
  onYearMinChange?: (value: string) => void;
  onYearMaxChange?: (value: string) => void;
  onMinIssuesChange?: (value: string) => void;
  onMaxIssuesChange?: (value: string) => void;
  onSortChange: (value: string) => void;

  // Options
  publisherOptions: string[];
  volumeOptions?: string[];
  sortOptions: SortOption[];

  // IDs prefix for unique form element IDs
  idPrefix?: string;
  className?: string;
}

export function VolumeFilters({
  publisherFilter,
  volumeFilter,
  yearMin,
  yearMax,
  minIssues,
  maxIssues,
  sortValue,
  onPublisherChange,
  onVolumeChange,
  onYearMinChange,
  onYearMaxChange,
  onMinIssuesChange,
  onMaxIssuesChange,
  onSortChange,
  publisherOptions,
  volumeOptions = [],
  sortOptions,
  idPrefix = "filter",
  className = ""
}: VolumeFiltersProps) {
  const prefix = idPrefix;
  const baseClassName = `volume-filters ${className}`.trim();

  return (
    <div className={baseClassName}>
      {/* Row 1: Publisher, Volume, Sort By */}
      <div className="volume-filters__group volume-filters__row1">
        <label htmlFor={`${prefix}-publisher`}>Publisher</label>
        <select
          id={`${prefix}-publisher`}
          value={publisherFilter}
          onChange={(e) => onPublisherChange(e.target.value)}
        >
          <option value="All">All</option>
          {publisherOptions
            .filter((p) => p !== "All")
            .map((publisher) => (
              <option key={publisher} value={publisher}>
                {publisher}
              </option>
            ))}
        </select>
      </div>

      {onVolumeChange && (
        <div className="volume-filters__group volume-filters__row1">
          <label htmlFor={`${prefix}-volume`}>Volume</label>
          <select
            id={`${prefix}-volume`}
            value={volumeFilter || "All"}
            onChange={(e) => onVolumeChange(e.target.value)}
            disabled={volumeOptions.length === 0}
          >
            <option value="All">All</option>
            {volumeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="volume-filters__group volume-filters__row1">
        <label htmlFor={`${prefix}-sort`}>Sort by</label>
        <select
          id={`${prefix}-sort`}
          value={sortValue}
          onChange={(e) => onSortChange(e.target.value)}
        >
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Row break - forces next items to new row */}
      <div className="volume-filters__row-break"></div>

      {/* Row 2: Year (min), Year (max), Issues (min), Issues (max) */}
      <div className="volume-filters__group volume-filters__group--numeric volume-filters__row2">
        <label htmlFor={`${prefix}-year-min`}>Year (min)</label>
        <input
          id={`${prefix}-year-min`}
          type="number"
          value={yearMin || ""}
          onChange={(e) => onYearMinChange?.(e.target.value)}
        />
      </div>

      <div className="volume-filters__group volume-filters__group--numeric volume-filters__row2">
        <label htmlFor={`${prefix}-year-max`}>Year (max)</label>
        <input
          id={`${prefix}-year-max`}
          type="number"
          value={yearMax || ""}
          onChange={(e) => onYearMaxChange?.(e.target.value)}
        />
      </div>

      <div className="volume-filters__group volume-filters__group--numeric volume-filters__row2">
        <label htmlFor={`${prefix}-min-issues`}>Issues (min)</label>
        <input
          id={`${prefix}-min-issues`}
          type="number"
          value={minIssues || ""}
          onChange={(e) => onMinIssuesChange?.(e.target.value)}
          min="0"
        />
      </div>

      <div className="volume-filters__group volume-filters__group--numeric volume-filters__row2">
        <label htmlFor={`${prefix}-max-issues`}>Issues (max)</label>
        <input
          id={`${prefix}-max-issues`}
          type="number"
          value={maxIssues || ""}
          onChange={(e) => onMaxIssuesChange?.(e.target.value)}
          min="0"
        />
      </div>
    </div>
  );
}



