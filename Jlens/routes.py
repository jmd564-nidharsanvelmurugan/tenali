from fastapi import APIRouter
from .controllers import login_controller, upload_controller

router = APIRouter()


@router.post("/")
async def login():
    return login_controller(app_name="Jlens")


@router.post("/upload")
async def upload():
    return upload_controller(app_name="Jlens")
