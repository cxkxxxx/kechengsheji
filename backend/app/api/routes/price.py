"""商品比价接口：自查比价结果、看数据源状态、补录站内价格库。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.api.routes.admin import get_current_admin
from app.models.price_history import PriceHistory
from app.models.user import User
from app.services import best_price
from app.services.price_service import compare
from app.utils.response import success

router = APIRouter()


@router.get("/status")
def status(check: bool = False, db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)):
    # 一眼看清实时比价可用不可用、降级后还有什么
    rows = db.query(func.count(PriceHistory.id), func.count(func.distinct(PriceHistory.product_name))).all()
    be = best_price.backend()
    out = {
        "mode": "live" if be["ok"] else "fallback",
        "provider": "best-price-mcp（京东/天猫，第三方中转）" if be["ok"] else "未安装",
        "reason": be["reason"],
        "timeout_seconds": be.get("timeout"),
        "caveat": ("数据源是包作者自建的腾讯云函数、全体使用者共享一份日配额，"
                   "京东侧可能整天返回「已达接口调用上限」；商品关键词会发送给该第三方。"),
        "local_library": {"rows": int(rows[0][0] or 0), "products": int(rows[0][1] or 0)},
    }
    if check:
        # 真打一次查询，让上游自己回答可用不可用（会占用共享配额，所以默认不开）
        items, warnings = best_price.search("小米15 手机", limit=2)
        out["check"] = {"ok": bool(items), "items": len(items), "warnings": warnings}
    return success(out)


@router.get("/compare")
def price_compare(keyword: str = "", link: str = "", budget: float = 0,
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 与 AI 工具 price_compare 走同一套编排，方便不经过模型直接验证
    if not (keyword or link).strip():
        return success(compare(keyword=keyword, link=link, budget=None, db=db))
    return success(compare(keyword=keyword, link=link, budget=budget or None, db=db))


class PriceHistoryIn(BaseModel):
    product_name: str
    platform: str = "其他"
    price: float
    url: str = ""


@router.post("/history")
def add_price(payload: PriceHistoryIn, db: Session = Depends(get_db),
              _admin=Depends(get_current_admin)):
    # 补录各平台价格，供降级模式与历史低价判断使用。
    # 站内价格库是全平台共享的运营数据，所以只开给管理端，普通用户写不了
    if payload.price <= 0:
        raise HTTPException(400, "价格必须大于 0")
    row = PriceHistory(product_name=payload.product_name.strip()[:120],
                       platform=payload.platform.strip()[:30] or "其他",
                       price=round(float(payload.price), 2),
                       url=payload.url.strip()[:500], recorded_at=datetime.now())
    db.add(row)
    db.commit()
    db.refresh(row)
    return success({"id": row.id, "product_name": row.product_name,
                    "platform": row.platform, "price": row.price})
