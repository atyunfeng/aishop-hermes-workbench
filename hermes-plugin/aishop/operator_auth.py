import hmac
import os
import secrets
from pathlib import Path


class OperatorAuthenticationFailed(PermissionError):
    pass


class OperatorAuth:
    TOKEN_FILE = "operator.token"

    def __init__(self, token: str, token_path: Path | None = None):
        self._token = token
        self.token_path = token_path

    @classmethod
    def load(cls, data_dir: Path) -> "OperatorAuth":
        configured = os.getenv("AISHOP_OPERATOR_TOKEN", "").strip()
        if configured:
            return cls(configured)

        data_dir.mkdir(parents=True, exist_ok=True)
        token_path = data_dir / cls.TOKEN_FILE
        if token_path.exists():
            token = token_path.read_text(encoding="utf-8").strip()
            if len(token) < 32:
                raise OperatorAuthenticationFailed("operator token file is invalid")
        else:
            token = secrets.token_urlsafe(32)
            descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(token)
                stream.write("\n")
        if os.name != "nt":
            os.chmod(token_path, 0o600)
        return cls(token, token_path)

    def verify(self, presented: str | None) -> None:
        if presented is None or not hmac.compare_digest(presented, self._token):
            raise OperatorAuthenticationFailed("valid operator token is required")

