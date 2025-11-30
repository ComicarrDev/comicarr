"""Application routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import structlog
from fastapi import APIRouter, FastAPI
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.routes import auth, comicvine, general, settings

logger = structlog.get_logger("comicarr.routes")


def create_app_router(
    app: FastAPI | None = None,
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]] | None = None,
) -> APIRouter:
    """Create and configure main application router.

    Args:
        app: FastAPI app instance
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter()

    # Include route modules that don't need database
    router.include_router(auth.router)  # Auth routes have their own prefix
    router.include_router(general.router, tags=["general"])
    router.include_router(settings.router, tags=["settings"])

    # Include ComicVine router (doesn't need database session)
    comicvine_router = comicvine.create_comicvine_router()
    router.include_router(comicvine_router, tags=["comicvine"])
    logger.debug("Included comicvine router in app_router")

    # Include routers that need database if get_db_session is available
    if app and get_db_session:
        from comicarr.routes.include_paths import create_include_paths_router
        from comicarr.routes.indexers import create_indexers_router
        from comicarr.routes.libraries import create_libraries_router
        from comicarr.routes.reading import create_reading_router
        from comicarr.routes.volumes import create_volumes_router

        indexers_router = create_indexers_router(get_db_session)
        router.include_router(indexers_router, tags=["indexers"])
        logger.debug("Included indexers router in app_router")

        volumes_router = create_volumes_router(get_db_session)
        router.include_router(volumes_router, tags=["volumes"])
        logger.debug("Included volumes router in app_router")

        libraries_router = create_libraries_router(get_db_session)
        router.include_router(libraries_router, tags=["libraries"])
        logger.debug("Included libraries router in app_router")

        include_paths_router = create_include_paths_router(get_db_session)
        router.include_router(include_paths_router, tags=["include-paths"])
        logger.debug("Included include paths router in app_router")

        from comicarr.routes.imports import create_imports_router

        imports_router = create_imports_router(get_db_session)
        router.include_router(imports_router, tags=["import"])
        logger.debug("Included imports router in app_router")

        from comicarr.routes.releases import create_releases_router

        releases_router = create_releases_router(get_db_session)
        router.include_router(releases_router, tags=["releases"])
        logger.debug("Included releases router in app_router")

        reading_router = create_reading_router(get_db_session)
        router.include_router(reading_router, tags=["reading"])
        logger.debug("Included reading router in app_router")

    return router


def include_db_dependent_routes(app: FastAPI) -> None:
    """Include routers that need database (legacy function, kept for future routers).

    Args:
        app: FastAPI app instance
    """
    # Indexers router is now included in create_app_router()
    # This function is kept for future routers like queue
    logger.debug("include_db_dependent_routes called (indexers already included in app_router)")
