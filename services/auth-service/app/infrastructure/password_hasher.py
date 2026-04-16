from __future__ import annotations

import bcrypt

from .config import BCRYPT_ROUNDS

class PasswordHasher:
    def __init__(self) -> None:
        self._rounds = BCRYPT_ROUNDS

    def hash(self, raw_password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._rounds)
        return bcrypt.hashpw(raw_password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                raw_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except ValueError:
            return False

password_hasher = PasswordHasher()