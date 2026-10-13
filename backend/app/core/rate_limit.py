import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from app.core.config import RATE_LIMIT_PER_MINUTE
from app.core.security import get_current_user
from app.models.user import User

# 60 秒滑动窗口计数。只挂在会烧大模型额度或可被暴力尝试的接口上，
# 普通 CRUD 交给 MySQL，没必要多拦一道。
_hits = defaultdict(deque)
_MAX_TRACKED = 5000


def _prune(now: float) -> None:
    # 进程内计数，重启即清零；只防 key 无限增长，不追求精确淘汰。
    # 多 worker 部署时每个进程各算各的，需要全局配额请换 Redis。
    if len(_hits) < _MAX_TRACKED:
        return
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > 60]:
        _hits.pop(key, None)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _guard(queue, now, cap, verb):
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= cap:
        raise HTTPException(status_code=429,
                            detail="%s，请 %d 秒后再试" % (verb, int(60 - (now - queue[0])) + 1))
    queue.append(now)
    _prune(now)


def limit_by_user(action: str, limit: int = None):
    """登录用户维度限流，用于 AI 对话这类会花钱的接口。"""
    cap = limit or RATE_LIMIT_PER_MINUTE

    def guard(current_user: User = Depends(get_current_user)):
        _guard(_hits[(action, "u", current_user.id)], time.monotonic(), cap, "操作太频繁")
    return guard


def hit(key, cap: int, verb: str = "操作太频繁") -> None:
    """给已经自己解析出身份的接口用（比如上传：用户和管理员的 sub 形状不一样，
    套不进 limit_by_user）。"""
    _guard(_hits[key], time.monotonic(), cap, verb)


def limit_by_ip(action: str, limit: int = 10):
    """IP 维度限流，用于登录/注册这类还没有 token 的接口，挡密码爆破。"""

    def guard(request: Request):
        _guard(_hits[(action, "ip", _client_ip(request))], time.monotonic(), limit, "尝试次数过多")
    return guard
