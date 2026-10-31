from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import LockError

from app.api.internal import router as internal_router
from app.api.routes import router as api_router
from app.services.redis_service import RedisService
from app.services.room_service import RoomError, RoomService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = RedisService()
    app.state.rooms = RoomService(app.state.redis)
    yield
    await app.state.redis.close()


app = FastAPI(lifespan=lifespan)

app.include_router(api_router, prefix="/api")
app.include_router(internal_router, prefix="/internal")


@app.exception_handler(RoomError)
async def room_error_handler(request: Request, error: RoomError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


@app.exception_handler(LockError)
async def lock_error_handler(request: Request, error: LockError):
    return JSONResponse(status_code=503, content={"detail": "The server is busy, try again."})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError):
    message = error.errors()[0]["msg"].removeprefix("Value error, ")
    return JSONResponse(status_code=422, content={"detail": message})


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "catan-backend"}
