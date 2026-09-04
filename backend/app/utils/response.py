

from typing import Any

def success(data: Any = None, message: str = "成功"):
    return {"code": 200, "message": message, "data": data}

def error(message: str = "失败", code: int = 400):
    return {"code": code, "message": message, "data": None}
