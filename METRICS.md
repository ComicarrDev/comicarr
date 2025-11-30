# Comicarr Metrics Documentation

> **Purpose**: This document lists all Prometheus metrics exported by Comicarr. Metrics are exposed at `/metrics` endpoint. Update this document whenever metrics are created, updated, or deleted.

## Table of Contents

1. [Application Metrics](#1-application-metrics)
2. [Database Metrics](#2-database-metrics)
3. [Authentication Metrics](#3-authentication-metrics)
4. [HTTP Metrics](#4-http-metrics)
5. [TODO: Missing Metrics](#5-todo-missing-metrics)

---

## 1. Application Metrics

### `app_info`

**Type**: Gauge  
**Labels**: `version`  
**Description**: Application information metric. Always set to `1`, used to track application version in Prometheus.

**Labels**:
- `version`: Application version string (e.g., `"0.1.0"`)

**Example**:
```
app_info{version="0.1.0"} 1.0
```

---

## 2. Database Metrics

### Connection Pool Metrics

#### `db_connections_active`

**Type**: Gauge  
**Description**: Number of active database connections currently in use.

**Example**:
```
db_connections_active 3.0
```

#### `db_connections_idle`

**Type**: Gauge  
**Description**: Number of idle database connections available in the pool.

**Example**:
```
db_connections_idle 7.0
```

#### `db_connections_overflow`

**Type**: Gauge  
**Description**: Number of overflow database connections beyond the configured pool size.

**Example**:
```
db_connections_overflow 2.0
```

#### `db_pool_size`

**Type**: Gauge  
**Description**: Configured database connection pool size.

**Example**:
```
db_pool_size 10.0
```

#### `db_pool_max_overflow`

**Type**: Gauge  
**Description**: Configured maximum overflow connections for the database pool.

**Example**:
```
db_pool_max_overflow 20.0
```

### Retry Operation Metrics

#### `db_retry_attempts_total`

**Type**: Counter  
**Labels**: `operation_type`  
**Description**: Total number of database operation retry attempts. Incremented whenever a database operation is retried due to lock errors or other retriable errors.

**Labels**:
- `operation_type`: Type of operation being retried (e.g., `"commit"`, `"query"`, `"insert"`)

**Example**:
```
db_retry_attempts_total{operation_type="commit"} 15.0
db_retry_attempts_total{operation_type="query"} 3.0
```

#### `db_lock_errors_total`

**Type**: Counter  
**Description**: Total number of database lock errors encountered. This indicates SQLite database contention.

**Example**:
```
db_lock_errors_total 18.0
```

#### `db_retries_succeeded_total`

**Type**: Counter  
**Labels**: `operation_type`  
**Description**: Total number of database operations that succeeded after retry. Indicates successful recovery from transient errors.

**Labels**:
- `operation_type`: Type of operation that succeeded after retry

**Example**:
```
db_retries_succeeded_total{operation_type="commit"} 14.0
db_retries_succeeded_total{operation_type="query"} 3.0
```

#### `db_retries_failed_total`

**Type**: Counter  
**Labels**: `operation_type`  
**Description**: Total number of database operations that failed after all retries were exhausted.

**Labels**:
- `operation_type`: Type of operation that failed

**Example**:
```
db_retries_failed_total{operation_type="commit"} 1.0
```

#### `db_retry_duration_seconds`

**Type**: Histogram  
**Labels**: `operation_type`  
**Description**: Duration of database retry operations in seconds. Tracks how long retry operations take.

**Labels**:
- `operation_type`: Type of operation being retried

**Buckets**: `0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0`

**Example**:
```
db_retry_duration_seconds_bucket{operation_type="commit",le="0.01"} 10.0
db_retry_duration_seconds_bucket{operation_type="commit",le="0.1"} 12.0
db_retry_duration_seconds_sum{operation_type="commit"} 0.045
db_retry_duration_seconds_count{operation_type="commit"} 15.0
```

**Usage**: Monitor SQLite concurrency issues. High retry counts or durations indicate database contention.

---

## 3. Authentication Metrics

### `auth_login_failures_total`

**Type**: Counter  
**Labels**: `reason`  
**Description**: Total number of failed login attempts. This is a **security metric** to detect potential break-in attempts in a single-user application.

**Labels**:
- `reason`: Reason for login failure
  - `invalid_username`: Wrong username provided
  - `invalid_password`: Wrong password provided
  - `not_configured`: Authentication not configured yet (setup not completed)
  - `not_properly_configured`: Authentication configuration is incomplete (missing username or password hash)

**Example**:
```
auth_login_failures_total{reason="invalid_username"} 5.0
auth_login_failures_total{reason="invalid_password"} 12.0
auth_login_failures_total{reason="not_configured"} 0.0
auth_login_failures_total{reason="not_properly_configured"} 0.0
```

**Usage**: 
- Monitor for potential security threats (unusual number of failures).
- Alert on high failure rates to detect brute-force attempts.
- Track failure reasons to understand configuration issues.

**Note**: We only track failures, not successes, since it's a single-user application and success tracking is not necessary.

---

## 4. HTTP Metrics

These metrics are automatically generated by `prometheus-fastapi-instrumentator`.

### `http_requests_total`

**Type**: Counter  
**Labels**: `method`, `status_code`, `path`  
**Description**: Total number of HTTP requests received by the application.

### `http_requests_inprogress`

**Type**: Gauge  
**Description**: Number of HTTP requests currently being processed.

### `http_request_duration_seconds`

**Type**: Histogram  
**Labels**: `method`, `status_code`, `path`  
**Description**: Duration of HTTP requests in seconds.

**Note**: See `prometheus-fastapi-instrumentator` documentation for full details on HTTP metrics.

---

## 5. TODO: Missing Metrics

The following metrics should be implemented to provide better observability but are currently missing:

### 5.1 Rate Limiting Metrics

Rate limiting is implemented in external API clients (e.g., ComicVine client) but metrics are not tracked:

- `rate_limit_waits_total` - Total number of times rate limiting caused a wait
  - **Labels**: `service` (e.g., `"comicvine"`, `"newznab"`)
  - **Type**: Counter
  - **Description**: Tracks when rate limits are hit and requests are delayed

- `rate_limit_wait_duration_seconds` - Time spent waiting due to rate limits
  - **Labels**: `service`
  - **Type**: Histogram
  - **Description**: Duration of rate limit waits in seconds
  - **Buckets**: `0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0`

### 5.2 External API Metrics

External API calls (ComicVine, indexers) should be tracked:

- `external_api_requests_total` - Total external API requests
  - **Labels**: `service` (e.g., `"comicvine"`, `"newznab"`, `"getcomics"`), `endpoint`
  - **Type**: Counter
  - **Description**: Total number of external API requests made

- `external_api_errors_total` - External API errors
  - **Labels**: `service`, `endpoint`, `error_type` (e.g., `"timeout"`, `"http_error"`, `"connection_error"`)
  - **Type**: Counter
  - **Description**: Total number of failed external API requests

- `external_api_duration_seconds` - External API call duration
  - **Labels**: `service`, `endpoint`
  - **Type**: Histogram
  - **Description**: Duration of external API calls in seconds
  - **Buckets**: `0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0`

- `external_api_rate_limit_hits_total` - Rate limit hits from external APIs
  - **Labels**: `service`, `endpoint`
  - **Type**: Counter
  - **Description**: Number of times external APIs returned rate limit errors (429)

### 5.3 Cache Metrics

Cache operations should be tracked for performance monitoring:

- `cache_hits_total` - Cache hits
  - **Labels**: `cache_type` (e.g., `"indexer_results"`, `"comicvine"`, `"downloaded_files"`)
  - **Type**: Counter
  - **Description**: Total number of cache hits

- `cache_misses_total` - Cache misses
  - **Labels**: `cache_type`
  - **Type**: Counter
  - **Description**: Total number of cache misses

- `cache_size_bytes` - Current cache size
  - **Labels**: `cache_type`
  - **Type**: Gauge
  - **Description**: Current size of cache in bytes

### 5.4 Job Processing Metrics

Background job processing should be tracked:

- `jobs_created_total` - Jobs created
  - **Labels**: `job_type` (e.g., `"import_scanning"`, `"import_processing"`, `"weekly_release_processing"`, `"weekly_release_matching"`)
  - **Type**: Counter
  - **Description**: Total number of jobs created

- `jobs_completed_total` - Jobs completed successfully
  - **Labels**: `job_type`
  - **Type**: Counter
  - **Description**: Total number of jobs that completed successfully

- `jobs_failed_total` - Jobs failed
  - **Labels**: `job_type`, `error_type` (optional, for common error categories)
  - **Type**: Counter
  - **Description**: Total number of jobs that failed

- `jobs_duration_seconds` - Job processing duration
  - **Labels**: `job_type`
  - **Type**: Histogram
  - **Description**: Duration of job processing in seconds
  - **Buckets**: `1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0, 3600.0`

- `jobs_in_progress` - Jobs currently being processed
  - **Labels**: `job_type`
  - **Type**: Gauge
  - **Description**: Number of jobs currently in "processing" status

### 5.5 Search Operation Metrics

Search operations should be tracked:

- `search_requests_total` - Search operations
  - **Labels**: `search_type` (e.g., `"indexer"`, `"comicvine"`, `"volume"`)
  - **Type**: Counter
  - **Description**: Total number of search operations

- `search_duration_seconds` - Search operation duration
  - **Labels**: `search_type`
  - **Type**: Histogram
  - **Description**: Duration of search operations in seconds
  - **Buckets**: `0.1, 0.5, 1.0, 2.5, 5.0, 10.0`

- `search_results_count` - Number of results returned
  - **Labels**: `search_type`
  - **Type**: Histogram
  - **Description**: Number of results returned per search
  - **Buckets**: `0, 1, 5, 10, 25, 50, 100, 250, 500, 1000`

### 5.6 File Processing Metrics

File operations should be tracked (when file processing is implemented):

- `file_operations_total` - File operations
  - **Labels**: `operation_type` (e.g., `"rename"`, `"convert"`, `"download"`)
  - **Type**: Counter
  - **Description**: Total number of file operations

- `file_operation_duration_seconds` - File operation duration
  - **Labels**: `operation_type`
  - **Type**: Histogram
  - **Description**: Duration of file operations in seconds

- `file_operation_errors_total` - File operation errors
  - **Labels**: `operation_type`, `error_type`
  - **Type**: Counter
  - **Description**: Total number of failed file operations

---

## Metrics Export

All metrics are exposed at the `/metrics` endpoint in Prometheus format.

**Endpoint**: `GET /metrics`  
**Content-Type**: `text/plain; version=0.0.4; charset=utf-8`

**Example Usage**:
```bash
curl http://localhost:8000/metrics
```

---

## Change Log

- **2025-01-XX**: Initial metrics documentation created
  - Application metrics: `app_info` for version tracking
  - Database metrics: Connection pool metrics and retry operation metrics
  - Authentication metrics: `auth_login_failures_total` for security monitoring
  - HTTP metrics: Automatically provided by `prometheus-fastapi-instrumentator`

---

## Notes

- All metrics use snake_case naming convention.
- Counter metrics end with `_total` suffix (Prometheus convention).
- Histogram metrics end with `_seconds` suffix for duration metrics.
- Metric labels should be consistent across related metrics (e.g., `operation_type` for all database retry metrics).

