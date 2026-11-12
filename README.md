# Playwright Task

## Requirements
- Docker
- Docker Compose

## Configuration
Create a `.env` file in the project root:

```env
DB_NAME=videos
DB_USER=username
DB_PASSWORD=change_this_password
```

## Build and Start

```bash
docker compose up --build
```

The web service will be available at `http://localhost:8000`.

To start the web service again without re-building it run this:

```bash
docker compose up
```

## Stop

```bash
docker compose down
```

