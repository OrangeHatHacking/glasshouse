"""Time sync API endpoint."""

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from glasshouse import timesync

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class TimeSyncRequest(BaseModel):
    timestamp: float


@router.get("/time")
async def get_time():
    """Return current Pi time and sync status."""
    return {
        "time": int(time.time()),
        "synced": timesync.is_synced(),
    }


@router.post("/time")
async def set_time(body: TimeSyncRequest):
    """Accept a Unix epoch from the phone and set the system clock."""
    result = await timesync.sync_from_client(body.timestamp)
    if not result["synced"]:
        raise HTTPException(status_code=500, detail=result.get("error", "sync failed"))

    return result
