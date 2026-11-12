"""Positional formatter and validators for DATASUS/SIA BPA-I files (ADR-012, US-11)."""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace

from src.modules.ambulatory.domain.exceptions import CompetenciaInvalidaError


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
    org_nome: str
    org_sigla: str
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
        nome_org = f"{sanitizar_texto_ascii(data.org_nome)[:30]:<30}"
        sigla_org = f"{sanitizar_texto_ascii(data.org_sigla)[:6]:<6}"
        cnpj_limpo = f"{''.join(filter(str.isdigit, data.cnpj))[:14]:0>14}"
        destino = f"{sanitizar_texto_ascii(data.destino)[:40]:<40}"
        tipo_dest = data.destino_tipo[:1].upper() if data.destino_tipo else "M"
        versao = f"{data.versao[:10]:<10}"

        linha = (
            f"01#BPA#{comp}{linhas}{folhas}{checksum}"
            f"{nome_org}{sigla_org}{cnpj_limpo}{destino}{tipo_dest}{versao}"
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
        sexo = item.sexo[:1].upper() if item.sexo else "M"
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
