from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401  (registers the tables)
from app.api import event_codes, events, simulator, tasks
from app.db import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Equipment Event Monitoring API", lifespan=lifespan)
app.include_router(simulator.router)
app.include_router(event_codes.router)
app.include_router(tasks.router)
app.include_router(events.router)


@app.get("/health")
def health():
    return {"status": "ok"}