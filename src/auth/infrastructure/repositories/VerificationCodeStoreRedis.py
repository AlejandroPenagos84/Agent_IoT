import redis

from auth.infrastructure.errors import redis_errors

FAILURES_TTL_SECONDS = 600


class RedisVerificationCodeStore:
    """Usar con ``redis.Redis(..., decode_responses=True)`` para recibir ``str``."""

    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    def _code_key(self, email: str) -> str:
        return f"verify:{email}"

    def _fail_key(self, email: str) -> str:
        return f"verify_fail:{email}"

    def _cooldown_key(self, email: str) -> str:
        return f"verify_cooldown:{email}"

    def save(self, email: str, code_hash: str, ttl_seconds: int) -> None:
        with redis_errors():
            self._r.set(self._code_key(email), code_hash, ex=ttl_seconds)

    def get(self, email: str) -> str | None:
        with redis_errors():
            value = self._r.get(self._code_key(email))
        return value.decode() if isinstance(value, bytes) else value

    def delete(self, email: str) -> None:
        with redis_errors():
            self._r.delete(self._code_key(email), self._fail_key(email))

    def register_failure(self, email: str) -> int:
        key = self._fail_key(email)
        with redis_errors():
            pipe = self._r.pipeline()
            pipe.incr(key)
            pipe.expire(key, FAILURES_TTL_SECONDS)
            count, _ = pipe.execute()
        return int(count)

    def try_start_cooldown(self, email: str, seconds: int) -> bool:
        with redis_errors():
            return bool(self._r.set(self._cooldown_key(email), 1, nx=True, ex=seconds))
