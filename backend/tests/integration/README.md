# Integration Tests

Integration tests verify that multiple components work together correctly, typically through API endpoints.

## Test Files

### Weekly Releases
- `test_weekly_releases_routes.py` - Weekly releases API endpoints
  - Currently most tests are skipped due to dependency injection setup complexity
  - Tests require proper route setup with database session dependency injection

### Import
- `test_import_routes.py` - Import API endpoints
  - Some tests are skipped due to dependency injection setup complexity
  - `test_list_import_jobs` and job status endpoints are working

### Authentication
- `test_auth_routes.py` - Authentication API endpoints

## Characteristics

- Test component interactions
- Use real database (in-memory SQLite)
- Test API contracts
- May require proper app setup with dependency injection
- Slower than unit tests but faster than e2e tests

## Current Status

Many integration tests are currently skipped because they require proper FastAPI dependency injection setup. The test client needs to properly override the `get_db_session` dependency that's passed to routers during app creation.

To enable these tests, we would need to:
1. Create a test app factory that accepts a session factory
2. Properly override dependencies at the router level
3. Or use a different testing approach (e.g., httpx.AsyncClient with proper dependency overrides)

