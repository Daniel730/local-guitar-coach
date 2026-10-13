"""FastAPI application entrypoint."""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend) - serve at root for UI
import os
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Include REST routes with /api prefix
app.include_router(rest_router, prefix="/api")

# Serve frontend at root
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/{path:path}")
async def static_files(path: str):
    file_path = f"frontend/{path}"
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(404, "Not found")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time audio processing."""
    global ws_handler
    if ws_handler is None:
        await websocket.close(code=1011)
        return
    await ws_handler.handle(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")