# app\main.py
'''
RailWay 배포 테스트
'''
import pymysql
pymysql.install_as_MySQLdb()

# -------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
<<<<<<< HEAD
# 각 도메인에서 router 만들어서 연결해주세요.
=======
>>>>>>> main
from app.api.v1.api_router import api_router
from app.core.lifespan import lifespan

app = FastAPI(title="Meeting Assistant Agent API", lifespan=lifespan, redirect_slashes=False)

# 웹 프론트엔드 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
<<<<<<< HEAD
    # Vite dev servers
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
=======
    allow_origins=["*"],
    allow_credentials=False,
>>>>>>> main
    allow_methods=["*"],
    allow_headers=["*"],
)

# 루트 경로
@app.get("/")
async def root():
    return {"message": "Meeting Assistant Agent API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# 통합 라우터 연결
app.include_router(api_router, prefix="/api/v1")