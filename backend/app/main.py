
import os
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from app.core.config import UPLOAD_DIR, LLM_API_KEY, LLM_MODEL, LLM_API_URL, DATABASE_URL
from fastapi.openapi.docs import get_swagger_ui_html
from sqlalchemy import text

from app.core.database import engine
from app.core.migrate import ensure_columns
from app.models import Base
from app.api.routes import auth, articles, posts, agent, bills, checkin, comments, favorites, admin, price, upload

# 首次启动自动建表
Base.metadata.create_all(bind=engine)
# create_all 不补列，后加的列在这里补（幂等）
_added = ensure_columns()
# 首次启动自动创建默认管理员（admin/admin123）
from app.api.routes.admin import _seed_admin
_seed_admin()


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))          # 不会真的发包，只为选出本机出口网卡
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def _startup_banner():
    # 控制台默认 GBK，输出用纯中文+ASCII，避免编码报错拖垮启动
    port = os.getenv("PORT", "8000")
    llm = "已配置 %s" % LLM_MODEL if LLM_API_KEY else "未配置 LLM_API_KEY（AI 助手会不可用）"
    from app.services import best_price as _bp
    _be = _bp.backend()
    if _be["ok"]:
        price_mode = "京东/天猫实时可用（best-price-mcp，第三方中转、共享日配额，京东侧可能整天限流）"
    else:
        price_mode = "降级（站内价格库 + 各平台搜索直达）；" + _be["reason"]
    lines = [
        "=" * 62,
        " 省活攻略 后端已启动",
        "   后端接口      http://127.0.0.1:%s" % port,
        "   可视化接口文档 http://127.0.0.1:%s/docs     (Swagger，已中文化)" % port,
        "   可视化管理后台 http://127.0.0.1:%s/admin    (默认账号 admin/admin123)" % port,
        "   健康检查      http://127.0.0.1:%s/health" % port,
        "   真机/手机预览  http://%s:%s" % (_lan_ip(), port),
        "                 小程序预览前把 miniprogram/app.js 的 baseUrl 换成上面这个地址",
        "   数据库        %s" % DATABASE_URL.split("@")[-1],
        "   大模型        %s" % llm,
        "   商品比价      %s" % price_mode,
        "=" * 62,
    ]
    if _added:
        lines.insert(-1, "   已自动补齐字段: " + ", ".join(_added))
    try:
        print("\n".join(lines))
    except UnicodeEncodeError:
        print("\n".join(l.encode("ascii", "ignore").decode() for l in lines))


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup_banner()
    yield


app = FastAPI(
    title="省活攻略 API",
    description="基于大语言模型的省钱攻略智能推荐平台后端",
    version="1.1.0",
    docs_url=None,
    lifespan=lifespan,
)


@app.get("/health", tags=["系统"])
def health():
    # 给小程序/运维探活用：数据库连通性 + 大模型配置状态
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_ok = False
        db_error = str(e)[:120]
    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "tables": len(Base.metadata.tables),
        "llm_configured": bool(LLM_API_KEY),
        "llm_model": LLM_MODEL,
        "llm_base": LLM_API_URL.split("/v4")[0],
    }
    if not db_ok:
        payload["database_error"] = db_error
    return payload

# 挂载静态上传目录（图片预览等）
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

# CORS 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join([f"{e.get('loc', ['?'])[-1]}: {e.get('msg', '')}" for e in errors])
    return JSONResponse(status_code=422, content={"code": 422, "message": f"参数错误: {msg}", "data": None})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"code": 500, "message": f"服务器内部错误: {str(exc)}", "data": None})

# 注册路由
app.include_router(auth.router,      prefix="/auth",      tags=["用户认证"])
app.include_router(articles.router,  prefix="/articles",  tags=["攻略文章"])
app.include_router(posts.router,     prefix="/posts",     tags=["社区帖子"])
app.include_router(comments.router,   prefix="/comments",  tags=["评论"])
app.include_router(favorites.router,  prefix="/favorites",  tags=["收藏"])
app.include_router(agent.router,     prefix="/agent",     tags=["AI智能体"])
app.include_router(bills.router,     prefix="/bills",      tags=["账单管理"])
app.include_router(checkin.router,    prefix="/checkin",    tags=["省钱打卡"])
app.include_router(price.router,      prefix="/price",      tags=["商品比价"])
app.include_router(upload.router,    prefix="/upload",     tags=["图片上传"])
app.include_router(admin.router)

@app.get("/")
def read_root():
    return {"message": "省活攻略 API 运行中", "docs": "/docs"}

# 中文化脚本
SWAGGER_CN_SCRIPT = """
<script>
(function() {
    var dict = {
        'Authorize': '授权认证',
        'Try it out': '试一下',
        'Execute': '执行',
        'Clear': '清除',
        'Close': '关闭',
        'Lock': '锁定',
        'Unlock': '解锁',
        'Hide': '隐藏',
        'Show': '显示',
        'Copy': '复制',
        'Expand': '展开',
        'Collapse': '折叠',
        'Models': '数据模型',
        'Schemas': '数据模型',
        'Model': '模型',
        'Download': '下载',
        'Filter': '过滤',
        'Add': '添加',
        'Remove': '移除',
        'Available authorizations': '可用认证方式',
        'Logout': '退出登录',
        'Done': '完成',
        'Cancel': '取消',
        'Parameters': '参数',
        'Responses': '响应',
        'Response body': '响应体',
        'Response headers': '响应头',
        'Request URL': '请求地址',
        'Server response': '服务器响应',
        'Curl': '命令行',
        'Loading...': '加载中...',
        'No results found': '未找到结果',
        'Search': '搜索',
        'Tags': '标签',
        'Paths': '接口列表',
        'No schema defined': '未定义模型',
        'No content': '无内容',
        'possible values': '可选值',
        'Value': '值',
        'Description': '描述',
        'Name': '名称',
        'Content-Type': '内容类型'
    };
    function translateAll() {
        var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        var nodes = [];
        while (walker.nextNode()) {
            var t = walker.currentNode.nodeValue.trim();
            if (dict[t]) nodes.push(walker.currentNode);
        }
        nodes.forEach(function(n) {
            n.nodeValue = ' ' + dict[n.nodeValue.trim()] + ' ';
        });
        document.querySelectorAll('[title]').forEach(function(el) {
            if (dict[el.title]) el.title = dict[el.title];
        });
        document.querySelectorAll('button, th, label, .title, span').forEach(function(el) {
            var t = el.textContent.trim();
            if (dict[t]) el.textContent = dict[t];
        });
    }
    var observer = new MutationObserver(function() {
        clearTimeout(window._cnTimer);
        window._cnTimer = setTimeout(translateAll, 100);
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('load', function() {
        setTimeout(translateAll, 300);
        setTimeout(translateAll, 1500);
        setTimeout(translateAll, 3000);
    });
})();
</script>
"""

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - 接口文档",
        swagger_ui_parameters={"docExpansion": "none"},
    )
    # 在 </body> 前注入中文化脚本
    content = html.body.decode() if hasattr(html, 'body') else str(html)
    content = content.replace("</body>", SWAGGER_CN_SCRIPT + "</body>")
    return HTMLResponse(content=content)
