# app\main.py
import os

from fastapi import FastAPI

app = FastAPI(title="Meeting Assistant Agent API")


@app.get("/")
async def root():
    return {"message": "Meeting Assistant Agent Backend is running!"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
