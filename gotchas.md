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
- Better long-term fix (applied): `main.py` now uses `os.environ.get("DATABASE_URL", "postgresql+pg8000://appuser:apppass@localhost:5432/telemetry")`, so this doesn't need to be remembered/exported every session — the export above is only needed if you want to point pytest at a different DB than the default.

## `git push` fails: "No configured push destination"

Repo was created locally with `git init` (not `git clone`), so no remote was ever registered. `git remote add <url>` is a **one-time setup step per repo** (writes into `.git/config`), distinct from `git pull`/`git push`, which are everyday commands that rely on that setup already existing. Using `git pull <url> <branch>` once (with a raw URL, not the name `origin`) can fetch/merge successfully without ever registering a persistent `origin` remote — leaving `push` broken even though `pull` appeared to work.

- Fix: `git remote add origin <url>` once, then `git push -u origin <branch>` (the `-u` links local branch → remote branch so future bare `git push` works).
- `git clone` never hits this — it auto-configures `origin` from the URL you cloned.

## Local default branch `master` vs. GitHub default `main`

Local Git's `init.defaultBranch` was still `master` (pre-2020 default), while GitHub creates new repos with `main`. Pushing local `master` up created a **second, separate branch** on GitHub alongside the existing `main` — did not overwrite or merge anything automatically.

- Fix applied: `git checkout -b main origin/main` (create local `main`, tracking remote), `git merge master`, `git push origin main`, then delete the now-redundant branch both locally and remotely (`git branch -d master`, `git push origin --delete master`).
- Prevention: `git config --global init.defaultBranch main` — one-time global setting so every future `git init` starts on `main`, matching GitHub. Doesn't affect `git clone`, which always follows the remote's actual default branch regardless of this setting.

## GitHub Actions workflow file only exists on GitHub until you `git pull`

Created `.github/workflows/ci.yml` via GitHub's browser UI (not from the local machine). It committed fine on GitHub's remote, but the local clone had no idea it existed — `.github/workflow` looked completely absent locally. Any file created through the website is just a normal commit on the remote; it doesn't materialize locally until pulled.

- Fix: `git pull`, then confirm with `ls -la .github/workflows/`.

## Local tools installed in CI don't exist on your machine, and vice versa

Installed `ruff` inside the GitHub Actions runner (a temporary, disposable VM) as part of the `lint` job. Assumed it would then be available locally to run `ruff check . --fix` — it wasn't (`fish: Unknown command: ruff`). CI's environment and your local machine are two completely separate machines; nothing installed in one carries over to the other.

- Fix: `pip install ruff` locally as a separate step, inside the project's venv.

## `pip-audit` and Trivy are two different checks in one `scan` job — one failing stops the other from running

`scan` job ran `pip-audit` first, then Trivy's filesystem scan as a second step. `pip-audit` failed on a real CVE (`pg8000` outdated), which halted the job — Trivy's step never executed at all that run. A job showing green after a re-run doesn't confirm every step in it passed if you only skimmed the top-level status; check each individual step in the Actions log.

- Fix: `pip-audit` found `pg8000 1.31.1` had a known vulnerability (`PYSEC-2026-1766`), fixed in `1.31.5`. Bumped the pin in `requirements.txt`, reinstalled locally, confirmed the app still ran, then re-pushed.

## Docker Hub access token needs "Read & Write" scope, not "Read-only" or "Read, Write & Delete"

Read-only tokens can't `docker push` (build job would fail at the push step). Read/Write/Delete is more permission than a CI pipeline that only builds and pushes needs — no reason to give it delete access to the registry.

- Fix: generate the Docker Hub access token with **Read & Write** scope specifically, store as `DOCKERHUB_TOKEN` GitHub secret (paired with `DOCKERHUB_USERNAME`) — exact name match required, case-sensitive, between the secret name in GitHub Settings and the `secrets.X` reference in the YAML.

## Bind-mounting a file that doesn't exist yet creates a directory instead

Referenced `./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro` in a `volumes:` entry before the file actually existed on disk. Docker Compose auto-creates the mount source/target if missing — but since there was no file yet, it guessed wrong and created `default.conf` as a **directory**, owned by `root` (the Docker daemon), which then couldn't be deleted with a normal `rm`.

- Fix: `sudo rm -rf ./nginx/default.conf`, then actually create the file (`nano nginx/default.conf`) *before* running `docker compose up` again. Verify with `ls -la nginx/` — should show `-rw-...`, not `drwx...`.
- Lesson: always create bind-mounted config files (Nginx configs, `.env`, certs) before the first `docker compose up` that references them.

## `upstream` name and `proxy_pass` target must match exactly

Defined `upstream fastapi_backend { ... }` but wrote `proxy_pass http://fastapi_telemetry_backend;` (extra `telemetry_` from a copy-paste/autocomplete slip). Nginx failed to start with `host not found in upstream "fastapi_telemetry_backend"` — it's not resolving a real hostname there, it's looking for an `upstream` block by that literal label, and the label is arbitrary but must be identical in both places.

- Fix: match the name exactly in both the `upstream` declaration and every `proxy_pass` referencing it.

## `worker_processes` / `events {}` don't belong in a `conf.d/*.conf` file

Added `worker_processes auto;` and an `events {}` block to `nginx/default.conf`, which is mounted to `/etc/nginx/conf.d/default.conf` — a file that's `include`d *inside* the main `nginx.conf`'s `http {}` block. Those two directives are top-level/main-config-only and aren't allowed inside `http {}`, so Nginx failed with `"worker_processes" directive is not allowed here`.

- Fix: removed both — the base `nginx:latest` image's default `nginx.conf` already sets sane values. To actually override them, you'd need to mount a full custom `nginx.conf` to `/etc/nginx/nginx.conf` (a separate file/mount), not put them in `conf.d/`.

## SSL cert file path/name must exactly match the volume mount and `ssl_certificate*` lines

Cert/key files (`nginx-cert.crt`, `nginx-privatekey.key`) existed directly in `nginx/`, but the volume mount (`./nginx/certs:/etc/nginx/certs:ro`) and `default.conf`'s `ssl_certificate`/`ssl_certificate_key` both expected them under `nginx/certs/` with specific filenames. Nginx failed with `cannot load certificate ... No such file or directory` until all three (actual file location, volume mount source, and the filename referenced in `default.conf`) lined up exactly.

- Fix: moved files into `nginx/certs/`, updated `ssl_certificate`/`ssl_certificate_key` to the real filenames/extensions (`.crt` / `.key`, not `.pem` — don't copy a placeholder extension from an example without checking your actual files).

## HTTP→HTTPS redirect breaks when host ports are remapped (local dev only)

Added `return 301 https://$host$request_uri;` to redirect plain HTTP to HTTPS. Locally, Nginx's host ports were mapped to non-standard `8000` (HTTP) and `8443` (HTTPS) instead of `80`/`443` — but `$host` doesn't carry port info, so the redirect always points at the *default* HTTPS port 443, not 8443. Visiting `http://localhost:8000/docs` redirected to `https://localhost/docs` (implicit port 443), which nothing was listening on, making the whole app look broken even though every container was `Up`.

- Fix (local dev only): hardcode the actual host HTTPS port into the redirect — `return 301 https://localhost:8443$request_uri;` — with a comment noting it's a local-only workaround.
- This isn't needed in real deployments; see README's local-vs-production HTTPS section for why.

## Nginx round-robin state is per worker process, not global

Sent 10 sequential `curl` requests (one at a time) to a load-balanced endpoint and got the *same* backend instance ID every time, despite 3 upstream servers being configured correctly. Cause: Nginx spawns one worker process per CPU core (`worker_processes auto`), and each worker keeps its **own independent** round-robin counter. Slow, one-at-a-time requests tend to get picked up by whichever worker is idle, and each idle worker's counter is often still at position 0 — so it looks like load balancing isn't working when it actually is.

- Fix/verification: fire requests **concurrently** instead (fish: `for i in (seq 1 20); curl -s $URL &; end; wait`) so several land on the same worker in quick succession — this reliably showed all 3 backend IDs.
- Lesson: a single-threaded/sequential test loop is not a reliable way to verify Nginx load balancing; concurrency is required to see the rotation.

## Fish shell doesn't support bash's `{1..N}` range or `do...done` for loops

Bash's `for i in {1..10}; do ...; done` doesn't work in fish. Fish syntax is `for i in (seq 1 10) ... end` — no `do`, `end` instead of `done`, and `(seq 1 10)` instead of `{1..10}`. (Extends the earlier heredoc gotcha — fish diverges from bash/zsh in several common scripting idioms, not just heredocs.)

## `async def` routes calling synchronous DB code block the event loop

Every route in `main.py` was declared `async def`, but the bodies called synchronous SQLModel/pg8000 operations (`session.exec()`, `session.commit()`). FastAPI only runs plain `def` routes in a thread pool automatically — an `async def` route is expected to `await` real async I/O, so a blocking synchronous call inside one blocks the single-threaded event loop directly, stalling every other concurrent request while it runs.

- Fix: changed every route from `async def` to plain `def` — FastAPI then dispatches them to its worker thread pool automatically, without needing an async DB driver.
- Note: this only matters under real concurrent load; a solo dev hitting the API one request at a time would never notice.

## Docker image ran as root; no `.dockerignore`

Two related hardening gaps caught in review: the `Dockerfile` never created/switched to a non-root user (containers ran as `root` by default), and there was no `.dockerignore`, so `COPY . .` would pull in `.venv/`, `__pycache__/`, `.pytest_cache/`, and any local `database.db`/`nginx/certs` into the image.

- Fix: added `addgroup`/`adduser` + `USER appuser` to the Dockerfile (after `chown -R appuser:appgroup /app`, before `CMD`), and added a `.dockerignore` excluding those paths.

## `requirements.txt` was an uncurated `pip freeze`, not a direct-dependency list

Root `requirements.txt` had 41 entries — including packages `main.py` never imports (`fastapi-cli`, `fastapi-cloud-cli`, `python-dotenv`, `sentry-sdk`, `watchfiles`, and a few completely unrelated ones like `asarPy`/`fastar`/`detect-installer`/`rignore` that look like leftovers from an unrelated tool's environment). A production requirements file should list direct dependencies only — pip resolves the rest.

- Fix: trimmed to the 6 packages `main.py`/`Dockerfile` actually need: `fastapi`, `uvicorn`, `sqlmodel`, `pydantic`, `prometheus-fastapi-instrumentator`, `pg8000`.
- Verify after trimming: rebuild and run the full test suite — a trim based on reading imports, not a full dependency-tree trace, so it's worth confirming nothing broke.
