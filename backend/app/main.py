import socketio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.redis_service import RedisService
from app.socket.events import register_socket_events
from app.api.routes import router as api_router

# 1. Setup Socket.IO Server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# 2. Lifecycle Manager (Startup/Shutdown logic)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Redis connection
    app.state.redis = RedisService()
    
    # Register Socket Events passing the app state (for Redis access inside events)
    register_socket_events(sio, app.state)
    
    yield
    
    # Shutdown: Close Redis connection safely
    await app.state.redis.close()

# 3. Initialize FastAPI Application
app = FastAPI(lifespan=lifespan)

# 4. Register REST API Routes
app.include_router(api_router, prefix="/api")

# 5. Mount Socket.IO Application
# This handles the WebSocket handshake at the root URL
socket_app = socketio.ASGIApp(sio, app)
app.mount("/", socket_app)

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint for Docker/Kubernetes probes.
    """
    return {"status": "ok", "service": "catan-backend"}