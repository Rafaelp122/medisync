"""Positional formatter and validators for DATASUS/SIA BPA-I files (ADR-012, US-11)."""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from src.modules.ambulatory.domain.exceptions import (
    CompetenciaInvalidaError,
    ProducaoNaoEncontradaError,
)


def validar_competencia(competencia: str) -> str:
    """Valida e normaliza a competência SUS no formato YYYYMM (01 a 12).

    Regras: docs/explanation/domains/ambulatory-domain.md, US-11 e Portaria 3.232/2024.
    """
    comp_limpa = competencia.strip()
    if len(comp_limpa) != 6 or not comp_limpa.isdigit():
        raise CompetenciaInvalidaError(competencia)

    mes = int(comp_limpa[4:6])
    if mes < 1 or mes > 12:
        raise CompetenciaInvalidaError(competencia)

    return comp_limpa


def sanitizar_texto_ascii(texto: str) -> str:
    """Remove acentos e converte texto para ASCII em maiúsculas conforme DATASUS."""
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", texto)
    return normalizado.encode("ASCII", "ignore").decode("ASCII").upper()


def calcular_checksum_bpa(soma_controle: int) -> int:
    """Calcula o checksum verificador cbc-smt-vrf no intervalo fechado [1111..2221].

    Fórmula oficial DATASUS SIA-SUS: (soma_controle % 1111) + 1111.
    """
    return (soma_controle % 1111) + 1111


@dataclass(frozen=True)
class BpaHeaderData:
    """Dados agregados para composição do registro Header Tipo 01 do BPA-I."""

    competencia: str
    total_linhas: int
    total_folhas: int
    smt_vrf: int
    unidade_nome: str
    unidade_sigla: str
    cnpj: str
    destino: str
    destino_tipo: str = "M"
    versao: str = "03.01"


@dataclass(frozen=True)
class BpaItemData:
    """Dados atômicos de um procedimento para composição do registro Detalhe Tipo 03."""

    cnes: str
    competencia: str
    cns_medico: str
    cbo: str
    data_atendimento: str
    num_folha: int
    num_seq: int
    codigo_sigtap: str
    cns_paciente: str
    sexo: str
    ibge_municipio: str
    cid: str
    idade: int
    carater_atendimento: str
    paciente_nome: str
    data_nascimento: str
    raca: str = "99"


@dataclass(frozen=True)
class BpaRegistroDetalheDTO:
    """Visão desnormalizada de produção para composição do detalhe Tipo 03 do BPA-I."""

    producao_id: UUID
    atendimento_id: UUID
    profissional_id: UUID
    paciente_id: UUID
    cnes: str | None
    codigo_sigtap: str
    carater_atendimento: str
    competencia: str
    consolidado_em: datetime
    paciente_nome: str | None
    paciente_cns: str | None
    paciente_cpf: str | None
    paciente_data_nascimento: str | None  # AAAAMMDD
    paciente_sexo: str | None  # M ou F
    paciente_ibge: str | None
    medico_cns: str | None
    medico_cbo: str | None
    unidade_nome: str | None
    unidade_sigla: str | None
    unidade_cnpj: str | None
    cid: str | None = None
    idade: int | None = None


@dataclass(frozen=True)
class BpaPendenciaCadastral:
    """Pendência cadastral real detectada durante a compilação da remessa BPA-I."""

    producao_id: UUID
    atendimento_id: UUID
    campos_ausentes: tuple[str, ...]


@dataclass(frozen=True)
class BpaArquivoExportadoDTO:
    """DTO com o conteúdo magnético SIA-SUS, metadados e pendências da remessa."""

    conteudo: str
    nome_arquivo: str
    total_registros: int
    total_folhas: int
    competencia: str
    pendencias: tuple[BpaPendenciaCadastral, ...] = ()


def _detectar_pendencias_registro(registro: BpaRegistroDetalheDTO) -> tuple[str, ...]:
    """Identifica campos obrigatórios ausentes sem falsos positivos."""
    ausentes: list[str] = []
    cnes_limpo = (registro.cnes or "").strip()
    if not cnes_limpo or cnes_limpo == "0000000":
        ausentes.append("cnes")
    if not (registro.paciente_nome or "").strip():
        ausentes.append("paciente_nome")
    if not (registro.paciente_cns or "").replace("0", "").strip():
        ausentes.append("paciente_cns")
    if not (registro.paciente_data_nascimento or "").strip():
        ausentes.append("paciente_data_nascimento")
    if not (registro.paciente_sexo or "").strip():
        ausentes.append("paciente_sexo")
    if not (registro.paciente_ibge or "").strip():
        ausentes.append("paciente_ibge")
    if not (registro.medico_cns or "").replace("0", "").strip():
        ausentes.append("medico_cns")
    if not (registro.medico_cbo or "").strip():
        ausentes.append("medico_cbo")
    if not (registro.unidade_nome or "").strip():
        ausentes.append("unidade_nome")
    if not (registro.unidade_cnpj or "").replace("0", "").strip():
        ausentes.append("unidade_cnpj")
    return tuple(ausentes)


class BpaPositionalFormatter:
    """Formatador de colunas fixas para arquivos magnéticos BPA-I do SIA-SUS/DATASUS.

    Header (Tipo 01): exatamente 130 caracteres.
    Detalhe (Tipo 03): exatamente 152 caracteres.
    Regras: US-11 (Critérios de Aceite BPA-I) e Manuais SIA/DATASUS.
    """

    @staticmethod
    def formatar_header(data: BpaHeaderData) -> str:
        """Formata a linha de cabeçalho tipo 01 com exatamente 130 caracteres."""
        comp = data.competencia[:6].zfill(6)
        linhas = f"{data.total_linhas:06d}"
        folhas = f"{data.total_folhas:06d}"
        checksum = f"{data.smt_vrf:04d}"
        nome_unidade = f"{sanitizar_texto_ascii(data.unidade_nome)[:30]:<30}"
        sigla_unidade = f"{sanitizar_texto_ascii(data.unidade_sigla)[:6]:<6}"
        cnpj_limpo = f"{''.join(filter(str.isdigit, data.cnpj))[:14]:0>14}"
        destino = f"{sanitizar_texto_ascii(data.destino)[:40]:<40}"
        tipo_dest = data.destino_tipo[:1].upper() if data.destino_tipo else "M"
        versao = f"{data.versao[:10]:<10}"

        linha = (
            f"01#BPA#{comp}{linhas}{folhas}{checksum}"
            f"{nome_unidade}{sigla_unidade}{cnpj_limpo}{destino}{tipo_dest}{versao}"
        )
        if len(linha) != 130:
            raise ValueError(
                f"Header BPA com tamanho incorreto ({len(linha)} chars; esperado 130)."
            )
        return linha

    @staticmethod
    def formatar_detalhe(item: BpaItemData) -> str:
        """Formata a linha de detalhe individualizado tipo 03 com 152 caracteres."""
        cnes = f"{item.cnes[:7]:0>7}"
        comp = f"{item.competencia[:6]:0>6}"
        cns_med = f"{item.cns_medico[:15]:0>15}"
        cbo = f"{item.cbo[:6]:<6}"
        dt_aten = f"{item.data_atendimento[:8]:0>8}"
        folha = f"{item.num_folha:03d}"
        seq = f"{item.num_seq:02d}"
        sigtap_digitos = "".join(filter(str.isdigit, item.codigo_sigtap))
        pa = f"{sigtap_digitos[:10]:0>10}"
        cns_pac = f"{item.cns_paciente[:15]:0>15}"
        sexo = item.sexo[:1].upper() if item.sexo and item.sexo.strip() else " "
        ibge = f"{item.ibge_municipio[:6]:0>6}"
        cid = f"{sanitizar_texto_ascii(item.cid)[:4]:<4}"
        idade = f"{min(max(item.idade, 0), 999):03d}"
        qt = "000001"
        caten = f"{item.carater_atendimento[:2]:0>2}"
        naut = f"{'':<13}"
        origem = "BPA"
        nome_pac = f"{sanitizar_texto_ascii(item.paciente_nome)[:30]:<30}"
        dt_nasc = f"{item.data_nascimento[:8]:0>8}"
        raca = f"{item.raca[:2]:0>2}"

        linha = (
            f"03{cnes}{comp}{cns_med}{cbo}{dt_aten}{folha}{seq}{pa}{cns_pac}"
            f"{sexo}{ibge}{cid}{idade}{qt}{caten}{naut}{origem}{nome_pac}{dt_nasc}{raca}"
        )
        if len(linha) != 152:
            raise ValueError(
                f"Detalhe BPA com tamanho incorreto ({len(linha)} chars; esperado 152)."
            )
        return linha

    @classmethod
    def gerar_arquivo_bpa(
        cls,
        header: BpaHeaderData,
        itens: Sequence[BpaItemData],
    ) -> list[str]:
        """Gera o arquivo com paginação de 20 linhas por folha e checksum."""
        total_linhas = len(itens)
        total_folhas = (total_linhas + 19) // 20 if total_linhas > 0 else 1

        # Soma de controle para cálculo de checksum oficial:
        # soma(quantidade=1) + soma(código do procedimento numérico)
        soma_controle = 0
        itens_paginados: list[BpaItemData] = []
        for idx, item in enumerate(itens):
            folha = (idx // 20) + 1
            seq = (idx % 20) + 1
            sigtap_num = int("".join(filter(str.isdigit, item.codigo_sigtap)) or "0")
            soma_controle += 1 + sigtap_num
            itens_paginados.append(replace(item, num_folha=folha, num_seq=seq))

        smt_vrf = calcular_checksum_bpa(soma_controle)
        header_final = replace(
            header,
            total_linhas=total_linhas,
            total_folhas=total_folhas,
            smt_vrf=smt_vrf,
        )

        linhas: list[str] = [cls.formatar_header(header_final)]
        for item in itens_paginados:
            linhas.append(cls.formatar_detalhe(item))

        return linhas

    @classmethod
    def compilar_remessa(
        cls,
        competencia: str,
        registros: Sequence[BpaRegistroDetalheDTO],
        *,
        destino: str = "SECRETARIA MUNICIPAL DE SAUDE",
        destino_tipo: str = "M",
    ) -> BpaArquivoExportadoDTO:
        """Compila remessa BPA-I validando pendências reais, paginação e checksum.

        Regras: docs/explanation/domains/ambulatory-domain.md, US-11 e ADR-012.
        """
        comp_validada = validar_competencia(competencia)
        if not registros:
            raise ProducaoNaoEncontradaError(competencia=comp_validada)

        pendencias: list[BpaPendenciaCadastral] = []
        itens_formatados: list[BpaItemData] = []
        for r in registros:
            ausentes = _detectar_pendencias_registro(r)
            if ausentes:
                pendencias.append(
                    BpaPendenciaCadastral(
                        producao_id=r.producao_id,
                        atendimento_id=r.atendimento_id,
                        campos_ausentes=ausentes,
                    )
                )
            itens_formatados.append(
                BpaItemData(
                    cnes=r.cnes or "",
                    competencia=comp_validada,
                    cns_medico=r.medico_cns or "",
                    cbo=r.medico_cbo or "",
                    data_atendimento=r.consolidado_em.strftime("%Y%m%d"),
                    num_folha=0,
                    num_seq=0,
                    codigo_sigtap=r.codigo_sigtap,
                    cns_paciente=r.paciente_cns or "",
                    sexo=r.paciente_sexo or "",
                    ibge_municipio=r.paciente_ibge or "",
                    cid=r.cid or "",
                    idade=r.idade if r.idade is not None else 0,
                    carater_atendimento=r.carater_atendimento,
                    paciente_nome=r.paciente_nome or "",
                    data_nascimento=r.paciente_data_nascimento or "",
                )
            )

        primeiro = registros[0]
        total_registros = len(registros)
        total_folhas = (total_registros + 19) // 20
        header = BpaHeaderData(
            competencia=comp_validada,
            total_linhas=total_registros,
            total_folhas=total_folhas,
            smt_vrf=0,
            unidade_nome=primeiro.unidade_nome or "",
            unidade_sigla=primeiro.unidade_sigla or "MSYNC",
            cnpj=primeiro.unidade_cnpj or "",
            destino=destino,
            destino_tipo=destino_tipo,
            versao="03.01",
        )

        linhas = cls.gerar_arquivo_bpa(header, itens_formatados)
        conteudo = "\r\n".join(linhas) + "\r\n"
        cnes_arquivo = (
            primeiro.cnes.strip()
            if primeiro.cnes and primeiro.cnes.strip()
            else "0000000"
        )
        nome_arquivo = f"BPA_I_{comp_validada}_{cnes_arquivo}.txt"

        return BpaArquivoExportadoDTO(
            conteudo=conteudo,
            nome_arquivo=nome_arquivo,
            total_registros=total_registros,
            total_folhas=total_folhas,
            competencia=comp_validada,
            pendencias=tuple(pendencias),
        )
