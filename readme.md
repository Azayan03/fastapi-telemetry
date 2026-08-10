# FastAPI Telemetry

A small FastAPI service demonstrating a REST API with built-in observability via Prometheus metrics.

## Features

* CRUD API for managing `Campaign` records (create, read, update, delete)
* PostgreSQL database with [SQLModel](https://sqlmodel.tiangolo.com/) as the ORM
* Automatic Prometheus metrics exposed via [`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator)
* Seeded sample data on startup
* Health check endpoint

## Requirements

* Python 3.10+
* Docker and Docker Compose (for infrastructure)
* Dependencies listed in `requirements.txt`

## Infrastructure

This project uses Docker Compose to run the required database and management tools.

To start the services in the background, run:

```bash
docker compose up -d

```

* **Database (`db`)**: A PostgreSQL 16 instance accessible on port `5432`. It automatically provisions a database named `telemetry` (User: `appuser`, Password: `apppass`) and persists data via a local Docker volume.
* **Adminer (`adminer`)**: A web-based database management interface available at `http://localhost:8080`.

## Installation

```bash
git clone https://github.com/Azayan03/fastapi-telemetry.git
cd fastapi-telemetry
pip install -r requirements.txt

```

## Running the app

```bash
uvicorn main:app --reload

```

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