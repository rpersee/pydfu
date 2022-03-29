from fastapi import APIRouter
from pydantic import BaseModel

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
async def get_users():
    return dfu_util.enum().exec()
