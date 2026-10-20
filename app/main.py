"""FastAPI application entrypoint."""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager

from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import FileResponse

from app.api.routes import router as rest_router
from app.api.websocket import WebSocketHandler, ws_handler
from app.services.session_service import SessionService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global services
session_service = SessionService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    global ws_handler
    ws_handler = WebSocketHandler(session_service)
    # Wire callbacks from AudioService to WebSocket handler
    # We'll do this per-session in the handler
    logger.info("Guitar Coach Web App started")
    yield
    logger.info("Guitar Coach Web App shutting down")


app = FastAPI(
    title="Guitar Coach (Riff)",
    version="0.6.0",
    lifespan=lifespan,
)

# No CORS middleware: the UI is served from this same origin, and other
# websites must not be able to read responses from this local server.
FRONTEND_DIR = Path("frontend").resolve()

# Include REST routes with /api prefix
app.include_router(rest_router, prefix="/api")

# Serve frontend at root
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/{path:path}")
async def static_files(path: str):
    file_path = (FRONTEND_DIR / path).resolve()
    # Only files inside frontend/ (blocks /..%2F.. path traversal).
    if file_path.is_relative_to(FRONTEND_DIR) and file_path.is_file():
        return FileResponse(file_path)
    raise HTTPException(404, "Not found")


def _same_origin(websocket: WebSocket) -> bool:
    """Browsers always send Origin on WebSocket; other sites must be refused."""
    origin = websocket.headers.get("origin")
    return origin is None or urlparse(origin).netloc == websocket.headers.get("host")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time audio processing."""
    global ws_handler
    if ws_handler is None:
        await websocket.close(code=1011)
        return
    if not _same_origin(websocket):
        await websocket.close(code=1008)  # policy violation
        return
    await ws_handler.handle(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")