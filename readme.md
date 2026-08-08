# FastAPI Telemetry

A small FastAPI service demonstrating a REST API with built-in observability via Prometheus metrics.

## Features

- CRUD API for managing `Campaign` records (create, read, update, delete)
- SQLite database with [SQLModel](https://sqlmodel.tiangolo.com/) as the ORM
- Automatic Prometheus metrics exposed via [`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator)
- Seeded sample data on startup
- Health check endpoint

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

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

| Method | Path                 | Description              |
|--------|----------------------|---------------------------|
| GET    | `/health`             | Health check              |
| GET    | `/campaigns`          | List all campaigns        |
| GET    | `/campaigns/{id}`     | Get a single campaign     |
| POST   | `/campaigns`          | Create a new campaign     |
| PUT    | `/campaigns/{id}`     | Update an existing campaign |
| DELETE | `/campaigns/{id}`     | Delete a campaign         |

## Metrics

Prometheus metrics are automatically exposed at `/metrics`, ready to be scraped by a Prometheus server.

## License

No license specified.