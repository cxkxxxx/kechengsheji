

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine
from app.models import Base
from app.api.routes import auth, articles, posts, agent, bills, checkin

# 首次启动自动建表
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="省活攻略 API",
    description="基于大语言模型的省钱攻略智能推荐平台后端",
    version="1.0.0",
)

# CORS 跨域（允许小程序访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router,     prefix="/auth",     tags=["用户认证"])
app.include_router(articles.router, prefix="/articles", tags=["攻略文章"])
app.include_router(posts.router,    prefix="/posts",    tags=["社区帖子"])
app.include_router(agent.router,    prefix="/agent",    tags=["AI智能体"])
app.include_router(bills.router,    prefix="/bills",    tags=["账单管理"])
app.include_router(checkin.router,  prefix="/checkin",  tags=["省钱打卡"])

@app.get("/")
def read_root():
    return {"message": "省活攻略 API 运行中", "docs": "/docs"}
