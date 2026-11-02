import { AlertCircle, CheckCircle2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type CfmIdentityGateData, cfmIdentityGateSchema } from "../schemas/consultation-schema";

export interface CfmIdentityGateProps {
  onVerificationChange: (isVerified: boolean, data?: CfmIdentityGateData) => void;
  isReadOnly?: boolean;
}

/**
 * Gate de Segurança Camada 2 — Conferência Visual de Identidade sob CFM nº 2.314/2022.
 * Exige conferência visual de documento oficial com foto (RG/CNH/CNS) ou justificativa de emergência
 * antes de destravar a emissão de prescrição digital e finalização da consulta.
 */
export function CfmIdentityGate({
  onVerificationChange,
  isReadOnly = false,
}: CfmIdentityGateProps) {
  const [tipoDocumento, setTipoDocumento] = useState<"RG" | "CNH" | "CNS" | "">("RG");
  const [isEmergencia, setIsEmergencia] = useState(false);
  const [justificativa, setJustificativa] = useState("");
  const [verificado, setVerificado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const handleConfirmar = () => {
    setErro(null);

    const payload: CfmIdentityGateData = {
      identidade_verificada: true,
      tipo_documento_apresentado: isEmergencia
        ? null
        : (tipoDocumento as "RG" | "CNH" | "CNS") || null,
      justificativa_excecao: isEmergencia ? justificativa.trim() : null,
    };

    const parseResult = cfmIdentityGateSchema.safeParse(payload);
    if (!parseResult.success) {
      const msg =
        parseResult.error.issues[0]?.message ||
        "Selecione um documento válido ou insira justificativa detalhada.";
      setErro(msg);
      return;
    }

    setVerificado(true);
    onVerificationChange(true, payload);
  };

  const handleRevogar = () => {
    if (isReadOnly) return;
    setVerificado(false);
    onVerificationChange(false);
  };

  return (
    <Card className="border-border">
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ShieldAlert className="size-4 text-primary" />
            <span>Conferência Visual de Identidade (CFM nº 2.314/2022)</span>
          </CardTitle>
          {verificado ? (
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
              <CheckCircle2 className="size-3.5" />
              Identidade Confirmada
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-600 bg-amber-50 dark:bg-amber-950/40 px-2 py-0.5 rounded-full border border-amber-200 dark:border-amber-800">
              <AlertCircle className="size-3.5" />
              Conferência Obrigatória
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3 text-xs">
        {verificado ? (
          <div className="flex items-center justify-between p-2.5 rounded-md bg-muted/60 text-muted-foreground">
            <div>
              <p className="font-medium text-foreground">
                {isEmergencia
                  ? "Liberado por Exceção Ética de Urgência / Emergência"
                  : `Documento com foto conferido em vídeo: ${tipoDocumento}`}
              </p>
              {isEmergencia && justificativa && (
                <p className="text-[11px] italic mt-0.5 line-clamp-1">
                  Justificativa: {justificativa}
                </p>
              )}
            </div>
            {!isReadOnly && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleRevogar}
                className="text-xs h-7 px-2 text-muted-foreground hover:text-foreground"
              >
                Alterar
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-muted-foreground">
              Solicite ao paciente que posicione o documento oficial com foto (RG, CNH ou CNS) em
              frente à câmera para validação antes de emitir receitas ou concluir o atendimento.
            </p>

            <div className="flex items-center gap-4">
              <Label className="flex items-center gap-1.5 cursor-pointer text-xs font-normal">
                <input
                  type="radio"
                  name="opcao-identidade"
                  checked={!isEmergencia}
                  onChange={() => setIsEmergencia(false)}
                  disabled={isReadOnly}
                  className="size-3.5"
                />
                <span>Documento com Foto</span>
              </Label>

              <Label className="flex items-center gap-1.5 cursor-pointer text-xs font-normal">
                <input
                  type="radio"
                  name="opcao-identidade"
                  checked={isEmergencia}
                  onChange={() => setIsEmergencia(true)}
                  disabled={isReadOnly}
                  className="size-3.5"
                />
                <span>Exceção Médica de Emergência</span>
              </Label>
            </div>

            {!isEmergencia ? (
              <div className="flex items-center gap-3 pt-1">
                <span className="text-muted-foreground">Tipo de documento:</span>
                {(["RG", "CNH", "CNS"] as const).map((doc) => (
                  <Label key={doc} className="flex items-center gap-1 cursor-pointer font-normal">
                    <input
                      type="radio"
                      name="tipo-doc"
                      value={doc}
                      checked={tipoDocumento === doc}
                      onChange={(e) => setTipoDocumento(e.target.value as "RG" | "CNH" | "CNS")}
                      disabled={isReadOnly}
                      className="size-3"
                    />
                    <span>{doc}</span>
                  </Label>
                ))}
              </div>
            ) : (
              <div className="space-y-1.5 pt-1">
                <Label htmlFor="justificativa-emergencia" className="text-xs">
                  Justificativa formal da exceção clínica (mínimo 10 caracteres):
                </Label>
                <Input
                  id="justificativa-emergencia"
                  placeholder="Ex: Paciente inconsciente ou em trauma grave"
                  value={justificativa}
                  onChange={(e) => setJustificativa(e.target.value)}
                  disabled={isReadOnly}
                  className="h-8 text-xs"
                />
              </div>
            )}

            {erro && (
              <Alert variant="destructive" className="py-2 text-xs">
                <AlertTitle className="text-xs font-semibold">Validação Pendente</AlertTitle>
                <AlertDescription className="text-xs">{erro}</AlertDescription>
              </Alert>
            )}

            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={handleConfirmar}
              disabled={isReadOnly}
              className="w-full text-xs font-medium h-8"
            >
              Confirmar Conferência Visual de Identidade
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
