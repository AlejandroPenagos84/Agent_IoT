from auth.application.dtos import TokenPair
from auth.application.errors import (AccountDisabled, AccountNotVerified, MalformedToken,
                                     RefreshTokenReused, RevokedToken)
from auth.application.ports.refresh_store import RefreshTokenStore
from auth.application.ports.token_service import TokenService
from auth.application.ports.user_repository import UserRepository
from auth.domain.user import UserStatus


class RefreshSession:
    """Rota el refresh token y emite un access token nuevo.

    Errores:
    - ``InvalidToken`` y subclases (lanzados por ``TokenService``): expirado,
      firma mala, malformado, tipo equivocado o sin familia.
    - ``RevokedToken``: el token no existe en el store o el usuario ya no existe.
    - ``MalformedToken``: los datos del token no coinciden con los guardados.
    - ``RefreshTokenReused``: se usó un token ya rotado o revocado; se revoca
      toda la familia porque puede haber sido robado.
    - ``AccountNotVerified`` / ``AccountDisabled``: la cuenta no puede iniciar
      sesión; también se revoca la familia.
    """

    def __init__(self, tokens: TokenService, user_repository: UserRepository,
                 store: RefreshTokenStore):
        self.tokens = tokens
        self.user_repository = user_repository
        self.store = store

    def execute(self, refresh_token: str) -> TokenPair:
        claims = self.tokens.decode_refresh(refresh_token)  # firma, exp y tipo
        stored = self.store.get(claims.jti)

        if stored is None:
            raise RevokedToken("Refresh token not found")

        if stored.user_id != claims.sub or stored.family_id != claims.family_id:
            raise MalformedToken("Refresh token does not match the stored session")

        if stored.revoked_at is not None:
            # Un token ya rotado que vuelve a llegar: alguien más lo tiene.
            self.store.revoke_family(claims.family_id)
            raise RefreshTokenReused("Refresh token reuse detected")

        user = self.user_repository.get_by_id(claims.sub)
        if user is None:
            self.store.revoke_family(claims.family_id)
            raise RevokedToken("Session is no longer valid")

        if not user.can_login:
            self.store.revoke_family(claims.family_id)
            if user.status is UserStatus.PENDING:
                raise AccountNotVerified("Email not verified")
            raise AccountDisabled("Account disabled")

        new_refresh = self.tokens.create_refresh(user.id, claims.family_id)

        # Atómico: si dos peticiones usan el mismo token a la vez, solo una gana.
        if not self.store.rotate(claims.jti, new_refresh.jti):
            self.store.revoke_family(claims.family_id)
            raise RefreshTokenReused("Refresh token reuse detected")

        self.store.save(new_refresh.jti, user.id, claims.family_id, new_refresh.expires_at)

        return TokenPair(
            access_token=self.tokens.create_access(user.id),
            refresh_token=new_refresh.token,
        )
