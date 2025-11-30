# Comicarr

Comicarr is a comic book library manager inspired by Kapowarr, borrowing ideas from Mylar3 and Komga, and aiming to feel at home within the *arr ecosystem. I originally built it to solve my own headaches using multiple apps to manage my own collection — but if it helps you streamline yours, even better.

There’s been a fair bit of vibe-coding along the way (especially on the frontend), so if you spot something you don’t love, go easy on the rants. If you’ve got a better approach - or simply more time than I had when I wrote it, open a PR, keep the tests green, and let’s all live happily ever after.

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for Python package management
- Node.js 18+ and npm for frontend development

### Installation

1. **Sync dependencies:**
   ```bash
   make sync
   # or
   uv sync
   ```

2. **Run the application:**
   
   **Production mode (single service):**
   ```bash
   make build-front  # Build frontend first
   make run          # Backend serves static files
   # or
   uv run python -m comicarr.app
   ```
   
   **Development mode (two services):**
   ```bash
   # Terminal 1: Backend
   make dev-back
   
   # Terminal 2: Frontend (with hot reload)
   make dev-front
   ```

3. **Access the application:**
   
   **Production mode:**
   - Frontend: http://127.0.0.1:8000/
   - API: http://127.0.0.1:8000/api/
   - API Docs: http://127.0.0.1:8000/docs
   - Health Check: http://127.0.0.1:8000/api/health
   
   **Development mode (two services):**
   - Frontend: http://127.0.0.1:5173/
   - API: http://127.0.0.1:8000/api/
   - API Docs: http://127.0.0.1:8000/docs
   - Health Check: http://127.0.0.1:8000/api/health

### Development

- **Backend development:** `make dev-back`
- **Frontend development:** `make dev-front`
- **Run tests:** `make test` or `make test-back` for backend only and `make test-front` for frontend only.
- **Build frontend:** `make build-front`

### Configuration

Runtime defaults are controlled through environment variables. Create a `.env` file in the project root if you need to override defaults:

Key variables:
- `COMICARR_HOST` / `COMICARR_PORT` – interface and port used by the backend
- `COMICARR_BASE_URL` – optional base path when running behind a reverse proxy
- `COMICARR_ENV` – environment (development/production)

## Project Structure

- `backend/`  – FastAPI Application code
- `frontend/` – React frontend application

## Design

[`DESIGN.md`](DESIGN.md) to be pushed soon.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

