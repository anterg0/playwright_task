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
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat
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

## Company Data & Impressum Enrichment

### Web Service Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/upload_companies` | Tiny HTML form for CSV upload |
| POST | `/upload_companies` | Upload CSV, import/upsert into companies |
| GET | `/companies` | List all companies (JSON) |
| GET | `/companies/<company_name>` | Read one company (JSON) |

### CSV Import

CSV format (UTF-8, delimiter `;`, field qualifier `"`):

```csv
URL;Company Name;Language;Country;Postcode;City;Street;HouseNo;Web
https://duckduckgo.com;ACME GmbH;German;Germany;10115;Berlin;Main Street;12;https://www.acme-gmbh.de
```

Only `Company Name` (unique key) and `Web` (company home page URL) are strictly required; other columns are stored as provided. Re-importing is idempotent: existing rows updated, new rows inserted. Enrichment results are never overwritten on re-import.

### Enrichment Script

Standalone script — run manually when needed:

```bash
# Process all pending companies
python enrich_companies.py

# Process specific company
python enrich_companies.py --company "ACME GmbH"

# Process at most N companies
python enrich_companies.py --limit 10

# Dry-run to see what would be sent to DeepSeek
python enrich_companies.py --dry-run --mock-company "https://example.com"
```

Options:
- `--company "Name"` — process only this specific company
- `--limit N` — process at most N rows
- `--status N` — process only rows with this status (default: pending rows)

## Stop

```bash
docker compose down
```