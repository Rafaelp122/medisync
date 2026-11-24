import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle, FileText, Loader2, Save } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSalvarSoap, useSoapEvolucao } from "../api/use-soap-evolucao";
import { useOptionalConsultationEncounter } from "../context/consultation-encounter-provider";
import {
  type CfmIdentityGateData,
  type SoapFormData,
  type SoapInputFormData,
  soapSchema,
} from "../schemas/consultation-schema";

export interface SoapEditorProps {
  atendimentoId: string;
  accessMode?: "editable" | "readonly";
  token?: string;
  dadosIdentidade?: CfmIdentityGateData | null;
}

/**
 * Editor estruturado de evolução clínica PEP no padrão SOAP (Subjetivo, Objetivo, Avaliação, Plano).
 * Propaga `shouldValidate`/`shouldDirty` no CID-10 e consome `ConsultationEncounterProvider`.
 * Regras: RF-07, US-09, CFM nº 1.821/2007 e CFM nº 2.314/2022.
 */
export function SoapEditor({ atendimentoId, accessMode, token, dadosIdentidade }: SoapEditorProps) {
  const encounter = useOptionalConsultationEncounter();
  const isLocked =
    (accessMode ?? (encounter?.isFinalizado ? "readonly" : "editable")) === "readonly";
  const resolvedToken = token ?? encounter?.atendimento.token;
  const resolvedIdentity = dadosIdentidade ?? encounter?.dadosIdentidade ?? null;

  const { data: soapExistente, isLoading: isLoadingSoap } = useSoapEvolucao(
    atendimentoId,
    resolvedToken,
  );
  const { mutate: salvarSoap, isPending: isSaving } = useSalvarSoap(atendimentoId);
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (successTimerRef.current) {
        clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<SoapInputFormData, unknown, SoapFormData>({
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
    if (isLocked) return;
    if (successTimerRef.current) {
      clearTimeout(successTimerRef.current);
      successTimerRef.current = null;
    }
    setMensagemSucesso(null);

    salvarSoap(
      {
        token: resolvedToken,
        anamnese: formData.anamnese,
        exame_fisico_virtual: formData.exame_fisico_virtual || null,
        cid10_principal: formData.cid10_principal ? formData.cid10_principal.toUpperCase() : null,
        conduta: formData.conduta,
        identidade_verificada:
          resolvedIdentity?.identidade_verificada ?? soapExistente?.identidade_verificada ?? false,
        tipo_documento_verificado:
          resolvedIdentity?.tipo_documento_apresentado ??
          (soapExistente?.tipo_documento_verificado as
            | CfmIdentityGateData["tipo_documento_apresentado"]
            | undefined) ??
          null,
        justificativa_excecao_identidade:
          resolvedIdentity?.justificativa_excecao ??
          soapExistente?.justificativa_excecao_identidade ??
          null,
      },
      {
        onSuccess: () => {
          setMensagemSucesso("Evolução clínica SOAP salva com sucesso no PEP.");
          successTimerRef.current = setTimeout(() => {
            setMensagemSucesso(null);
            successTimerRef.current = null;
          }, 4000);
        },
      },
    );
  };

  const handleCid10Change = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue("cid10_principal", e.target.value.toUpperCase(), {
      shouldValidate: true,
      shouldDirty: true,
    });
  };

  return (
    <Card className="border-border">
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <FileText className="size-4 text-primary" />
            <span>Registro Clínico Estruturado (PEP SOAP)</span>
          </CardTitle>
          {isLocked && (
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
            <div className="space-y-1">
              <Label htmlFor="soap-anamnese" className="text-xs font-semibold text-foreground">
                Subjetivo (S) — Queixa e Anamnese Clínica:
              </Label>
              <Textarea
                id="soap-anamnese"
                placeholder="Descreva a queixa principal, evolução dos sintomas, histórico clínico e medicações em uso…"
                disabled={isLocked}
                className="text-xs min-h-[70px] resize-y"
                {...register("anamnese")}
              />
              {errors.anamnese && (
                <p className="text-[11px] text-destructive font-medium">
                  {errors.anamnese.message}
                </p>
              )}
            </div>

            <div className="space-y-1">
              <Label htmlFor="soap-exame" className="text-xs font-semibold text-foreground">
                Objetivo (O) — Exame Físico Virtual / Telepropedêutica:
              </Label>
              <Textarea
                id="soap-exame"
                placeholder="Inspeção visual em vídeo, estado geral, padrão respiratório, fácies e telepropedêutica…"
                disabled={isLocked}
                className="text-xs min-h-[60px] resize-y"
                {...register("exame_fisico_virtual")}
              />
            </div>

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
                disabled={isLocked}
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

            <div className="space-y-1">
              <Label htmlFor="soap-conduta" className="text-xs font-semibold text-foreground">
                Plano (P) — Conduta Terapêutica e Orientações:
              </Label>
              <Textarea
                id="soap-conduta"
                placeholder="Prescrições médicas, orientações de isolamento, repouso e sinais de alerta para reavaliação…"
                disabled={isLocked}
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

            {!isLocked && (
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
