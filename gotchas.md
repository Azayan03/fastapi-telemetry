# Gotchas

Real issues hit while dockerizing this project, and what actually fixed them. Kept here instead of in my head.

## `db` vs `localhost` as a hostname

- From your **host machine** (running the app locally, not in a container): use `localhost` — the Postgres port is published to the host via `ports: ["5432:5432"]`.
- From **another container** on the same Compose network (e.g. `api`): use the **service name** (`db`) — Compose's internal DNS resolves it, `localhost` inside a container means "this container," not the host.

## `psycopg2-binary` fails to build on very new Python versions

Hit `pg_config executable not found` trying to install `psycopg2-binary` locally on Python 3.14 — no prebuilt wheel existed yet for that Python version, so pip tried to compile from source.

- Fix used: switched to `pg8000` — pure Python, no compiled extension, works regardless of Python version.
- Connection string changes accordingly: `postgresql+pg8000://...` instead of plain `postgresql://`.
- Note: inside the Docker container (pinned to `python:3.12-slim`), `psycopg2`/`psycopg` would likely have worked fine — the problem was really "local Python too new," not a fundamental issue with the driver.

## Compose file must be named `compose.yaml` or `docker-compose.yml`

Any other name (e.g. `postgres.yaml`) is not auto-detected — `docker compose up` silently does nothing relevant, and you have to pass `-f <filename>` every time. Cost real time before realizing the file just wasn't being picked up.

## `Dockerfile` must be named exactly `Dockerfile`, no extension

`build: .` in Compose looks for a file literally named `Dockerfile` in that directory. Also — more than once, edits made in an editor buffer or pasted into chat never actually got written to disk. Always verify after editing:
```bash
cat Dockerfile
```

## YAML indentation = ownership

A block indented at the same level as a service name (`db:`, `api:`) becomes a **sibling service**, not a property of that service. This caused `healthcheck:` to be parsed as its own broken service instead of living inside `db:`. Error messages here (`services.test must be a mapping`, `services.retries must be a mapping`) are misleading — they point at a nested key, not the actual indentation problem.

Fix: verify actual saved indentation with:
```bash
cat -A compose.yaml
```
(`^I` = a tab, which YAML doesn't accept for indentation — mixing tabs and spaces breaks parsing unpredictably.)

## Fish shell doesn't support `<<` heredoc syntax

Pasting a `cat > file << 'EOF' ... EOF` block into **fish** shell fails outright (`Expected a string, but found a redirection`) and everything after gets typed as literal commands. Bash/zsh support heredocs; fish doesn't. Use `nano <file>` instead when on fish, or switch to bash for heredoc-based file writes.

## `depends_on` alone doesn't wait for Postgres to be ready

`depends_on: db` only waits for the **container to start**, not for Postgres to finish initializing and accept connections. Needed a `healthcheck` on `db` (`pg_isready`) plus `depends_on: db: condition: service_healthy` on `api` to actually wait for readiness.

## Port conflicts from leftover containers

`adminer` failed to start with `address already in use` on port 8080 — caused by an old container from earlier testing still running and bound to that port. `docker ps` (not `-a`) shows what's actually running and holding ports; `docker container prune` clears out stopped containers cluttering things up.

## Stale `db` container silently holding port 5432 across sessions

Got `Bind for 0.0.0.0:5432 failed: port is already allocated` on a normal `docker compose up`, weeks after the container was first created. Cause: a `db` container from a previous session — with `restart: always` — was still running in the background (`docker ps` showed it "Up 13 minutes," restarted by a reboot, despite being 3 weeks old).

- Fix: `docker stop <name> && docker rm <name>`, then `docker compose up` again.
- Prevention: use `docker compose down` (not just closing the terminal) to actually stop *and remove* containers at the end of a session. Also swapped `restart: always` → `restart: unless-stopped` for local dev `db` service, so it doesn't silently survive a stop/reboot the way `always` does.

## `api` service port mapping pointed at the wrong container port

`compose.yaml` had `api: ports: ["5433:5432"]` — mapping host 5433 to container port **5432**, which is Postgres's port, not anything the FastAPI app listens on. The app actually listens on 8000 inside the container. Result: `docker compose ps` showed `8000/tcp` with **no host-side mapping at all** — Uvicorn logs looked completely healthy, but port 8000 was never published, so `localhost:8000` was unreachable.

- Fix: `api: ports: ["8000:8000"]`.
- Lesson: `docker compose logs` looking clean doesn't mean the port is reachable — always cross-check `docker compose ps`'s `PORTS` column for `host:container`, not just container-internal bindings.

## `pip install` fails with `externally-managed-environment` (PEP 668)

Hit this on Arch (also affects recent Debian/Ubuntu) any time `pip install` is run without an active venv — both installing `fastapi[standard]` and later `pytest`/`httpx`. Arch's system Python refuses global installs to protect pacman-managed packages.

- Fix: always create/activate a venv first — `python -m venv .venv` (once per project) then `source .venv/bin/activate.fish` (every new terminal session). Never use `--break-system-packages` for project dependencies; it risks the system Python install.
- `python -m venv .venv` = build the venv (one-time). `source .venv/bin/activate.fish` = step into it (per shell session, forgotten on close).

## `fastapi dev` / `fastapi: Unknown command` on host shell

Ran `fastapi dev` directly on the host (fish shell) while the actual app runs via Docker Compose. Since the project is Docker-only, there's no need for `fastapi-cli`/`uvicorn` on the host at all — the Dockerfile handles running the server inside the container. Confusing the two (host shell vs. container) was the root issue, not a missing package. To run something inside the container instead: `docker compose exec api bash`.

## Duplicate `app = FastAPI(...)` silently drops the first instance

`main.py` had `app = FastAPI(...)` defined twice — once early (with `Instrumentator().instrument(app).expose(app)` attached), and again later with `lifespan=lifespan`. The second assignment fully replaces the first in Python; the instrumented `app` object was discarded, so `/metrics` was likely attached to a dead reference. No error was raised — it failed silently.

- Fix: define `app = FastAPI(...)` exactly once, after `lifespan` is defined (Python reads top-to-bottom, so referencing `lifespan` before its `def` raises `NameError: name 'lifespan' is not defined`), then call `Instrumentator().instrument(app).expose(app)` immediately after that single definition.

## Wrong `HTTPException` imported — 404s silently became 500s

`from http.client import HTTPException` imports Python's **stdlib** exception class, not FastAPI's (`fastapi.HTTPException` / `starlette.exceptions.HTTPException`). FastAPI's error-handling middleware only recognizes its own exception type — raising the stdlib one meant every intended `404` (missing campaign on GET/PUT/DELETE) surfaced as an unhandled `500 Internal Server Error` instead. No warning at import time; only caught once tests exercised the not-found paths.

- Fix: `from fastapi import HTTPException` (can be combined into the existing `from fastapi import Depends, FastAPI` line).
- Lesson: two identically-named classes from different modules is an easy, silent trap — always double check *which* `HTTPException` an editor/autocomplete pulled in.

## pytest fails at collection: `create_engine(DATABASE_URL)` with `DATABASE_URL=None`

`conftest.py` imports `main`, which unconditionally runs `engine = create_engine(DATABASE_URL)` at module load. `DATABASE_URL` is only set inside the Docker Compose `environment:` block — running `pytest` on the bare host, the env var is unset, so `os.environ.get("DATABASE_URL")` returns `None` and `create_engine(None)` raises `ArgumentError: Expected string or URL object, got None` before any test even runs (the tests themselves never touch this `engine` — they use an in-memory SQLite session via `dependency_overrides` — but the import still fails first).

- Fix used: `export DATABASE_URL="postgresql+pg8000://appuser:apppass@localhost:5432/telemetry"` before running `pytest`, purely so `create_engine()` doesn't choke on `None` at import time.
- Better long-term fix (not yet applied): give `main.py` a safe default — `os.environ.get("DATABASE_URL", "postgresql+pg8000://appuser:apppass@localhost:5432/telemetry")` — so this doesn't need to be remembered/exported every session.

## `git push` fails: "No configured push destination"

Repo was created locally with `git init` (not `git clone`), so no remote was ever registered. `git remote add <url>` is a **one-time setup step per repo** (writes into `.git/config`), distinct from `git pull`/`git push`, which are everyday commands that rely on that setup already existing. Using `git pull <url> <branch>` once (with a raw URL, not the name `origin`) can fetch/merge successfully without ever registering a persistent `origin` remote — leaving `push` broken even though `pull` appeared to work.

- Fix: `git remote add origin <url>` once, then `git push -u origin <branch>` (the `-u` links local branch → remote branch so future bare `git push` works).
- `git clone` never hits this — it auto-configures `origin` from the URL you cloned.

## Local default branch `master` vs. GitHub default `main`

Local Git's `init.defaultBranch` was still `master` (pre-2020 default), while GitHub creates new repos with `main`. Pushing local `master` up created a **second, separate branch** on GitHub alongside the existing `main` — did not overwrite or merge anything automatically.

- Fix applied: `git checkout -b main origin/main` (create local `main`, tracking remote), `git merge master`, `git push origin main`, then delete the now-redundant branch both locally and remotely (`git branch -d master`, `git push origin --delete master`).
- Prevention: `git config --global init.defaultBranch main` — one-time global setting so every future `git init` starts on `main`, matching GitHub. Doesn't affect `git clone`, which always follows the remote's actual default branch regardless of this setting.
