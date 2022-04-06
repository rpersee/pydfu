import asyncio
import warnings

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

from ..common.publisher import Publisher
from ... import dfu_util

router = APIRouter()


class Device(BaseModel):
    msg: str
    vid: str
    pid: str
    ver: int
    devnum: int
    cfg: int
    intf: int
    path: str
    alt: int
    name: str
    serial: str


@router.get("/devices/", tags=["devices"], response_model=list[Device])
async def get_devices():
    return dfu_util.enum().exec()


@router.get("/devices/events", tags=["devices"])
async def get_events(req: Request):
    async def event_publisher():
        queue = asyncio.Queue()
        await Publisher.subscribe(queue)

        try:
            while True:
                disconnected = await req.is_disconnected()
                if disconnected:
                    warnings.warn(f"Disconnecting client {req.client}")
                    break

                device = await queue.get()

                yield dict(data=dict(device))

            warnings.warn(f"Disconnected from client {req.client}")

        except asyncio.CancelledError as e:
            warnings.warn(f"Disconnected from client (via refresh/close) {req.client}")
            raise e

        finally:
            await Publisher.unsubscribe(queue)
            del queue

    return EventSourceResponse(event_publisher())
