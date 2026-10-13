

from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# bcrypt 自带盐值，比 admin 那套 sha256(SECRET_KEY+pwd) 合适；passlib 已在 requirements 里
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    # bcrypt 上限 72 字节，超了会直接抛错而不是默默截断，这里先挡一道
    return _pwd.hash(raw.encode("utf-8")[:72].decode("utf-8", "ignore"))


def verify_password(raw: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return _pwd.verify(raw, hashed)
    except ValueError:
        return False        # 库里存的是老数据/脏值，当密码不对，别抛 500


def create_access_token(data: dict) -> str:
    # # 生成 JWT token，data 含 {"sub": user_id}
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    # # 依赖注入：从 Header 解析 JWT，返回当前登录用户
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
    except (JWTError, ValueError):
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user
