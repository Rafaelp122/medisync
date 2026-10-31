const DDDS_VALIDOS = new Set([
  "11",
  "12",
  "13",
  "14",
  "15",
  "16",
  "17",
  "18",
  "19",
  "21",
  "22",
  "24",
  "27",
  "28",
  "31",
  "32",
  "33",
  "34",
  "35",
  "37",
  "38",
  "41",
  "42",
  "43",
  "44",
  "45",
  "46",
  "47",
  "48",
  "49",
  "51",
  "53",
  "54",
  "55",
  "61",
  "62",
  "63",
  "64",
  "65",
  "66",
  "67",
  "68",
  "69",
  "71",
  "73",
  "74",
  "75",
  "77",
  "79",
  "81",
  "82",
  "83",
  "84",
  "85",
  "86",
  "87",
  "88",
  "89",
  "91",
  "92",
  "93",
  "94",
  "95",
  "96",
  "97",
  "98",
  "99",
]);

/**
 * Remove qualquer caractere que não seja dígito numérico.
 */
export function limparDigitos(valor: string): string {
  return valor.replace(/\D/g, "");
}

/**
 * Valida se a string informada representa um número de telefone celular brasileiro válido
 * com DDD oficial e o 9º dígito obrigatório (11 dígitos).
 */
export function validarTelefoneCelularBR(valor: string): boolean {
  if (!valor) return false;
  let digitos = limparDigitos(valor);
  if (digitos.startsWith("55") && digitos.length === 13) {
    digitos = digitos.slice(2);
  }
  if (digitos.length !== 11) {
    return false;
  }
  const ddd = digitos.slice(0, 2);
  if (!DDDS_VALIDOS.has(ddd)) {
    return false;
  }
  const nonoDigito = digitos[2];
  return nonoDigito === "9";
}

/**
 * Aplica máscara dinâmica progressiva de telefone celular brasileiro durante digitação.
 * Exemplo: (11) 98765-4321
 */
export function mascararTelefoneBR(valor: string): string {
  const digitos = limparDigitos(valor).slice(0, 11);
  if (digitos.length === 0) return "";
  if (digitos.length <= 2) return `(${digitos}`;
  if (digitos.length <= 6) return `(${digitos.slice(0, 2)}) ${digitos.slice(2)}`;
  if (digitos.length <= 10) {
    return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 6)}-${digitos.slice(6)}`;
  }
  return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 7)}-${digitos.slice(7)}`;
}

/**
 * Converte o número de telefone informado para o formato canônico internacional E.164 (+55...).
 */
export function formatarTelefoneE164(valor: string): string {
  const digitos = limparDigitos(valor);
  if (digitos.startsWith("55") && digitos.length === 13) {
    return `+${digitos}`;
  }
  return `+55${digitos}`;
}

/**
 * Valida CPF utilizando o algoritmo Módulo 11 (RFC mod-11).
 * Rejeita tamanhos inválidos e sequências com todos os dígitos iguais.
 */
export function validarCPF(valor: string): boolean {
  if (!valor) return false;
  const digitos = limparDigitos(valor);
  if (digitos.length !== 11) return false;
  if (new Set(digitos).size === 1) return false;

  const intDigits = Array.from(digitos).map(Number);

  // Primeiro dígito verificador
  const soma1 = intDigits.slice(0, 9).reduce((acc, d, i) => acc + d * (10 - i), 0);
  const resto1 = soma1 % 11;
  const dv1 = resto1 < 2 ? 0 : 11 - resto1;
  if (intDigits[9] !== dv1) return false;

  // Segundo dígito verificador
  const soma2 = intDigits.slice(0, 10).reduce((acc, d, i) => acc + d * (11 - i), 0);
  const resto2 = soma2 % 11;
  const dv2 = resto2 < 2 ? 0 : 11 - resto2;
  return intDigits[10] === dv2;
}

/**
 * Aplica máscara dinâmica progressiva de CPF durante digitação (000.000.000-00).
 */
export function mascararCPF(valor: string): string {
  const digitos = limparDigitos(valor).slice(0, 11);
  if (digitos.length <= 3) return digitos;
  if (digitos.length <= 6) return `${digitos.slice(0, 3)}.${digitos.slice(3)}`;
  if (digitos.length <= 9) {
    return `${digitos.slice(0, 3)}.${digitos.slice(3, 6)}.${digitos.slice(6)}`;
  }
  return `${digitos.slice(0, 3)}.${digitos.slice(3, 6)}.${digitos.slice(6, 9)}-${digitos.slice(9)}`;
}

/**
 * Valida Cartão Nacional de Saúde (CNS) padrão DATASUS (15 dígitos).
 * Suporta modelo definitivo (início 1 ou 2) e provisório (início 7, 8 ou 9).
 */
export function validarCNS(valor: string): boolean {
  if (!valor) return false;
  const digitos = limparDigitos(valor);
  if (digitos.length !== 15) return false;

  const primeiro = digitos[0];
  if (!["1", "2", "7", "8", "9"].includes(primeiro)) return false;

  const intDigits = Array.from(digitos).map(Number);

  if (["1", "2"].includes(primeiro)) {
    const soma = intDigits.slice(0, 11).reduce((acc, d, i) => acc + d * (15 - i), 0);
    const resto = soma % 11;
    let dv = resto === 0 ? 0 : 11 - resto;
    if (dv === 11) dv = 0;

    let esperado: number[];
    if (dv === 10) {
      const restoAlt = (soma + 2) % 11;
      let dvAlt = restoAlt === 0 ? 0 : 11 - restoAlt;
      if (dvAlt === 11) dvAlt = 0;
      esperado = [...intDigits.slice(0, 11), 0, 0, 1, dvAlt];
    } else {
      esperado = [...intDigits.slice(0, 11), 0, 0, 0, dv];
    }
    return intDigits.every((d, i) => d === esperado[i]);
  }

  // Provisório (7, 8, 9)
  const soma = intDigits.reduce((acc, d, i) => acc + d * (15 - i), 0);
  return soma % 11 === 0;
}

/**
 * Aplica máscara dinâmica progressiva de CNS durante digitação (000 0000 0000 0000).
 */
export function mascararCNS(valor: string): string {
  const digitos = limparDigitos(valor).slice(0, 15);
  if (digitos.length <= 3) return digitos;
  if (digitos.length <= 7) return `${digitos.slice(0, 3)} ${digitos.slice(3)}`;
  if (digitos.length <= 11) {
    return `${digitos.slice(0, 3)} ${digitos.slice(3, 7)} ${digitos.slice(7)}`;
  }
  return `${digitos.slice(0, 3)} ${digitos.slice(3, 7)} ${digitos.slice(7, 11)} ${digitos.slice(11)}`;
}

/**
 * Valida Código de Endereçamento Postal (CEP) de 8 dígitos, rejeitando sequência de zeros.
 */
export function validarCEP(valor: string): boolean {
  if (!valor) return false;
  const digitos = limparDigitos(valor);
  if (digitos.length !== 8) return false;
  if (digitos === "00000000") return false;
  return true;
}

/**
 * Aplica máscara dinâmica progressiva de CEP durante digitação (00000-000).
 */
export function mascararCEP(valor: string): string {
  const digitos = limparDigitos(valor).slice(0, 8);
  if (digitos.length <= 5) return digitos;
  return `${digitos.slice(0, 5)}-${digitos.slice(5)}`;
}

/**
 * Calcula o hash SHA-256 nativo de um texto usando a Web Crypto API do navegador.
 * Retorna string hexadecimal em minúsculas com 64 caracteres.
 */
export async function calcularHashTcle(texto: string): Promise<string> {
  const buffer = new TextEncoder().encode(texto);
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
