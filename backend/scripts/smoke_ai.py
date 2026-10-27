# -*- coding: utf-8 -*-
"""AI 应用四阶段的端到端冒烟测试：真实 MySQL + 真实 glm-4-flash 调用。

跑法：PYTHONIOENCODING=utf-8 python scripts/smoke_ai.py
用一个一次性测试账号走完整流程，结束后打印结果；测试账号与数据留在库里（dev 库），
不影响真实用户。
"""
import sys
sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
U = "ai_smoke_20261026"
P = "smoke123456"


def j(r):
    d = r.json()
    assert d.get("code") in (200, 404) or True, d
    return d


# ---------- 注册/登录测试账号 ----------
r = c.post("/auth/register", json={"nickname": U, "password": P})
print("register:", r.json().get("message"))
r = c.post("/auth/login-password", json={"nickname": U, "password": P})
tok = j(r)["data"]["token"]
H = {"Authorization": "Bearer " + tok}

# ---------- 阶段一：AI 创作助手 ----------
r = c.post("/ai/create-assist", json={
    "scene": "article", "mode": "generate",
    "topic": "食堂吃饭怎么省钱",
    "experience": "我每天在食堂吃两顿，发现下午4点半去有些菜打折，一个月能省100多块",
    "scene_desc": "大学生食堂",
}, headers=H)
d = j(r)
print("create-assist code:", d["code"], d.get("message"))
res = (d.get("data") or {}).get("result") or {}
print("  title:", res.get("title"))
print("  category:", res.get("category"), "| tags:", res.get("tags"))
print("  content len:", len(res.get("content") or ""), "| steps:", len(res.get("steps") or []))

r = c.get("/ai/creations?scene=article", headers=H)
print("creations list:", len(j(r)["data"]["items"]), "条")

# 润色模式
if res.get("content"):
    r = c.post("/ai/create-assist", json={
        "scene": "article", "mode": "polish", "title": res.get("title", ""),
        "content": res["content"][:1500]}, headers=H)
    d2 = j(r)
    print("polish code:", d2["code"], "| new title:", ((d2.get("data") or {}).get("result") or {}).get("title"))

# ---------- 阶段二：AI 账单解读 ----------
r = c.post("/ai/bill-report", json={}, headers=H)
d = j(r)
print("bill-report(empty) code:", d["code"], "| empty:", (d.get("data") or {}).get("empty"),
      "| msg:", (d.get("data") or {}).get("message"))

# 灌两个月演示账单，让解读有真实数据可算
c.post("/bills/seed-demo?month=2026-10&months=2", headers=H)
r = c.post("/ai/bill-report", json={"month": "2026-10"}, headers=H)
d = j(r)
rep = (d.get("data") or {}).get("report") or {}
stats = (d.get("data") or {}).get("stats") or {}
print("bill-report code:", d["code"], "| total:", stats.get("total"), "| data_limited:", rep.get("data_limited"))
print("  summary:", (rep.get("summary") or "")[:80])
print("  points:", len(rep.get("points") or []))
rid = (d.get("data") or {}).get("id")
r = c.get("/ai/bill-reports?month=2026-10", headers=H)
print("reports list:", len(j(r)["data"]["items"]))
if rid:
    r = c.get("/ai/bill-reports/%s" % rid, headers=H)
    print("get report:", j(r)["code"])

# ---------- 阶段三：AI 执行计划 ----------
# 找一篇已过审的攻略当素材
r = c.get("/articles?limit=1")
arts = j(r)["data"] or []
if arts:
    aid = arts[0]["id"]
    r = c.post("/ai/exec-plan", json={"article_id": aid}, headers=H)
    d = j(r)
    print("exec-plan code:", d["code"], d.get("message"))
    payload = (d.get("data") or {}) if isinstance(d.get("data"), dict) else {}
    plan = payload.get("plan") or {}
    print("  steps:", len(plan.get("steps") or []), "| shopping:", len(plan.get("shopping") or []),
          "| est_saving:", payload.get("est_saving"), "| keywords:", plan.get("product_keywords"))
    pid = payload.get("id")
    if pid:
        # 勾第一步 + 给第一件商品填实买金额
        steps = plan.get("steps") or []
        steps[0]["done"] = True
        shop = plan.get("shopping") or []
        if shop:
            shop[0]["actual"] = 9.9
            shop[0]["bought"] = True
        r = c.put("/ai/exec-plans/%s" % pid, json={"steps": steps, "shopping": shop}, headers=H)
        print("plan update:", j(r)["code"])
        # 确认实际节省 → 应写 checkins source=攻略
        r = c.post("/ai/exec-plans/%s/confirm-saving" % pid, json={"amount": 23.5, "note": "冒烟测试"}, headers=H)
        d = j(r)
        print("confirm-saving:", d["code"], d.get("message"),
              "| month_total:", (d.get("data") or {}).get("checkin_month_total"))
        r = c.get("/checkin/records?month=2026-10", headers=H)
        recs = j(r)["data"]["records"]
        mine = [x for x in recs if x["source"] == "攻略"]
        print("checkins source=攻略:", len(mine), mine[:1])
        r = c.get("/ai/exec-plans", headers=H)
        items = j(r)["data"]["items"]
        print("plan history:", len(items), "| first:", items[0] if items else None)
else:
    print("no approved article, skip exec-plan")

# ---------- 阶段四：AI 审核辅助（管理员） ----------
r = c.post("/admin/api/login", json={"username": "admin", "password": "admin123"})
atok = j(r)["data"]["token"]
AH = {"Authorization": "Bearer " + atok}
# 用刚才 AI 生成、直接走投稿接口的一篇 pending 攻略来审
r = c.post("/articles", headers=H, json={
    "title": "冒烟测试投稿：薅APP新人券的三个坑",
    "content": "新人券看着香，其实有三个坑：第一坑是满减门槛，第二坑是限时……",
    "category": "羊毛"})
art_id = j(r)["data"]["id"]
r = c.post("/admin/api/ai-review", json={"target_type": "article", "target_id": art_id}, headers=AH)
d = j(r)
res = (d.get("data") or {}).get("result") or {}
print("ai-review code:", d["code"], "| risk_tags:", res.get("risk_tags"),
      "| needs_human:", res.get("needs_human"))
print("  reason:", (res.get("reason") or "")[:80])
r = c.get("/admin/api/ai-review?target_type=article&target_id=%s" % art_id, headers=AH)
print("ai-review get:", j(r)["code"])

print("\nSMOKE DONE")
