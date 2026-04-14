from ..domain.models import AuthUser
from ..domain.schemas import AuthUserResponse


def to_auth_user_response(u: AuthUser) -> AuthUserResponse:
    return AuthUserResponse(
        id=u.id,
        email=u.email,
        roles=list(u.roles or []),
        last_login_at=u.last_login_at,
    )
