import { AlertCircle, Loader2, Users } from "lucide-react";
import { extractProblemDetail } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDependents } from "@/features/citizen/api/use-dependents";
import { DependentForm } from "@/features/citizen/components/dependent-form";
import { formatarDataBR, getGrauParentescoLabel } from "@/lib/formatters";

export interface DependentsSectionProps {
  pacienteId: string;
}

/**
 * Seção de listagem e gestão de dependentes legais/menores do cidadão titular.
 */
export function DependentsSection({ pacienteId }: DependentsSectionProps) {
  const dependentsQuery = useDependents(pacienteId);
  const dependentes = dependentsQuery.data ?? [];

  return (
    <section aria-labelledby="dependentes-heading" className="space-y-4">
      <Card className="border-border shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle id="dependentes-heading" className="text-lg flex items-center gap-2">
              <Users className="h-5 w-5 text-primary" aria-hidden="true" />
              <span>Meus Dependentes ({dependentes.length})</span>
            </CardTitle>
            <Badge variant="outline">Vínculo Familiar</Badge>
          </div>
          <CardDescription>
            Cadastre filhos, tutelados ou dependentes legais para agilizar atendimentos na rede SUS.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {dependentsQuery.isLoading && (
            <div role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
              <span>Carregando dependentes…</span>
            </div>
          )}

          {dependentsQuery.isError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              <AlertTitle>Erro ao listar dependentes</AlertTitle>
              <AlertDescription>
                {extractProblemDetail(
                  dependentsQuery.error,
                  "Não foi possível carregar os dependentes vinculados.",
                )}
              </AlertDescription>
            </Alert>
          )}

          {!dependentsQuery.isLoading && !dependentsQuery.isError && dependentes.length === 0 && (
            <p className="text-xs text-muted-foreground rounded-lg border border-dashed border-border p-4 text-center">
              Nenhum dependente vinculado até o momento.
            </p>
          )}

          {dependentes.length > 0 && (
            <ul className="space-y-2">
              {dependentes.map((dep) => (
                <li
                  key={dep.id}
                  className="rounded-lg border border-border bg-muted/20 p-3 flex flex-wrap items-center justify-between gap-2 text-xs"
                >
                  <div className="space-y-0.5">
                    <p className="font-semibold text-sm text-foreground">
                      {dep.nome_completo || "Dependente cadastrado"}
                    </p>
                    <p className="text-muted-foreground">
                      Nascimento: {formatarDataBR(dep.data_nascimento)}
                      {dep.cpf ? ` · CPF: ${dep.cpf}` : ""}
                      {dep.cns ? ` · CNS: ${dep.cns}` : ""}
                    </p>
                  </div>
                  <Badge variant="secondary">{getGrauParentescoLabel(dep.grau_parentesco)}</Badge>
                </li>
              ))}
            </ul>
          )}

          <DependentForm pacienteId={pacienteId} />
        </CardContent>
      </Card>
    </section>
  );
}
