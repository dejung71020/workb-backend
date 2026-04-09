# app\main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# 각 도메인에서 router 만들어서 연결해주세요.
# from app.api.v1.api_router import api_router
from app.core.lifespan import lifespan

app = FastAPI(title="Meeting Assistant Agent API", lifespan=lifespan)

# 웹 프론트엔드 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
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
# app.include_router(api_router, prefix="/api/v1")