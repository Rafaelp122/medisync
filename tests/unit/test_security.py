from src.core.security import hash_password, verify_password


def test_hash_password_generates_argon2id():
    pwd = "SecretPassword123!"
    h = hash_password(pwd)
    assert isinstance(h, str)
    assert h.startswith("$argon2id$")
    assert verify_password(pwd, h)
    assert not verify_password("WrongPassword", h)


def test_verify_password_invalid_hash():
    assert not verify_password("password", "invalid-hash-string")
    assert not verify_password("password", "")
