

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
        # 测试根路径健康检查

    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
