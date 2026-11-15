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

## Zoom Feature

Videos can be zoomed during recording using the **F5** key. The first press marks the zoom-in position at the current mouse coordinates, and the second press marks the zoom-out. The same functionality can be triggered programmatically using `window.__zoomAt(x, y)`.

Zoom events are saved in a JSON sidecar file alongside the video. After upload, the background worker automatically processes videos containing zoom data using FFmpeg, producing a new WebM video with smooth zoom-in and zoom-out transitions.

Videos without zoom events are left unchanged.

## Stop

```bash
docker compose down
```