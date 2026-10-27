"""AI 应用接口的归属隔离与幂等回归测试。

不碰真库、不调模型：sqlite 内存库 + 覆盖 get_db / get_current_user，
只测「钱和内容不能越权、重复请求不能重复入账」这些纯业务规则。
运行：pytest tests/test_ai_assist_api.py
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db, Base
from app.core.security import get_current_user, oauth2_scheme, hash_password
import app.models  # noqa: F401  确保全部模型注册进 Base.metadata
from app.models.user import User
from app.models.ai_assist import AICreation, AIExecPlan

from app.api.routes import ai_assist, articles

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False)
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# 测试夹具：两个用户 A / B，token 直接连到用户行
# ---------------------------------------------------------------------------
import pytest


@pytest.fixture()
def client():
    session = TestSession()
    a = User(nickname="用户A", password_hash=hash_password("pwd12345"))
    b = User(nickname="用户B", password_hash=hash_password("pwd12345"))
    session.add_all([a, b])
    session.commit()
    tokens = {"token-A": a, "token-B": b}   # id 稳定，直接存对象

    def _override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def _override_user(token: str = Depends(oauth2_scheme)):
        u = tokens.get(token)
        if not u:
            raise HTTPException(401, "未登录")
        return u

    app = FastAPI()
    app.include_router(ai_assist.router, prefix="/ai")
    app.include_router(articles.router, prefix="/articles")
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as c:
        # 把用户 id 挂在 client 上，测试里好拿
        c.uid_a, c.uid_b = a.id, b.id
        yield c
    session.close()


def _mk_plan(client, **over):
    """给用户 A 建一条执行计划，默认 article_id=501。"""
    db = TestSession()
    row = AIExecPlan(
        user_id=client.uid_a, article_id=over.get("article_id", 501),
        title=over.get("title", "测试攻略"),
        plan_json='{"steps": [{"text": "比价", "done": false}]}',
        est_saving=30,
    )
    db.add(row)
    db.commit()
    pid = row.id
    db.close()
    return pid


def _checkins(client, uid):
    from app.models.checkin import Checkin
    db = TestSession()
    rows = db.query(Checkin).filter(Checkin.user_id == uid).all()
    n = len(rows)
    db.close()
    return n


# ---------------------------------------------------------------------------
# 幂等：confirm-saving 重复请求不得重复入账
# ---------------------------------------------------------------------------

def test_confirm_saving_duplicate_request_records_once(client):
    pid = _mk_plan(client)
    r1 = client.post("/ai/exec-plans/%d/confirm-saving" % pid, json={"amount": 23.5},
                     headers={"Authorization": "Bearer token-A"})
    assert r1.status_code == 200
    assert r1.json()["data"]["duplicate"] is False
    assert _checkins(client, client.uid_a) == 1

    # 同用户/同攻略/同日/同金额的第二次请求：不报错、不产生第二笔
    r2 = client.post("/ai/exec-plans/%d/confirm-saving" % pid, json={"amount": 23.5},
                     headers={"Authorization": "Bearer token-A"})
    assert r2.status_code == 200
    assert r2.json()["data"]["duplicate"] is True
    assert _checkins(client, client.uid_a) == 1


def test_confirm_saving_different_amount_same_day_is_a_new_record(client):
    # 同日不同金额视为又一次真实节省，允许入账（与「防重复提交」不冲突）
    pid = _mk_plan(client)
    client.post("/ai/exec-plans/%d/confirm-saving" % pid, json={"amount": 23.5},
                headers={"Authorization": "Bearer token-A"})
    r2 = client.post("/ai/exec-plans/%d/confirm-saving" % pid, json={"amount": 10},
                     headers={"Authorization": "Bearer token-A"})
    assert r2.status_code == 200
    assert r2.json()["data"]["duplicate"] is False
    assert _checkins(client, client.uid_a) == 2


def test_confirm_saving_invalid_amount_rejected(client):
    pid = _mk_plan(client)
    for bad in (0, -5):
        r = client.post("/ai/exec-plans/%d/confirm-saving" % pid, json={"amount": bad},
                        headers={"Authorization": "Bearer token-A"})
        assert r.status_code == 400
    assert _checkins(client, client.uid_a) == 0


# ---------------------------------------------------------------------------
# 归属隔离：别人的计划/报告/草稿一个都摸不到
# ---------------------------------------------------------------------------

def test_other_users_plan_is_404_and_writes_nothing(client):
    pid = _mk_plan(client)   # 属于 A
    r = client.post("/ai/exec-plans/%d/confirm-saving" % pid, json={"amount": 23.5},
                    headers={"Authorization": "Bearer token-B"})
    assert r.status_code == 404
    assert _checkins(client, client.uid_b) == 0
    assert _checkins(client, client.uid_a) == 0

    r2 = client.get("/ai/exec-plans/%d" % pid, headers={"Authorization": "Bearer token-B"})
    assert r2.status_code == 404


def test_plans_list_only_contains_own_rows(client):
    _mk_plan(client)
    r = client.get("/ai/exec-plans", headers={"Authorization": "Bearer token-B"})
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []


def test_bill_report_detail_is_user_scoped(client):
    # A 的报告，B 按 id 直接访问必须 404
    db = TestSession()
    import json as _json
    row = __import__("app.models.ai_assist", fromlist=["AIBillReport"]).AIBillReport(
        user_id=client.uid_a, month="2026-10",
        stats_json="{}", report_json=_json.dumps({"summary": "x"}, ensure_ascii=False))
    db.add(row)
    db.commit()
    rid = row.id
    db.close()

    r = client.get("/ai/bill-reports/%d" % rid, headers={"Authorization": "Bearer token-B"})
    assert r.status_code == 404
    r2 = client.get("/ai/bill-reports/%d" % rid, headers={"Authorization": "Bearer token-A"})
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# creation_id 回填：发布后 AI 草稿能挂上攻略，且只认自己的草稿
# ---------------------------------------------------------------------------

def _mk_creation(client, **over):
    db = TestSession()
    row = AICreation(
        user_id=client.uid_a, scene="article", mode="generate",
        input_json="{}", output_json='{"title": "AI 草稿标题", "content": "正文内容足够长了"}',
        article_id=over.get("article_id", 0),
    )
    db.add(row)
    db.commit()
    cid = row.id
    db.close()
    return cid


def _creation_article_id(client, cid):
    db = TestSession()
    row = db.query(AICreation).get(cid)
    aid = row.article_id
    db.close()
    return aid


def test_submit_article_backfills_own_creation(client):
    cid = _mk_creation(client)
    r = client.post("/articles", json={"title": "我的攻略", "content": "这篇正文肯定超过十个字",
                                       "creation_id": cid},
                    headers={"Authorization": "Bearer token-A"})
    assert r.status_code == 200
    aid = r.json()["data"]["id"]
    assert _creation_article_id(client, cid) == aid


def test_submit_article_ignores_foreign_creation_id(client):
    cid = _mk_creation(client)   # A 的草稿
    r = client.post("/articles", json={"title": "B 的攻略", "content": "这篇正文肯定超过十个字",
                                       "creation_id": cid},
                    headers={"Authorization": "Bearer token-B"})
    assert r.status_code == 200          # 文章照常建
    assert _creation_article_id(client, cid) == 0   # 但别人的草稿不被挂上


def test_submit_article_does_not_overwrite_existing_link(client):
    cid = _mk_creation(client, article_id=999)   # 已关联过
    r = client.post("/articles", json={"title": "再投一次", "content": "这篇正文肯定超过十个字",
                                       "creation_id": cid},
                    headers={"Authorization": "Bearer token-A"})
    assert r.status_code == 200
    assert _creation_article_id(client, cid) == 999   # 原关联不被覆盖


def test_creations_list_scoped_and_marks_published(client):
    cid = _mk_creation(client)
    r = client.get("/ai/creations", headers={"Authorization": "Bearer token-B"})
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []

    r2 = client.get("/ai/creations", headers={"Authorization": "Bearer token-A"})
    items = r2.json()["data"]["items"]
    assert [it["id"] for it in items] == [cid]
    assert items[0]["article_id"] == 0
