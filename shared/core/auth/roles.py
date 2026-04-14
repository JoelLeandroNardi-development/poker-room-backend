from __future__ import annotations

ALLOWED_ROLES = frozenset({"user", "admin"})

def normalize_roles(
    roles: list[str],
    *,
    allow_empty: bool = False,
    default: list[str] | None = None,
) -> list[str]:
    normalized: list[str] = []
    for r in roles:
        rr = (r or "").strip().lower()
        if rr not in ALLOWED_ROLES:
            raise ValueError(f"Invalid role: {r!r}. Allowed: {sorted(ALLOWED_ROLES)}")
        if rr not in normalized:
            normalized.append(rr)

    if not normalized:
        if not allow_empty:
            if default is not None:
                return list(default)
            raise ValueError("roles must not be empty")

    return normalized