import { AlertCircle, CalendarPlus, CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { getHumanizedErrorMessage } from "@/api/errors";
import type { SlotDisponivelResponse } from "@/api/generated/types.gen";
import { useEspecialidades } from "@/api/hooks/use-especialidades";
import { useMeusAgendamentos } from "@/api/hooks/use-meus-agendamentos";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  formatarDataHoraBR,
  formatarDataIso,
  formatarEspecialidadeNome,
  formatarHorarioSlot,
  somarDiasIso,
} from "@/lib/formatters";
import { useCancelarAgendamento } from "../api/use-cancelar-agendamento";
import { useCriarAgendamento } from "../api/use-criar-agendamento";
import { useSlots } from "../api/use-slots";
import { MyAppointmentsList } from "../components/my-appointments-list";
import { SlotPicker } from "../components/slot-picker";
import { SpecialtySelector } from "../components/specialty-selector";
import { criarAgendamentoFormSchema, validarPeriodoSlots } from "../schemas/scheduling-schema";

export interface ScheduleAppointmentPageProps {
  initialEspecialidade?: string;
  token?: string;
}

/**
 * Página da jornada de agendamento multiprofissional do paciente (`/agendar`).
 * Integra seleção de especialidade, escolha de horário livre, confirmação com
 * tratamento RFC 7807 (ex.: 409) e visualização/cancelamento dos agendamentos.
 */
export function ScheduleAppointmentPage({
  initialEspecialidade = "",
  token,
}: ScheduleAppointmentPageProps) {
  const hojeIso = formatarDataIso(new Date());
  const [especialidade, setEspecialidade] = useState(() =>
    initialEspecialidade.trim().toUpperCase(),
  );
  const [dataInicio, setDataInicio] = useState(hojeIso);
  const [dataFim, setDataFim] = useState(() => somarDiasIso(hojeIso, 7));
  const [selectedSlot, setSelectedSlot] = useState<SlotDisponivelResponse | null>(null);
  const [observacoes, setObservacoes] = useState("");
  const [erroValidacao, setErroValidacao] = useState<string | null>(null);
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const {
    data: especialidades = [],
    isLoading: isLoadingEspecialidades,
    error: especialidadesError,
  } = useEspecialidades({ token });

  const periodoInvalido = Boolean(validarPeriodoSlots(dataInicio, dataFim));
  const {
    data: slots = [],
    isLoading: isLoadingSlots,
    error: slotsError,
    refetch: refetchSlots,
  } = useSlots({
    especialidade,
    dataInicio,
    dataFim,
    token,
    enabled: Boolean(especialidade) && !periodoInvalido,
  });

  const {
    data: meusAgendamentos = [],
    isLoading: isLoadingAgendamentos,
    error: meusAgendamentosError,
  } = useMeusAgendamentos({ token });

  const {
    mutate: criarAgendamento,
    isPending: isCreating,
    error: createError,
    reset: resetCreateError,
  } = useCriarAgendamento();

  const { mutate: cancelarAgendamento, error: cancelError } = useCancelarAgendamento();

  const handleSelectEspecialidade = (codigo: string) => {
    setEspecialidade(codigo);
    setSelectedSlot(null);
    setErroValidacao(null);
    setMensagemSucesso(null);
    resetCreateError();
  };

  const handleChangePeriodo = (novoInicio: string, novoFim: string) => {
    setDataInicio(novoInicio);
    setDataFim(novoFim);
    setSelectedSlot(null);
    resetCreateError();
  };

  const handleConfirmarAgendamento = (e: React.FormEvent) => {
    e.preventDefault();
    setErroValidacao(null);
    setMensagemSucesso(null);
    resetCreateError();

    if (!selectedSlot) {
      setErroValidacao("Selecione um horário disponível antes de confirmar o agendamento.");
      return;
    }

    const parsed = criarAgendamentoFormSchema.safeParse({
      profissional_id: selectedSlot.profissional_id,
      especialidade: selectedSlot.especialidade,
      slot_inicio: selectedSlot.slot_inicio,
      slot_fim: selectedSlot.slot_fim,
      observacoes: observacoes.trim() ? observacoes.trim() : null,
    });

    if (!parsed.success) {
      setErroValidacao(
        parsed.error.issues[0]?.message ?? "Verifique os dados informados antes de continuar.",
      );
      return;
    }

    criarAgendamento(
      { body: parsed.data, token },
      {
        onSuccess: (agendamento) => {
          setSelectedSlot(null);
          setObservacoes("");
          setMensagemSucesso(
            `Consulta de ${formatarEspecialidadeNome(agendamento.especialidade)} agendada para ${formatarDataHoraBR(agendamento.slot_inicio)}.`,
          );
        },
      },
    );
  };

  const handleCancelarAgendamento = (agendamentoId: string) => {
    setCancellingId(agendamentoId);
    cancelarAgendamento(
      { agendamentoId, token },
      {
        onSettled: () => {
          setCancellingId(null);
        },
      },
    );
  };

  const erroCriacaoHumanizado = createError ? getHumanizedErrorMessage(createError) : null;
  const tituloErroCriacao =
    createError?.status === 409
      ? "Horário já ocupado"
      : (erroCriacaoHumanizado?.title ?? "Não foi possível agendar");

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6 py-4 px-2 sm:px-0">
      <header className="space-y-1.5">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
          <CalendarPlus className="size-3.5" aria-hidden="true" />
          <span>Agenda Multiprofissional · eMulti SUS</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
          Agendar Consulta
        </h1>
        <p className="text-sm text-muted-foreground">
          Escolha a especialidade desejada, selecione um horário livre e acompanhe seus
          agendamentos.
        </p>
      </header>

      {mensagemSucesso && (
        <Alert className="border-acr-green/40 bg-acr-green/10 text-foreground">
          <CheckCircle2 className="size-4 text-acr-green" aria-hidden="true" />
          <AlertTitle>Agendamento confirmado</AlertTitle>
          <AlertDescription>{mensagemSucesso}</AlertDescription>
        </Alert>
      )}

      <SpecialtySelector
        especialidades={especialidades}
        selectedCodigo={especialidade}
        onSelect={handleSelectEspecialidade}
        isLoading={isLoadingEspecialidades}
        error={especialidadesError}
      />

      <SlotPicker
        especialidade={especialidade}
        dataInicio={dataInicio}
        dataFim={dataFim}
        onChangePeriodo={handleChangePeriodo}
        slots={slots}
        selectedSlot={selectedSlot}
        onSelectSlot={(slot) => {
          setSelectedSlot(slot);
          setErroValidacao(null);
          resetCreateError();
        }}
        isLoading={isLoadingSlots}
        error={slotsError}
        onRetry={() => {
          void refetchSlots();
        }}
      />

      <Card className="border-border shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">3. Confirmação do Agendamento</CardTitle>
          <CardDescription>
            Revise o horário escolhido e informe, se desejar, o motivo ou observações da consulta.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleConfirmarAgendamento} className="space-y-4">
            {selectedSlot ? (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-3.5 text-sm">
                <p className="font-semibold text-foreground">
                  {formatarEspecialidadeNome(selectedSlot.especialidade)} ·{" "}
                  {formatarDataHoraBR(selectedSlot.slot_inicio)} às{" "}
                  {formatarHorarioSlot(selectedSlot.slot_fim)}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Duração prevista: {selectedSlot.duracao_minutos} minutos
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nenhum horário selecionado até o momento.
              </p>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="agendamento-observacoes">
                Observações ou motivo da consulta (opcional)
              </Label>
              <Textarea
                id="agendamento-observacoes"
                value={observacoes}
                onChange={(e) => setObservacoes(e.target.value)}
                maxLength={500}
                rows={3}
                placeholder="Ex.: Acompanhamento de ansiedade ou orientação nutricional…"
              />
              <p className="text-xs text-muted-foreground text-right">
                {observacoes.length}/500 caracteres
              </p>
            </div>

            {erroValidacao && (
              <Alert variant="destructive" role="alert">
                <AlertCircle className="size-4" aria-hidden="true" />
                <AlertTitle>Dados incompletos</AlertTitle>
                <AlertDescription>{erroValidacao}</AlertDescription>
              </Alert>
            )}

            {erroCriacaoHumanizado && (
              <Alert variant="destructive" role="alert">
                <AlertCircle className="size-4" aria-hidden="true" />
                <AlertTitle>{tituloErroCriacao}</AlertTitle>
                <AlertDescription>{erroCriacaoHumanizado.detail}</AlertDescription>
              </Alert>
            )}

            <Button
              type="submit"
              disabled={!selectedSlot || isCreating}
              className="min-h-[44px] w-full sm:w-auto gap-2"
            >
              {isCreating ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <CalendarPlus className="size-4" aria-hidden="true" />
              )}
              <span>{isCreating ? "Confirmando agendamento…" : "Confirmar Agendamento"}</span>
            </Button>
          </form>
        </CardContent>
      </Card>

      <MyAppointmentsList
        agendamentos={meusAgendamentos}
        isLoading={isLoadingAgendamentos}
        error={meusAgendamentosError}
        cancellingId={cancellingId}
        cancelError={cancelError}
        onCancelar={handleCancelarAgendamento}
      />
    </div>
  );
}
