from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .common.publisher import Publisher
from .routers import devices

description = """
A REST API above the dfu-util CLI utility.
"""

tags_metadata = [
    {
        "name": "devices",
        "description": "Currently attached DFU-capable USB devices.",
    },
]

app = FastAPI(
    title="Python Device Firmware Upgrade (DFU)",
    description=description,
    version="0.0.1",
    # terms_of_service="http://example.com/terms/",
    # contact={
    #     "name": "Deadpoolio the Amazing",
    #     "url": "http://x-force.example.com/contact/",
    #     "email": "dp@x-force.example.com",
    # },
    license_info={
        "name": "GNU GPLv3",
        "url": "https://spdx.org/licenses/GPL-3.0-or-later.html",
    },
    openapi_tags=tags_metadata,
)

app.include_router(devices.router)


@app.on_event("startup")
async def start_publisher():
    await Publisher.start()


@app.on_event("shutdown")
async def stop_publisher():
    await Publisher.stop()


@app.get("/", response_class=RedirectResponse)  # status_code=301  // moved permanently
async def redirect_docs():
    return "/redoc"
