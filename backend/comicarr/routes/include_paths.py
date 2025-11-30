"""Include path routes for managing library include paths."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.dependencies import require_auth
from comicarr.db.models import IncludePath, Library

logger = structlog.get_logger("comicarr.routes.include_paths")


# Request/Response Models
class IncludePathResponse(BaseModel):
    """Include path response model."""

    id: str
    library_id: str
    path: str
    enabled: bool
    created_at: int
    updated_at: int


class IncludePathCreate(BaseModel):
    """Request model for creating an include path."""

    library_id: str = Field(..., description="Library ID")
    path: str = Field(
        ...,
        min_length=1,
        description="Absolute path to include folder (must be within library root)",
    )
    enabled: bool = Field(default=True, description="Enable include path")


class IncludePathUpdate(BaseModel):
    """Request model for updating an include path."""

    path: str | None = Field(
        default=None,
        min_length=1,
        description="Absolute path to include folder (must be within library root)",
    )
    enabled: bool | None = Field(default=None, description="Enable include path")


class IncludePathListResponse(BaseModel):
    """Response model for listing include paths."""

    include_paths: list[IncludePathResponse]


def create_include_paths_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create include paths router.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api", tags=["include-paths"])

    @router.get("/libraries/{library_id}/include-paths", response_model=IncludePathListResponse)
    async def list_include_paths(
        library_id: str,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IncludePathListResponse:
        """List all include paths for a library."""
        # Verify library exists
        library = await session.get(Library, library_id)
        if not library:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {library_id} not found",
            )

        result = await session.exec(select(IncludePath).where(IncludePath.library_id == library_id))
        include_paths = result.all()

        include_paths_list = [
            IncludePathResponse(
                id=ip.id,
                library_id=ip.library_id,
                path=ip.path,
                enabled=ip.enabled,
                created_at=ip.created_at,
                updated_at=ip.updated_at,
            )
            for ip in include_paths
        ]

        return IncludePathListResponse(include_paths=include_paths_list)

    @router.post(
        "/libraries/{library_id}/include-paths",
        status_code=status.HTTP_201_CREATED,
        response_model=IncludePathResponse,
    )
    async def create_include_path(
        library_id: str,
        payload: IncludePathCreate,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IncludePathResponse:
        """Create a new include path for a library."""
        # Verify library exists
        library = await session.get(Library, library_id)
        if not library:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {library_id} not found",
            )

        # Ensure library_id in payload matches URL parameter
        if payload.library_id != library_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Library ID in payload must match URL parameter",
            )

        # Check for duplicates (same path for same library)
        existing = await session.exec(
            select(IncludePath)
            .where(IncludePath.library_id == library_id)
            .where(IncludePath.path == payload.path)
        )
        if existing.one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Include path '{payload.path}' already exists for this library",
            )

        include_path = IncludePath(
            library_id=library_id,
            path=payload.path,
            enabled=payload.enabled,
        )

        session.add(include_path)
        await session.commit()
        await session.refresh(include_path)

        logger.info(
            "Include path created",
            include_path_id=include_path.id,
            library_id=library_id,
            path=include_path.path,
        )

        return IncludePathResponse(
            id=include_path.id,
            library_id=include_path.library_id,
            path=include_path.path,
            enabled=include_path.enabled,
            created_at=include_path.created_at,
            updated_at=include_path.updated_at,
        )

    @router.get("/include-paths/{include_path_id}", response_model=IncludePathResponse)
    async def get_include_path(
        include_path_id: str,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IncludePathResponse:
        """Get a single include path by ID."""
        include_path = await session.get(IncludePath, include_path_id)
        if not include_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Include path {include_path_id} not found",
            )

        return IncludePathResponse(
            id=include_path.id,
            library_id=include_path.library_id,
            path=include_path.path,
            enabled=include_path.enabled,
            created_at=include_path.created_at,
            updated_at=include_path.updated_at,
        )

    @router.put("/include-paths/{include_path_id}", response_model=IncludePathResponse)
    async def update_include_path(
        include_path_id: str,
        payload: IncludePathUpdate,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IncludePathResponse:
        """Update an include path."""
        include_path = await session.get(IncludePath, include_path_id)
        if not include_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Include path {include_path_id} not found",
            )

        # Update fields if provided
        if payload.path is not None:
            # Check for duplicates if path is being changed
            if payload.path != include_path.path:
                existing = await session.exec(
                    select(IncludePath)
                    .where(IncludePath.library_id == include_path.library_id)
                    .where(IncludePath.path == payload.path)
                    .where(IncludePath.id != include_path_id)
                )
                if existing.one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Include path '{payload.path}' already exists for this library",
                    )
            include_path.path = payload.path

        if payload.enabled is not None:
            include_path.enabled = payload.enabled

        include_path.updated_at = int(time.time())

        await session.commit()
        await session.refresh(include_path)

        logger.info(
            "Include path updated",
            include_path_id=include_path.id,
            path=include_path.path,
        )

        return IncludePathResponse(
            id=include_path.id,
            library_id=include_path.library_id,
            path=include_path.path,
            enabled=include_path.enabled,
            created_at=include_path.created_at,
            updated_at=include_path.updated_at,
        )

    @router.delete("/include-paths/{include_path_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_include_path(
        include_path_id: str,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> None:
        """Delete an include path."""
        include_path = await session.get(IncludePath, include_path_id)
        if not include_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Include path {include_path_id} not found",
            )

        await session.delete(include_path)
        await session.commit()

        logger.info(
            "Include path deleted",
            include_path_id=include_path_id,
            path=include_path.path,
        )

    return router
