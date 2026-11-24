import { createContext, type ReactNode, use, useMemo, useState } from "react";
import type { DocumentoClinicoResponse } from "@/api/generated/types.gen";
import type { LivenessResultMessage } from "../lib/liveness-channel";
import type { CfmIdentityGateData } from "../schemas/consultation-schema";

export interface AtendimentoClinicoSnapshot {
  atendimentoId: string;
  pacienteId: string;
  pacienteNome: string;
  pacienteIdentificador: string;
  medicoId: string;
  medicoNome: string;
  crmUf: string;
  prioridadeClinica: number;
  queixaPrincipal: string;
  chamadaIniciadaEm?: string | null;
  ttlSegundos?: number | null;
  token?: string;
}

export interface ConsultationEncounterContextValue {
  atendimento: AtendimentoClinicoSnapshot;
  identidadeVerificada: boolean;
  dadosIdentidade: CfmIdentityGateData | null;
  documentoPendente: DocumentoClinicoResponse | null;
  documentoAssinado: boolean;
  precisaAssinar: boolean;
  isFinalizado: boolean;
  livenessResult: LivenessResultMessage | null;
  mode: "active" | "finalized";
  setIdentidadeConfirmada: (verificado: boolean, data?: CfmIdentityGateData | null) => void;
  setDocumentoPendente: (doc: DocumentoClinicoResponse | null) => void;
  marcarDocumentoAssinado: () => void;
  marcarFinalizado: () => void;
  setLivenessResult: (result: LivenessResultMessage | null) => void;
}

const ConsultationEncounterContext = createContext<ConsultationEncounterContextValue | null>(null);

export interface ConsultationEncounterProviderProps {
  atendimento: AtendimentoClinicoSnapshot;
  children: ReactNode;
}

/**
 * Provider React 19 (`use()`) isolado por atendimento (`key={atendimentoId}`).
 * Impede vazamento de `identidadeVerificada`, `documentoPendente`, `documentoAssinado`
 * ou status finalizado entre pacientes consecutivos.
 * @see docs/user-stories/US-09-teleconsulta-pep-soap.md
 */
export function ConsultationEncounterProvider({
  atendimento,
  children,
}: ConsultationEncounterProviderProps) {
  const [identidadeVerificada, setIdentidadeVerificada] = useState(false);
  const [dadosIdentidade, setDadosIdentidade] = useState<CfmIdentityGateData | null>(null);
  const [documentoPendente, setDocumentoPendenteState] = useState<DocumentoClinicoResponse | null>(
    null,
  );
  const [documentoAssinado, setDocumentoAssinado] = useState(false);
  const [isFinalizado, setIsFinalizado] = useState(false);
  const [livenessResult, setLivenessResult] = useState<LivenessResultMessage | null>(null);

  const precisaAssinar = Boolean(
    documentoPendente && !documentoPendente.assinado_em && !documentoAssinado,
  );

  const value = useMemo<ConsultationEncounterContextValue>(
    () => ({
      atendimento,
      identidadeVerificada,
      dadosIdentidade,
      documentoPendente,
      documentoAssinado,
      precisaAssinar,
      isFinalizado,
      livenessResult,
      mode: isFinalizado ? "finalized" : "active",
      setIdentidadeConfirmada: (verificado, data) => {
        setIdentidadeVerificada(verificado);
        setDadosIdentidade(verificado ? (data ?? null) : null);
      },
      setDocumentoPendente: (doc) => {
        setDocumentoPendenteState(doc);
        setDocumentoAssinado(Boolean(doc?.assinado_em));
      },
      marcarDocumentoAssinado: () => {
        setDocumentoAssinado(true);
      },
      marcarFinalizado: () => {
        setIsFinalizado(true);
      },
      setLivenessResult,
    }),
    [
      atendimento,
      dadosIdentidade,
      documentoAssinado,
      documentoPendente,
      identidadeVerificada,
      isFinalizado,
      livenessResult,
      precisaAssinar,
    ],
  );

  return <ConsultationEncounterContext value={value}>{children}</ConsultationEncounterContext>;
}

/**
 * Lê o contexto clínico atual via hook React 19 `use()`, retornando null quando renderizado isoladamente.
 */
export function useOptionalConsultationEncounter(): ConsultationEncounterContextValue | null {
  return use(ConsultationEncounterContext);
}

/**
 * Lê o contexto clínico atual via hook React 19 `use()`, exigindo provider ativo.
 */
export function useConsultationEncounter(): ConsultationEncounterContextValue {
  const ctx = use(ConsultationEncounterContext);
  if (!ctx) {
    throw new Error(
      "useConsultationEncounter deve ser utilizado dentro de ConsultationEncounterProvider.",
    );
  }
  return ctx;
}
