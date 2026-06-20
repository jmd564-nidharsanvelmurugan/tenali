from .services import perform_login, handle_upload


def login_controller(app_name: str):
    return {"message": perform_login(app_name)}


def upload_controller(app_name: str):
    return {"message": handle_upload(app_name)}
