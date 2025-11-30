"""Import processing - moves/links approved files to library."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import retry_db_operation
from comicarr.core.processing.naming import NamingService
from comicarr.core.utils import normalize_issue_number

# Import the consolidated version from weekly_releases to avoid duplication
from comicarr.core.weekly_releases.processing import _create_volume_from_comicvine
from comicarr.db.models import (
    ImportJob,
    ImportPendingFile,
    Library,
    LibraryIssue,
    LibraryVolume,
)
from comicarr.routes.comicvine import (
    fetch_comicvine,
)
from comicarr.routes.settings import _get_external_apis, _get_media_settings

logger = structlog.get_logger("comicarr.core.import_process")


def _resolve_volume_folder(library: Library, volume: LibraryVolume) -> Path:
    """Resolve the folder path for a volume.

    Args:
        library: Library containing the volume
        volume: Volume to get folder for

    Returns:
        Path to volume folder
    """
    library_root = Path(library.library_root)

    # Use custom folder name if set, otherwise use title
    if volume.folder_name:
        folder_name = volume.folder_name
    else:
        # Use volume_folder_naming template from media settings
        from comicarr.core.processing.naming import NamingService

        media_settings = _get_media_settings()
        template = media_settings.get("volume_folder_naming", "{Series Title}")

        naming_service = NamingService()
        folder_name = naming_service.render_volume_folder(
            template=template,
            volume_title=volume.title,
            volume_year=volume.year,
            Publisher=volume.publisher or "Unknown",
        )

    return library_root / folder_name


def _ensure_unique_path(target_path: Path) -> Path:
    """Ensure a file path is unique by appending a number if needed.

    Args:
        target_path: Desired file path

    Returns:
        Unique file path (may have number appended)
    """
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent

    counter = 1
    while True:
        new_name = f"{stem} ({counter}){suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


async def _process_pending_file(
    pending_file: ImportPendingFile,
    import_job: ImportJob,
    library: Library,
    session: SQLModelAsyncSession,
) -> tuple[bool, str | None]:
    """Process a single pending file.

    Args:
        pending_file: The pending file to process
        import_job: The import job
        library: The library
        session: Database session

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    try:
        source_path = Path(pending_file.file_path)

        if not source_path.exists():
            error_msg = f"Source file not found: {pending_file.file_path}"
            logger.warning(error_msg, job_id=import_job.id, pending_file_id=pending_file.id)
            return False, error_msg

        # Determine target volume and issue
        # Priority: 1) Manual selection (target_*), 2) ComicVine match, 3) Library match (matched_*)
        target_volume_id = pending_file.target_volume_id
        target_issue_id = pending_file.target_issue_id

        # If no manual selection, try ComicVine match first
        if not target_volume_id and pending_file.comicvine_volume_id:
            # Look up existing volume by ComicVine ID
            volume_result = await session.exec(
                select(LibraryVolume).where(
                    LibraryVolume.comicvine_id == pending_file.comicvine_volume_id,
                    LibraryVolume.library_id == import_job.library_id,
                )
            )
            volume = volume_result.one_or_none()

            if not volume:
                # Create volume from ComicVine
                try:
                    volume = await _create_volume_from_comicvine(
                        session=session,
                        comicvine_id=pending_file.comicvine_volume_id,
                        library_id=import_job.library_id,
                        monitored=True,
                        monitor_new_issues=True,
                    )
                    logger.info(
                        "Created volume from ComicVine",
                        volume_id=volume.id,
                        comicvine_id=pending_file.comicvine_volume_id,
                    )
                except Exception as exc:
                    error_msg = f"Failed to create volume for {pending_file.file_name}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    return False, error_msg

            target_volume_id = volume.id

        # Fall back to library match if no ComicVine match
        if not target_volume_id:
            target_volume_id = pending_file.matched_volume_id

        # Same logic for issue
        if not target_issue_id and pending_file.comicvine_issue_id and target_volume_id:
            # Look up existing issue by ComicVine ID
            issue_result = await session.exec(
                select(LibraryIssue).where(
                    LibraryIssue.comicvine_id == pending_file.comicvine_issue_id,
                    LibraryIssue.volume_id == target_volume_id,
                )
            )
            issue = issue_result.one_or_none()

            if not issue:
                # Create issue from ComicVine
                try:
                    volume = await session.get(LibraryVolume, target_volume_id)
                    if volume:
                        # Fetch issue details from ComicVine
                        external_apis = _get_external_apis()
                        comicvine_settings = external_apis.get("comicvine", {})
                        if comicvine_settings.get("api_key"):
                            from comicarr.routes.comicvine import normalize_comicvine_payload

                            normalized_settings = normalize_comicvine_payload(comicvine_settings)

                            issue_payload = await fetch_comicvine(
                                normalized_settings,
                                f"issue/4000-{pending_file.comicvine_issue_id}",
                                {
                                    "field_list": "id,issue_number,name,description,site_detail_url,image,cover_date,date_added,date_last_updated",
                                },
                            )
                            issue_data = issue_payload.get("results", {})

                            if issue_data:
                                # Extract issue image
                                issue_image = None
                                if isinstance(issue_data.get("image"), dict):
                                    issue_image = (
                                        issue_data["image"].get("medium_url")
                                        or issue_data["image"].get("original_url")
                                        or issue_data["image"].get("icon_url")
                                    )
                                elif isinstance(issue_data.get("image"), str):
                                    issue_image = issue_data["image"]

                                # Create the issue
                                issue = LibraryIssue(
                                    volume_id=volume.id,
                                    comicvine_id=pending_file.comicvine_issue_id,
                                    number=pending_file.extracted_issue_number
                                    or str(issue_data.get("issue_number", "?")),
                                    title=issue_data.get("name"),
                                    description=issue_data.get("description"),
                                    site_url=issue_data.get("site_detail_url"),
                                    release_date=issue_data.get("cover_date"),
                                    image=issue_image,
                                    status="wanted",  # New issues start as wanted
                                )

                                session.add(issue)
                                # Use retry logic for flush to handle lock errors
                                await retry_db_operation(
                                    lambda: session.flush(),
                                    session=session,
                                    operation_type="flush_issue",
                                )
                                target_issue_id = issue.id

                                logger.info(
                                    "Created issue from ComicVine during import",
                                    issue_id=issue.id,
                                    comicvine_id=pending_file.comicvine_issue_id,
                                    issue_number=issue.number,
                                )
                except Exception as exc:
                    logger.warning(
                        "Failed to create issue from ComicVine",
                        error=str(exc),
                        comicvine_issue_id=pending_file.comicvine_issue_id,
                        exc_info=True,
                    )

        # Fall back to library match or issue number matching
        if not target_issue_id:
            target_issue_id = pending_file.matched_issue_id

            # If still no issue and we have a volume, try matching by issue number
            if not target_issue_id and target_volume_id and pending_file.extracted_issue_number:
                volume = await session.get(LibraryVolume, target_volume_id)
                if volume:
                    issues_result = await session.exec(
                        select(LibraryIssue).where(LibraryIssue.volume_id == volume.id)
                    )
                    volume_issues = issues_result.all()

                    extracted_numeric = normalize_issue_number(pending_file.extracted_issue_number)
                    for vol_issue in volume_issues:
                        vol_issue_numeric = normalize_issue_number(vol_issue.number)
                        if (
                            extracted_numeric
                            and vol_issue_numeric
                            and abs(extracted_numeric - vol_issue_numeric) < 0.1
                        ):
                            target_issue_id = vol_issue.id
                            break

        if not target_volume_id or not target_issue_id:
            error_msg = f"No target volume/issue for: {pending_file.file_name}"
            logger.warning(error_msg)
            return False, error_msg

        # Get volume and issue
        volume = await session.get(LibraryVolume, target_volume_id)
        issue = await session.get(LibraryIssue, target_issue_id)

        if not volume or not issue:
            error_msg = f"Volume/issue not found for: {pending_file.file_name}"
            logger.warning(error_msg)
            return False, error_msg

        # Resolve target folder
        target_folder = _resolve_volume_folder(library, volume)
        target_folder.mkdir(parents=True, exist_ok=True)

        # Get media settings for filename template
        media_settings = _get_media_settings()
        file_naming_template = media_settings.get(
            "file_naming", "{Series Title} ({Year}) - {Issue:000}.{ext}"
        )

        # Generate target filename from template
        naming_service = NamingService()
        source_ext = source_path.suffix.lstrip(".")
        if not source_ext:
            source_ext = "cbz"  # Default extension

        # Check if template contains path separator (e.g., {Publisher}/...)
        # Split template into folder and filename parts if it contains /
        template_parts = file_naming_template.split("/", 1)
        if len(template_parts) == 2:
            # Template has folder structure (e.g., "{Publisher}/{Series Title}...")
            folder_template = template_parts[0]
            filename_template = template_parts[1]

            # Render folder name (e.g., Publisher)
            folder_name = naming_service.render_issue_filename(
                template=folder_template,
                volume_title=volume.title,
                issue_number=issue.number,
                ext=source_ext,
                release_date=issue.release_date,
                volume_year=volume.year,
                Publisher=volume.publisher or "Unknown",
            )
            # Sanitize folder name (but keep it as a folder name, not a filename)
            folder_name = naming_service._sanitize_filename(folder_name)

            # Render filename part
            rendered_filename = naming_service.render_issue_filename(
                template=filename_template,
                volume_title=volume.title,
                issue_number=issue.number,
                ext=source_ext,
                release_date=issue.release_date,
                volume_year=volume.year,
                Publisher=volume.publisher or "Unknown",
            )

            # Create publisher subfolder if folder_name is not empty
            if folder_name:
                target_folder = target_folder / folder_name
                target_folder.mkdir(parents=True, exist_ok=True)

            target_file = target_folder / rendered_filename
        else:
            # No path separator, just render the filename
            rendered_filename = naming_service.render_issue_filename(
                template=file_naming_template,
                volume_title=volume.title,
                issue_number=issue.number,
                ext=source_ext,
                release_date=issue.release_date,
                volume_year=volume.year,
                Publisher=volume.publisher or "Unknown",
            )
            target_file = target_folder / rendered_filename

        if target_file.exists() and target_file != source_path:
            target_file = _ensure_unique_path(target_file)

        # Determine whether to link or move the file
        # For external_folder: job.link_files is the primary setting
        # pending_file.action only overrides if explicitly set to "move" (to force move when link_files is True)
        should_link = False
        if import_job.scan_type == "root_folders":
            # Root folders: always link (files are already in root folders)
            should_link = True
        elif import_job.scan_type == "external_folder":
            # External folder: use job.link_files as the primary decision
            should_link = import_job.link_files
            # Only override if pending_file.action is explicitly "move" (to force move)
            if pending_file.action == "move":
                should_link = False
            # Note: We ignore pending_file.action == "link" to respect job.link_files setting

        # Move or link file
        if not should_link and import_job.scan_type == "external_folder":
            # Move file to target folder
            shutil.move(str(source_path), str(target_file))
            issue.file_path = str(target_file.relative_to(Path(library.library_root)))
            logger.info(f"Moved file {source_path} to {target_file}")
        elif should_link and import_job.scan_type == "external_folder":
            # Create symbolic link for external_folder scans when linking is enabled
            try:
                # Remove existing file/link if it exists
                if target_file.exists() or target_file.is_symlink():
                    target_file.unlink()

                # Create symbolic link (source is absolute, target is relative or absolute)
                # Use absolute path for source to avoid broken links
                os.symlink(str(source_path.resolve()), str(target_file))
                issue.file_path = str(target_file.relative_to(Path(library.library_root)))
                logger.info(f"Created symbolic link {target_file} -> {source_path}")
            except OSError as e:
                error_msg = f"Failed to create symbolic link for {pending_file.file_name}: {e}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg
        else:
            # Root folders scan: just update database (files already in library root)
            try:
                # Check if file is within library root
                library_root = Path(library.library_root)
                if library_root in source_path.parents or source_path == library_root:
                    issue.file_path = str(source_path.relative_to(library_root))
                else:
                    # File is outside library root, can't register directly
                    error_msg = (
                        f"File not in library root, cannot register: {pending_file.file_name}"
                    )
                    logger.warning(error_msg)
                    return False, error_msg
            except ValueError:
                error_msg = f"File not in library root, cannot register: {pending_file.file_name}"
                logger.warning(error_msg)
                return False, error_msg

        # Update issue with file info
        issue.file_size = pending_file.file_size
        issue.status = "ready"
        issue.updated_at = int(time.time())

        # Update pending file status to "processed" (consistent with weekly releases)
        pending_file.status = "processed"
        pending_file.updated_at = int(time.time())

        session.add(issue)
        # pending_file is already in the session, so changes will be saved
        # Use retry logic for commit to handle lock errors
        await retry_db_operation(
            lambda: session.commit(),
            session=session,
            operation_type="commit_import_file",
        )

        logger.info(
            "Processed file",
            job_id=import_job.id,
            pending_file_id=pending_file.id,
            file_name=pending_file.file_name,
            volume_id=target_volume_id,
            issue_id=target_issue_id,
        )

        return True, None

    except Exception as exc:
        error_msg = f"Failed to process file {pending_file.file_name}: {exc}"
        logger.error(
            error_msg, job_id=import_job.id, pending_file_id=pending_file.id, exc_info=True
        )
        return False, error_msg
