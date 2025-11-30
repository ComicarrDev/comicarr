# Test Organization

Tests are organized into three categories:

## Unit Tests (`tests/unit/`)

Unit tests focus on testing individual functions and classes in isolation, with mocked dependencies.

**Includes:**
- Core logic tests (matching, processing, scanning)
- Job processor tests
- Utility function tests
- Model tests
- Configuration and settings tests

**Characteristics:**
- Fast execution
- Isolated from external dependencies
- Use mocks for external APIs and services
- Test individual functions/classes

## Integration Tests (`tests/integration/`)

Integration tests verify that multiple components work together correctly, typically through API endpoints.

**Includes:**
- Route/API endpoint tests
- Database integration tests
- Authentication flow tests

**Characteristics:**
- Test component interactions
- May use real database (in-memory SQLite)
- Test API contracts
- May require proper app setup with dependency injection

## E2E Tests (`tests/e2e/`)

End-to-end tests verify complete workflows from user action to final result.

**Includes:**
- Full workflow tests (e.g., import a file from scan to library)
- User journey tests
- Cross-feature integration tests

**Characteristics:**
- Test complete user workflows
- Use real or near-real environments
- Slower execution
- Highest confidence in system behavior

## Running Tests

```bash
# Run all tests
make test-back

# Run only unit tests
uv run pytest backend/tests/unit

# Run only integration tests
uv run pytest backend/tests/integration

# Run only e2e tests
uv run pytest backend/tests/e2e

# Run with coverage
uv run pytest backend/tests/unit backend/tests/integration --cov=comicarr --cov-report=html
```

## Test Structure

- `conftest.py` - Shared fixtures (copied to each directory)
- `__init__.py` - Makes directories Python packages
- Test files follow `test_*.py` naming convention

