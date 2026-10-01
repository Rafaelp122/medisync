import uuid

import pytest
from src.core.uuid7 import is_valid_uuid, uuid7, uuid7_str


def test_uuid7_generation():
    u = uuid7()
    assert isinstance(u, uuid.UUID)
    assert u.version == 7
    assert u.variant == uuid.RFC_4122


def test_uuid7_str_format():
    s = uuid7_str()
    assert isinstance(s, str)
    assert len(s) == 36
    assert is_valid_uuid(s)


def test_is_valid_uuid():
    assert is_valid_uuid(str(uuid.uuid4()))
    assert is_valid_uuid(uuid7_str())
    assert not is_valid_uuid("not-a-uuid")
    assert not is_valid_uuid("")


def test_uuid7_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.core.uuid7 as uuid7_module

    # Force fallback branch by deleting or setting uuid7 attribute to None
    monkeypatch.delattr(uuid, "uuid7", raising=False)
    u = uuid7_module.uuid7()
    assert isinstance(u, uuid.UUID)
    assert u.version == 7
    assert u.variant == uuid.RFC_4122
