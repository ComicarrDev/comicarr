"""Pydantic models for processing configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MediaSettings(BaseModel):
    """Media management settings for file processing."""

    # Renaming & Cleanup
    rename_downloaded_files: bool = Field(
        default=True, description="Enable automatic file renaming"
    )
    replace_illegal_characters: bool = Field(
        default=True, description="Replace illegal characters in filenames"
    )
    long_special_version: bool = Field(default=False, description="Use long special version format")
    create_empty_volume_folders: bool = Field(
        default=False, description="Create empty volume folders"
    )
    delete_empty_folders: bool = Field(default=False, description="Delete empty folders")
    unmonitor_deleted_issues: bool = Field(default=False, description="Unmonitor deleted issues")

    # File naming templates
    volume_folder_naming: str = Field(
        default="{Series Title} ({Year})", description="Template for volume folder names"
    )
    file_naming: str = Field(
        default="{Series Title} ({Year}) - {Issue:000}.{ext}",
        description="Template for renaming issue files",
    )
    file_naming_empty: str = Field(
        default="{Series Title} ({Year}) - {Issue:000}.{ext}",
        description="Template for empty volumes",
    )
    file_naming_special_version: str = Field(
        default="{Series Title} ({Year}) - {Issue:000} - {Special}.{ext}",
        description="Template for special version files",
    )
    file_naming_vai: str = Field(
        default="{Series Title} ({Year}) - {Issue:000}.{ext}",
        description="Template for volume alternate issue files",
    )

    # Conversion
    convert: bool = Field(default=False, description="Enable automatic format conversion")
    extract_issue_ranges: bool = Field(
        default=False, description="Extract issue ranges from archives"
    )
    format_preference: list[str] = Field(
        default_factory=lambda: ["No Conversion"],
        description="Preferred file formats in order of preference",
    )

    # Legacy fields (for backward compatibility)
    convert_files: bool = Field(default=False, description="Legacy: use 'convert' instead")
    preferred_format: Literal["CBZ", "CBR", "CB7", "PDF", "No Conversion"] = Field(
        default="No Conversion", description="Legacy: use 'format_preference' instead"
    )
    file_naming_template: str = Field(
        default="{Series Title} ({Year}) - {Issue Number:03d}.{ext}",
        description="Legacy: use 'file_naming' instead",
    )
    processing_order: Literal["rename_then_convert", "convert_then_rename"] = Field(
        default="rename_then_convert", description="Order of post-processing operations"
    )
