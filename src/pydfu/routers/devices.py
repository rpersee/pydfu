import asyncio
import warnings

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

from .images import DataStore
from ..common import dfu_util
from ..common.publisher import Publisher

router = APIRouter()


class Mapping(BaseModel):
    number: int
    size: int
    multiplier: str
    permissions: str


class Sector(BaseModel):
    address: str
    mapping: list[Mapping]


class AlternateSetting(BaseModel):
    id: int
    name: str
    sectors: list[Sector]


class Device(BaseModel):
    # msg: str
    serial: str
    vid: str
    pid: str
    ver: int
    devnum: int
    cfg: int
    intf: int
    path: str
    alt: list[AlternateSetting]


class FileRequest(BaseModel):
    filename: str


@router.get("/devices/", tags=["devices"], response_model=list[Device])
async def get_devices():
    return dfu_util.enum().exec()


@router.get("/devices/{serial}/{alt}", tags=["devices"], response_model=Device)
async def get_device(serial: str, alt: int):
    return next(iter(device for device in dfu_util.enum().exec()
                     if device["serial"] == serial and device["alt"] == alt), None)


@router.post("/devices/{serial}/{alt}/{address}", tags=["devices"])
def post_firmware(serial: str, alt: int, address: str, filename: FileRequest):
    file = DataStore.data_path / filename
    assert file.exists()
    (
        dfu_util.download(file)
            .serial(serial)
            .alt_setting(alt)
            .dfuse_address(address)
            .exec()
    )


@router.post("/devices/{serial}/{alt}/{address}")
def get_firmware(serial: str, alt: int, address: str, filename: FileRequest):
    file = DataStore.data_path / filename
    assert file.exists()
    (
        dfu_util.upload(file)
            .serial(serial)
            .alt_setting(alt)
            .dfuse_address(address)
            .exec()
    )


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
