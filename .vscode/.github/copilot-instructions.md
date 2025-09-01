**Daily Development Workflow:**

1. **Check out tasks** in `TODO.md`
2. **Pull** main branch and ensure your branch is up to date.
3. **Write/Refactor/Implement** code in `src/` or `app/`
4. **Write/Update tests** in `tests/`
5. **Automate pre-commit** (format, lint, type-check) before every push:
   - `uv run ruff format .`
   - `uv run ruff check . --fix`
   - `uv run ty check .`
6. **Run all tests**: `uv run pytest`
   - **Test coverage**: `uv run pytest --cov=yourproject`
7. **Update** `TODO.md`, `CHANGELOG.md`, and documentation as needed.
8. **Push** changes to your branch/repository.
9. **Commit message**: Should reflect the main change/task (see Conventional Commits if using them).
10. **CI/CD will verify** using GitHub Actions on push/PR.
11. **Keep update files** `README.md`, `TODO.md`, `CHANGELOG.md`, `INSTRUCTIONS.md` and `/docs` current.

more in (instructions)[AGENT.md]
