# app\main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api_router import api_router

app = FastAPI(title="Meeting Assistant Agent API")

# 웹 프론트엔드 연결 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 배포 시에는 웹사이트 주소만 넣으세요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Meeting Assistant Agent Backend is running!"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}