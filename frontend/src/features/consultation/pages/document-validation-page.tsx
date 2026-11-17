import { Link } from "@tanstack/react-router";
import {
  AlertCircle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  FileCheck2,
  Loader2,
  Pill,
  QrCode,
  Search,
  ShieldCheck,
  Stethoscope,
  UserCheck,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { extractProblemDetail, extractProblemStatus } from "@/api/errors";
import type { ValidarDocumentoResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useValidateDocument } from "@/features/consultation/api/use-validate-document";
import { formatarDataHoraBR, getTipoDocumentoLabel } from "@/lib/formatters";

export interface DocumentValidationPageProps {
  token?: string;
  initialToken?: string;
}

function ValidationResultCard({ documento }: { documento: ValidarDocumentoResponse }) {
  const tipoLabel = getTipoDocumentoLabel(documento.tipo_documento);
  const isAuthentic = documento.assinatura_digital_valida;

  return (
    <Card className="border-border shadow-sm text-left" data-testid="validation-result-card">
      <CardHeader className="space-y-3 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <CheckCircle2 className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-lg font-bold text-foreground">
                {isAuthentic ? "Documento Clínico Autêntico" : "Documento Localizado"}
              </CardTitle>
              <CardDescription className="text-xs sm:text-sm">
                {tipoLabel} · Status: {documento.status_documento}
              </CardDescription>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            <Badge variant={isAuthentic ? "success" : "warning"}>
              {isAuthentic ? "Assinatura Digital Válida" : "Assinatura Pendente"}
            </Badge>
            {documento.conformidade_icp_brasil && (
              <Badge variant="nivel5">Selo ICP-Brasil / ITI</Badge>
            )}
          </div>
        </div>

        {documento.conformidade_icp_brasil && (
          <div className="flex items-start gap-2.5 rounded-lg border border-border bg-muted/40 p-3 text-xs">
            <ShieldCheck className="h-4 w-4 shrink-0 text-primary mt-0.5" aria-hidden="true" />
            <p className="text-muted-foreground">
              Assinatura eletrônica qualificada em conformidade com a MP nº 2.200-2/2001, padrão
              ICP-Brasil / ITI e Resoluções CFM nº 2.299/2021 e nº 2.314/2022.
            </p>
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg border border-border bg-muted/30 p-3.5">
          <div className="space-y-1">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <UserCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Paciente (Mascarado LGPD)
            </span>
            <p className="font-semibold text-foreground">{documento.paciente_nome_mascarado}</p>
            <p className="text-xs text-muted-foreground font-mono">
              CPF: {documento.paciente_cpf_mascarado}
            </p>
          </div>
          <div className="space-y-1">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Stethoscope className="h-3.5 w-3.5" aria-hidden="true" />
              Profissional Emissor
            </span>
            <p className="font-semibold text-foreground">{documento.emissor_medico_nome}</p>
            <p className="text-xs text-muted-foreground">
              CRM {documento.emissor_medico_crm}/{documento.emissor_medico_uf}
            </p>
          </div>
          <div className="space-y-1">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
              Unidade / Organização
            </span>
            <p className="font-medium text-foreground">{documento.organizacao_nome}</p>
          </div>
          <div className="space-y-1">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
              Data da Assinatura
            </span>
            <p className="font-medium text-foreground">
              {documento.assinado_em ? formatarDataHoraBR(documento.assinado_em) : "Não informado"}
            </p>
          </div>
        </div>

        {documento.sha256_hash && (
          <div className="rounded-md border border-border/70 bg-muted/20 px-3 py-2 text-xs">
            <span className="text-muted-foreground block">Hash SHA-256 de Integridade:</span>
            <code className="font-mono text-foreground break-all">{documento.sha256_hash}</code>
          </div>
        )}

        {documento.itens.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              <Pill className="h-4 w-4 text-primary" aria-hidden="true" />
              <span>Itens Prescritos ({documento.itens.length})</span>
            </h2>
            <ul className="space-y-2">
              {documento.itens.map((item) => (
                <li
                  key={`${item.medicamento}-${item.dosagem}-${item.posologia}`}
                  className="rounded-lg border border-border p-3 text-xs space-y-1"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-foreground text-sm">
                      {item.medicamento} · {item.dosagem}
                    </span>
                    {item.controle_especial && (
                      <Badge variant="warning">Controle Especial (344/98)</Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground">{item.posologia}</p>
                  {item.duracao && <p className="text-muted-foreground">Duração: {item.duracao}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Página pública de validação de documentos clínicos e receitas digitais (`/validar` e `/validar/$token`).
 */
export function DocumentValidationPage({ token, initialToken }: DocumentValidationPageProps) {
  const routeToken = (token ?? initialToken ?? "").trim();
  const [inputToken, setInputToken] = useState(routeToken);
  const [submittedToken, setSubmittedToken] = useState(routeToken);

  useEffect(() => {
    if (routeToken) {
      setInputToken(routeToken);
      setSubmittedToken(routeToken);
    }
  }, [routeToken]);

  const { data, isLoading, isError, error } = useValidateDocument(submittedToken);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = inputToken.trim();
    if (trimmed) setSubmittedToken(trimmed);
  };

  const errorStatus = isError ? extractProblemStatus(error) : null;
  const errorMessage = isError
    ? extractProblemDetail(error, "Não foi possível validar o código informado.")
    : null;

  return (
    <div className="w-full max-w-2xl mx-auto py-4 px-2 space-y-5">
      <div>
        <Link
          to="/"
          className="inline-flex min-h-[44px] items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          <span>Voltar ao Início</span>
        </Link>
      </div>

      <Card className="border-border shadow-sm text-left">
        <CardHeader className="space-y-1.5">
          <div className="inline-flex w-fit items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            <QrCode className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Validação Pública CFM / ITI</span>
          </div>
          <CardTitle className="text-xl sm:text-2xl font-bold">
            Validar Receita ou Documento Clínico
          </CardTitle>
          <CardDescription>
            Informe o código de validação impresso no documento ou leia o QR Code para confirmar a
            autenticidade da assinatura digital ICP-Brasil.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="token-validacao-input">Código ou Token de Validação</Label>
              <div className="flex flex-col sm:flex-row gap-2">
                <Input
                  id="token-validacao-input"
                  type="text"
                  value={inputToken}
                  onChange={(e) => setInputToken(e.target.value)}
                  placeholder="Ex: ITI-MEDISYNC-998877 ou UUID do documento…"
                  spellCheck={false}
                  autoComplete="off"
                  className="flex-1 font-mono text-sm"
                />
                <Button
                  type="submit"
                  disabled={!inputToken.trim() || isLoading}
                  className="min-h-[44px] shrink-0 gap-2"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      <span>Validando…</span>
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4" aria-hidden="true" />
                      <span>Validar Documento</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>

      {isLoading && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center justify-center gap-2 rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground"
        >
          <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
          <span>Consultando registro de autenticidade…</span>
        </div>
      )}

      {isError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>
            {errorStatus === 404
              ? "Documento não encontrado ou código inválido"
              : "Falha ao validar documento"}
          </AlertTitle>
          <AlertDescription>
            {errorStatus === 404
              ? "Nenhum documento clínico foi localizado para o código informado. Confira os caracteres e tente novamente."
              : errorMessage}
          </AlertDescription>
        </Alert>
      )}

      {data && !isLoading && <ValidationResultCard documento={data} />}
    </div>
  );
}

export default DocumentValidationPage;
