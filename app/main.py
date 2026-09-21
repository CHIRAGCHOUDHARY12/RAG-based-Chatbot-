from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth.routes import get_current_user
from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.config import settings
from app.database import repositories as repo
from app.database.db import init_db
from app.rag import pipeline
from app.rag.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app.main")

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, same_site="lax")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router)
app.include_router(chat_router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting %s", settings.APP_NAME)
    init_db()
    app.state.vector_store = VectorStore()
    app.state.index_status = pipeline.ensure_index()
    logger.info("Index status: %s", app.state.index_status.message)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conversations = repo.list_conversations(user.id)
    index_status = request.app.state.index_status
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "conversations": conversations,
            "app_name": settings.APP_NAME,
            "source_pdf": index_status.source_pdf,
            "index_ready": index_status.ready,
            "index_message": index_status.message,
        },
    )


@app.post("/admin/reindex")
async def admin_reindex(request: Request):
    """Manually rebuild the vector index. Requires an authenticated user;
    this is a local single-tenant app, so any logged-in user may trigger
    a rebuild of the shared document index."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    request.app.state.index_status = pipeline.ensure_index(force_rebuild=True)
    return RedirectResponse("/dashboard", status_code=302)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return HTMLResponse("<h1>404</h1><p>Page not found.</p><a href='/'>Go home</a>", status_code=404)
