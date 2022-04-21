"""Firmware images / binaries"""
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, UploadFile
# from fastapi.responses import HTMLResponse

router = APIRouter()


class DataStore:
    package_name = "pydfu"
    data_path = Path.home() / ".local" / "share" / package_name / "images"
    data_path.mkdir(exist_ok=True)


@router.post("/images/", tags=["images"])
async def upload_image(
        upload_file: UploadFile = File(..., description="A file read as UploadFile")
):
    async with aiofiles.open(DataStore.data_path / upload_file.filename, "wb") as output_file:
        contents = await upload_file.read()
        await output_file.write(contents)

    return {"Result": f"File saved as '{upload_file.filename}'."}


@router.get("/images/", tags=["images"])
async def get_images():
    return [{"filename": file.name, "size": file.stat().st_size} for file in DataStore.data_path.glob('*')
            if file.is_file()]


# @router.get("/images/test")
# async def test_images():
#     content = """
# <body>
#     <form action="/images/" enctype="multipart/form-data" method="post">
#         <input name="upload_file" type="file" multiple>
#         <input type="submit">
#     </form>
# </body>
#     """
#     return HTMLResponse(content=content)


if __name__ == "__main__":
    print(__package__)
