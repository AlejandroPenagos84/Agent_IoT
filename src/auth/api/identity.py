from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    user_id: str
    username: str
    email: str
