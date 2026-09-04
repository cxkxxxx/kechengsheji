

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    # # 获取数据库会话（FastAPI 依赖注入）
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
