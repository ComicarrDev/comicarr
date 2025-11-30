# Comicarr Design Document

> **Purpose**: This document defines the architectural patterns, design decisions, and conventions used in Comicarr. All implementation must follow these patterns. When new patterns emerge, document them here first.

## Table of Contents

1. [Stack](#1-stack)
2. [Type Safety and Code Quality](#2-type-safety-and-code-quality)
3. [Architecture Overview](#3-architecture-overview)
4. [Project Structure](#4-project-structure)
5. [Routes Layer](#5-routes-layer)
6. [Core Layer](#6-core-layer)
7. [Job Queue System](#7-job-queue-system)
8. [Indexer Client Patterns](#8-indexer-client-patterns)
9. [Settings Management](#9-settings-management)
10. [Frontend Patterns](#10-frontend-patterns)
11. [Database Patterns](#11-database-patterns)
12. [Authentication](#12-authentication)
13. [Distributed Tracing](#13-distributed-tracing)
14. [Error Handling](#14-error-handling)
15. [Testing](#15-testing)
16. [Configuration](#16-configuration)

---

## 1. Stack

### 1.1 Backend

1.1.1 **FastAPI** - Web framework prioritizing async operations.

1.1.2 **SQLite (async)** - Database using `aiosqlite` for async operations.

1.1.3 **Alembic** - Database migrations. Migrations are **not** auto-applied on startup. The app checks schema status and logs warnings if migrations are pending. Users must run `alembic upgrade head` manually.

1.1.4 **Static File Serving** - FastAPI serves the Vite-built React app from `backend/comicarr/static/frontend/` directory. This is **Client-Side Rendering (CSR)**, not server-side rendering (SSR).

1.1.5 **Background Jobs** - Jobs are stored as stateful models in the database with status fields. Jobs are processed by creating background tasks (`asyncio.create_task`) that call job processor functions. This approach is sufficient for a single-user application. A `WorkerManager` with persisted async queues could be implemented as a future improvement for better concurrency control and scalability (see [Job Queue System](#7-job-queue-system) for details).

1.1.6 **Structured Logging** - `structlog` for all logging. All log messages include context (resource IDs, trace IDs, etc.).

1.1.7 **Metrics** - Prometheus metrics exported via `prometheus-fastapi-instrumentator`. All metrics are documented in `METRICS.md`.

1.1.8 **OpenAPI Documentation** - FastAPI auto-generates OpenAPI/Swagger docs at `/docs`.

1.1.9 **Data Models** - Pydantic for request/response validation, SQLModel for database models.

1.1.10 **HTTP Clients** - `httpx` for all external HTTP requests with proper timeout and redirect handling.

1.1.11 **Task Scheduling** - `apscheduler` for scheduled tasks (e.g., weekly releases).

### 1.2 Frontend

1.2.1 **Build Tool**: Vite 5.x - Fast development server and optimized production builds.

1.2.2 **Language**: TypeScript with strict type checking. Separate configs for app, node, and tests.

1.2.3 **Framework**: React 18.x with React Router DOM v6 for routing.

1.2.4 **State Management**: React Context API for global state (auth, page actions). Local component state with hooks (`useState`, `useEffect`) for UI state.

1.2.5 **Styling**: CSS modules (`.css` files alongside components). No CSS-in-JS or preprocessors.

1.2.6 **Testing**: Vitest with React Testing Library for component testing.

1.2.7 **Toast Notifications**: Sonner (`sonner` package) for user feedback.

1.2.8 **Icons**: Lucide React (`lucide-react`) for icon components.

---

## 2. Type Safety and Code Quality

### 2.1 Type Hints and Avoiding `Any`

**CRITICAL**: We avoid `typing.Any` at all costs. Using `Any` defeats the purpose of type checking and makes code harder to understand and maintain.

**Rules:**
1. **Never use `Any`** - If you find yourself reaching for `Any`, find the proper type instead.
2. **Use TYPE_CHECKING** - For types only needed at type-checking time (imports that would cause circular dependencies).
3. **Use Union types** - Instead of `Any`, use `Union[str, int, None]` or more specific unions.
4. **Use Protocols/TypedDict** - For structural typing when inheritance isn't appropriate.
5. **Be specific with Dict/List** - Use `Dict[str, str]` not `Dict[str, Any]`. Use TypedDict for complex dictionaries.
6. **Use proper exception types** - Use `Type[BaseException]`, `TracebackType | None`, etc., instead of `Any` for exception handling.
7. **Prefer `X | None` over `Optional[X]`** - Use the modern union syntax `X | None` instead of `Optional[X]` for nullable types.

**When you can't avoid it:**
- Only in external library interfaces where we have no control
- Document why `Any` is necessary with a comment
- Consider creating a Protocol or TypedDict to type the external interface

**Examples:**

```python
# ❌ BAD
def process_data(data: Any) -> Dict[str, Any]:
    ...

# ✅ GOOD
def process_data(data: Dict[str, Union[str, int, None]]) -> Dict[str, str]:
    ...

# ✅ GOOD (with TypedDict)
from typing import TypedDict

class ProcessedData(TypedDict):
    id: str
    status: str
    count: int

def process_data(data: Dict[str, Union[str, int]]) -> ProcessedData:
    ...

# ❌ BAD (old-style Optional)
from typing import Optional

def get_user(name: Optional[str] = None) -> Optional[User]:
    ...

# ✅ GOOD (modern union syntax)
def get_user(name: str | None = None) -> User | None:
    ...
```

### 2.2 Code Quality Tools

- **Black** - Code formatter (line length: 100)
- **isort** - Import sorting
- **ruff** - Fast linter (replaces flake8, pylint, etc.)
- **pyrefly** - Type checker (stricter than mypy)
- **Pre-commit hooks** - All tools run automatically on commit

---

## 3. Architecture Overview

### 3.1 High-Level Layers

```
┌─────────────────────────────────────┐
│         Frontend (React)            │
│  - Pages, Components, State Mgmt    │
└──────────────┬──────────────────────┘
               │ HTTP/REST
┌──────────────▼──────────────────────┐
│       API Routes (FastAPI)          │
│  - Request/Response Handling        │
│  - Authentication/Authorization     │
│  - Create Jobs (stateful models)   │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│      Core Layer (Business Logic)    │
│  - Domain Logic                     │
│  - External API Integration         │
│  - Job Processors                   │
│  - Background Tasks (asyncio)       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│    Data Layer (SQLModel/SQLite)     │
│  - Models, Migrations, Queries      │
│  - Job State (queued/processing/etc)│
└─────────────────────────────────────┘
```

### 3.2 Principles

1. **Separation of Concerns**: Each layer has a single responsibility.
2. **Async-First**: All I/O operations are asynchronous.
3. **Type Safety**: Type hints throughout, validated at runtime where needed.
4. **Error Transparency**: Errors bubble up with context, user-friendly messages at API boundary.
5. **Testability**: Layers can be tested in isolation with mocked dependencies.

---

## 4. Project Structure

### 4.1 Directory Layout

```
backend/
├── comicarr/
│   ├── __init__.py
│   ├── app.py                    # FastAPI app entry point
│   ├── core/                     # Core business logic
│   │   ├── __init__.py
│   │   ├── auth.py               # Password hashing/verification
│   │   ├── bootstrap.py          # Startup bootstrap (indexers, libraries)
│   │   ├── config.py             # Settings/configuration
│   │   ├── database.py           # Database setup
│   │   ├── dependencies.py       # FastAPI dependencies
│   │   ├── logging.py            # Logging setup
│   │   ├── metrics.py            # Prometheus metrics
│   │   ├── middleware.py         # HTTP middleware
│   │   ├── models.py             # Core domain models
│   │   ├── routes.py             # Route registration
│   │   ├── security.py           # Security utilities
│   │   ├── settings_persistence.py # Settings file I/O
│   │   ├── tracing.py            # Distributed tracing
│   │   ├── utils.py              # Utility functions
│   │   ├── clients/              # External HTTP clients
│   │   ├── comicvine/            # ComicVine API client
│   │   ├── indexers/             # Indexer clients (base, newznab, etc.)
│   │   ├── matching/             # Volume/issue matching logic
│   │   ├── processing/           # File processing (rename, conversion)
│   │   ├── search/               # Search functionality
│   │   └── weekly_releases/      # Weekly releases processing
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py             # SQLModel database models
│   │   └── migrations/           # Alembic migrations
│   ├── routes/                   # API route handlers
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── comicvine.py
│   │   ├── general.py
│   │   ├── imports.py
│   │   ├── indexers.py
│   │   ├── libraries.py
│   │   ├── queue.py
│   │   ├── reading.py
│   │   ├── releases.py
│   │   ├── settings.py
│   │   └── volumes.py
│   └── static/
│       └── frontend/              # Built frontend assets
frontend/
├── src/
│   ├── api/                       # API client
│   ├── components/                # Reusable components
│   ├── contexts/                  # React contexts
│   ├── pages/                     # Page components
│   └── themes/                    # Theme definitions
└── package.json
```

### 4.2 Module Organization

- **`routes/`** - HTTP route handlers (thin controllers)
- **`core/`** - Business logic, utilities, external integrations
- **`db/`** - Database models and migrations
- **`static/frontend/`** - Built frontend assets (served by FastAPI)

---

## 5. Routes Layer

### 5.1 Route Organization

**Pattern**: Routes are organized by domain in separate files. Each route file exports a factory function that creates and returns an `APIRouter`.

**Structure**:
```python
# routes/volumes.py
from fastapi import APIRouter, Depends
from collections.abc import AsyncIterator, Callable
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

def create_volumes_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]]
) -> APIRouter:
    """Create volumes router."""
    router = APIRouter(prefix="/api/volumes", tags=["volumes"])
    
    @router.get("/")
    async def list_volumes(
        session: SQLModelAsyncSession = Depends(get_db_session),
    ):
        # Route implementation
        ...
    
    return router
```

**Route Registration**:
Routes are registered in `core/routes.py` using `create_app_router()`:

```python
# core/routes.py
def create_app_router(
    app: FastAPI | None = None,
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]] | None = None,
) -> APIRouter:
    router = APIRouter()
    
    # Routes that don't need database
    router.include_router(auth.router)
    router.include_router(general.router, tags=["general"])
    
    # Routes that need database
    if app and get_db_session:
        volumes_router = create_volumes_router(get_db_session)
        router.include_router(volumes_router, tags=["volumes"])
        # ... other routers
    
    return router
```

### 5.2 Route Patterns

1. **Thin Controllers** - Routes delegate to core functions immediately.
2. **Pydantic Models** - Use Pydantic for request/response validation.
3. **Dependency Injection** - Use FastAPI `Depends()` for database sessions and auth.
4. **Structured Responses** - Return Pydantic models or dictionaries.
5. **Error Handling** - Use HTTPException with appropriate status codes.
6. **Logging** - Log all operations with context using structlog.

**Example**:
```python
@router.get("/{volume_id}")
async def get_volume(
    volume_id: str,
    session: SQLModelAsyncSession = Depends(get_db_session),
    _: None = Depends(require_auth),
) -> VolumeResponse:
    """Get volume by ID."""
    logger.info("Getting volume", volume_id=volume_id)
    
    volume = await session.get(LibraryVolume, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    
    return VolumeResponse.from_orm(volume)
```

### 5.3 Route Files

- `auth.py` - Authentication endpoints
- `comicvine.py` - ComicVine API proxy
- `general.py` - General endpoints (health, etc.)
- `imports.py` - Import job management
- `indexers.py` - Indexer management
- `libraries.py` - Library management
- `queue.py` - Job queue management
- `reading.py` - Reading progress
- `releases.py` - Weekly releases
- `settings.py` - Settings management
- `volumes.py` - Volume management

---

## 6. Core Layer

### 6.1 Core Modules

The `core/` directory contains business logic, utilities, and external integrations:

**Core Utilities**:
- `auth.py` - Password hashing/verification (bcrypt)
- `bootstrap.py` - Startup initialization (indexers, libraries)
- `config.py` - Settings/configuration (Pydantic Settings)
- `database.py` - Database engine and session factory
- `dependencies.py` - FastAPI dependencies (auth, sessions)
- `logging.py` - Structured logging setup
- `metrics.py` - Prometheus metrics
- `middleware.py` - HTTP middleware (tracing, etc.)
- `models.py` - Core domain models (non-database)
- `security.py` - Security utilities
- `settings_persistence.py` - Settings file I/O
- `tracing.py` - Distributed tracing
- `utils.py` - General utilities

**Domain Modules**:
- `clients/` - External HTTP clients (base client, getcomics, readcomicsonline)
- `comicvine/` - ComicVine API client
- `indexers/` - Indexer clients (base, newznab, torznab, getcomics, readcomicsonline)
- `matching/` - Volume/issue matching logic
- `processing/` - File processing (rename, conversion, naming)
- `search/` - Search functionality (normalization, caching, blacklist)
- `weekly_releases/` - Weekly releases processing

### 6.2 Job Processors

Job processors are async functions that process individual jobs. They are called by background tasks created via `asyncio.create_task`:

**Pattern**:
```python
# core/import_processing_job_processor.py
async def process_import_processing_job(
    session: SQLModelAsyncSession,
    job_id: str,
) -> None:
    """Process an import processing job."""
    # Load job from database
    job = await session.get(ImportProcessingJob, job_id)
    
    # Update status to processing
    job.status = "processing"
    await session.commit()
    
    try:
        # Do the work
        ...
        job.status = "completed"
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
    finally:
        await session.commit()
```

**Job Processor Files**:
- `import_processing_job_processor.py` - Process import jobs
- `import_scanning_job_processor.py` - Scan files for import
- `weekly_releases/job_processor.py` - Process weekly releases
- `weekly_releases/matching_job_processor.py` - Match weekly releases

### 6.3 Processing Services

**TODO**: File processing logic would be in `core/processing/` when implemented:

- `conversion.py` - File conversion (CBR → CBZ, etc.) - *Not yet implemented*
- `naming.py` - Naming template rendering - *Not yet implemented*
- `rename.py` - File renaming - *Not yet implemented*
- `service.py` - Processing service orchestration - *Not yet implemented*

**Note**: These modules exist in the workspace branch but are part of the unused WorkerManager pattern. They would need to be adapted to the current stateful model approach if implemented.

---

## 7. Job Queue System

### 7.1 Current Approach: Stateful Database Models

**Pattern**: Jobs are stored as stateful models in the database with status fields. Jobs are processed by creating background tasks directly.

**Why This Approach**:
- **Simple**: Direct task creation, no queue abstraction needed
- **Durable**: Jobs persist in database, survive restarts
- **Sufficient for Single-User**: For a single-user application, this provides adequate concurrency and job management
- **Easy to Query**: Can easily query job status, progress, errors from database
- **No Additional Infrastructure**: No need for message brokers or queue systems

**Job Model Pattern**:
All jobs must:
- Have `id`, `status`, `created_at`, `updated_at` fields
- Status flow: `queued` → `processing` → `completed` / `failed` / `cancelled`
- Track `progress` and `total` when applicable
- Store `error` message on failure
- Optionally track `retry_count` for retry logic

**Job Types** (in `db/models.py`):
- `ImportJob` - Import scan operations
- `ImportScanningJob` - Background scanning job
- `ImportProcessingJob` - Background processing job
- `WeeklyReleaseProcessingJob` - Process weekly releases
- `WeeklyReleaseMatchingJob` - Match weekly releases to volumes

### 7.2 Current Job Processing Pattern

**How Jobs Are Processed**:

```python
# 1. Create job in database (status: 'queued')
job = ImportProcessingJob(
    id=job_id,
    import_job_id=import_job_id,
    status='queued'
)
session.add(job)
await session.commit()

# 2. Start background task to process job
async def run_job(job_id: str):
    async with session_factory() as session:
        await process_import_processing_job(session, job_id)

asyncio.create_task(run_job(job.id))
```

**Job Processor Functions**:
- Job processors are async functions: `async def process_*_job(session, job_id) -> None`
- They load the job from database, update status to `processing`, do the work, then update to `completed`/`failed`
- Located in `core/` (e.g., `import_processing_job_processor.py`, `weekly_releases/job_processor.py`)

**Job Recovery on Startup**:
On application startup, jobs with status `queued` or `processing` are recovered and restarted:

```python
# In app.py lifespan
processing_jobs = await session.exec(
    select(ImportProcessingJob).where(
        col(ImportProcessingJob.status).in_(["queued", "processing"])
    )
)
for job in processing_jobs:
    if job.status == "processing":
        job.status = "queued"  # Reset stuck jobs
        await session.commit()
    asyncio.create_task(run_job(job.id))
```

**Limitations of Current Approach**:
- No built-in retry/backoff logic (must be implemented in each processor)
- Limited concurrency control (all tasks run concurrently)
- No worker pool management
- Harder to rate-limit or throttle jobs

### 7.3 Future Improvement: Persisted Async Queues

**When to Consider**: If we need better concurrency control, retry logic, rate limiting, or plan to scale to multiple instances.

**TODO: Implement `WorkerManager` Pattern**

A `WorkerManager` class could be implemented to provide persisted async queues:

```python
class WorkerManager:
    def __init__(self, session_factory: async_sessionmaker):
        # Create queues
        self.rename_queue: asyncio.Queue[str] = asyncio.Queue()
        self.conversion_queue: asyncio.Queue[str] = asyncio.Queue()
        
        # Create workers
        self.rename_worker = RenameWorker(...)
        self.conversion_worker = ConversionWorker(...)
    
    async def start(self) -> None:
        """Start all background workers."""
        # Load queued jobs from database into queues
        await self._load_queued_jobs()
        
        # Start worker loops
        self._rename_task = asyncio.create_task(self._rename_worker_loop())
        self._conversion_task = asyncio.create_task(self._conversion_worker_loop())
    
    async def _load_queued_jobs(self) -> None:
        """Load queued jobs from database into queues on startup."""
        async with self.session_factory() as session:
            queued_rename_jobs = await session.exec(
                select(RenameJob).where(RenameJob.status == "queued")
            )
            for job in queued_rename_jobs:
                await self.rename_queue.put(job.id)
    
    async def _rename_worker_loop(self) -> None:
        """Main loop for rename worker."""
        while self._running:
            job_id = await self.rename_queue.get()
            async with self.session_factory() as session:
                await process_rename_job(session, job_id)
            self.rename_queue.task_done()
```

**Benefits of Persisted Async Queues**:
- ✅ **Durability**: Jobs persist in database, survive restarts
- ✅ **Performance**: In-memory queues are fast
- ✅ **Concurrency Control**: Worker pools, rate limiting, backpressure
- ✅ **Retry Logic**: Built into worker loops
- ✅ **Observability**: Can monitor queue depth
- ✅ **Scalability**: Can add more workers or scale horizontally
- ✅ **Standard Pattern**: Used by Celery, RQ, Sidekiq, Bull, etc.

**Implementation Steps** (if we decide to implement):
1. Create `WorkerManager` class in `core/workers/manager.py`
2. Start `WorkerManager` in application lifespan
3. Load queued jobs from database into queues on startup
4. Update job creation to: persist to DB → add to queue
5. Workers consume from queue → update DB status
6. Gradually migrate job types to use queues

**Trade-offs**:
- ⚠️ More complex than direct task creation
- ⚠️ Need to handle queue persistence on startup
- ⚠️ Need to handle queue overflow/backpressure
- ✅ Better for production workloads and scaling

---

## 8. Indexer Client Patterns

### 8.1 Base Indexer Client

All indexer clients inherit from `IndexerClient` base class (`core/indexers/base.py`):

**Pattern**:
```python
from abc import ABC, abstractmethod

class IndexerClient(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = structlog.get_logger(f"comicarr.indexers.{name.lower()}")
    
    @abstractmethod
    async def search(
        self,
        query: str | None = None,
        title: str | None = None,
        issue_number: str | None = None,
        year: int | None = None,
        categories: list[int] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Search for content."""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connection to the indexer."""
        pass
```

### 8.2 Indexer Implementations

- `newznab.py` - Newznab-compatible indexers
- `torznab.py` - Torznab-compatible indexers
- `getcomics.py` - GetComics indexer
- `readcomicsonline.py` - ReadComicsOnline indexer

### 8.3 Client Error Handling

- Catch `httpx.ConnectTimeout` separately (show timeout message)
- Catch `httpx.ConnectError` separately (show connection failure)
- Catch `httpx.HTTPStatusError` for HTTP errors (show status code and message)
- Log all errors with context (URL, parameters, etc.)
- Return user-friendly error messages

---

## 9. Settings Management

### 9.1 Configuration Structure

**Storage**: Settings stored in JSON file (`settings.json` in `config_dir`).

**Format**: **Flat structure** (not nested). Settings use prefixed field names:

```json
{
  "host_bind_address": "127.0.0.1",
  "host_port": 8000,
  "host_base_url": "",
  "external_apis_comicvine_api_key": "...",
  "external_apis_comicvine_base_url": "...",
  "external_apis_comicvine_enabled": true
}
```

**Backend**: Uses flat prefixed field names (`host_bind_address`, `external_apis_comicvine_api_key`) for simplicity.

**Loading**:
- Loaded on startup via Pydantic Settings
- Local config file has precedence over environment variables
- Settings reloaded after save to ensure consistency

### 9.2 Settings Persistence

Settings are saved via `core/settings_persistence.py`:

```python
from comicarr.core.settings_persistence import save_settings_to_file

# Save settings
save_settings_to_file({
    "host_port": 8080,
    "external_apis_comicvine_enabled": False
})
```

### 9.3 Settings Categories

- **Host Settings**: `host_bind_address`, `host_port`, `host_base_url`
- **Logging**: `log_level` (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Directories**: `data_dir`, `config_dir`, `database_dir`, `cache_dir`, `library_dir`, `logs_dir`
- **Database**: `database_url`
- **External APIs**: `external_apis_comicvine_*` (api_key, base_url, enabled)
- **Weekly Releases**: `weekly_releases_auto_fetch_enabled`, `weekly_releases_auto_fetch_interval_hours`
- **Security**: Stored in separate `security.json` file (auth method, username, password hash, API key)

### 9.4 Settings Pages Pattern

1. **Settings Index Page** (`/settings`): Card-based navigation
2. **Category Pages**: Individual settings pages for each category
3. **Breadcrumb Navigation**: Shows current location
4. **Individual Save Buttons**: Each category has its own save button
5. **Change Detection**: Save buttons disabled until changes detected
6. **Toast Notifications**: Multiple toasts shown when multiple settings change

---

## 10. Frontend Patterns

### 10.1 Modal Pattern

All modals must:
- Use flexbox layout for proper scrolling
- Footer buttons: `flex-shrink: 0` to prevent clipping
- Body: `flex: 1; min-height: 0; overflow: auto` for scrolling
- Test buttons return detailed success/error messages
- Cancel button closes modal without saving

### 10.2 Form Pattern

- Controlled components (React state)
- Validation on blur/submit
- Clear error messages
- Loading states during async operations
- Disable form during save/test operations

### 10.3 Status Display Pattern

- Use consistent status badges/colors
- Progress bars for long operations
- Indeterminate progress when progress data not available
- Time ago formatting for timestamps
- Show "X ago" for relative times

### 10.4 Component Structure

- **Pages**: Route-level components in `pages/` directory
- **Components**: Reusable components in `components/` directory
- **Contexts**: Global state providers in `contexts/` and `auth/`
- **CSS**: Component-scoped CSS files (`.css` files alongside components)

### 10.5 Routing Pattern

- Use React Router v6 with `BrowserRouter`
- Protected routes using `RequireAuth` component
- Nested routes where appropriate
- Link components for navigation

### 10.6 Layout Pattern

**Three-Panel Layout**: Comicarr uses a consistent three-panel layout:

1. **Left Sidebar (Collapsible)**:
   - Fixed navigation menu with primary sections
   - Collapsible to save screen space (persists state to localStorage)
   - Collapsed state shows icons only, expanded shows full labels
   - Dark theme (#0f172a) with yellow accent (#facc15)
   - **Notch Toggle**: A notch/handle on the right edge toggles collapse/expand
   - **Logo and Branding**: Logo + text when expanded, logo only when collapsed

2. **Top Header**:
   - Breadcrumb navigation showing current location
   - User authentication controls (when forms auth is enabled)
   - Clean, minimal design

3. **Main Content Area**:
   - Dashboard-style summary cards on home page
   - Consistent padding and spacing
   - Light background (#f4f6fb) for visual separation

### 10.7 Toast Notifications

**Library**: Sonner (`sonner` npm package).

**Usage**: All user feedback uses toast notifications:

```typescript
import { toast } from 'sonner';

// Success
toast.success("Operation completed successfully");

// Error
toast.error("Operation failed: reason");

// Loading with Promise
toast.promise(asyncOperation(), {
  loading: "Processing...",
  success: "Done",
  error: "Failed"
});
```

---

## 11. Database Patterns

### 11.1 Model Naming

- **Models**: Singular nouns: `LibraryVolume`, `LibraryIssue`, `DownloadJob`
- **Tables**: Plural, snake_case: `library_volumes`, `library_issues`, `download_jobs`

### 11.2 Migration Pattern

- **Never auto-migrate on startup**
- Check schema on startup, log warning if migrations are pending
- User runs `alembic upgrade head` manually
- This prevents blocking startup and migration conflicts

**Migration Workflow**:
1. Create migration: `alembic revision --autogenerate -m "description"`
2. Review generated migration
3. Test migration: `alembic upgrade head`
4. Commit migration to version control

### 11.3 Session Management

- Use async sessions everywhere (`SQLModelAsyncSession` from `sqlmodel.ext.asyncio.session`)
- Pass session as parameter (don't create in functions)
- Commit explicitly in routes/processors (not in model methods)
- Always use `async with session:` or dependency injection
- Don't share sessions across concurrent operations
- Session factory returns `async_sessionmaker[SQLModelAsyncSession]`

### 11.4 Query Patterns

- Use SQLModel's query syntax for type safety
- Use `session.exec()` for queries (not deprecated `session.execute()`)
- Avoid raw SQL when possible
- Filter before fetching when possible

### 11.5 Model Location

All database models are defined in `db/models.py` and imported in `db/__init__.py`.

---

## 12. Authentication

### 12.1 Authentication Overview

Comicarr is a **single-user application**. Authentication is optional and configurable.

### 12.2 Authentication Methods

We support two authentication methods:

1. **`"none"`**: No authentication required
2. **`"forms"`**: Form-based authentication with username and password

### 12.3 Security Configuration

**Storage**: Security configuration is stored in `config_dir/security.json` (not in database).

**Configuration Structure**:
```json
{
  "auth_method": "forms",
  "username": "admin",
  "password_hash": "$2b$12$..."  // bcrypt hash, never plaintext
}
```

### 12.4 Password Hashing

- Use **bcrypt** for password hashing (12 rounds)
- Passwords are **never stored in plaintext**
- Plaintext passwords only exist in memory during initial setup/login

### 12.5 Bootstrap Logic

**First Run Detection**:
1. On startup, check if `config_dir/security.json` exists
2. If **not exists**:
   - Check for `COMICARR_USERNAME` and `COMICARR_PASSWORD` environment variables
   - If env vars exist → auto-create user from env vars
   - If not → wait for setup via `/api/auth/setup` endpoint
3. If **exists**: Load configuration, ignore env vars

### 12.6 Session Management

- Use **Starlette SessionMiddleware** for session management
- Sessions stored in encrypted cookies (7-day expiry)
- Session secret key configurable via `COMICARR_SECRET_KEY` environment variable

### 12.7 Authentication Endpoints

- `POST /api/auth/setup` - Initial setup (unauthenticated, only works if no config exists)
- `POST /api/auth/login` - Login with username/password
- `POST /api/auth/logout` - Logout (clear session)
- `GET /api/auth/session` - Get current session status

### 12.8 Protected Routes

- Use `require_auth()` dependency for protected routes
- Works with both `"none"` (always allows) and `"forms"` (checks session) auth methods

---

## 13. Distributed Tracing

### 13.1 Tracing Overview

Comicarr implements distributed tracing to track requests across async operations and background tasks.

**Problem**: When multiple async tasks run in parallel, logs from different operations interleave, making it difficult to follow a single operation's flow.

**Solution**: Each request/operation gets a unique **trace ID** that propagates through all async operations. All logs include the trace ID.

### 13.2 Trace ID Format

- **Format**: 32-character hexadecimal string (UUID4 hex)
- **Generation**: Automatically generated per request, or can be set manually
- **Example**: `a1b2c3d4e5f6789012345678901234ab`

### 13.3 Automatic Request Tracing

**`TracingMiddleware`** automatically:
1. Extracts `X-Trace-ID` header from incoming requests
2. Generates a new trace ID if not present
3. Sets trace ID in `structlog.contextvars` context for the request
4. Adds trace ID to response headers as `X-Trace-ID`
5. Ensures all logs during request processing include the trace ID

### 13.4 Manual Trace Context Management

For background tasks or operations that span multiple async tasks:

```python
from comicarr.core.tracing import trace_context

async def process_volume(volume_id: str):
    with trace_context() as trace_id:
        logger.info("Processing volume", volume_id=volume_id)
        # All logs here include trace_id
        await download_issues(volume_id)
```

### 13.5 Tracing Utilities

```python
from comicarr.core.tracing import get_trace_id, set_trace_id

# Get current trace ID
trace_id = get_trace_id()

# Set trace ID manually
set_trace_id("custom-trace-id")
```

---

## 14. Error Handling

### 14.1 Error Hierarchy

1. **Business Errors**: Return structured errors (dict with `success: false, message: str`)
2. **Validation Errors**: Pydantic validation, return 400 with details
3. **Authentication Errors**: Return 401 with clear message
4. **Not Found Errors**: Return 404
5. **Server Errors**: Log full traceback, return 500 with generic message

### 14.2 Logging Pattern

- Use `structlog` for structured logging
- Include context: `logger.error("Action failed", resource_id=id, error=str(e))`
- Log at appropriate levels:
  - `DEBUG`: Verbose information for debugging
  - `INFO`: Normal flow information
  - `WARNING`: Unusual situations that don't cause errors
  - `ERROR`: Exceptions and failures

### 14.3 Error Messages

- **User-facing**: Clear, actionable (e.g., "Connection timeout. Check host and port.")
- **Logs**: Detailed with context (e.g., "Connection timeout to indexer", url=..., timeout=30)

### 14.4 Exception Handling in Background Tasks

- Always wrap job processing in try/except
- Log exceptions with full traceback
- Update job status to "failed" with error message
- Don't let exceptions crash the background task

---

## 15. Testing

### 15.1 Testing Requirements

For every feature we enable, we MUST have tests covering all known cases. Before moving to the next feature, we make sure we didn't break any previous tests.

### 15.2 Test Organization

- **Unit Tests** (`tests/unit/`): Test functions/modules in isolation (mock dependencies). Fast, no I/O.
- **Integration Tests** (`tests/integration/`): Test external API clients (with test fixtures). May require network access.
- **E2E Tests** (`tests/e2e/`): End-to-end tests (future)

### 15.3 Test Patterns

- Use `pytest` for Python tests
- Use `pytest-asyncio` for async tests
- Use `@pytest.fixture` for test dependencies
- Mock external services/APIs
- Use factories for creating test data

### 15.4 Frontend Testing

- Use Vitest with React Testing Library
- Test user interactions, not implementation details
- Test error states and edge cases

---

## 16. Configuration

### 16.1 Configuration Sources

We use Pydantic Settings with environment variable support. Local config file (`settings.json`) has precedence over environment variables, so settings changed by the user within the UI will be reflected right away.

**Priority Order** (highest to lowest):
1. Local config file (`settings.json`)
2. Environment variables (`.env` file)
3. Default values in code

### 16.2 Environment Variables

Key variables:
- `COMICARR_HOST` / `COMICARR_PORT` – interface and port used by the backend
- `COMICARR_BASE_URL` – optional base path when running behind a reverse proxy
- `COMICARR_ENV` – environment (development/production)
- `COMICARR_SECRET_KEY` – session secret key
- `COMICARR_USERNAME` / `COMICARR_PASSWORD` – auto-create user on first run

### 16.3 Configuration Loading

- Load environment variables from `.env` file on startup
- Load local config from `settings.json` in config directory
- Merge with precedence: local config > env vars > defaults

---

## Change Log

- **2025-01-XX**: Initial design document created
  - Documented current implementation patterns and architecture
  - Project structure, routes, core layer, job processing (stateful model approach)
  - Settings management, frontend patterns, database patterns
  - Authentication, distributed tracing, error handling
  - Future improvements: Persisted async queues (WorkerManager pattern) as TODO
