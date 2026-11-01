import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle, FileText, Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSalvarSoap, useSoapEvolucao } from "../api/use-soap-evolucao";
import { type SoapFormData, soapSchema } from "../schemas/consultation-schema";

export interface SoapEditorProps {
  atendimentoId: string;
  isReadOnly?: boolean;
  token?: string;
}

/**
 * Editor estruturado de evolução clínica PEP no padrão SOAP (Subjetivo, Objetivo, Avaliação, Plano).
 * Garante imutabilidade pós-encerramento conforme CFM nº 1.821/2007 e RN06.
 * Regras: RF-07, US-09.
 */
export function SoapEditor({ atendimentoId, isReadOnly = false, token }: SoapEditorProps) {
  const { data: soapExistente, isLoading: isLoadingSoap } = useSoapEvolucao(atendimentoId, token);
  const { mutate: salvarSoap, isPending: isSaving } = useSalvarSoap(atendimentoId);
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<SoapFormData>({
    resolver: zodResolver(soapSchema),
    defaultValues: {
      anamnese: "",
      exame_fisico_virtual: "",
      cid10_principal: "",
      conduta: "",
    },
  });

  useEffect(() => {
    if (soapExistente) {
      reset({
        anamnese: soapExistente.anamnese,
        exame_fisico_virtual: soapExistente.exame_fisico_virtual || "",
        cid10_principal: soapExistente.cid10_principal || "",
        conduta: soapExistente.conduta,
      });
    }
  }, [soapExistente, reset]);

  const onSubmit = (formData: SoapFormData) => {
    if (isReadOnly) return;
    setMensagemSucesso(null);

    salvarSoap(
      {
        token,
        anamnese: formData.anamnese,
        exame_fisico_virtual: formData.exame_fisico_virtual || null,
        cid10_principal: formData.cid10_principal ? formData.cid10_principal.toUpperCase() : null,
        conduta: formData.conduta,
      },
      {
        onSuccess: () => {
          setMensagemSucesso("Evolução clínica SOAP salva com sucesso no PEP.");
          setTimeout(() => setMensagemSucesso(null), 4000);
        },
      },
    );
  };

  const handleCid10Change = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue("cid10_principal", e.target.value.toUpperCase());
  };

  return (
    <Card className="border-border">
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <FileText className="size-4 text-primary" />
            <span>Registro Clínico Estruturado (PEP SOAP)</span>
          </CardTitle>
          {isReadOnly && (
            <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground font-medium">
              Somente Leitura (Finalizado)
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {isLoadingSoap ? (
          <div className="flex items-center justify-center p-6 text-muted-foreground">
            <Loader2 className="size-5 animate-spin mr-2" />
            <span className="text-xs">Carregando notas SOAP…</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-3.5">
            {/* Subjetivo (S) */}
            <div className="space-y-1">
              <Label htmlFor="soap-anamnese" className="text-xs font-semibold text-foreground">
                Subjetivo (S) — Queixa e Anamnese Clínica:
              </Label>
              <Textarea
                id="soap-anamnese"
                placeholder="Descreva a queixa principal, evolução dos sintomas, histórico clínico e medicações em uso…"
                disabled={isReadOnly}
                className="text-xs min-h-[70px] resize-y"
                {...register("anamnese")}
              />
              {errors.anamnese && (
                <p className="text-[11px] text-destructive font-medium">
                  {errors.anamnese.message}
                </p>
              )}
            </div>

            {/* Objetivo (O) */}
            <div className="space-y-1">
              <Label htmlFor="soap-exame" className="text-xs font-semibold text-foreground">
                Objetivo (O) — Exame Físico Virtual / Telepropedêutica:
              </Label>
              <Textarea
                id="soap-exame"
                placeholder="Inspeção visual em vídeo, estado geral, padrão respiratório, fácies e telepropedêutica…"
                disabled={isReadOnly}
                className="text-xs min-h-[60px] resize-y"
                {...register("exame_fisico_virtual")}
              />
            </div>

            {/* Avaliação (A) - CID-10 */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="soap-cid10" className="text-xs font-semibold text-foreground">
                  Avaliação (A) — Diagnóstico Principal (CID-10):
                </Label>
                <span className="text-[10px] text-muted-foreground">Ex: J03.0, J00, A09</span>
              </div>
              <Input
                id="soap-cid10"
                placeholder="Código CID-10 (ex: J03.0)"
                disabled={isReadOnly}
                className="h-8 text-xs uppercase"
                {...register("cid10_principal")}
                onChange={handleCid10Change}
              />
              {errors.cid10_principal && (
                <p className="text-[11px] text-destructive font-medium">
                  {errors.cid10_principal.message}
                </p>
              )}
            </div>

            {/* Plano (P) */}
            <div className="space-y-1">
              <Label htmlFor="soap-conduta" className="text-xs font-semibold text-foreground">
                Plano (P) — Conduta Terapêutica e Orientações:
              </Label>
              <Textarea
                id="soap-conduta"
                placeholder="Prescrições médicas, orientações de isolamento, repouso e sinais de alerta para reavaliação…"
                disabled={isReadOnly}
                className="text-xs min-h-[70px] resize-y"
                {...register("conduta")}
              />
              {errors.conduta && (
                <p className="text-[11px] text-destructive font-medium">{errors.conduta.message}</p>
              )}
            </div>

            {mensagemSucesso && (
              <Alert className="py-2 text-xs border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200">
                <CheckCircle className="size-4 text-emerald-600 mr-2 inline" />
                <AlertDescription className="text-xs inline">{mensagemSucesso}</AlertDescription>
              </Alert>
            )}

            {!isReadOnly && (
              <Button
                type="submit"
                size="sm"
                disabled={isSaving}
                className="w-full text-xs font-medium h-8 gap-1.5"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    <span>Salvando Evolução…</span>
                  </>
                ) : (
                  <>
                    <Save className="size-3.5" />
                    <span>Salvar Evolução SOAP</span>
                  </>
                )}
              </Button>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}
