import stat

import pytest
from aishop.operator_auth import OperatorAuth, OperatorAuthenticationFailed


def test_generated_operator_token_is_private_and_stable(tmp_path, monkeypatch):
    monkeypatch.delenv("AISHOP_OPERATOR_TOKEN", raising=False)
    first = OperatorAuth.load(tmp_path)
    second = OperatorAuth.load(tmp_path)
    token = (tmp_path / "operator.token").read_text(encoding="utf-8").strip()
    first.verify(token)
    second.verify(token)
    assert stat.S_IMODE((tmp_path / "operator.token").stat().st_mode) == 0o600


def test_operator_auth_rejects_missing_or_wrong_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AISHOP_OPERATOR_TOKEN", "configured-secret")
    auth = OperatorAuth.load(tmp_path)
    with pytest.raises(OperatorAuthenticationFailed):
        auth.verify(None)
    with pytest.raises(OperatorAuthenticationFailed):
        auth.verify("wrong")
    auth.verify("configured-secret")
