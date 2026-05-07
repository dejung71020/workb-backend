from pathlib import Path
from time import time

from fastapi import HTTPException, UploadFile, status

MAX_LOCAL_IMAGE_SIZE = 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_local_image(file: UploadFile, directory: Path, stem: str) -> str:
    if file.content_type not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지 파일만 업로드할 수 있습니다.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 파일은 업로드할 수 없습니다.",
        )
    if len(content) > MAX_LOCAL_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지는 1MB 이하 파일을 사용해 주세요.",
        )

    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.glob(f"{stem}.*"):
        existing.unlink(missing_ok=True)

    extension = IMAGE_EXTENSIONS[file.content_type]
    path = directory / f"{stem}{extension}"
    path.write_bytes(content)
    return f"/storage/{directory.name}/{path.name}?v={int(time())}"
