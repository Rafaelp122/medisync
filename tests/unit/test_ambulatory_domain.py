"""Unit tests for SUS ambulatory domain: competence and BPA-I formatting."""

import pytest
from src.modules.ambulatory.domain.bpa_formatter import (
    BpaHeaderData,
    BpaItemData,
    BpaPositionalFormatter,
    calcular_checksum_bpa,
    sanitizar_texto_ascii,
    validar_competencia,
)
from src.modules.ambulatory.domain.exceptions import (
    CompetenciaInvalidaError,
    ProducaoNaoEncontradaError,
)


class TestCompetenceValidation:
    """Validações de competência no formato YYYYMM."""

    def test_validar_competencia_valida(self) -> None:
        assert validar_competencia("202611") == "202611"
        assert validar_competencia("202601") == "202601"
        assert validar_competencia("202612") == "202612"

    @pytest.mark.parametrize(
        "comp_invalida",
        ["202600", "202613", "202699", "2026-11", "20261", "ABCDEF", ""],
    )
    def test_validar_competencia_invalida_lanca_excecao(
        self, comp_invalida: str
    ) -> None:
        with pytest.raises(CompetenciaInvalidaError) as exc_info:
            validar_competencia(comp_invalida)
        assert comp_invalida in str(exc_info.value)
        assert "esperado formato 'YYYYMM'" in str(exc_info.value)


class TestSanitizeAscii:
    """Normalização e sanitização para texto ASCII em maiúsculas sem diacríticos."""

    def test_sanitizar_texto_ascii_com_acentos_e_cedilha(self) -> None:
        entrada = "João da Conceição & Araújo"
        esperado = "JOAO DA CONCEICAO & ARAUJO"
        assert sanitizar_texto_ascii(entrada) == esperado

    def test_sanitizar_texto_vazio(self) -> None:
        assert sanitizar_texto_ascii("") == ""


class TestChecksumBpa:
    """Verificação da fórmula cbc-smt-vrf no intervalo fechado [1111..2221]."""

    @pytest.mark.parametrize("soma", [0, 1, 10, 1110, 1111, 1112, 5000, 999999])
    def test_checksum_bpa_intervalo_estrito(self, soma: int) -> None:
        resultado = calcular_checksum_bpa(soma)
        assert 1111 <= resultado <= 2221
        assert resultado == (soma % 1111) + 1111


class TestBpaPositionalFormatter:
    """Formatação posicional rígida de registros Header (01) e Detalhe (03) do BPA-I."""

    def test_formatar_header_bpa_tamanho_e_posicoes(self) -> None:
        header_data = BpaHeaderData(
            competencia="202611",
            total_linhas=1,
            total_folhas=1,
            smt_vrf=1112,
            org_nome="UPA DIGITAL CONSORCIO INTERMUNICIPAL",
            org_sigla="MSYNC",
            cnpj="12345678000199",
            destino="SECRETARIA MUNICIPAL DE SAUDE",
            destino_tipo="M",
            versao="03.01",
        )
        linha = BpaPositionalFormatter.formatar_header(header_data)

        # Regra do DATASUS: exatos 130 caracteres na linha do header
        assert len(linha) == 130
        assert linha[0:2] == "01"
        assert linha[2:7] == "#BPA#"
        assert linha[7:13] == "202611"
        assert linha[13:19] == "000001"
        assert linha[19:25] == "000001"
        assert linha[25:29] == "1112"
        assert (
            linha[29:59] == "UPA DIGITAL CONSORCIO INTERMUN"
        )  # truncado a 30 caracteres
        assert linha[59:65] == "MSYNC "
        assert linha[65:79] == "12345678000199"
        assert linha[79:119] == "SECRETARIA MUNICIPAL DE SAUDE           "
        assert linha[119:120] == "M"
        assert linha[120:130] == "03.01     "

    def test_formatar_detalhe_bpa_tamanho_e_posicoes(self) -> None:
        item = BpaItemData(
            cnes="2000001",
            competencia="202611",
            cns_medico="700000000000001",
            cbo="225125",
            data_atendimento="20261110",
            num_folha=1,
            num_seq=1,
            codigo_sigtap="03.01.01.025-0",
            cns_paciente="700000000000002",
            sexo="M",
            ibge_municipio="355030",
            cid="R509",
            idade=35,
            carater_atendimento="02",
            paciente_nome="SILVA, JOAO",
            data_nascimento="19910515",
            raca="99",
        )
        linha = BpaPositionalFormatter.formatar_detalhe(item)

        # Regra do DATASUS: exatos 152 caracteres na linha do detalhe
        assert len(linha) == 152
        assert linha[0:2] == "03"
        assert linha[2:9] == "2000001"
        assert linha[9:15] == "202611"
        assert linha[15:30] == "700000000000001"
        assert linha[30:36] == "225125"
        assert linha[36:44] == "20261110"
        assert linha[44:47] == "001"
        assert linha[47:49] == "01"
        assert (
            linha[49:59] == "0301010250"
        )  # SIGTAP desmascarado com 10 dígitos numéricos
        assert linha[59:74] == "700000000000002"
        assert linha[74:75] == "M"
        assert linha[75:81] == "355030"
        assert linha[81:85] == "R509"
        assert linha[85:88] == "035"
        assert linha[88:94] == "000001"  # Quantidade
        assert linha[94:96] == "02"  # Caráter de urgência
        assert linha[96:109] == " " * 13  # Número de autorização em branco
        assert linha[109:112] == "BPA"
        assert linha[112:142] == f"{'SILVA, JOAO':<30}"
        assert linha[142:150] == "19910515"
        assert linha[150:152] == "99"

    def test_gerar_lote_completo_com_paginacao_de_folhas(self) -> None:
        itens: list[BpaItemData] = []
        for i in range(1, 26):
            itens.append(
                BpaItemData(
                    cnes="2000001",
                    competencia="202611",
                    cns_medico="700000000000001",
                    cbo="225125",
                    data_atendimento="20261110",
                    num_folha=0,
                    num_seq=0,
                    codigo_sigtap="03.01.01.025-0",
                    cns_paciente=f"700000000000{i:03d}",
                    sexo="F",
                    ibge_municipio="355030",
                    cid="",
                    idade=28,
                    carater_atendimento="02",
                    paciente_nome=f"PACIENTE {i}",
                    data_nascimento="19980101",
                    raca="99",
                )
            )

        header_base = BpaHeaderData(
            competencia="202611",
            total_linhas=0,
            total_folhas=0,
            smt_vrf=0,
            org_nome="UPA DIGITAL CONSORCIO",
            org_sigla="MSYNC",
            cnpj="12345678000199",
            destino="SECRETARIA MUNICIPAL DE SAUDE",
            destino_tipo="M",
            versao="03.01",
        )

        linhas_arquivo = BpaPositionalFormatter.gerar_arquivo_bpa(header_base, itens)

        # 1 linha de header + 25 linhas de detalhes = 26 linhas
        assert len(linhas_arquivo) == 26
        header_linha = linhas_arquivo[0]
        assert header_linha.startswith("01#BPA#202611")
        assert header_linha[13:19] == "000025"  # total linhas
        assert (
            header_linha[19:25] == "000002"
        )  # total folhas (20 na folha 1, 5 na folha 2)

        # Checa folha e sequencial do item 1 (linha 1 do arquivo)
        item_1_linha = linhas_arquivo[1]
        assert item_1_linha[44:47] == "001"  # folha 1
        assert item_1_linha[47:49] == "01"  # seq 01

        # Checa folha e sequencial do item 20 (linha 20 do arquivo)
        item_20_linha = linhas_arquivo[20]
        assert item_20_linha[44:47] == "001"  # folha 1
        assert item_20_linha[47:49] == "20"  # seq 20

        # Checa folha e sequencial do item 21 (linha 21 do arquivo)
        item_21_linha = linhas_arquivo[21]
        assert item_21_linha[44:47] == "002"  # folha 2
        assert item_21_linha[47:49] == "01"  # seq 01 reiniciado

        # Checa folha e sequencial do item 25 (linha 25 do arquivo)
        item_25_linha = linhas_arquivo[25]
        assert item_25_linha[44:47] == "002"  # folha 2
        assert item_25_linha[47:49] == "05"  # seq 05


class TestDomainExceptions:
    """Validações das exceções de domínio com offending value."""

    def test_competencia_invalida_error_mensage(self) -> None:
        err = CompetenciaInvalidaError("202699")
        assert "202699" in str(err)
        assert err.competencia == "202699"

    def test_producao_nao_encontrada_error_mensagem(self) -> None:
        err = ProducaoNaoEncontradaError(competencia="202611", organizacao_id=12)
        assert "202611" in str(err)
        assert "12" in str(err)
        assert err.competencia == "202611"
        assert err.organizacao_id == 12
