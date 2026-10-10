from fastapi import APIRouter, Request, Response
from app.services.caller_identity import COOKIE_NAME, ORIGIN, ACTOR_TTL_SECONDS, CallerDenied, check_host, check_write, initialize, resolve_credential
router = APIRouter(prefix="/api/caller", tags=["anonymous-caller"])

@router.post("/clear-invalid")
def clear_invalid_caller(request: Request, response: Response):
    check_host(request)
    if request.headers.get("origin") != ORIGIN or request.headers.get("x-anonymous-reset") != "clear-invalid-context":
        raise CallerDenied("EXPLICIT_INVALID_CONTEXT_RESET_REQUIRED", 403)
    credential = request.cookies.get(COOKIE_NAME)
    if credential:
        try:
            resolve_credential(credential)
        except CallerDenied as exc:
            if exc.code != "CALLER_INVALID_OR_EXPIRED":
                raise
        else:
            raise CallerDenied("VALID_CONTEXT_CANNOT_BE_CLEARED", 409)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=False, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"cleared": True}

@router.post("/init")
def init_caller(request: Request, response: Response):
    check_host(request)
    if request.headers.get("origin") != ORIGIN:
        raise CallerDenied("ORIGIN_INVALID", 403)
    if request.cookies.get(COOKIE_NAME):
        _, existing = resolve_credential(request.cookies.get(COOKIE_NAME))
        check_write(request, existing)
    token, _, row = initialize(request.cookies.get(COOKIE_NAME))
    response.headers["Cache-Control"] = "no-store"
    if token:
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=False, samesite="strict", max_age=ACTOR_TTL_SECONDS, path="/")
    return {"csrf_token": row["csrf_token"], "expires_at": row["expires_at"], "mode": "anonymous-local-development"}

@router.get("/context")
def caller_context(request: Request, response: Response):
    check_host(request)
    _, row = resolve_credential(request.cookies.get(COOKIE_NAME))
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": row["csrf_token"], "expires_at": row["expires_at"], "mode": "anonymous-local-development"}
