"""
Convenience launcher: `python run.py`

Equivalent to running:
    uvicorn app.main:app --reload --host <HOST> --port <PORT>
but reads the host/port from your .env file automatically.
"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
