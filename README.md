# FastAPI Telemetry

A small FastAPI service demonstrating a REST API with built-in observability via Prometheus metrics.

## Features

* CRUD API for managing `Campaign` records (create, read, update, delete)
* PostgreSQL database with [SQLModel](https://sqlmodel.tiangolo.com/) as the ORM
* Automatic Prometheus metrics exposed via [`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator)
* Seeded sample data on startup
* Health check endpoint
* Fully containerized — API, database, and DB admin UI all run via Docker Compose
* Docker image runs as a dedicated non-root user, not `root`

## Requirements

* Docker and Docker Compose
* Python 3.10+ and dependencies in `requirements.txt` (only needed if running the API outside Docker)

## Running with Docker (recommended)

This starts the whole stack — three load-balanced API instances, the database, Adminer, and Nginx (reverse proxy, load balancing, HTTPS) — together.

```bash
git clone https://github.com/Azayan03/fastapi-telemetry.git
cd fastapi-telemetry
docker compose up --build
```

First run takes a bit longer while the `api1`/`api2`/`api3` images build and dependencies install. Subsequent runs reuse the cached layer and start much faster.

* **API (`api1`, `api2`, `api3`)**: Three identical FastAPI instances, load-balanced by Nginx. They don't publish a host port individually by design — all traffic goes through Nginx (see below).
* **Nginx (`nginx`)**: Reverse proxy, load balancer, and TLS termination in front of the three API instances. This is the actual entry point — see [Reverse proxy, load balancing, and HTTPS](#reverse-proxy-load-balancing-and-https-nginx) below for details and access URLs.
* **Database (`db`)**: A PostgreSQL 16 instance accessible on port `5432`. It automatically provisions a database named `telemetry` (User: `appuser`, Password: `apppass`) and persists data via a local Docker volume.
* **Adminer (`adminer`)**: A web-based database management interface available at `http://localhost:8080`. Log in with System `PostgreSQL`, Server `db`, and the credentials above.

To run in the background, add `-d`:

```bash
docker compose up -d --build
```

To stop everything:

```bash
docker compose down
```

Add `-v` to also wipe the database volume (`docker compose down -v`).

### Verifying it's up

```bash
docker compose ps
```

`api1`, `api2`, `api3` are expected to show only `8000/tcp` with **no host-side mapping** — that's correct, not a bug; they're only reachable internally, through Nginx. The `nginx` service is the one that should show published ports (`0.0.0.0:8000->80/tcp` and `0.0.0.0:8443->443/tcp`); if those are missing, check the `ports:` entries for `nginx` in `compose.yaml`.

Once it's up:

* `https://localhost:8443/docs` — interactive API docs (Swagger UI), served through Nginx
* `https://localhost:8443/health` — health check (includes the responding container's instance ID)
* `http://localhost:8000/docs` — redirects to the HTTPS URL above

## Running locally without Docker

Useful for fast iteration while developing. You'll still need Postgres running somewhere — easiest is to start just the `db` service from Docker Compose.

```bash
git clone https://github.com/Azayan03/fastapi-telemetry.git
cd fastapi-telemetry
python -m venv .venv
source .venv/bin/activate   # fish shell: source .venv/bin/activate.fish
pip install -r requirements.txt
docker compose up db
```

> On distros with [PEP 668](https://peps.python.org/pep-0668/) "externally managed" Python (e.g. Arch, recent Debian/Ubuntu), a plain `pip install` outside a venv will fail with `externally-managed-environment`. Always install into a virtual environment as shown above rather than passing `--break-system-packages`.

Then point the app at it and run it:

```bash
export DATABASE_URL="postgresql+pg8000://appuser:apppass@localhost:5432/telemetry"
uvicorn main:app --reload
```

Note the hostname here is `localhost`, not `db` — `db` only resolves as a hostname from inside another container on the same Docker network. When the API itself runs via Compose, it connects to Postgres using `db` as the host instead.

The API will be available at `http://localhost:8000/api/v1`.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Health check |
| GET | `/campaigns` | List all campaigns |
| GET | `/campaigns/{id}` | Get a single campaign |
| POST | `/campaigns` | Create a new campaign |
| PUT | `/campaigns/{id}` | Update an existing campaign |
| DELETE | `/campaigns/{id}` | Delete a campaign |

## Reverse proxy, load balancing, and HTTPS (Nginx)

The stack can run three load-balanced instances of the API (`api1`, `api2`, `api3`) behind an Nginx reverse proxy, which also terminates TLS:

```
Browser --[HTTPS]--> Nginx --[HTTP, internal Docker network]--> api1 / api2 / api3
```

* Nginx's `upstream` block pools the three instances and round-robins requests across them.
* Nginx handles TLS termination — it accepts encrypted HTTPS, decrypts it, and forwards plain HTTP internally to whichever `apiN` instance is next in rotation. The backend instances never see encrypted traffic directly.
* Plain HTTP requests are redirected (`302`) to HTTPS. A temporary (`302`) rather than permanent (`301`) redirect is used deliberately during local development — browsers cache `301`s aggressively, which can hide the effect of later config changes behind a stale cached redirect. Worth switching to `301` once this config is stable and no longer actively changing.

Bring it up the same way as the base stack:

```bash
docker compose up -d --build
```

Access points:

* `http://localhost:8000/docs` — redirects to HTTPS
* `https://localhost:8443/docs` — interactive docs, served through Nginx and load-balanced across all three instances
* `https://localhost:8443/health` — includes the responding container's instance ID, useful for confirming load balancing is actually distributing requests

### Verifying load balancing

Sequential single requests can misleadingly appear to always hit the same instance — Nginx tracks round-robin state per worker process, and slow one-at-a-time requests tend to land on whichever worker is idle. Send concurrent requests instead:

```fish
for i in (seq 1 20)
    curl -sk https://localhost:8443/health &
end
wait
```

You should see multiple distinct `instance` IDs across the responses.

### Local dev HTTPS vs. real deployment

This project currently uses a **self-signed certificate** for local HTTPS — sufficient to develop and test TLS termination, but not something a browser will trust by default (expect a certificate warning; that's expected and safe to bypass locally with `curl -k` or a manual browser exception).

| | Local dev (current) | Real deployment (e.g. AWS) |
| --- | --- | --- |
| Certificate | Self-signed, generated once via `openssl` | Issued by a trusted CA (e.g. Let's Encrypt via Certbot), or managed by a cloud load balancer (e.g. AWS ACM behind an ALB) |
| Domain | `localhost` — can't be verified by a real CA | A real, DNS-resolvable domain the CA can confirm you own |
| Trust | Browsers show a warning; you accept it manually | Trusted automatically, no warning |
| Ports | Nonstandard host ports (`8000`/`8443`) to avoid needing elevated privileges locally | Standard ports (`80`/`443`), since the server owns the whole host/instance |
| HTTP→HTTPS redirect | Must hardcode the nonstandard HTTPS port (`https://localhost:8443$request_uri`) since `$host` carries no port info | Works with the default `https://$host$request_uri`, no hardcoding needed, since 443 is implicit |
| Renewal | N/A — cert is just regenerated manually if needed | Must be automated (Let's Encrypt certs expire every 90 days; Certbot or the cloud provider typically handles renewal) |

Generating the local self-signed cert (already done for this repo, kept here for reference/regeneration):

```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/nginx-privatekey.key \
  -out nginx/certs/nginx-cert.crt \
  -subj "/CN=localhost"
```

`nginx/certs/` is gitignored — regenerate locally rather than relying on a committed cert/key.

## Metrics

Prometheus metrics are automatically exposed at `/metrics`, ready to be scraped by a Prometheus server.

## Running tests

Tests use an in-memory SQLite database (via `StaticPool`) with FastAPI's `get_session` dependency overridden — no real Postgres connection needed to run the suite.

Test/lint/scan tooling (`pytest`, `ruff`, `pip-audit`) lives in `requirements-dev.txt`, separate from the runtime dependencies in `requirements.txt`, so the production Docker image doesn't carry tooling it never uses.

```bash
pip install -r requirements-dev.txt
pytest
```

> `main.py` creates its database engine at import time from `DATABASE_URL`. If that variable isn't set, `pytest` will fail during test collection rather than during a test itself. Export a placeholder before running if needed:
> ```bash
> export DATABASE_URL="postgresql+pg8000://appuser:apppass@localhost:5432/telemetry"
> ```

## CI/CD

Every push and pull request against `main` runs through a GitHub Actions pipeline (`.github/workflows/ci.yml`) with four sequential stages:

1. **Lint** — [`ruff`](https://docs.astral.sh/ruff/) checks code style and correctness.
2. **Test** — the `pytest` suite described above.
3. **Scan** — [`pip-audit`](https://pypi.org/project/pip-audit/) checks dependencies in `requirements.txt` for known CVEs; [Trivy](https://aquasecurity.github.io/trivy/) scans the filesystem for vulnerabilities and accidental secrets.
4. **Build** — builds the Docker image and pushes it to Docker Hub.

Each stage only runs if the previous one passes, so a broken lint or failing test stops the pipeline before an image is ever built or pushed. The lint, test, and scan stages install `requirements-dev.txt` (which pulls in `requirements.txt` plus `ruff`/`pytest`/`pip-audit`); the build stage's Docker image only ever installs `requirements.txt`.

## Contributing

`main` is protected: direct pushes are rejected, including for repo admins. All changes go through a pull request, and the four CI stages (lint, test, scan, build) must pass before the merge button is enabled.

```bash
git checkout -b my-change
# make edits
git add .
git commit -m "Describe the change"
git push -u origin my-change
```

Then open a pull request on GitHub targeting `main`. Once CI passes, merge and delete the branch (GitHub offers a one-click "Delete branch" button post-merge). Locally:

```bash
git checkout main
git pull origin main
git branch -d my-change
```

## License

No license specified.
