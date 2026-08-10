# FastAPI Telemetry

A small FastAPI service demonstrating a REST API with built-in observability via Prometheus metrics.

## Features

* CRUD API for managing `Campaign` records (create, read, update, delete)
* PostgreSQL database with [SQLModel](https://sqlmodel.tiangolo.com/) as the ORM
* Automatic Prometheus metrics exposed via [`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator)
* Seeded sample data on startup
* Health check endpoint
* Fully containerized — API, database, and DB admin UI all run via Docker Compose

## Requirements

* Docker and Docker Compose
* Python 3.10+ and dependencies in `requirements.txt` (only needed if running the API outside Docker)

## Running with Docker (recommended)

This starts the whole stack — the API, the database, and Adminer — together.

```bash
git clone https://github.com/Azayan03/fastapi-telemetry.git
cd fastapi-telemetry
docker compose up --build

```

First run takes longer while the `api` image builds and dependencies install. Subsequent runs reuse the cached layer and start much faster.

* **API (`api`)**: The FastAPI app, available at `http://localhost:8000/api/v1`.
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

## Running locally without Docker

Useful for fast iteration while developing. You'll still need Postgres running somewhere — easiest is to start just the `db` service from Compose.

```bash
git clone https://github.com/Azayan03/fastapi-telemetry.git
cd fastapi-telemetry
pip install -r requirements.txt
docker compose up db

```

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

## Metrics

Prometheus metrics are automatically exposed at `/metrics`, ready to be scraped by a Prometheus server.

## License

No license specified.
