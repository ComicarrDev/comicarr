"""Pydantic models for search results and configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DownloadLink(BaseModel):
    """A download link with metadata."""

    url: str = Field(..., description="Download URL")
    service: str = Field(..., description="Download service name (e.g., 'pixeldrain', 'mega')")
    priority: int = Field(default=0, description="Link priority (higher = better)")
    issue_range: tuple[float, float] | None = Field(
        default=None, description="Issue range covered by this link (for multi-link packs)"
    )
    context_text: str | None = Field(
        default=None, description="Context text from the source (e.g., heading before the link)"
    )


class SearchResult(BaseModel):
    """Standardized search result from any indexer."""

    title: str = Field(..., description="Release/issue title")
    guid: str = Field(..., description="Unique identifier (URL or ComicVine ID)")
    link: str = Field(..., description="Download URL or page URL")
    pub_date: datetime | None = Field(default=None, description="Publication date")
    size: int | None = Field(default=None, description="File size in bytes")
    categories: list[int] = Field(default_factory=list, description="Category IDs")
    indexer_id: str = Field(..., description="ID of the indexer that returned this result")
    indexer_name: str = Field(..., description="Name of the indexer")
    source_type: Literal["usenet", "torrent", "http"] = Field(..., description="Source type")

    # For HTTP indexers
    download_links: list[DownloadLink] | None = Field(
        default=None, description="Multiple server options (e.g., for GetComics)"
    )
    requires_scraping: bool = Field(
        default=False, description="True if this requires page scraping (e.g., ReadComicsOnline)"
    )

    # For volume packs
    is_volume_pack: bool = Field(default=False, description="True if this is a volume pack")
    covers_issues: list[str] = Field(
        default_factory=list, description="Issue numbers this pack covers"
    )
    pack_issue_count: int | None = Field(default=None, description="Number of issues in the pack")


class SearchPreferences(BaseModel):
    """User preferences for search and ranking."""

    prefer_volume_packs: Literal[
        "always", "never", "when_multiple", "only_if_no_individual", "if_missing_threshold"
    ] = Field(default="when_multiple", description="When to prefer volume packs")
    pack_missing_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum percentage of missing issues that must be covered by pack (only used if prefer_volume_packs='if_missing_threshold')",
    )
    indexer_priority_weight: float = Field(
        default=1.0, description="Weight for indexer priority in ranking"
    )
    client_priority_weight: float = Field(
        default=1.0, description="Weight for download client priority in ranking"
    )
    prefer_source_type: Literal["usenet", "torrent", "http", "none"] = Field(
        default="none", description="Preferred source type (none = no preference)"
    )
