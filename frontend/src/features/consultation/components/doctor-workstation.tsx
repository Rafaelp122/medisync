import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Lock, LogOut, PhoneCall, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { getActiveTenantId } from "@/api/client";
import type { ChamarProximoResponse, DocumentoClinicoResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { useChamarProximo } from "../api/use-chamar-proximo";
import { useLiveKitToken } from "../api/use-livekit-token";
import { usePainelTelemetria } from "../api/use-painel-telemetria";
import { CfmIdentityGate } from "./cfm-identity-gate";
import { FinalizeConsultationModal } from "./finalize-consultation-modal";
import { MedicalRecordsPane } from "./medical-records-pane";
import { PrescriptionBuilder } from "./prescription-builder";
import { SoapEditor } from "./soap-editor";
import { TmaTimerBadge } from "./tma-timer-badge";
import { WorkstationMediaPane } from "./workstation-media-pane";

export interface DoctorWorkstationProps {
  medicoId?: string;
  medicoNome?: string;
  crmUf?: string;
  token?: string;
  organizacaoId?: number;
  onLogout?: () => void;
  idleTimeoutMs?: number;
}

/**
 * Estação de Trabalho Clínica Unificada do Médico Plantonista (Doctor Single-Pane Workstation).
 * Integra em tela única contínua sem troca de abas:
 * 1. Coluna Esquerda: LiveKit WebRTC + TMA Timer (RN06) + Gate CFM nº 2.314/2022.
 * 2. Coluna Central: Prontuário Eletrônico, Dados de Triagem e Documentos Emitidos (PEP).
 * 3. Coluna Direita: Editor SOAP estruturado + Prescritor digital (Portaria 344/98) + Encerramento ICP-Brasil.
 * Regras: RF-07, RN06, CFM nº 2.314/2022, CFM nº 1.821/2007, US-09, US-10 e ADR-011.
 */
export function DoctorWorkstation({
  medicoId = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
  medicoNome = "Dr. Eduardo Rocha",
  crmUf = "123456/SP",
  token,
  organizacaoId,
  onLogout,
  idleTimeoutMs = 15 * 60 * 1000,
}: DoctorWorkstationProps) {
  // Inatividade Clínica (Auto-Logout em estações de pronto atendimento compartilhadas)
  // Regras: CFM nº 2.314/2022, LGPD Art. 11, OWASP Session Management
  useEffect(() => {
    if (!onLogout) return;

    let timer: ReturnType<typeof setTimeout>;

    const resetTimer = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        onLogout();
      }, idleTimeoutMs);
    };

    const activityEvents = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;
    for (const event of activityEvents) {
      window.addEventListener(event, resetTimer, { passive: true });
    }

    resetTimer();

    return () => {
      clearTimeout(timer);
      for (const event of activityEvents) {
        window.removeEventListener(event, resetTimer);
      }
    };
  }, [onLogout, idleTimeoutMs]);
  const [atendimentoAtivo, setAtendimentoAtivo] = useState<ChamarProximoResponse | null>(null);
  const [identidadeVerificada, setIdentidadeVerificada] = useState(false);
  const [documentoPendente, setDocumentoPendente] = useState<DocumentoClinicoResponse | null>(null);
  const [isFinalizado, setIsFinalizado] = useState(false);
  const [modalFinalizarAberto, setModalFinalizarAberto] = useState(false);
  const [mensagemFilaVazia, setMensagemFilaVazia] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const { data: painelTelemetria, isLoading: isCarregandoPainel } = usePainelTelemetria(token);
  const totalPacientesFila = painelTelemetria?.total_pacientes_fila ?? 0;

  const { mutate: chamarProximo, isPending: isCallingNext } = useChamarProximo();
  const { data: livekitData, mutate: emitirLivekitToken } = useLiveKitToken(
    atendimentoAtivo?.atendimento_id || "",
  );

  const handleChamarProximo = () => {
    setMensagemFilaVazia(null);
    chamarProximo(
      { token },
      {
        onSuccess: (data) => {
          if (data.alocado && data.atendimento_id) {
            setAtendimentoAtivo(data);
            setIdentidadeVerificada(false);
            setDocumentoPendente(null);
            setIsFinalizado(false);

            // Emite token LiveKit WebRTC para a sala médica
            const tenantVal = Number(getActiveTenantId());
            const fallbackOrgId = Number.isFinite(tenantVal) && tenantVal > 0 ? tenantVal : 1;
            emitirLivekitToken({
              token,
              atendimento_id: data.atendimento_id,
              organizacao_id: organizacaoId ?? fallbackOrgId,
              participant_id: medicoId,
              role: "medico",
              participant_name: medicoNome,
              is_publisher: true,
              ttl_seconds: 3600,
            });
          } else {
            setMensagemFilaVazia(
              data.mensagem ||
                "Nenhum paciente aguardando na fila virtual no momento. Aguarde novos ingressos.",
            );
          }
        },
        onError: (err) => {
          setMensagemFilaVazia(
            err.detail ||
              "Erro ao alocar paciente da fila virtual. Verifique a autenticação e conexão com o servidor.",
          );
        },
        onSettled: () => {
          void queryClient.invalidateQueries({ queryKey: ["telemetria-painel"] });
        },
      },
    );
  };

  const handleFinalizadoComSucesso = () => {
    setIsFinalizado(true);
  };

  return (
    <div className="w-full flex flex-col gap-4 max-w-[1600px] mx-auto p-2 sm:p-4 text-foreground">
      {/* Barra de Cabeçalho da Estação Clínica */}
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 rounded-lg border border-border bg-card shadow-xs">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
            ER
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-foreground">{medicoNome}</h1>
              <Badge variant="outline" className="text-[11px] py-0 px-1.5">
                CRM {crmUf}
              </Badge>
              <Badge variant="success" className="text-[10px] py-0 px-1.5 gap-1">
                <span className="inline-block size-1.5 rounded-full bg-emerald-500" />
                Em Plantão
              </Badge>
              <Badge
                variant={totalPacientesFila > 0 ? "outline" : "secondary"}
                className="text-[10px] py-0 px-2 gap-1.5"
                data-testid="badge-pacientes-fila"
              >
                <Users className="size-3 text-muted-foreground" />
                <span>
                  {isCarregandoPainel
                    ? "Consultando fila…"
                    : totalPacientesFila === 1
                      ? "1 paciente na fila"
                      : totalPacientesFila > 1
                        ? `${totalPacientesFila} pacientes na fila`
                        : "Fila vazia (0)"}
                </span>
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Estação Clínica Integrada • Telemedicina de Urgência MediSync Express
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          {atendimentoAtivo?.atendimento_id && (
            <TmaTimerBadge
              iniciadoEm={atendimentoAtivo.chamada_iniciada_em}
              tmaPlanejadoSegundos={atendimentoAtivo.ttl_segundos ?? undefined}
            />
          )}

          <Button
            type="button"
            size="sm"
            onClick={handleChamarProximo}
            disabled={isCallingNext}
            className="text-xs font-semibold h-9 px-4 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <PhoneCall className="size-4" />
            <span>{isCallingNext ? "Adquirindo da fila…" : "Chamar Próximo Paciente"}</span>
          </Button>

          {onLogout && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onLogout}
              className="text-xs font-medium h-9 px-3 gap-1.5 text-muted-foreground hover:text-foreground border-border"
            >
              <LogOut className="size-3.5" />
              <span>Sair do Plantão</span>
            </Button>
          )}
        </div>
      </header>

      {/* Aviso de Fila Vazia */}
      {mensagemFilaVazia && (
        <Alert className="py-2.5 text-xs bg-muted/50 border-border">
          <AlertCircle className="size-4 text-muted-foreground" />
          <AlertDescription className="text-xs text-muted-foreground">
            {mensagemFilaVazia}
          </AlertDescription>
        </Alert>
      )}

      {/* Banner de Consulta Finalizada (Imutabilidade Legal) */}
      {isFinalizado && (
        <Alert className="py-2.5 text-xs border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200">
          <CheckCircle2 className="size-4 text-emerald-600 inline mr-2" />
          <AlertDescription className="text-xs inline font-medium">
            Atendimento concluído com sucesso. Todos os registros clínicos PEP e prescrições foram
            congelados em modo imutável conforme a Resolução CFM nº 1.821/2007 e LGPD Art. 16.
          </AlertDescription>
        </Alert>
      )}

      {/* Estado Vazio: Nenhum Paciente em Atendimento */}
      {!atendimentoAtivo?.atendimento_id ? (
        <Card className="border-dashed border-2 border-border p-12 text-center bg-card/50">
          <CardContent className="flex flex-col items-center justify-center p-0 space-y-3">
            <div className="size-14 rounded-full bg-muted flex items-center justify-center text-muted-foreground">
              <Users className="size-7" />
            </div>
            <CardTitle className="text-base font-semibold">
              Nenhum atendimento clínico ativo
            </CardTitle>
            <p className="text-xs text-muted-foreground max-w-md">
              A fila virtual está monitorada em tempo real.{" "}
              {totalPacientesFila > 0 ? (
                <span>
                  Há{" "}
                  <strong>
                    {totalPacientesFila}{" "}
                    {totalPacientesFila === 1 ? "paciente aguardando" : "pacientes aguardando"}
                  </strong>{" "}
                  por atendimento.
                </span>
              ) : (
                <span>Não há pacientes aguardando no momento.</span>
              )}{" "}
              Clique em <strong>"Chamar Próximo Paciente"</strong> para alocar o próximo atendimento
              por ordem de prioridade clínica.
            </p>
          </CardContent>
        </Card>
      ) : (
        /* Workstation Clínica Single-Pane em 3 Colunas Integradas */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Coluna 1: Mídia WebRTC LiveKit & Gate CFM 2.314/2022 (4 colunas no desktop) */}
          <section
            aria-label="Videoconferência e Identificação"
            className="lg:col-span-4 flex flex-col gap-3.5"
          >
            <WorkstationMediaPane
              atendimentoId={atendimentoAtivo.atendimento_id}
              medicoNome={medicoNome}
              remoteParticipantName="Juliana Silva (Paciente)"
              livekitToken={livekitData?.token}
              wsUrl={livekitData?.server_url}
              roomName={livekitData?.room_name}
            />

            <CfmIdentityGate
              onVerificationChange={(verificado) => setIdentidadeVerificada(verificado)}
              isReadOnly={isFinalizado}
            />
          </section>

          {/* Coluna 2: Prontuário Eletrônico & Histórico de Documentos (4 colunas no desktop) */}
          <section
            aria-label="Prontuário Médico e Histórico"
            className="lg:col-span-4 flex flex-col gap-3.5"
          >
            <MedicalRecordsPane
              atendimentoId={atendimentoAtivo.atendimento_id}
              pacienteNome="Juliana Silva"
              pacienteCpf="123.***.***-00"
              prioridadeClinica={atendimentoAtivo.prioridade_clinica ?? 3}
              queixaPrincipal="Paciente refere dor de garganta, febre aferida em 38.5C e tosse seca."
              token={token}
            />
          </section>

          {/* Coluna 3: Evolução SOAP, Prescritor Portaria 344/98 e Conclusão (4 colunas no desktop) */}
          <section
            aria-label="Evolução Clínica e Prescrição"
            className="lg:col-span-4 flex flex-col gap-3.5"
          >
            <SoapEditor
              atendimentoId={atendimentoAtivo.atendimento_id}
              isReadOnly={isFinalizado}
              token={token}
            />

            <PrescriptionBuilder
              atendimentoId={atendimentoAtivo.atendimento_id}
              identidadeVerificada={identidadeVerificada}
              isReadOnly={isFinalizado}
              duracaoSegundos={
                atendimentoAtivo.chamada_iniciada_em
                  ? Math.max(
                      0,
                      Math.floor(
                        (Date.now() - new Date(atendimentoAtivo.chamada_iniciada_em).getTime()) /
                          1000,
                      ),
                    )
                  : 0
              }
              onPrescriptionIssued={(doc) => setDocumentoPendente(doc)}
              token={token}
            />

            {/* Ação de Conclusão Clínica */}
            {!isFinalizado && (
              <Button
                type="button"
                size="sm"
                onClick={() => setModalFinalizarAberto(true)}
                className="w-full h-9 text-xs font-semibold gap-2 bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs"
              >
                <Lock className="size-4" />
                <span>Concluir Atendimento & Assinar</span>
              </Button>
            )}
          </section>
        </div>
      )}

      {/* Modal de Conclusão e Assinatura ICP-Brasil */}
      {atendimentoAtivo?.atendimento_id && (
        <FinalizeConsultationModal
          open={modalFinalizarAberto}
          onOpenChange={setModalFinalizarAberto}
          atendimentoId={atendimentoAtivo.atendimento_id}
          identidadeVerificada={identidadeVerificada}
          documentoPendente={documentoPendente}
          onFinalized={handleFinalizadoComSucesso}
          token={token}
        />
      )}
    </div>
  );
}
