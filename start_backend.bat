@echo off
echo Starting AdAware AI Backend...
uvicorn backend.main:app --reload --port 8000
pause