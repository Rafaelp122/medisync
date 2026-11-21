"""Application service orchestrating passwordless and hybrid patient authentication."""

import asyncio
import hashlib
import json
import logging
import re
import secrets
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz.roles import Role
from src.core.errors import ConflictError, ValidationError
from src.core.privacy import mascarar_cns, mascarar_cpf, mascarar_telefone
from src.modules.auth.application.dtos import (
    IdentificarPacienteCommand,
    IdentificarPacienteOutputDTO,
    LoginPacienteSenhaCommand,
    MetodosAutenticacaoPacienteOutputDTO,
    RegistrarPacienteCommand,
    RegistrarPacienteOutputDTO,
    SolicitarOtpInput,
    SolicitarOtpOutputDTO,
    VerificarOtpInput,
    VerificarOtpOutputDTO,
)
from src.modules.auth.application.ports.active_attendance_lookup_port import (
    ActiveAttendanceLookupPort,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.challenge_store_port import (
    ChallengeStorePort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    IdentityReaderPort,
    PacienteAuthLookupDTO,
)
from src.modules.auth.application.ports.identity_writer_port import (
    IdentityWriterPort,
)
from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.application.ports.patient_credential_repository_port import (
    PatientCredentialRepositoryPort,
)
from src.modules.auth.application.ports.sms_sender_port import SmsSenderPort
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.domain.exceptions import (
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    IdentificacaoRateLimitExcedidoError,
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    OtpTentativasExcedidasError,
    PacienteNaoEncontradoError,
)
from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial
from src.modules.auth.domain.validators import (
    validate_cns,
    validate_cpf,
    validate_telefone,
)

logger = logging.getLogger("medisync.auth.patient_auth")

OTP_TTL_SECONDS = 300  # 5 minutes validity
OTP_RATE_LIMIT_WINDOW = 900  # 15 minutes window
OTP_MAX_REQUESTS_PER_WINDOW = 3
OTP_MAX_VERIFY_ATTEMPTS = 3
IDENTIFY_RATE_LIMIT_WINDOW = 900
IDENTIFY_MAX_REQUESTS_PER_IP = 15
IDENTIFY_MAX_REQUESTS_PER_IDENT = 10
CADSUS_MAX_REQUESTS_PER_IP = 10
REGISTER_RATE_LIMIT_WINDOW = 900
REGISTER_MAX_REQUESTS_PER_IP = 10
PASSWORD_MAX_FAILURES = 5
PASSWORD_LOCKOUT_MINUTES = 15
UNUSABLE_CREDENTIAL_MARKER = "!UNUSABLE:"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_pii_key(value: str) -> str:
    """Hash PII identifier into a non-reversible 16-char Valkey key suffix."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class PatientAuthService:
    """Autenticação híbrida de pacientes (OTP SMS, CADSUS/Gov.br, senha Argon2id).

    Regras: RN-AUT-02, RN-AUT-03, RN-AUT-04, RN-AUT-09, ADR-012, ADR-013, RF-01.
    Documentação: docs/explanation/domains/auth-domain.md e
    docs/adrs/ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md
    """

    def __init__(
        self,
        *,
        token_service: TokenServicePort,
        challenge_store: ChallengeStorePort,
        rate_limiter: AuthRateLimiterPort,
        identity_reader: IdentityReaderPort | None = None,
        sms_sender: SmsSenderPort | None = None,
        expose_debug_otp: bool = False,
        active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
        identity_writer: IdentityWriterPort | None = None,
        credential_repo: PatientCredentialRepositoryPort | None = None,
        password_hasher: PasswordHasherPort | None = None,
        govbr_oidc_enabled: bool = False,
        session: AsyncSession | None = None,
    ) -> None:
        self._token_service = token_service
        self._challenge_store = challenge_store
        self._rate_limiter = rate_limiter
        self._identity_reader = identity_reader
        self._sms_sender = sms_sender
        self._expose_debug_otp = expose_debug_otp
        self._active_attendance = active_attendance_lookup
        self._identity_writer = identity_writer
        self._credential_repo = credential_repo
        self._password_hasher = password_hasher
        self._govbr_oidc_enabled = govbr_oidc_enabled
        self._session = session

    async def _resolve_active_attendance(self, paciente_id: UUID) -> UUID | None:
        if self._active_attendance is None:
            return None
        return await self._active_attendance.buscar_atendimento_ativo_paciente(
            paciente_id=paciente_id,
        )

    def _issue_patient_token(
        self,
        paciente_id: UUID,
        atendimento_id: UUID | None = None,
    ) -> VerificarOtpOutputDTO:
        token_pair = self._token_service.gerar_tokens(
            usuario_id=paciente_id,
            papel=Role.PACIENTE.value,
        )
        return VerificarOtpOutputDTO(
            access_token=token_pair.access_token,
            token_type="bearer",  # noqa: S106
            expires_in=token_pair.expires_in,
            paciente_id=paciente_id,
            role=Role.PACIENTE.value,
            atendimento_id=atendimento_id,
        )

    async def _enforce_ip_rate_limit(
        self,
        *,
        namespace: str,
        client_ip: str,
        max_requests: int,
        window_seconds: int,
        action_label: str,
    ) -> None:
        clean_ip = client_ip.strip() or "127.0.0.1"
        res = await self._rate_limiter.verificar_e_incrementar(
            chave=f"{namespace}:ip:{clean_ip}",
            limite=max_requests,
            janela_segundos=window_seconds,
        )
        if not res.permitido:
            raise IdentificacaoRateLimitExcedidoError(
                f"Limite de solicitações de {action_label} excedido para "
                f"IP '{clean_ip}'. Tente novamente em {res.retry_after_segundos}s.",
                retry_after_segundos=res.retry_after_segundos,
            )

    async def _enforce_otp_rate_limit(self, clean_telefone: str) -> None:
        """Enforce maximum 3 OTP requests per 15-minute window using hashed PII."""
        phone_hash = _hash_pii_key(clean_telefone)
        res = await self._rate_limiter.verificar_e_incrementar(
            chave=f"otp:request:{phone_hash}",
            limite=OTP_MAX_REQUESTS_PER_WINDOW,
            janela_segundos=OTP_RATE_LIMIT_WINDOW,
        )
        if not res.permitido:
            tel_mask = mascarar_telefone(clean_telefone)
            raise OtpRateLimitExcedidoError(
                f"Limite de solicitações de OTP excedido para o telefone '{tel_mask}'. "
                f"Tente novamente em {res.retry_after_segundos}s.",
                retry_after_segundos=res.retry_after_segundos,
            )

    async def _emitir_otp_para_telefone(
        self,
        *,
        clean_telefone: str,
        clean_cpf: str | None,
    ) -> SolicitarOtpOutputDTO:
        reader = self._require_identity_reader()
        await self._enforce_otp_rate_limit(clean_telefone)

        paciente = await reader.buscar_paciente_por_telefone(
            telefone=clean_telefone,
            cpf=clean_cpf,
        )
        if paciente is None:
            return SolicitarOtpOutputDTO(
                mensagem="Código de verificação enviado com sucesso.",
                expira_em_segundos=OTP_TTL_SECONDS,
                codigo_debug=None,
            )

        codigo = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
        payload = json.dumps(
            {
                "code_hash": code_hash,
                "paciente_id": str(paciente.id),
                "attempts": 0,
            }
        )
        await self._challenge_store.store_one_time(
            key=f"otp:{clean_telefone}",
            value=payload,
            ttl_seconds=OTP_TTL_SECONDS,
        )

        if self._sms_sender is not None:
            await self._sms_sender.enviar_otp(clean_telefone, codigo)

        codigo_debug = codigo if self._expose_debug_otp else None
        return SolicitarOtpOutputDTO(
            mensagem="Código de verificação enviado com sucesso.",
            expira_em_segundos=OTP_TTL_SECONDS,
            codigo_debug=codigo_debug,
        )

    async def solicitar_otp(
        self,
        dados: SolicitarOtpInput,
    ) -> SolicitarOtpOutputDTO:
        """Emite código OTP de 6 dígitos com rate limiting por telefone (janela 15m).

        Regras: RN-AUT-03, RN-AUT-04, ADR-012, ADR-013, RF-01.
        Documentação: docs/explanation/domains/auth-domain.md
        """
        clean_telefone = validate_telefone(dados.telefone)
        clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None
        return await self._emitir_otp_para_telefone(
            clean_telefone=clean_telefone,
            clean_cpf=clean_cpf,
        )

    async def verificar_otp(
        self,
        dados: VerificarOtpInput,
    ) -> VerificarOtpOutputDTO:
        """Valida OTP atomicamente via ChallengeStorePort e emite JWT de paciente.

        Regras: RN-AUT-03, RN-AUT-04, ADR-012, ADR-013, RF-01.
        Documentação: docs/explanation/domains/auth-domain.md
        """
        clean_telefone = validate_telefone(dados.telefone)
        tel_mask = mascarar_telefone(clean_telefone)
        codigo = dados.codigo.strip()
        if len(codigo) != 6 or not codigo.isdigit():
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP '{codigo}' deve conter exatamente 6 dígitos numéricos."
            )

        input_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
        outcome = await self._challenge_store.verify_and_increment_otp(
            key=f"otp:{clean_telefone}",
            code_hash=input_hash,
            max_attempts=OTP_MAX_VERIFY_ATTEMPTS,
        )

        if outcome.status == "not_found":
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP incorreto ou expirado para o telefone '{tel_mask}'."
            )

        if outcome.status == "max_attempts":
            raise OtpTentativasExcedidasError(
                f"Número máximo de {OTP_MAX_VERIFY_ATTEMPTS} tentativas de "
                f"validação excedido para o telefone '{tel_mask}'. "
                f"Código invalidado; tente novamente em {OTP_RATE_LIMIT_WINDOW}s.",
                retry_after_segundos=OTP_RATE_LIMIT_WINDOW,
            )

        if outcome.status == "invalid":
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP incorreto para o telefone '{tel_mask}'. "
                f"Restam {outcome.tentativas_restantes} tentativa(s) antes do bloqueio."
            )

        if outcome.paciente_id is None:
            raise OtpInvalidoOuExpiradoError(
                f"Registro de OTP inconsistente sem paciente vinculado ('{tel_mask}')."
            )

        atendimento_id = await self._resolve_active_attendance(outcome.paciente_id)
        return self._issue_patient_token(outcome.paciente_id, atendimento_id)

    async def autenticar_cadsus_govbr(
        self,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
        nome_mae: str | None = None,
        *,
        client_ip: str = "127.0.0.1",
    ) -> VerificarOtpOutputDTO:
        """Autenticação sem senha via CADSUS/Gov.br com 2º fator civil e rate limit.

        Regras: RN-AUT-09, ADR-012, ADR-013, RF-01, CFM nº 2.314/2022 e
        docs/explanation/domains/auth-domain.md.
        """
        reader = self._require_identity_reader()
        await self._enforce_ip_rate_limit(
            namespace="cadsus",
            client_ip=client_ip,
            max_requests=CADSUS_MAX_REQUESTS_PER_IP,
            window_seconds=OTP_RATE_LIMIT_WINDOW,
            action_label="autenticação CADSUS",
        )

        if data_nascimento is None:
            raise ValidationError(
                "Data de nascimento é obrigatória para autenticação CADSUS/Gov.br "
                f"(recebido data_nascimento={data_nascimento!r})."
            )

        clean_cpf = validate_cpf(cpf) if cpf and cpf.strip() else None
        clean_cns = validate_cns(cns) if cns and cns.strip() else None

        if not clean_cpf and not clean_cns:
            raise ValidationError(
                f"Desambiguação CADSUS inválida (recebido cpf={cpf!r}, "
                f"cns={cns!r}); esperado ao menos CPF (11 dígitos) ou CNS "
                "(15 dígitos) válido para autenticação sem senha."
            )

        clean_nome_mae = nome_mae.strip() if nome_mae and nome_mae.strip() else None
        if clean_cpf and not clean_cns and clean_nome_mae is None:
            raise ValidationError(
                "Autenticação CADSUS por CPF exige também o nome completo da mãe "
                f"ou CNS como segundo fator civil (recebido nome_mae={nome_mae!r}, "
                f"cns={cns!r}; RN-AUT-09)."
            )

        paciente = await reader.buscar_paciente_cadsus(
            cpf=clean_cpf,
            data_nascimento=data_nascimento,
            cns=clean_cns,
            nome_mae=clean_nome_mae,
        )
        if paciente is None:
            cpf_masked = mascarar_cpf(clean_cpf) if clean_cpf else "N/A"
            cns_masked = mascarar_cns(clean_cns) if clean_cns else "N/A"
            raise PacienteNaoEncontradoError(
                "Paciente com dados civis informados "
                f"(CPF: {cpf_masked}, CNS: {cns_masked}) "
                "não encontrado na plataforma."
            )

        atendimento_id = await self._resolve_active_attendance(paciente.id)
        return self._issue_patient_token(paciente.id, atendimento_id)

    def _require_identity_reader(self) -> IdentityReaderPort:
        if self._identity_reader is None:
            raise ValueError(
                f"IdentityReaderPort não configurado no PatientAuthService "
                f"(recebido: {self._identity_reader!r}; esperado instância de "
                "IdentityReaderPort)."
            )
        return self._identity_reader

    def _require_identity_writer(self) -> IdentityWriterPort:
        if self._identity_writer is None:
            raise ValueError(
                f"IdentityWriterPort não configurado no PatientAuthService "
                f"(recebido: {self._identity_writer!r}; esperado instância de "
                "IdentityWriterPort)."
            )
        return self._identity_writer

    def _require_credential_repo(self) -> PatientCredentialRepositoryPort:
        if self._credential_repo is None:
            raise ValueError(
                "PatientCredentialRepositoryPort não configurado no "
                f"PatientAuthService (recebido: {self._credential_repo!r}; "
                "esperado repositório de credenciais)."
            )
        return self._credential_repo

    def _require_password_hasher(self) -> PasswordHasherPort:
        if self._password_hasher is None:
            raise ValueError(
                f"PasswordHasherPort não configurado no PatientAuthService "
                f"(recebido: {self._password_hasher!r}; esperado instância de "
                "PasswordHasherPort)."
            )
        return self._password_hasher

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise ValueError(
                f"AsyncSession não configurada no PatientAuthService "
                f"(recebido: {self._session!r}; esperado instância de AsyncSession)."
            )
        return self._session

    def _validate_registration_payload(
        self, dados: RegistrarPacienteCommand
    ) -> tuple[str, str, str, str, str | None]:
        if not dados.aceite_privacidade:
            raise ValidationError(
                "Aceite da política de privacidade (LGPD) é obrigatório "
                f"(recebido aceite_privacidade={dados.aceite_privacidade!r}; "
                "esperado True)."
            )

        clean_cpf = validate_cpf(dados.cpf)
        clean_telefone = validate_telefone(dados.telefone)
        clean_nome = dados.nome_completo.strip()
        if len(clean_nome) < 2:
            raise ValidationError(
                f"Nome completo '{clean_nome}' inválido ({len(clean_nome)} chars); "
                "esperado ao menos 2 caracteres."
            )

        if dados.data_nascimento > date.today():
            raise ValidationError(
                f"Data de nascimento '{dados.data_nascimento}' não pode ser futura "
                f"(hoje: {date.today()})."
            )

        clean_email = dados.email.strip().lower()
        if not clean_email or not _EMAIL_RE.match(clean_email):
            raise ValidationError(
                f"E-mail '{clean_email}' inválido; esperado formato 'usuario@dominio'."
            )

        clean_senha = dados.senha
        if clean_senha is not None and len(clean_senha.strip()) < 8:
            raise ValidationError(
                f"Senha informada possui {len(clean_senha.strip())} caractere(s); "
                "esperado mínimo de 8 caracteres."
            )

        return clean_cpf, clean_telefone, clean_nome, clean_email, clean_senha

    async def _validate_and_build_credential_spec(
        self,
        *,
        clean_email: str,
        clean_senha: str | None,
    ) -> tuple[str, str]:
        cred_repo = self._require_credential_repo()
        if await cred_repo.existe_identificador(clean_email):
            if clean_senha is not None:
                hasher = self._require_password_hasher()
                await asyncio.to_thread(hasher.dummy_verify)
            logger.warning("Conflito de identificador no cadastro de paciente.")
            raise ConflictError(
                "Não foi possível concluir o cadastro com os dados informados. "
                "Caso já possua conta, utilize a opção Entrar."
            )

        if clean_senha is None:
            return clean_email, f"{UNUSABLE_CREDENTIAL_MARKER}{secrets.token_hex(16)}"

        hasher = self._require_password_hasher()
        senha_hash = await asyncio.to_thread(hasher.hash, clean_senha)
        return clean_email, senha_hash

    async def _dispatch_initial_otp(
        self, clean_telefone: str, clean_cpf: str
    ) -> tuple[bool, int, str | None]:
        try:
            otp_out = await self._emitir_otp_para_telefone(
                clean_telefone=clean_telefone,
                clean_cpf=clean_cpf,
            )
            return True, otp_out.expira_em_segundos, otp_out.codigo_debug
        except OtpRateLimitExcedidoError:
            return False, OTP_TTL_SECONDS, None

    async def registrar_paciente(
        self,
        command: RegistrarPacienteCommand,
    ) -> RegistrarPacienteOutputDTO:
        """Registra novo paciente (cidadão) com e-mail obrigatório e envia OTP inicial.

        Regras: RN-AUT-09, ADR-012, ADR-013, RF-01, LGPD Art. 11 e
        docs/explanation/domains/auth-domain.md.
        """
        session = self._require_session()
        writer = self._require_identity_writer()
        cred_repo = self._require_credential_repo()

        await self._enforce_ip_rate_limit(
            namespace="patient_reg",
            client_ip=command.client_ip,
            max_requests=REGISTER_MAX_REQUESTS_PER_IP,
            window_seconds=REGISTER_RATE_LIMIT_WINDOW,
            action_label="cadastro",
        )

        (
            clean_cpf,
            clean_telefone,
            clean_nome,
            clean_email,
            clean_senha,
        ) = self._validate_registration_payload(command)

        identificador, senha_hash = await self._validate_and_build_credential_spec(
            clean_email=clean_email,
            clean_senha=clean_senha,
        )

        paciente = await writer.criar_paciente(
            cpf=clean_cpf,
            nome_completo=clean_nome,
            data_nascimento=command.data_nascimento,
            telefone=clean_telefone,
        )

        await cred_repo.criar_credencial(
            UsuarioCredencial(
                usuario_id=paciente.id,
                identificador=identificador,
                senha_hash=senha_hash,
                papel=Role.PACIENTE.value,
                ativo=True,
                mfa_ativo=False,
            )
        )

        await session.commit()

        otp_enviado, expira_em, codigo_debug = await self._dispatch_initial_otp(
            clean_telefone=clean_telefone,
            clean_cpf=clean_cpf,
        )
        return RegistrarPacienteOutputDTO(
            paciente_id=paciente.id,
            telefone_mascarado=mascarar_telefone(clean_telefone),
            otp_enviado=otp_enviado,
            expira_em_segundos=expira_em,
            codigo_debug=codigo_debug,
        )

    async def _enforce_identify_rate_limit(
        self,
        client_ip: str,
        normalized_ident: str,
    ) -> None:
        ident_hash = _hash_pii_key(normalized_ident)
        checks = (
            (
                f"identify:ip:{client_ip}",
                IDENTIFY_MAX_REQUESTS_PER_IP,
            ),
            (
                f"identify:id:{ident_hash}",
                IDENTIFY_MAX_REQUESTS_PER_IDENT,
            ),
        )
        for key, max_req in checks:
            res = await self._rate_limiter.verificar_e_incrementar(
                chave=key,
                limite=max_req,
                janela_segundos=IDENTIFY_RATE_LIMIT_WINDOW,
            )
            if not res.permitido:
                raise IdentificacaoRateLimitExcedidoError(
                    f"Limite de solicitações de identificação excedido para "
                    f"IP '{client_ip}'. Tente novamente em "
                    f"{res.retry_after_segundos}s.",
                    retry_after_segundos=res.retry_after_segundos,
                )

    def _parse_patient_identifier(
        self, raw_identificador: str
    ) -> tuple[str | None, str | None]:
        cleaned = raw_identificador.strip()
        if "@" in cleaned:
            email_lower = cleaned.lower()
            if not _EMAIL_RE.match(email_lower):
                raise ValidationError(
                    f"Identificador de e-mail '{email_lower}' inválido; "
                    "esperado formato 'usuario@dominio'."
                )
            return None, email_lower

        digits = re.sub(r"\D", "", cleaned)
        if len(digits) == 11:
            return digits, None

        raise ValidationError(
            f"Identificador '{cleaned}' inválido; esperado CPF (11 dígitos) "
            "ou endereço de e-mail válido."
        )

    async def _resolve_patient_and_credential(
        self,
        clean_cpf: str | None,
        clean_email: str | None,
    ) -> tuple[PacienteAuthLookupDTO | None, UsuarioCredencial | None]:
        reader = self._require_identity_reader()
        if clean_cpf is not None:
            paciente = await reader.buscar_paciente_cadsus(cpf=clean_cpf)
            cred = None
            if paciente is not None and self._credential_repo is not None:
                cred = await self._credential_repo.buscar_por_usuario_id(
                    paciente.id, Role.PACIENTE.value
                )
            return paciente, cred

        if clean_email is None or self._credential_repo is None:
            return None, None

        cred = await self._credential_repo.buscar_por_identificador(
            clean_email, Role.PACIENTE.value
        )
        if cred is None:
            return None, None
        paciente = await reader.buscar_paciente_por_id(cred.usuario_id)
        return paciente, cred

    async def _collect_patient_methods(
        self,
        paciente: PacienteAuthLookupDTO,
        cred: UsuarioCredencial | None,
    ) -> list[Literal["otp", "senha", "passkey", "govbr"]]:
        reader = self._require_identity_reader()
        metodos: list[Literal["otp", "senha", "passkey", "govbr"]] = []
        if paciente.telefone:
            metodos.append("otp")
        if (
            cred is not None
            and cred.ativo
            and not cred.senha_hash.startswith(UNUSABLE_CREDENTIAL_MARKER)
        ):
            metodos.append("senha")
        passkeys = await reader.listar_passkeys_paciente(paciente.id)
        if passkeys:
            metodos.append("passkey")
        if self._govbr_oidc_enabled:
            metodos.append("govbr")
        return metodos

    async def identificar_paciente(
        self,
        command: IdentificarPacienteCommand,
    ) -> IdentificarPacienteOutputDTO:
        """Identifica métodos de autenticação disponíveis sem vazar PII ou enumeração.

        Regras: RN-AUT-09 (Anti-Enumeração), ADR-012, ADR-013, RF-01 e
        docs/explanation/domains/auth-domain.md.
        """
        _ = self._require_identity_reader()
        clean_cpf, clean_email = self._parse_patient_identifier(command.identificador)
        normalized_key = clean_cpf if clean_cpf is not None else str(clean_email)

        await self._enforce_identify_rate_limit(command.client_ip, normalized_key)

        paciente, cred = await self._resolve_patient_and_credential(
            clean_cpf, clean_email
        )
        if paciente is None:
            metodos_absent: list[Literal["otp", "senha", "passkey", "govbr"]] = (
                ["govbr"] if self._govbr_oidc_enabled else []
            )
            return IdentificarPacienteOutputDTO(
                possui_conta=False,
                metodos_disponiveis=metodos_absent,
                telefone_mascarado=None,
                govbr_habilitado=self._govbr_oidc_enabled,
            )

        metodos = await self._collect_patient_methods(paciente, cred)
        tel_mask = mascarar_telefone(paciente.telefone) if paciente.telefone else None
        return IdentificarPacienteOutputDTO(
            possui_conta=True,
            metodos_disponiveis=metodos,
            telefone_mascarado=tel_mask,
            govbr_habilitado=self._govbr_oidc_enabled,
        )

    async def _resolve_credential_for_password_login(
        self, raw_identificador: str
    ) -> UsuarioCredencial | None:
        cred_repo = self._require_credential_repo()
        cleaned = raw_identificador.strip()
        if "@" in cleaned:
            return await cred_repo.buscar_por_identificador(
                cleaned.lower(), Role.PACIENTE.value
            )

        clean_cpf = validate_cpf(cleaned)
        if self._identity_reader is None:
            return None

        paciente = await self._identity_reader.buscar_paciente_cadsus(cpf=clean_cpf)
        if paciente is None:
            return None
        return await cred_repo.buscar_por_usuario_id(paciente.id, Role.PACIENTE.value)

    async def _verify_patient_password_or_lockout(
        self, cred: UsuarioCredencial, senha: str
    ) -> Literal["ok", "invalid", "locked"]:
        hasher = self._require_password_hasher()
        is_valida = await asyncio.to_thread(hasher.verify, senha, cred.senha_hash)
        if is_valida:
            cred.registrar_sucesso_login()
            if hasher.needs_rehash(cred.senha_hash):
                novo_hash = await asyncio.to_thread(hasher.hash, senha)
                cred.atualizar_senha(novo_hash)
            return "ok"

        recem_bloqueado = cred.registrar_falha_login(
            max_falhas=PASSWORD_MAX_FAILURES,
            minutos_bloqueio=PASSWORD_LOCKOUT_MINUTES,
        )
        return "locked" if recem_bloqueado else "invalid"

    async def autenticar_paciente_senha(
        self,
        command: LoginPacienteSenhaCommand,
    ) -> VerificarOtpOutputDTO:
        """Autentica paciente via senha Argon2id com lockout sem exigir MFA TOTP.

        Regras: RN-AUT-02 (Lockout), RN-AUT-09, ADR-012, ADR-013, RF-01 e
        docs/explanation/domains/auth-domain.md.
        """
        session = self._require_session()
        _ = self._require_credential_repo()
        hasher = self._require_password_hasher()

        await self._enforce_ip_rate_limit(
            namespace="patient_pwd",
            client_ip=command.client_ip,
            max_requests=PASSWORD_MAX_FAILURES * 3,
            window_seconds=OTP_RATE_LIMIT_WINDOW,
            action_label="autenticação",
        )

        cred = await self._resolve_credential_for_password_login(command.identificador)
        if cred is None or cred.senha_hash.startswith(UNUSABLE_CREDENTIAL_MARKER):
            await asyncio.to_thread(hasher.dummy_verify)
            raise CredenciaisInvalidasError()

        if not cred.ativo:
            await asyncio.to_thread(hasher.dummy_verify)
            raise ContaDesativadaError()

        if cred.is_bloqueado():
            await asyncio.to_thread(hasher.dummy_verify)
            raise ContaBloqueadaError()

        outcome = await self._verify_patient_password_or_lockout(cred, command.senha)
        await session.commit()
        if outcome == "locked":
            raise ContaBloqueadaError()
        if outcome == "invalid":
            raise CredenciaisInvalidasError()

        paciente_id = cred.usuario_id
        atendimento_id = await self._resolve_active_attendance(paciente_id)
        return self._issue_patient_token(paciente_id, atendimento_id)

    def obter_capacidades_metodos(self) -> MetodosAutenticacaoPacienteOutputDTO:
        """Retorna capacidades habilitadas de login do paciente conforme settings.

        Regras: ADR-009 (Configurações Desacopladas), RF-01 e
        docs/explanation/domains/auth-domain.md.
        """
        return MetodosAutenticacaoPacienteOutputDTO(
            govbr_oidc_enabled=self._govbr_oidc_enabled,
            passkeys_enabled=True,
            otp_enabled=True,
            password_fallback_enabled=True,
        )
