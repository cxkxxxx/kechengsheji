
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from app.core.config import UPLOAD_DIR
import os
from fastapi.openapi.docs import get_swagger_ui_html

from app.core.database import engine
from app.models import Base
from app.api.routes import auth, articles, posts, agent, bills, checkin, comments, favorites, admin

# 首次启动自动建表
Base.metadata.create_all(bind=engine)
# 首次启动自动创建默认管理员（admin/admin123）
from app.api.routes.admin import _seed_admin
_seed_admin()

app = FastAPI(
    title="省活攻略 API",
    description="基于大语言模型的省钱攻略智能推荐平台后端",
    version="1.0.0",
    docs_url=None,
)

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
