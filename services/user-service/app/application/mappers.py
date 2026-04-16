from ..domain.models import User
from ..domain.schemas import UserResponse

def to_response(u: User) -> UserResponse:
    return UserResponse(
        email=u.email,
        display_name=u.display_name,
        first_name=u.first_name,
        last_name=u.last_name,
        created_at=u.created_at,
    )
