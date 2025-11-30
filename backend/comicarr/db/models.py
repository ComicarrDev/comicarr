"""Database models for Comicarr.

All SQLModel models should be defined here and imported in db/__init__.py.

Models follow these patterns:
- Use singular nouns: LibraryVolume, LibraryIssue
- Table names use plural, snake_case: library_volumes, library_issues
- Use uuid.uuid4().hex for IDs (32 character hex strings)
- Include created_at and updated_at timestamps where appropriate
- Use proper indexes on foreign keys and frequently queried fields
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import JSON, Column, Index, Text
from sqlmodel import Field, SQLModel

# SQLModel metadata - required for Alembic migrations
# All models with table=True will be registered here automatically
metadata = SQLModel.metadata


class Indexer(SQLModel, table=True):
    """Indexer model for content indexers."""

    __tablename__ = "indexers"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str  # Display name (e.g., "NZBgeek", "GetComics")
    type: str  # "builtin_http", "newznab", "torrent"
    is_builtin: bool = False  # True for pre-seeded indexers
    enabled: bool = True
    priority: int = 0  # Lower = higher priority

    # Type-specific configuration stored as JSON
    # For newznab: {"url": "...", "api_key": "...", "api_path": "/api", "categories": [...]}
    # For torrent: {"url": "...", "api_key": "...", "api_path": "/api", "categories": [...]}
    # For builtin_http: {"base_url": "...", "rate_limit": 10, "rate_limit_period": 60}
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Capabilities (like Sonarr)
    enable_rss: bool = True
    enable_automatic_search: bool = True
    enable_interactive_search: bool = True

    # Tags for filtering (optional)
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))

    # Indexes
    __table_args__ = (
        Index("idx_indexers_enabled", "enabled"),
        Index("idx_indexers_type", "type"),
        Index("idx_indexers_builtin", "is_builtin"),
    )


class ImportJob(SQLModel, table=True):
    """Represents a single import scan operation."""

    __tablename__ = "import_jobs"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    library_id: str = Field(index=True)  # Target library for import
    scan_type: str = Field(index=True)  # "root_folders" or "external_folder"
    folder_path: str | None = Field(default=None)  # For external_folder scans
    link_files: bool = Field(default=False)  # If True, link files instead of moving them
    status: str = Field(
        default="scanning", index=True
    )  # scanning, pending_review, processing, completed, cancelled
    scanned_files: int = Field(default=0)
    total_files: int = Field(default=0)  # Total files to scan (0 = unknown/not counted yet)
    processed_files: int = Field(
        default=0
    )  # Files processed during import (0 = not processing yet)
    matched_count: int = Field(default=0)
    unmatched_count: int = Field(default=0)
    approved_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    error: str | None = Field(default=None)
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    completed_at: int | None = Field(default=None)

    __table_args__ = (
        Index("idx_import_jobs_status", "status"),
        Index("idx_import_jobs_scan_type", "scan_type"),
    )


class ImportScanningJob(SQLModel, table=True):
    """Background job for scanning files during import."""

    __tablename__ = "import_scanning_jobs"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    import_job_id: str = Field(index=True)  # Foreign key to import_jobs
    status: str = Field(
        default="queued", index=True
    )  # queued, processing, completed, failed, cancelled, paused
    progress_current: int = Field(
        default=0
    )  # Number of files scanned (that created ImportPendingFile entries)
    progress_total: int = Field(
        default=0
    )  # Total number of files to scan (excluding files already in library)
    error_count: int = Field(default=0)  # Number of errors
    error: str | None = Field(default=None)  # Error message if failed
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    started_at: int | None = Field(default=None)  # When scanning started
    completed_at: int | None = Field(default=None)  # When scanning completed

    __table_args__ = (
        Index("idx_import_scanning_jobs_import_job", "import_job_id"),
        Index("idx_import_scanning_jobs_status", "status"),
    )


class ImportProcessingJob(SQLModel, table=True):
    """Background job for processing approved files during import."""

    __tablename__ = "import_processing_jobs"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    import_job_id: str = Field(index=True)  # Foreign key to import_jobs
    status: str = Field(
        default="queued", index=True
    )  # queued, processing, completed, failed, cancelled, paused
    progress_current: int = Field(default=0)  # Number of files processed
    progress_total: int = Field(default=0)  # Total number of files to process
    error_count: int = Field(default=0)  # Number of errors
    error: str | None = Field(default=None)  # Error message if failed
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    started_at: int | None = Field(default=None)  # When processing started
    completed_at: int | None = Field(default=None)  # When processing completed

    __table_args__ = (
        Index("idx_import_processing_jobs_import_job", "import_job_id"),
        Index("idx_import_processing_jobs_status", "status"),
    )


class ImportPendingFile(SQLModel, table=True):
    """Represents a file pending import."""

    __tablename__ = "import_pending_files"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    import_job_id: str = Field(index=True)
    file_path: str  # Absolute or relative path
    file_name: str  # Just filename
    file_size: int
    file_extension: str  # .cbz, .cbr, etc.

    # Matching results
    status: str = Field(default="pending", index=True)  # pending, import, skipped, processed
    matched_volume_id: str | None = Field(default=None, index=True)
    matched_issue_id: str | None = Field(default=None, index=True)
    matched_confidence: float | None = Field(default=None)  # 0.0-1.0

    # ComicVine matching (if file doesn't match library)
    comicvine_volume_id: int | None = Field(default=None, index=True)
    comicvine_issue_id: int | None = Field(default=None)
    comicvine_match_type: str | None = Field(
        default=None
    )  # "auto" for auto-matched, "manual" for user-selected, null if no match
    comicvine_volume_name: str | None = Field(default=None)
    comicvine_issue_name: str | None = Field(default=None)
    comicvine_issue_number: str | None = Field(default=None)
    comicvine_issue_image: str | None = Field(default=None)  # Cover image URL
    comicvine_confidence: float | None = Field(default=None)  # 0.0-1.0

    # User decisions
    action: str | None = Field(default=None, index=True)  # "link", "create_volume", "skip", "move"
    target_volume_id: str | None = Field(
        default=None, index=True
    )  # User-selected volume if manual match
    target_issue_id: str | None = Field(
        default=None, index=True
    )  # User-selected issue if manual match
    target_folder_id: str | None = Field(default=None)  # Root folder to move file to

    # Processing decisions (preview)
    preview_rename_to: str | None = Field(default=None)  # What file will be renamed to
    preview_convert_to: str | None = Field(default=None)  # Target format if conversion needed
    preview_metatag: bool = Field(default=True)  # Whether to metatag after import

    # Metadata extracted from filename
    extracted_series: str | None = Field(default=None, index=True)
    extracted_issue_number: str | None = Field(default=None)
    extracted_year: int | None = Field(default=None)
    extracted_month: str | None = Field(default=None)  # Full month name, e.g., "January"
    extracted_volume: str | None = Field(
        default=None
    )  # Volume identifier, e.g., "2022" from "v2022"

    # ComicVine search details (for troubleshooting)
    cv_search_query: str | None = Field(default=None)  # What query was sent to ComicVine
    cv_results_count: int | None = Field(default=None)  # How many results returned
    cv_results_sample: str | None = Field(
        default=None
    )  # Sample of results (JSON string, first 5 volumes)
    cv_issue_filter: str | None = Field(default=None)  # Filter string used for issue query

    notes: str | None = Field(default=None)
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_import_pending_files_job", "import_job_id"),
        Index("idx_import_pending_files_status", "status"),
        Index("idx_import_pending_files_matched_volume", "matched_volume_id"),
        Index("idx_import_pending_files_comicvine_volume", "comicvine_volume_id"),
    )


class Library(SQLModel, table=True):
    """Library model for organizing volumes into separate collections (e.g., Comics, Mangas)."""

    __tablename__ = "libraries"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str  # Display name (e.g., "Comics", "Mangas")
    library_root: str  # Base path where files are organized (e.g., "/comics")
    default: bool = Field(default=False, index=True)  # Default library for new volumes
    enabled: bool = Field(default=True, index=True)

    # Library-specific settings stored as JSON
    # Includes: file_naming_template, volume_folder_naming, convert_files, preferred_format, etc.
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_libraries_default", "default"),
        Index("idx_libraries_enabled", "enabled"),
    )


class IncludePath(SQLModel, table=True):
    """Include path model for scoping library to specific folders (incremental imports).

    Include paths limit the library scope to specific subdirectories of the library root.
    When include paths are configured, only these paths are scanned/managed.
    When no include paths exist, the entire library root is managed.
    """

    __tablename__ = "include_paths"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    library_id: str = Field(index=True)  # Foreign key to libraries
    path: str  # Absolute path to include folder (must be within library root, e.g., "/comics/publisher/DC")
    enabled: bool = Field(default=True, index=True)
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_include_paths_library", "library_id"),
        Index("idx_include_paths_enabled", "enabled"),
    )


class LibraryVolume(SQLModel, table=True):
    """Volume model representing a comic series/volume in a library."""

    __tablename__ = "library_volumes"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    library_id: str = Field(index=True)  # Foreign key to libraries
    include_path_id: str | None = Field(
        default=None, index=True
    )  # Which include path this volume came from

    # ComicVine metadata
    comicvine_id: int | None = Field(default=None, index=True)
    title: str
    year: int | None = Field(default=None, index=True)
    publisher: str | None = Field(default=None, index=True)
    publisher_country: str | None = None
    description: str | None = None
    site_url: str | None = None
    count_of_issues: int | None = None
    image: str | None = None

    # Monitoring
    monitored: bool = Field(default=True)
    monitor_new_issues: bool = Field(default=True)

    # Folder organization
    folder_name: str | None = None  # Custom folder name (if different from template)
    custom_folder: bool = Field(default=False)  # Whether folder_name is custom

    # Metadata
    date_last_updated: str | None = None  # ComicVine date_last_updated
    is_ended: bool = Field(default=False)  # Computed: ended AND we have all issues

    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_library_volumes_library", "library_id"),
        Index("idx_library_volumes_comicvine", "comicvine_id"),
        Index("idx_library_volumes_publisher", "publisher"),
        Index("idx_library_volumes_year", "year"),
    )


class LibraryIssue(SQLModel, table=True):
    """Issue model representing a single comic issue in a volume."""

    __tablename__ = "library_issues"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    volume_id: str = Field(index=True)  # Foreign key to library_volumes

    # ComicVine metadata
    comicvine_id: int | None = Field(default=None, index=True)
    number: str  # Issue number (e.g., "1", "1.5", "Annual 1")
    title: str | None = None
    release_date: str | None = None
    description: str | None = None
    site_url: str | None = None
    image: str | None = None

    # Monitoring
    monitored: bool = Field(default=True)

    # File status
    status: str = Field(default="missing", index=True)  # missing, downloaded, processed, ready
    file_path: str | None = None  # Relative path from library root
    file_size: int | None = None

    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_library_issues_volume", "volume_id"),
        Index("idx_library_issues_comicvine", "comicvine_id"),
        Index("idx_library_issues_status", "status"),
    )


class WeeklyReleaseWeek(SQLModel, table=True):
    """Represents a single week's fetch operation for weekly comic releases.

    Comics are typically released on Wednesdays, so each week starts on a Wednesday.
    This model tracks when we fetched releases from external sources for that week.
    """

    __tablename__ = "weekly_release_weeks"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    week_start: str = Field(index=True)  # ISO date (YYYY-MM-DD) for Wednesday (comics release day)
    fetched_at: int = Field(default_factory=lambda: int(time.time()))
    status: str = Field(default="completed")  # completed, fetching, error
    ignored_files_json: str | None = Field(
        default=None, sa_column=Column("ignored_files", Text)
    )  # JSON array of ignored filenames
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))


class WeeklyReleaseProcessingJob(SQLModel, table=True):
    """Background job for processing weekly releases (creating/updating library issues)."""

    __tablename__ = "weekly_release_processing_jobs"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    week_id: str = Field(index=True)  # Foreign key to weekly_release_weeks
    status: str = Field(
        default="queued", index=True
    )  # queued, processing, completed, failed, cancelled
    progress_current: int = Field(default=0)  # Number of items processed
    progress_total: int = Field(default=0)  # Total number of items to process
    error_count: int = Field(default=0)  # Number of errors
    error: str | None = Field(default=None)  # Error message if failed
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    started_at: int | None = Field(default=None)  # When processing started
    completed_at: int | None = Field(default=None)  # When processing completed

    __table_args__ = (
        Index("idx_weekly_release_processing_jobs_week", "week_id"),
        Index("idx_weekly_release_processing_jobs_status", "status"),
    )


class WeeklyReleaseMatchingJob(SQLModel, table=True):
    """Background job for bulk matching weekly releases to ComicVine or library."""

    __tablename__ = "weekly_release_matching_jobs"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    week_id: str = Field(index=True)  # Foreign key to weekly_release_weeks
    match_type: str = Field(index=True)  # "comicvine" or "library"
    entry_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # Entry IDs to match
    status: str = Field(
        default="queued", index=True
    )  # queued, processing, completed, failed, cancelled
    progress_current: int = Field(default=0)  # Number of items matched
    progress_total: int = Field(default=0)  # Total number of items to match
    matched_count: int = Field(default=0)  # Number successfully matched
    error_count: int = Field(default=0)  # Number of errors
    error: str | None = Field(default=None)  # Error message if failed
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    started_at: int | None = Field(default=None)  # When matching started
    completed_at: int | None = Field(default=None)  # When matching completed

    __table_args__ = (
        Index("idx_weekly_release_matching_jobs_week", "week_id"),
        Index("idx_weekly_release_matching_jobs_status", "status"),
        Index("idx_weekly_release_matching_jobs_type", "match_type"),
    )


class WeeklyReleaseItem(SQLModel, table=True):
    """Represents an individual comic release found from external sources during a week.

    Each item can come from multiple sources (readcomicsonline, getcomics, previewsworld,
    comicgeeks) and may be matched to ComicVine and/or library volumes/issues.
    """

    __tablename__ = "weekly_release_items"  # type: ignore[assignment]

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    week_id: str = Field(index=True)  # Foreign key to weekly_release_weeks
    week_start: str | None = Field(default=None, index=True)  # Denormalized for easier querying

    # Source information
    source: str = Field(
        index=True
    )  # "readcomicsonline", "getcomics", "previewsworld", "comicgeeks"
    sources_json: str | None = Field(
        default=None, sa_column=Column("sources", Text)
    )  # JSON array if found in multiple sources
    issue_key: str | None = Field(default=None, index=True)  # Source-specific identifier
    url: str | None = Field(default=None)  # Source URL

    # Comic metadata
    title: str
    publisher: str | None = Field(default=None)
    release_date: str | None = Field(default=None)

    # User decisions and matching
    status: str = Field(default="pending", index=True)  # pending, import, skipped, processed, error
    notes: str | None = Field(default=None)
    matched_volume_id: str | None = Field(default=None, index=True)  # Library volume ID
    matched_issue_id: str | None = Field(default=None, index=True)  # Library issue ID

    # ComicVine matching
    comicvine_volume_id: int | None = Field(default=None, index=True)
    comicvine_issue_id: int | None = Field(default=None, index=True)
    comicvine_volume_name: str | None = Field(default=None)
    comicvine_issue_name: str | None = Field(default=None)
    comicvine_issue_number: str | None = Field(default=None)
    comicvine_site_url: str | None = Field(default=None)
    comicvine_cover_date: str | None = Field(default=None)
    comicvine_confidence: float | None = Field(default=None)
    cv_search_query: str | None = Field(default=None)  # What query was sent to ComicVine
    cv_results_count: int | None = Field(default=None)  # How many results returned
    cv_results_sample: str | None = Field(
        default=None, sa_column=Column("cv_results_sample", Text)
    )  # Sample of results (JSON string) for volume picker

    # Bundle/pack information (for getcomics weekly packs)
    bundle_id: str | None = Field(default=None, index=True)
    bundle_name: str | None = Field(default=None)
    download_url: str | None = Field(default=None)
    pack_file_path: str | None = Field(default=None)

    # Additional metadata
    metadata_json: str | None = Field(default=None, sa_column=Column("metadata", Text))

    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))


__all__ = [
    "metadata",
    "Indexer",
    "Library",
    "IncludePath",
    "LibraryVolume",
    "LibraryIssue",
    "ImportJob",
    "ImportScanningJob",
    "ImportProcessingJob",
    "ImportPendingFile",
    "WeeklyReleaseWeek",
    "WeeklyReleaseItem",
    "WeeklyReleaseProcessingJob",
    "WeeklyReleaseMatchingJob",
]
