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
