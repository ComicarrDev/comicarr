# End-to-End Tests

End-to-end tests verify complete workflows from user action to final result.

## Test Files

Currently empty - e2e tests can be added here as needed.

## Potential E2E Tests

- Complete import workflow: scan folder → match files → process files → verify in library
- Complete weekly release workflow: fetch releases → match to library → process → verify in library
- User authentication flow: login → access protected routes → logout
- Multi-step operations: create library → add volumes → import files → verify organization

## Characteristics

- Test complete user workflows
- Use real or near-real environments
- Slower execution
- Highest confidence in system behavior
- May require test fixtures for file system operations

