# Contributing to Comicarr

Thank you for your interest in contributing to Comicarr! This document provides guidelines and instructions for contributing.

## Getting Started

1. **Fork the repository** and clone your fork locally
2. **Set up your development environment:**
   ```bash
   make sync
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

## Development Workflow

### Code Quality

Before submitting a pull request, ensure your code:

- **Passes all tests:** Run `make test` or `make test-back` for backend tests
- **Passes type checking:** Run `make type-check` to verify type safety
- **Follows code style:** The project uses:
  - `black` for code formatting
  - `isort` for import sorting
  - `ruff` for linting
  - `pyrefly` for type checking

All of these are enforced via pre-commit hooks. You can run them manually:
```bash
make format  # Runs black and isort
make lint    # Runs ruff
make type-check  # Runs pyrefly
```

Or install pre-commit hooks:
```bash
pre-commit install
```

### Testing

- Write tests for new features and bug fixes
- Ensure existing tests continue to pass
- Aim for good test coverage, especially for critical paths

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/) format:

- **Format:** `<type>: <description>`
- **Types:** `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `style`
- Keep the first line under 72 characters
- Add more details in the body if needed

**Commit types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `chore`: Maintenance tasks, dependency updates
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `perf`: Performance improvements
- `style`: Code style changes (formatting, etc.)

Examples:
```
feat: add support for new indexer type

Implements the Newznab indexer protocol to enable
compatibility with additional indexer services.
```

```
fix: handle volume matching when year is missing

Handles cases where publication year is not available
in ComicVine data.
```

```
docs: update API documentation for search endpoints
```

## Pull Request Process

1. **Update documentation** if you're adding features or changing behavior
2. **Add tests** for your changes
3. **Ensure all checks pass** (tests, linting, type checking)
4. **Update CHANGELOG.md** with a brief description of your changes
5. **Create a pull request** with a clear description of:
   - What changes you made
   - Why you made them
   - How to test the changes

### PR Checklist

- [ ] Code follows the project's style guidelines
- [ ] Tests pass locally
- [ ] Type checking passes
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] No breaking changes (or breaking changes are documented)

## Code Style Guidelines

### Python

- Follow PEP 8 style guide
- Use type hints for function parameters and return values
- Prefer async/await for I/O operations
- Keep functions focused and single-purpose
- Add docstrings for public functions and classes

### Frontend

- Follow React best practices
- Use functional components with hooks
- Keep components small and focused
- Use TypeScript for type safety

## Reporting Issues

When reporting bugs or requesting features:

- **Use the issue templates** provided in the repository
- **Provide clear descriptions** of the problem or feature request
- **Include steps to reproduce** for bugs
- **Add relevant logs** or error messages (sanitize any sensitive information)

## Questions?

If you have questions about contributing, feel free to:
- Open a discussion in the repository
- Check existing issues and pull requests for similar questions

Thank you for contributing to Comicarr!

