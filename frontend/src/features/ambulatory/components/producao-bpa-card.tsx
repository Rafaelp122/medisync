import { AlertCircle, CheckCircle2, Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatarDataBR } from "@/lib/formatters";
import { useExportarBpa, useProducaoBpa } from "../api/use-producao-bpa";

/**
 * Retorna competência mensal canônica (YYYYMM) em UTC, alinhada ao servidor DATASUS.
 */
export function getCompetenciaAtualUtc(now: Date = new Date()): string {
  const ano = now.getUTCFullYear();
  const mes = String(now.getUTCMonth() + 1).padStart(2, "0");
  return `${ano}${mes}`;
}

/**
 * Extrai CNES real de 7 dígitos da linha `03` DATASUS BPA-I (posições 3..9),
 * evitando o prefixo literal `01#BPA#` do cabeçalho.
 */
export function extractCnesFromBpaContent(conteudo: string): string | null {
  for (const linha of conteudo.split(/\r?\n/)) {
    const trimmed = linha.trim();
    const matchLinha03 = trimmed.match(/^03(\d{7})/);
    if (matchLinha03?.[1]) {
      return matchLinha03[1];
    }
  }
  return null;
}

/**
 * Cartão de apuração ambulatorial SUS BPA-I e exportação oficial .txt (US-11 / RF-08).
 */
export function ProducaoBpaCard() {
  const [competencia, setCompetencia] = useState(() => getCompetenciaAtualUtc());
  const [exportStatus, setExportStatus] = useState<string | null>(null);

  const competenciaValida = /^\d{6}$/.test(competencia);
  const { data: producao, isLoading, error: listError } = useProducaoBpa(competencia);
  const { mutate: exportarBpa, isPending: isExporting, error: exportError } = useExportarBpa();

  const handleExportar = () => {
    if (!competenciaValida) return;
    setExportStatus(null);
    exportarBpa(competencia, {
      onSuccess: ({ conteudo, filename: serverFilename }) => {
        const cnes = producao?.items[0]?.cnes || extractCnesFromBpaContent(conteudo) || "0000000";
        const filename = serverFilename || `BPA_I_${competencia}_${cnes}.txt`;

        if (typeof URL.createObjectURL === "function") {
          const blob = new Blob([conteudo], { type: "text/plain;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
        }
        setExportStatus(
          `Arquivo BPA-I da competência ${competencia} exportado (${filename}, ${conteudo.length} caracteres).`,
        );
      },
    });
  };

  const erroAtivo = exportError ?? listError;

  return (
    <Card className="border-border/80 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <FileSpreadsheet className="h-4 w-4 text-primary" aria-hidden="true" />
            Produção Ambulatorial SUS (BPA-I)
          </CardTitle>
          <Badge variant="outline">
            {isLoading ? "Carregando…" : `${producao?.total ?? 0} registros`}
          </Badge>
        </div>
        <CardDescription>
          Consulte atendimentos liquidados por competência e gere a remessa oficial DATASUS (.txt).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="competencia-bpa">Competência (YYYYMM)</Label>
            <Input
              id="competencia-bpa"
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={competencia}
              onChange={(e) => setCompetencia(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="YYYYMM"
            />
          </div>
          <Button
            type="button"
            onClick={handleExportar}
            disabled={isExporting || !competenciaValida}
            className="gap-1.5"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {isExporting ? "Exportando…" : "Exportar BPA-I (.txt)"}
          </Button>
        </div>

        {!competenciaValida && (
          <p className="text-xs text-destructive" role="alert">
            Informe uma competência válida com 6 dígitos no formato YYYYMM.
          </p>
        )}

        {erroAtivo && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Erro na produção ambulatorial</AlertTitle>
            <AlertDescription>{erroAtivo.detail || erroAtivo.message}</AlertDescription>
          </Alert>
        )}

        {exportStatus && (
          <Alert
            role="status"
            className="border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
          >
            <CheckCircle2
              className="h-4 w-4 text-emerald-700 dark:text-emerald-400"
              aria-hidden="true"
            />
            <AlertTitle>Exportação concluída</AlertTitle>
            <AlertDescription>{exportStatus}</AlertDescription>
          </Alert>
        )}

        {producao && producao.items.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-border/70">
            <table className="w-full text-xs text-left">
              <thead className="bg-muted/60 text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    SIGTAP
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    CNES
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Caráter
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Consolidado
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {producao.items.slice(0, 5).map((item) => (
                  <tr key={item.atendimento_id}>
                    <td className="px-3 py-2 font-mono">{item.codigo_sigtap}</td>
                    <td className="px-3 py-2 font-mono">{item.cnes}</td>
                    <td className="px-3 py-2">{item.carater_atendimento}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {formatarDataBR(item.consolidado_em)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !isLoading && (
            <p className="text-xs text-muted-foreground">
              Nenhum registro BPA-I consolidado para a competência {competencia}.
            </p>
          )
        )}
      </CardContent>
    </Card>
  );
}
