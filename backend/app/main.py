import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.services.redis_service import RedisService
from app.socket.events import register_socket_events
from app.api.routes import router as api_router

ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]


sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=[] 
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = RedisService()
    register_socket_events(sio, app.state)
    yield
    await app.state.redis.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

socket_app = socketio.ASGIApp(sio, app)
app.mount("/", socket_app)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "catan-backend"}