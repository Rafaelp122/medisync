import type { BadgeProps } from "@/components/ui/badge";

/**
 * Fuso horário canônico para exibição consistente de slots, consultas e carimbos
 * clínicos entre `/agendar`, `/historico`, `/receitas`, `/validar` e `/medico`.
 */
const CANONICAL_TIMEZONE = "UTC";

const timeFormatter = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: CANONICAL_TIMEZONE,
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: CANONICAL_TIMEZONE,
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: CANONICAL_TIMEZONE,
});

export const DIAS_SEMANA_OPCOES = [
  { valor: 0, label: "Segunda-feira" },
  { valor: 1, label: "Terça-feira" },
  { valor: 2, label: "Quarta-feira" },
  { valor: 3, label: "Quinta-feira" },
  { valor: 4, label: "Sexta-feira" },
  { valor: 5, label: "Sábado" },
  { valor: 6, label: "Domingo" },
] as const;

export const TIPO_DOCUMENTO_LABELS: Record<string, string> = {
  RECEITA_SIMPLES: "Receita Médica Simples",
  RECEITA_ANTIMICROBIANO: "Receita de Antimicrobiano",
  RECEITA_CONTROLE_ESPECIAL: "Receita de Controle Especial (Portaria 344/98)",
  RECEITA_CONTROLE_ESPECIAL_C1: "Receita de Controle Especial (Portaria 344/98)",
  ATESTADO_MEDICO: "Atestado Médico",
  RELATORIO_ENCAMINHAMENTO: "Relatório / Encaminhamento",
  PEDIDO_EXAME: "Pedido de Exames Complementares",
};

const ESPECIALIDADE_LABELS: Record<string, string> = {
  PSICOLOGIA: "Psicologia",
  NUTRICAO: "Nutrição",
};

const PARENTESCO_LABELS: Record<string, string> = {
  FILHO: "Filho(a)",
  FILHA: "Filha",
  ENTEADO: "Enteado(a)",
  TUTELADO: "Tutelado(a)",
  CONJUGE: "Cônjuge / Companheiro(a)",
  OUTRO: "Outro Responsável",
};

export type StatusBadgeVariant = Extract<
  NonNullable<BadgeProps["variant"]>,
  "default" | "secondary" | "destructive" | "outline" | "success" | "warning"
>;

export interface StatusBadgeInfo {
  label: string;
  variant: StatusBadgeVariant;
}

export const STATUS_BADGE_MAP: Record<string, StatusBadgeInfo> = {
  AGENDADO: { label: "Agendado", variant: "default" },
  CONFIRMADO: { label: "Confirmado", variant: "success" },
  EM_ATENDIMENTO: { label: "Em atendimento", variant: "warning" },
  CHAMANDO_PACIENTE: { label: "Chamando", variant: "warning" },
  AGUARDANDO_CHAMADA: { label: "Aguardando chamada", variant: "default" },
  APTO_PARA_CHAMADA: { label: "Aguardando chamada", variant: "default" },
  TRIADO_AGUARDANDO_ELEGIBILIDADE: { label: "Aguardando cadastro", variant: "warning" },
  CONCLUIDO: { label: "Concluído", variant: "success" },
  FINALIZADO: { label: "Finalizado", variant: "success" },
  REALIZADO: { label: "Realizado", variant: "success" },
  CANCELADO: { label: "Cancelado", variant: "destructive" },
  CANCELADO_PACIENTE: { label: "Cancelado", variant: "destructive" },
  FALTA: { label: "Falta", variant: "destructive" },
  PACIENTE_AUSENTE: { label: "Ausência", variant: "destructive" },
};

/**
 * Formata o tempo de espera estimado em segundos para uma representação amigável e empática em português.
 * Regras: US-07, US-08 e Diretrizes de UI em Telemedicina.
 */
export function formatarTempoEstimado(segundos: number | null | undefined): string {
  if (segundos === null || segundos === undefined) {
    return "Calculando estimativa...";
  }

  if (segundos < 60) {
    return "Menos de 1 minuto";
  }

  const minutosTotais = Math.round(segundos / 60);

  if (minutosTotais < 60) {
    return `Aproximadamente ${minutosTotais} ${minutosTotais === 1 ? "minuto" : "minutos"}`;
  }

  const horas = Math.floor(minutosTotais / 60);
  const minutosRestantes = minutosTotais % 60;

  if (minutosRestantes === 0) {
    return `Aproximadamente ${horas} ${horas === 1 ? "hora" : "horas"}`;
  }

  return `Aproximadamente ${horas} ${horas === 1 ? "hora" : "horas"} e ${minutosRestantes} ${minutosRestantes === 1 ? "minuto" : "minutos"}`;
}

/**
 * Formata a posição ordinal do paciente na fila virtual.
 * Exemplo: 1 -> "1º na fila", null -> "—"
 */
export function formatarPosicaoOrdinal(posicao: number | null | undefined): string {
  if (!posicao || posicao < 1) {
    return "—";
  }
  return `${posicao}º na fila`;
}

export function formatarDataHoraBR(iso?: string | null): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return dateTimeFormatter.format(parsed);
}

export function formatarDataBR(iso?: string | null): string {
  if (!iso) return "—";
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00Z` : iso;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return iso;
  return dateFormatter.format(parsed);
}

export function formatarHorarioSlot(isoDateTime: string): string {
  const parsed = new Date(isoDateTime);
  if (Number.isNaN(parsed.getTime())) return isoDateTime;
  return timeFormatter.format(parsed);
}

export function formatarDataIso(date: Date): string {
  const ano = date.getUTCFullYear();
  const mes = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dia = String(date.getUTCDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
}

export function somarDiasIso(dateIso: string, dias: number): string {
  const base = new Date(`${dateIso}T00:00:00Z`);
  base.setUTCDate(base.getUTCDate() + dias);
  return base.toISOString().slice(0, 10);
}

export function getTipoDocumentoLabel(tipo: string): string {
  const normalizado = tipo.trim().toUpperCase();
  return TIPO_DOCUMENTO_LABELS[normalizado] ?? tipo.replace(/_/g, " ");
}

export function formatarEspecialidadeNome(codigo: string): string {
  const normalizado = codigo.trim().toUpperCase();
  return ESPECIALIDADE_LABELS[normalizado] ?? codigo;
}

export function getGrauParentescoLabel(grau: string): string {
  return PARENTESCO_LABELS[grau.trim().toUpperCase()] ?? grau;
}

export function getPrioridadeBadgeProps(nivel: number): {
  variant: Extract<BadgeProps["variant"], "nivel1" | "nivel2" | "nivel3" | "nivel4" | "nivel5">;
  label: string;
} {
  switch (nivel) {
    case 1:
      return { variant: "nivel1", label: "Nível 1 · Emergência" };
    case 2:
      return { variant: "nivel2", label: "Nível 2 · Muito Urgente" };
    case 3:
      return { variant: "nivel3", label: "Nível 3 · Urgente" };
    case 4:
      return { variant: "nivel4", label: "Nível 4 · Pouco Urgente" };
    default:
      return { variant: "nivel5", label: "Nível 5 · Não Urgente" };
  }
}

export function getStatusBadgeProps(status: string): StatusBadgeInfo {
  const normalizado = status.trim().toUpperCase();
  return (
    STATUS_BADGE_MAP[normalizado] ?? {
      label: normalizado.replace(/_/g, " "),
      variant: "secondary",
    }
  );
}

export function isAgendamentoCancelavel(status: string): boolean {
  const normalizado = status.trim().toUpperCase();
  return normalizado === "AGENDADO" || normalizado === "CONFIRMADO";
}

export function isAgendamentoIniciavel(status: string): boolean {
  const normalizado = status.trim().toUpperCase();
  return normalizado === "AGENDADO" || normalizado === "CONFIRMADO";
}
