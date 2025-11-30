"""Library routes for managing libraries."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.dependencies import require_auth
from comicarr.core.processing.models import MediaSettings
from comicarr.db.models import Library, LibraryVolume

logger = structlog.get_logger("comicarr.routes.libraries")


# Request/Response Models
class LibraryResponse(BaseModel):
    """Library response model."""

    id: str
    name: str
    library_root: str
    default: bool
    enabled: bool
    settings: dict[str, Any]
    created_at: int
    updated_at: int
    volume_count: int = 0


class LibraryCreate(BaseModel):
    """Request model for creating a library."""

    name: str = Field(..., min_length=1, description="Library name")
    library_root: str = Field(..., min_length=1, description="Root path for library files")
    default: bool = Field(default=False, description="Set as default library")
    enabled: bool = Field(default=True, description="Enable library")
    settings: dict[str, Any] | None = Field(default=None, description="Library settings (optional)")


class LibraryUpdate(BaseModel):
    """Request model for updating a library."""

    name: str | None = Field(default=None, min_length=1, description="Library name")
    library_root: str | None = Field(
        default=None, min_length=1, description="Root path for library files"
    )
    default: bool | None = Field(default=None, description="Set as default library")
    enabled: bool | None = Field(default=None, description="Enable library")
    settings: dict[str, Any] | None = Field(default=None, description="Library settings")


class LibraryListResponse(BaseModel):
    """Response model for listing libraries."""

    libraries: list[LibraryResponse]


def create_libraries_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create libraries router.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api", tags=["libraries"])

    @router.get("/libraries", response_model=LibraryListResponse)
    async def list_libraries(
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> LibraryListResponse:
        """List all libraries with volume counts."""
        result = await session.exec(select(Library))
        libraries = result.all()

        libraries_list: list[LibraryResponse] = []

        for library in libraries:
            # Count volumes in this library
            volumes_result = await session.exec(
                select(LibraryVolume).where(LibraryVolume.library_id == library.id)
            )
            volume_count = len(volumes_result.all())

            library_dict = LibraryResponse(
                id=library.id,
                name=library.name,
                library_root=library.library_root,
                default=library.default,
                enabled=library.enabled,
                settings=library.settings,
                created_at=library.created_at,
                updated_at=library.updated_at,
                volume_count=volume_count,
            )
            libraries_list.append(library_dict)

        return LibraryListResponse(libraries=libraries_list)

    @router.post("/libraries", status_code=status.HTTP_201_CREATED, response_model=LibraryResponse)
    async def create_library(
        payload: LibraryCreate,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> LibraryResponse:
        """Create a new library."""
        # If this is set as default, unset other defaults
        if payload.default:
            result = await session.exec(select(Library).where(Library.default == True))
            existing_defaults = result.all()
            for lib in existing_defaults:
                lib.default = False
                lib.updated_at = int(time.time())

        # Use provided settings or default MediaSettings
        if payload.settings is None:
            default_settings = MediaSettings().model_dump()
        else:
            default_settings = payload.settings

        library = Library(
            name=payload.name,
            library_root=payload.library_root,
            default=payload.default,
            enabled=payload.enabled,
            settings=default_settings,
        )

        session.add(library)
        await session.commit()
        await session.refresh(library)

        logger.info("Library created", library_id=library.id, name=library.name)

        return LibraryResponse(
            id=library.id,
            name=library.name,
            library_root=library.library_root,
            default=library.default,
            enabled=library.enabled,
            settings=library.settings,
            created_at=library.created_at,
            updated_at=library.updated_at,
            volume_count=0,
        )

    @router.get("/libraries/{library_id}", response_model=LibraryResponse)
    async def get_library(
        library_id: str,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> LibraryResponse:
        """Get a single library by ID."""
        library = await session.get(Library, library_id)
        if not library:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {library_id} not found",
            )

        # Count volumes
        volumes_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.library_id == library.id)
        )
        volume_count = len(volumes_result.all())

        return LibraryResponse(
            id=library.id,
            name=library.name,
            library_root=library.library_root,
            default=library.default,
            enabled=library.enabled,
            settings=library.settings,
            created_at=library.created_at,
            updated_at=library.updated_at,
            volume_count=volume_count,
        )

    @router.put("/libraries/{library_id}", response_model=LibraryResponse)
    async def update_library(
        library_id: str,
        payload: LibraryUpdate,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> LibraryResponse:
        """Update a library."""
        library = await session.get(Library, library_id)
        if not library:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {library_id} not found",
            )

        # Update fields if provided
        if payload.name is not None:
            library.name = payload.name
        if payload.library_root is not None:
            library.library_root = payload.library_root
        if payload.enabled is not None:
            library.enabled = payload.enabled
        if payload.settings is not None:
            library.settings = payload.settings

        # Handle default flag - if setting to True, unset others
        if payload.default is not None:
            if payload.default and not library.default:
                # Unset other defaults
                result = await session.exec(select(Library).where(Library.default == True))
                existing_defaults = result.all()
                for lib in existing_defaults:
                    if lib.id != library_id:
                        lib.default = False
                        lib.updated_at = int(time.time())
            library.default = payload.default

        library.updated_at = int(time.time())

        await session.commit()
        await session.refresh(library)

        logger.info("Library updated", library_id=library.id, name=library.name)

        # Count volumes
        volumes_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.library_id == library.id)
        )
        volume_count = len(volumes_result.all())

        return LibraryResponse(
            id=library.id,
            name=library.name,
            library_root=library.library_root,
            default=library.default,
            enabled=library.enabled,
            settings=library.settings,
            created_at=library.created_at,
            updated_at=library.updated_at,
            volume_count=volume_count,
        )

    @router.delete("/libraries/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_library(
        library_id: str,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> None:
        """Delete a library.

        Note: This will fail if the library has volumes. You must delete or move volumes first.
        """
        library = await session.get(Library, library_id)
        if not library:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {library_id} not found",
            )

        # Check if library has volumes
        volumes_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.library_id == library_id)
        )
        volumes = volumes_result.all()
        if volumes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete library with {len(volumes)} volumes. Delete or move volumes first.",
            )

        # Check if this is the default library
        if library.default:
            # Set another library as default if available
            result = await session.exec(
                select(Library).where(Library.id != library_id).where(Library.enabled == True)
            )
            other_libraries = result.all()
            if other_libraries:
                other_libraries[0].default = True
                other_libraries[0].updated_at = int(time.time())

        await session.delete(library)
        await session.commit()

        logger.info("Library deleted", library_id=library_id)

    return router
