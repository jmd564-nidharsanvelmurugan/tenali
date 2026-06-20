import io
import os
from datetime import datetime, timedelta
from PIL import Image
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

AZURE_BLOB_STORAGE_CONNECTION_STRING = os.getenv("AZURE_BLOB_STORAGE_CONNECTION_STRING")
IMAGE_CONTAINER = "tenaliai-jlens-images"

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

blob_service_client = BlobServiceClient.from_connection_string(AZURE_BLOB_STORAGE_CONNECTION_STRING)


def validate_image(file_bytes: bytes, filename: str) -> bool:
    """Check file is a valid image by extension and content."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        return True
    except Exception:
        return False


def resize_image(file_bytes: bytes, max_size: int = 2048) -> bytes:
    """Resize image if larger than max_size, returns bytes."""
    img = Image.open(io.BytesIO(file_bytes))
    if max(img.size) <= max_size:
        return file_bytes
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buf = io.BytesIO()
    fmt = img.format or "PNG"
    img.save(buf, format=fmt)
    return buf.getvalue()


async def upload_image_to_blob(file_bytes: bytes, filename: str, user_id: str, workspace_id: str) -> str:
    """Upload image to blob container and return a SAS URL."""
    blob_path = f"{user_id}/{workspace_id}/{filename}"
    container_client = blob_service_client.get_container_client(IMAGE_CONTAINER)
    try:
        await container_client.create_container()
    except Exception:
        pass
    blob_client = container_client.get_blob_client(blob_path)
    await blob_client.upload_blob(file_bytes, overwrite=True)

    # Generate SAS URL
    conn = AZURE_BLOB_STORAGE_CONNECTION_STRING
    account_name = account_key = None
    for part in conn.split(";"):
        if part.startswith("AccountName="):
            account_name = part.split("=", 1)[1]
        elif part.startswith("AccountKey="):
            account_key = part.split("=", 1)[1]

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=IMAGE_CONTAINER,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=24),
    )
    return f"https://{account_name}.blob.core.windows.net/{IMAGE_CONTAINER}/{blob_path}?{sas_token}"


def prepare_image_for_vision(image_url: str) -> dict:
    """Return OpenAI vision message content block."""
    return {"type": "image_url", "image_url": {"url": image_url}}
