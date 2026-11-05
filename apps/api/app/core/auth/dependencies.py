"""Authorization dependencies for verified v1 sessions."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.auth.context import auth_context
from app.core.auth.router import bearer_token
from app.core.auth.schemas import SessionUser
from app.core.errors import ApiError

CurrentPrincipal = SessionUser
type CourseAccess = Callable[[str, str, str], bool]


def require_user(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> CurrentPrincipal:
    token = bearer_token(authorization)
    headers = {"WWW-Authenticate": "Bearer"}
    if token is None:
        raise ApiError(401, "TOKEN_REQUIRED", "缺少登录凭证", headers=headers)
    with auth_context(request) as context:
        user = context.authority.parse(token)
    if user is None:
        raise ApiError(401, "INVALID_TOKEN", "登录凭证无效", headers=headers)
    return user


def require_teacher(user: Annotated[CurrentPrincipal, Depends(require_user)]) -> CurrentPrincipal:
    if user.role != "teacher":
        raise ApiError(403, "FORBIDDEN", "需要教师权限")
    return user


def require_owner(user: CurrentPrincipal, owner_id: str) -> None:
    if user.user_id != owner_id:
        raise ApiError(404, "NOT_FOUND", "未找到资源")


def require_course_access(
    request: Request, course_id: str, user: Annotated[CurrentPrincipal, Depends(require_user)]
) -> CurrentPrincipal:
    access: CourseAccess | None = request.app.state.course_access
    if access is None:
        raise ApiError(503, "SERVICE_UNAVAILABLE", "课程权限服务暂不可用")
    if not access(user.user_id, user.role, course_id):
        raise ApiError(404, "COURSE_NOT_FOUND", "未找到课程")
    return user
