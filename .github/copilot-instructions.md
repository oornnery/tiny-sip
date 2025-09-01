# AGENTS.md

**Universal AI Agent Configuration for Python Projects with Modern Toolchain**

This file provides context, instructions, and best practices for AI coding agents working with Python projects using **UV**, **Ruff**, **Ty**, **Pytest**, and modern development workflows.

---

## 🎯 Project Overview

**Goal**: Automate development workflows, maintain code quality, and ensure robust CI/CD for Python applications using the Astral-sh ecosystem.

**Tech Stack**: Python 3.11+, UV (package management), Ruff (linting/formatting), Ty (type checking), Pytest (testing), MkDocs (documentation), Docker, GitHub Actions.

**Allowed Operations**: Modify `src/`, `app/`, `tests/`, `docs/`, configuration files, and workflows.
**Restricted Operations**: System-wide changes, package metadata outside scope, database migrations (unless explicitly instructed).

---

## 🚀 Quick Start Commands

### Environment Setup

```bash
# Pin and install Python version
uv python pin 3.11.9
uv python install

# Sync dependencies (frozen for CI)
uv sync                    # Development
uv sync --frozen           # Production/CI
```

### Daily Development Workflow

```bash
# 1. Format and lint code
uv run ruff format .
uv run ruff check . --fix

# 2. Type checking
uv run ty check .

# 3. Run tests with coverage
uv run pytest
uv run pytest --cov=app --cov-report=html

# 4. Documentation
uv run mkdocs serve -a 0.0.0.0:8001
```

### Package Management

```bash
# Add dependencies (NEVER edit pyproject.toml manually)
uv add fastapi              # Runtime dependency
uv add --dev pytest-cov    # Development dependency

# Remove packages
uv remove package-name

# Show dependency tree
uv tree

# Clean cache
uv cache clean
```

---

## 📁 Project Structure

```
.
├── .env.example           # Environment template
├── .gitignore            # Git ignore rules
├── .python-version       # Python version lock
├── .vscode/              # VS Code configuration
├── AGENTS.md            # This file (agent instructions)
├── CHANGELOG.md         # Version history
├── INSTRUCTIONS.md      # Architecture notes
├── README.md            # Human-readable documentation
├── TODO.md              # Task tracking
├── app/                 # Source code
│   ├── __init__.py
│   └── main.py
├── docs/                # MkDocs documentation
├── tests/               # Test files
├── pyproject.toml       # Project metadata (PEP 621)
└── uv.lock             # Dependency lock file
```

---

## 🧪 Testing Strategy

### Test Execution

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_module.py

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run tests matching pattern
uv run pytest -k "test_authentication"

# Fail fast on first error
uv run pytest --maxfail=1 --tb=short
```

### Test Guidelines

- **Coverage**: Aim for >90% code coverage on critical paths
- **Structure**: Mirror source structure in `tests/` directory
- **Naming**: Use `test_` prefix for test functions and files
- **Fixtures**: Leverage pytest fixtures for setup/teardown
- **Mocking**: Use `unittest.mock` or `pytest-mock` judiciously

---

## 🎨 Code Quality Standards

### Python Best Practices

- **Type Hints**: Use comprehensive type annotations
- **Docstrings**: Google-style docstrings for all public functions
- **Error Handling**: Explicit exception handling with custom exceptions
- **Logging**: Use structured logging with appropriate levels
- **Security**: Input validation, no hardcoded secrets

### Code Style (Ruff Configuration)

```toml
[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "UP", "S", "B", "A", "C4", "T20"]
ignore = ["E203", "E501"]
exclude = [".venv", "build", "dist"]

[tool.ruff.isort]
known-first-party = ["app"]
```

### Type Checking (Ty Configuration)

```toml
[tool.ty]
strict = true
warn_unused_ignores = true
disallow_untyped_defs = true
```

---

## 🔄 Development Workflow

### Daily Routine

1. **Planning**: Check `TODO.md` for current tasks
2. **Branch**: Create feature branch from main
3. **Develop**: Implement changes in `app/` or `src/`
4. **Test**: Write/update tests in `tests/`
5. **Quality**: Run format → lint → type-check → test
6. **Document**: Update relevant documentation
7. **Commit**: Use conventional commits format
8. **Push**: GitHub Actions will validate changes

### Pre-commit Checklist

```bash
# Must pass before committing
uv run ruff format .       # ✅ Code formatted
uv run ruff check .        # ✅ Linting passed
uv run ty check .          # ✅ Type checking passed
uv run pytest             # ✅ All tests passed
```

### Commit Message Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**: feat, fix, docs, style, refactor, test, chore
**Example**: `feat(auth): add JWT token validation`

---

## 📋 PR Instructions

### Title Format

`[<module>] <brief description>`
**Example**: `[auth] Add OAuth2 authentication flow`

### Pre-PR Checklist

- [ ] All quality checks pass locally
- [ ] Tests added/updated for changes
- [ ] Documentation updated if needed
- [ ] `CHANGELOG.md` updated for user-facing changes
- [ ] No merge conflicts with main branch

### PR Description Template

```markdown
## Changes

Brief description of what changed

## Motivation

Why this change was needed

## Testing

How the changes were tested

## Breaking Changes

Any breaking changes (if applicable)

## Checklist

- [ ] Tests pass
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
```

---

## 🐳 Docker & Containerization

### Production Dockerfile

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY .python-version ./.python-version

RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install && \
    uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "python", "-m", "app.main"]
```

### Development Commands

```bash
# Development environment
docker compose -f docker-compose-dev.yml up --build

# Production environment
docker compose up --build
```

---

## 📚 Documentation

### MkDocs Setup

```bash
# Install documentation dependencies
uv add --dev mkdocs mkdocs-material mkdocstrings[python]

# Serve documentation locally
uv run mkdocs serve -a 0.0.0.0:8001

# Build static documentation
uv run mkdocs build --clean --site-dir site

# Deploy to GitHub Pages
uv run mkdocs gh-deploy --force
```

### Documentation Structure

```
docs/
├── index.md              # Project overview
├── getting-started.md    # Quick start guide
├── api/                  # API documentation
├── tutorials/            # Step-by-step guides
└── contributing.md       # Contribution guidelines
```

---

## 🔒 Security Considerations

### Environment Variables

- Use `.env.example` as template (committed)
- Keep actual `.env` files local (never commit)
- Use strong validation for environment variables

### Dependency Security

```bash
# Audit dependencies for vulnerabilities
uv audit

# Update dependencies
uv sync --upgrade
```

### Code Security

- Input validation on all external data
- Sanitize outputs to prevent injection
- Use secrets management for sensitive data
- Regular dependency updates

---

## 🚨 Troubleshooting

### Common Issues

**UV sync fails**:

```bash
# Clear cache and retry
uv cache clean
uv sync
```

**Import errors**:

```bash
# Verify Python path and virtual environment
uv run python -c "import sys; print(sys.path)"
```

**Type check failures**:

```bash
# Run specific file type checking
uv run ty check app/specific_module.py
```

**Test failures**:

```bash
# Run with verbose output
uv run pytest -v --tb=long
```

---

## 🛠️ Extensions & Customization

### Adding New Tools

```bash
# Add development tools
uv add --dev tool-name

# Add runtime dependencies
uv add package-name

# Update lock file
uv sync
```

### IDE Configuration

**VS Code Settings** (`.vscode/settings.json`):

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.ruffEnabled": true,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true,
    "source.fixAll.ruff": true
  }
}
```

---

## 📖 Code Examples

### Project Structure Example

```python
# app/__init__.py
"""Main application package."""
__version__ = "0.1.0"

# app/main.py
"""Application entry point."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

def main() -> int:
    """Main application function.

    Returns:
        Exit code (0 for success)
    """
    try:
        logger.info("Starting application")
        # Application logic here
        return 0
    except Exception as e:
        logger.error(f"Application failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
```

### Test Example

```python
# tests/test_main.py
"""Tests for main application module."""
import pytest
from unittest.mock import patch
from app.main import main

def test_main_success():
    """Test successful application execution."""
    result = main()
    assert result == 0

@patch("app.main.logger")
def test_main_with_exception(mock_logger):
    """Test application handles exceptions properly."""
    with patch("app.main.some_function", side_effect=Exception("Test error")):
        result = main()
        assert result == 1
        mock_logger.error.assert_called_once()
```

### Configuration Example

```python
# app/config.py
"""Application configuration management."""
import os
from typing import Optional
from pydantic import BaseSettings

class Settings(BaseSettings):
    """Application settings with validation."""

    app_name: str = "My App"
    debug: bool = False
    database_url: Optional[str] = None
    secret_key: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

## 🔗 References & Resources

### Official Documentation

- [UV Documentation](https://docs.astral.sh/uv/)
- [Ruff Linter](https://docs.astral.sh/ruff/)
- [Ty Type Checker](https://docs.astral.sh/ty/)
- [Pytest Documentation](https://docs.pytest.org/)
- [MkDocs](https://www.mkdocs.org/)

### Python Best Practices

- [PEP 8 Style Guide](https://pep8.org/)
- [PEP 621 Project Metadata](https://peps.python.org/pep-0621/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)

### Development Tools

- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Actions](https://docs.github.com/en/actions)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

---

## 🎯 Automation Rules

**Critical**:

- Never edit `pyproject.toml` dependencies manually - always use `uv add/remove`
- Always run quality checks before committing
- Keep documentation synchronized with code changes
- Use `--dry-run` flags when available for destructive operations

**Logging**: All automation steps should be logged with structured format:

```json
{
  "timestamp": "2025-08-30T22:21:00Z",
  "action": "format_code",
  "result": "success",
  "files_affected": ["app/main.py", "app/config.py"]
}
```

**File Maintenance**: Keep `README.md`, `TODO.md`, `CHANGELOG.md`, `INSTRUCTIONS.md`, and `/docs` current with any workflow or architectural changes.

---

_This AGENTS.md file is designed to work with any AI coding agent. Update sections as your project evolves and new tools are adopted._
