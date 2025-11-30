"""Reading routes for viewing comic book files."""

from __future__ import annotations

import io
import json
import re
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.dependencies import require_auth
from comicarr.core.settings_persistence import get_settings_file_path
from comicarr.db.models import Library, LibraryIssue, LibraryVolume

logger = structlog.get_logger("comicarr.routes.reading")

# Image file extensions (case-insensitive)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _is_image_file(filename: str) -> bool:
    """Check if a file is an image based on extension."""
    ext = Path(filename).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def _natural_sort_key(filename: str) -> tuple[int | str, ...]:
    """Generate a sort key for natural sorting of filenames.

    This ensures "page1.jpg" comes before "page10.jpg".
    """

    def convert(text: str) -> int | str:
        return int(text) if text.isdigit() else text.lower()

    return tuple(convert(c) for c in re.split(r"(\d+)", filename))


def _get_pages_from_zip(zip_path: Path) -> list[str]:
    """Extract sorted list of image filenames from a ZIP/CBZ file."""
    import zipfile

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Get all files, filter for images, and sort naturally
            image_files = [
                name for name in zf.namelist() if _is_image_file(name) and not name.endswith("/")
            ]
            # Sort naturally (page1.jpg before page10.jpg)
            image_files.sort(key=_natural_sort_key)
            return image_files
    except zipfile.BadZipFile as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ZIP file: {str(e)}",
        ) from e
    except Exception as e:
        logger.error("Failed to read ZIP file", path=str(zip_path), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read ZIP file: {str(e)}",
        ) from e


def _get_pages_from_rar(rar_path: Path) -> list[str]:
    """Extract sorted list of image filenames from a RAR/CBR file."""
    try:
        import rarfile
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="rarfile library is required for RAR/CBR support. Install with: pip install rarfile",
        )

    try:
        with rarfile.RarFile(str(rar_path), "r") as rf:
            # Get all files, filter for images, and sort naturally
            image_files = [
                name for name in rf.namelist() if _is_image_file(name) and not name.endswith("/")
            ]
            # Sort naturally (page1.jpg before page10.jpg)
            image_files.sort(key=_natural_sort_key)
            return image_files
    except rarfile.RarCannotExec:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="unrar command not found. rarfile requires unrar to read RAR files.",
        )
    except rarfile.BadRarFile as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid RAR file: {str(e)}",
        ) from e
    except Exception as e:
        logger.error("Failed to read RAR file", path=str(rar_path), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read RAR file: {str(e)}",
        ) from e


def _get_pages_from_archive(archive_path: Path) -> list[str]:
    """Get sorted list of image filenames from an archive (ZIP or RAR)."""
    ext = archive_path.suffix.lower()

    if ext in {".zip", ".cbz"}:
        return _get_pages_from_zip(archive_path)
    elif ext in {".rar", ".cbr"}:
        return _get_pages_from_rar(archive_path)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported archive format: {ext}. Only ZIP/CBZ and RAR/CBR are supported.",
        )


def _extract_image_from_zip(zip_path: Path, image_name: str) -> bytes:
    """Extract a specific image from a ZIP/CBZ file."""
    import zipfile

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if image_name not in zf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Image '{image_name}' not found in archive",
                )
            return zf.read(image_name)
    except zipfile.BadZipFile as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ZIP file: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(
            "Failed to extract image from ZIP",
            path=str(zip_path),
            image=image_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract image: {str(e)}",
        ) from e


def _extract_image_from_rar(rar_path: Path, image_name: str) -> bytes:
    """Extract a specific image from a RAR/CBR file."""
    try:
        import rarfile
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="rarfile library is required for RAR/CBR support. Install with: pip install rarfile",
        )

    try:
        with rarfile.RarFile(str(rar_path), "r") as rf:
            if image_name not in rf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Image '{image_name}' not found in archive",
                )
            return rf.read(image_name)
    except rarfile.RarCannotExec:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="unrar command not found. rarfile requires unrar to read RAR files.",
        )
    except rarfile.BadRarFile as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid RAR file: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(
            "Failed to extract image from RAR",
            path=str(rar_path),
            image=image_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract image: {str(e)}",
        ) from e


def _extract_image_from_archive(archive_path: Path, image_name: str) -> bytes:
    """Extract a specific image from an archive (ZIP or RAR)."""
    ext = archive_path.suffix.lower()

    if ext in {".zip", ".cbz"}:
        return _extract_image_from_zip(archive_path, image_name)
    elif ext in {".rar", ".cbr"}:
        return _extract_image_from_rar(archive_path, image_name)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported archive format: {ext}",
        )


def _is_reading_enabled() -> bool:
    """Check if reading functionality is enabled in settings."""
    settings_file = get_settings_file_path()

    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
                reading_settings = all_settings.get("reading", {})
                return reading_settings.get("enabled", True)  # Default to enabled
        except Exception:
            pass

    return True  # Default to enabled if settings file doesn't exist or can't be read


def create_reading_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create reading router.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api", tags=["reading"])

    @router.get("/reading/{issue_id}/pages")
    async def get_pages(
        issue_id: str,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """Get list of pages (images) in a comic book file.

        Returns:
            Dictionary with 'pages' list containing image filenames
        """
        # Check if reading is enabled
        if not _is_reading_enabled():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reading functionality is disabled",
            )

        # Get issue from database
        issue = await session.get(LibraryIssue, issue_id)
        if not issue:
            logger.warning("Issue not found", issue_id=issue_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue {issue_id} not found",
            )

        # Check if issue has a file
        if not issue.file_path:
            logger.warning("Issue has no file_path", issue_id=issue_id, issue_number=issue.number)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue has no file associated (status: {issue.status})",
            )

        # Get volume and library to construct full file path
        volume = await session.get(LibraryVolume, issue.volume_id)
        if not volume:
            logger.warning(
                "Volume not found for issue", issue_id=issue_id, volume_id=issue.volume_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Volume {issue.volume_id} not found",
            )

        library = await session.get(Library, volume.library_id)
        if not library:
            logger.warning(
                "Library not found for volume", volume_id=volume.id, library_id=volume.library_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {volume.library_id} not found",
            )

        # Construct full path: library_root + file_path (file_path is relative)
        archive_path = Path(library.library_root) / issue.file_path

        logger.debug(
            "Constructed archive path",
            issue_id=issue_id,
            library_root=library.library_root,
            file_path=issue.file_path,
            archive_path=str(archive_path),
            exists=archive_path.exists(),
        )

        if not archive_path.exists():
            logger.warning(
                "Archive file not found",
                issue_id=issue_id,
                archive_path=str(archive_path),
                library_root=library.library_root,
                file_path=issue.file_path,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {archive_path}",
            )

        # Get list of pages
        try:
            pages = _get_pages_from_archive(archive_path)
            return {"pages": pages}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Failed to get pages",
                issue_id=issue_id,
                path=str(archive_path),
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read archive: {str(e)}",
            ) from e

    @router.get("/reading/{issue_id}/page/{page_index}")
    async def get_page(
        issue_id: str,
        page_index: int,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> Response:
        """Get a specific page image from a comic book file.

        Args:
            issue_id: Issue ID
            page_index: Zero-based index of the page

        Returns:
            Image file as streaming response
        """
        # Check if reading is enabled
        if not _is_reading_enabled():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reading functionality is disabled",
            )

        # Get issue from database
        issue = await session.get(LibraryIssue, issue_id)
        if not issue:
            logger.warning("Issue not found", issue_id=issue_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue {issue_id} not found",
            )

        # Check if issue has a file
        if not issue.file_path:
            logger.warning("Issue has no file_path", issue_id=issue_id, issue_number=issue.number)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue has no file associated (status: {issue.status})",
            )

        # Get volume and library to construct full file path
        volume = await session.get(LibraryVolume, issue.volume_id)
        if not volume:
            logger.warning(
                "Volume not found for issue", issue_id=issue_id, volume_id=issue.volume_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Volume {issue.volume_id} not found",
            )

        library = await session.get(Library, volume.library_id)
        if not library:
            logger.warning(
                "Library not found for volume", volume_id=volume.id, library_id=volume.library_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {volume.library_id} not found",
            )

        # Construct full path
        archive_path = Path(library.library_root) / issue.file_path

        logger.debug(
            "Constructed archive path for page",
            issue_id=issue_id,
            page_index=page_index,
            library_root=library.library_root,
            file_path=issue.file_path,
            archive_path=str(archive_path),
            exists=archive_path.exists(),
        )

        if not archive_path.exists():
            logger.warning(
                "Archive file not found for page",
                issue_id=issue_id,
                page_index=page_index,
                archive_path=str(archive_path),
                library_root=library.library_root,
                file_path=issue.file_path,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {archive_path}",
            )

        # Get list of pages first
        try:
            pages = _get_pages_from_archive(archive_path)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Failed to get pages for page extraction",
                issue_id=issue_id,
                path=str(archive_path),
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read archive: {str(e)}",
            ) from e

        # Validate page index
        if page_index < 0 or page_index >= len(pages):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Page index {page_index} out of range (0-{len(pages)-1})",
            )

        # Extract the image
        image_name = pages[page_index]
        try:
            image_data = _extract_image_from_archive(archive_path, image_name)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Failed to extract page",
                issue_id=issue_id,
                page_index=page_index,
                image=image_name,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to extract page: {str(e)}",
            ) from e

        # Determine content type from file extension
        ext = Path(image_name).suffix.lower()
        content_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        content_type = content_type_map.get(ext, "image/jpeg")

        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(image_data),
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )

    return router
