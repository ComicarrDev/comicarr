# Unit Tests

Unit tests focus on testing individual functions and classes in isolation, with mocked dependencies.

## Test Files

### Weekly Releases
- `test_weekly_releases_matching.py` - Library and ComicVine matching logic
- `test_weekly_releases_processing.py` - Volume creation from ComicVine
- `test_weekly_releases_job_processor.py` - Processing job execution
- `test_weekly_releases_matching_job_processor.py` - Matching job execution

### Import
- `test_import_scan.py` - File scanning and matching logic
- `test_import_process.py` - File processing and import logic
- `test_import_job_processors.py` - Scanning and processing job execution

### Core Functionality
- `test_auth.py` - Authentication utilities
- `test_auth_metrics.py` - Authentication metrics
- `test_bootstrap.py` - Bootstrap functionality
- `test_config.py` - Configuration management
- `test_database_metrics.py` - Database metrics
- `test_general.py` - General routes
- `test_indexers_routes.py` - Indexer routes (unit-level)
- `test_logging.py` - Logging configuration
- `test_metrics.py` - Metrics setup
- `test_middleware.py` - Middleware functionality
- `test_security.py` - Security configuration
- `test_settings_routes.py` - Settings routes (unit-level)
- `test_tracing.py` - Tracing functionality
- `test_utils_normalization.py` - String normalization utilities

## Characteristics

- Fast execution
- Isolated from external dependencies
- Use mocks for external APIs and services
- Test individual functions/classes
- Use in-memory SQLite for database tests

