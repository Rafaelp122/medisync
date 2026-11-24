import { CalendarClock, ClipboardList, FileCheck2, Stethoscope } from "lucide-react";
import type {
  AgendamentoResponse,
  HistoricoAtendimentoItemResponse,
} from "@/api/generated/types.gen";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatarDataHoraBR,
  formatarEspecialidadeNome,
  getPrioridadeBadgeProps,
  getStatusBadgeProps,
} from "@/lib/formatters";

export interface HistoryRecordsListProps {
  paItems: HistoricoAtendimentoItemResponse[];
  agendamentoItems: AgendamentoResponse[];
}

export function HistoryRecordsList({ paItems, agendamentoItems }: HistoryRecordsListProps) {
  if (paItems.length + agendamentoItems.length === 0) {
    return (
      <Card className="border-dashed border-border">
        <CardContent className="py-10 text-center space-y-2 text-muted-foreground">
          <ClipboardList className="h-8 w-8 mx-auto opacity-60" aria-hidden="true" />
          <p className="text-sm font-medium text-foreground">
            Nenhuma consulta encontrada para os filtros selecionados.
          </p>
          <p className="text-xs">
            Seus atendimentos digitais e agendamentos concluídos aparecerão aqui.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {paItems.length > 0 && (
        <section aria-label="Atendimentos de Pronto-Atendimento" className="space-y-3">
          <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Stethoscope className="h-4 w-4 text-primary" aria-hidden="true" />
            <span>Pronto-Atendimento Digital ({paItems.length})</span>
          </h2>
          <div className="space-y-3">
            {paItems.map((item) => {
              const prioridade = getPrioridadeBadgeProps(item.prioridade_clinica);
              const statusBadge = getStatusBadgeProps(item.status);
              return (
                <Card key={item.atendimento_id} className="border-border shadow-sm">
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <CardTitle className="text-base">
                          {item.queixa_principal || "Atendimento de Pronto-Atendimento"}
                        </CardTitle>
                        <CardDescription className="text-xs">
                          Iniciado em {formatarDataHoraBR(item.criado_em)}
                          {item.finalizado_em
                            ? ` · Finalizado em ${formatarDataHoraBR(item.finalizado_em)}`
                            : ""}
                        </CardDescription>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant={prioridade.variant}>{prioridade.label}</Badge>
                        <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
                      </div>
                    </div>
                  </CardHeader>
                  {(item.diagnostico_cid10 || item.conduta_resumo) && (
                    <CardContent className="pt-2 space-y-2 text-xs">
                      <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-1.5">
                        {item.diagnostico_cid10 && (
                          <p className="font-semibold text-foreground flex items-center gap-1.5">
                            <FileCheck2 className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                            <span>CID-10: {item.diagnostico_cid10}</span>
                          </p>
                        )}
                        {item.conduta_resumo && (
                          <p className="text-muted-foreground">
                            <strong className="text-foreground">Resumo da conduta:</strong>{" "}
                            {item.conduta_resumo}
                          </p>
                        )}
                      </div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        </section>
      )}

      {agendamentoItems.length > 0 && (
        <section aria-label="Consultas Agendadas eMulti" className="space-y-3">
          <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-primary" aria-hidden="true" />
            <span>Consultas Agendadas eMulti ({agendamentoItems.length})</span>
          </h2>
          <div className="space-y-3">
            {agendamentoItems.map((ag) => {
              const statusBadge = getStatusBadgeProps(ag.status);
              return (
                <Card key={ag.id} className="border-border shadow-sm">
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <CardTitle className="text-base">
                          {formatarEspecialidadeNome(ag.especialidade)}
                        </CardTitle>
                        <CardDescription className="text-xs">
                          Horário: {formatarDataHoraBR(ag.slot_inicio)} até{" "}
                          {formatarDataHoraBR(ag.slot_fim)}
                        </CardDescription>
                      </div>
                      <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
                    </div>
                  </CardHeader>
                  {ag.observacoes && (
                    <CardContent className="pt-1 text-xs text-muted-foreground">
                      Observações: {ag.observacoes}
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
