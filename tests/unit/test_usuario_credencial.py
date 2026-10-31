"""Unit tests for UsuarioCredencial domain entity (lockout and rate limiting)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.auth.domain.models import UsuarioCredencial


def test_usuario_credencial_creation_and_defaults() -> None:
    user_id = uuid7()
    cred = UsuarioCredencial(
        organizacao_id=1,
        usuario_id=user_id,
        identificador="MEDICO@HOSPITAL.COM",
        senha_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        papel="medico",
    )

    assert isinstance(cred.id, UUID)
    assert cred.organizacao_id == 1
    assert cred.usuario_id == user_id
    assert cred.identificador == "medico@hospital.com"
    assert cred.papel == "MEDICO"
    assert cred.ativo is True
    assert cred.falhas_login_consecutivas == 0
    assert cred.bloqueado_ate is None
    assert cred.is_bloqueado() is False


def test_usuario_credencial_lockout_after_max_failures() -> None:
    now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
    cred = UsuarioCredencial(
        organizacao_id=1,
        usuario_id=uuid7(),
        identificador="admin@hospital.com",
        senha_hash="hash",
        papel="ADMIN_GLOBAL",
    )

    # 4 falhas consecutivas: não bloqueia
    for i in range(1, 5):
        blocked = cred.registrar_falha_login(
            max_falhas=5, minutos_bloqueio=15, agora=now
        )
        assert blocked is False
        assert cred.falhas_login_consecutivas == i
        assert cred.is_bloqueado(agora=now) is False

    # 5ª falha: atinge limiar e bloqueia por 15 minutos
    blocked = cred.registrar_falha_login(max_falhas=5, minutos_bloqueio=15, agora=now)
    assert blocked is True
    assert cred.falhas_login_consecutivas == 5
    assert cred.bloqueado_ate == now + timedelta(minutes=15)
    assert cred.is_bloqueado(agora=now) is True

    # 10 minutos depois: ainda bloqueado
    assert cred.is_bloqueado(agora=now + timedelta(minutes=10)) is True

    # 15 minutos e 1 segundo depois: auto-reset desbloqueia e limpa falhas
    assert cred.is_bloqueado(agora=now + timedelta(minutes=15, seconds=1)) is False
    assert cred.bloqueado_ate is None
    assert cred.falhas_login_consecutivas == 0


def test_usuario_credencial_sucesso_limpa_falhas() -> None:
    now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
    cred = UsuarioCredencial(
        organizacao_id=1,
        usuario_id=uuid7(),
        identificador="user@hospital.com",
        senha_hash="hash",
        papel="GESTOR_UNIDADE",
    )

    cred.registrar_falha_login(agora=now)
    cred.registrar_falha_login(agora=now)
    assert cred.falhas_login_consecutivas == 2

    cred.registrar_sucesso_login(agora=now + timedelta(minutes=1))
    assert cred.falhas_login_consecutivas == 0
    assert cred.bloqueado_ate is None
    assert cred.is_bloqueado(agora=now + timedelta(minutes=1)) is False


def test_usuario_credencial_atualizar_senha() -> None:
    cred = UsuarioCredencial(
        organizacao_id=1,
        usuario_id=uuid7(),
        identificador="medico@hospital.com",
        senha_hash="old_hash",
        papel="MEDICO",
    )
    assert cred.senha_hash == "old_hash"

    cred.atualizar_senha("new_argon2id_hash")
    assert cred.senha_hash == "new_argon2id_hash"
