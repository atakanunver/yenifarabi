# Repository Guidelines

## Project Structure & Module Organization

Dijital Okul is a FastAPI school portal with Jinja2 templates and SQLite storage. `app.py` creates the application and registers routers from `rotalar/`; root-level Python modules contain domain logic, authentication, and database migrations. `kaynaklar/` integrates external data sources. Put HTML in `templates/`, CSS and JavaScript in `static/`, tests in `tests/`, operational scripts in `scripts/`, and service definitions in `systemd/`. `config/` holds configuration; `veri/` contains local runtime data.

## Build, Test, and Development Commands

Run commands from `okul/`:

- `python3 -m venv venv` and `venv/bin/pip install -r requirements.txt` create the environment and install dependencies.
- `venv/bin/uvicorn app:app --host 127.0.0.1 --port 9090` runs the application locally. Check configuration and data paths first; startup can access local data.
- `venv/bin/python -m pytest -q` runs the test suite. Add a path or test selector to run a subset, for example `venv/bin/python -m pytest tests/test_odevler.py -q`.
- From the repository root, `.venv-tools/bin/ruff check okul/<file>` lints a changed Python file when the shared tools environment is available.

## Coding Style & Architecture

Use four-space Python indentation and follow existing `snake_case` names and Turkish domain terminology. Keep route handling in `rotalar/` and reusable business logic in the corresponding root module; register new routers in `app.py`. Use `zaman.simdi()` for current time. Add database migrations to `db.GOCLER` without changing existing migrations, and add a matching rollback to `scripts/geri_al.py`. For CSS or JavaScript changes, update the relevant template version query and `static/sw.js` cache version and asset list.

## Testing Guidelines

Use pytest with `tests/test_*.py` files and descriptive `test_*` functions. Cover behavior and authorization changes, using FastAPI's test client where appropriate. The shared `tests/conftest.py` fixture redirects runtime paths to temporary storage; extend it for new paths or settings, and mock external services. No coverage threshold is specified.

## Commits & Pull Requests

Recent commit subjects are short, descriptive, often Turkish, and sometimes use a component prefix such as `docs:` or `tahta:`. Follow that pattern and keep each change focused. Describe the problem, solution, and tests in pull requests; link relevant issues and include screenshots for visible interface changes.

## Security & Configuration

Never commit credentials, tokens, private invite links, or student data. Keep secrets in ignored `config/gizli.json`. Treat external sources as read-only, preserve existing role checks, and return 404 for unauthorized access. Consult `CLAUDE.md` for detailed operational and privacy rules.
