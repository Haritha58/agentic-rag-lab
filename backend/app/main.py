from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.api_applications import router as applications_router
from app.api_coach import router as coach_router
from app.api_jobs import router as jobs_router
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="JobPilot", version="0.1.0")
    app.include_router(router)
    app.include_router(jobs_router)
    app.include_router(coach_router)
    app.include_router(applications_router)

    # Serve the built dashboard when present (`npm run build`); in dev, Vite serves it.
    dist = get_settings().frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            return FileResponse(dist / "index.html")

    return app


app = create_app()
