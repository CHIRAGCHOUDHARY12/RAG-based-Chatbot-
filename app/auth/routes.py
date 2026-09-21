from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.service import AuthError, authenticate_user, register_user
from app.database import repositories as repo

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request) -> repo.User | None:
    """Return the logged-in user (from the signed session cookie) or None."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return repo.get_user_by_id(user_id)


def require_user(request: Request) -> repo.User:
    """FastAPI dependency for protected routes: redirects unauthenticated
    users by raising a redirect-carrying exception is awkward in FastAPI,
    so protected routes call this and check for None themselves, or use
    require_user_or_redirect below."""
    return get_current_user(request)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
):
    try:
        user = authenticate_user(identifier, password)
    except AuthError as exc:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": str(exc), "identifier": identifier},
            status_code=400,
        )
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    try:
        user = register_user(email, username, password, confirm_password)
    except AuthError as exc:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": str(exc),
                "email": email,
                "username": username,
            },
            status_code=400,
        )
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
