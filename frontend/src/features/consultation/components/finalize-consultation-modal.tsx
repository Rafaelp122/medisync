import { AlertCircle, CheckCircle, KeyRound, Loader2, Lock } from "lucide-react";
import { useState } from "react";
import type { DocumentoClinicoResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { env } from "@/config/env";
import { useAssinarDocumento } from "../api/use-assinar-documento";
import { useFinalizarConsulta } from "../api/use-finalizar-consulta";

export interface FinalizeConsultationModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  atendimentoId: string;
  identidadeVerificada: boolean;
  documentoPendente?: DocumentoClinicoResponse | null;
  onFinalized?: () => void;
  token?: string;
}

/**
 * Modal de finalização formal da teleconsulta e aplicação de assinatura ICP-Brasil.
 * Trava o prontuário em modo imutável (CFM nº 1.821/2007) e bloqueia se a identidade não foi verificada (CFM 2.314).
 * Regras: RF-07, RF-08, US-09, US-10.
 */
export function FinalizeConsultationModal({
  open,
  onOpenChange,
  atendimentoId,
  identidadeVerificada,
  documentoPendente,
  onFinalized,
  token,
}: FinalizeConsultationModalProps) {
  const [pscToken, setPscToken] = useState(env.isDemoMode ? "demo-psc-token-123" : "");
  const [pscProvider, setPscProvider] = useState(env.defaultPscProvider);
  const [documentoAssinado, setDocumentoAssinado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const { mutate: assinarDocumento, isPending: isSigning } = useAssinarDocumento(atendimentoId);
  const { mutate: finalizarConsulta, isPending: isFinalizing } =
    useFinalizarConsulta(atendimentoId);

  const precisaAssinar = Boolean(
    documentoPendente && !documentoPendente.assinado_em && !documentoAssinado,
  );

  const handleAssinarDocumento = () => {
    if (!documentoPendente || !pscToken.trim()) {
      setErro("Informe o token de autorização emitido pelo seu provedor PSC.");
      return;
    }
    setErro(null);

    assinarDocumento(
      {
        token,
        documento_id: documentoPendente.id,
        payload: {
          token: pscToken.trim(),
          provider: pscProvider,
        },
      },
      {
        onSuccess: () => {
          setDocumentoAssinado(true);
          setPscToken("");
        },
        onError: (err) => {
          setErro(err.detail || "Falha na assinatura digital ICP-Brasil via PSC.");
        },
      },
    );
  };

  const handleConfirmarFinalizacao = () => {
    if (!identidadeVerificada) {
      setErro("A conferência de identidade oficial com foto é obrigatória (CFM nº 2.314/2022).");
      return;
    }
    if (precisaAssinar) {
      setErro("Assine digitalmente a receita antes de finalizar a consulta.");
      return;
    }
    setErro(null);

    finalizarConsulta(
      { token },
      {
        onSuccess: () => {
          onFinalized?.();
          onOpenChange(false);
        },
        onError: (err) => {
          setErro(err.detail || "Erro ao finalizar consulta.");
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Lock className="size-5 text-primary" />
            <span>Concluir Atendimento Clínico</span>
          </DialogTitle>
          <DialogDescription>
            O encerramento tornará todos os registros do prontuário (SOAP e documentos)
            juridicamente imutáveis conforme a CFM nº 1.821/2007.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2 text-xs">
          {/* Bloqueio se identidade não verificada */}
          {!identidadeVerificada && (
            <Alert variant="destructive">
              <AlertCircle className="size-4" />
              <AlertTitle className="font-semibold text-xs">Bloqueio Ético Regulatório</AlertTitle>
              <AlertDescription className="text-xs">
                A conferência visual de documento oficial com foto (RG/CNH/CNS) sob a Resolução CFM
                nº 2.314/2022 não foi concluída. Feche este modal e confirme a identidade na coluna
                de mídia antes de finalizar.
              </AlertDescription>
            </Alert>
          )}

          {/* Etapa de Assinatura Digital ICP-Brasil se houver receita emitida */}
          {precisaAssinar && identidadeVerificada && (
            <div className="p-3 rounded-lg border border-border bg-muted/40 space-y-3">
              <div className="flex items-center gap-2 font-semibold text-foreground">
                <KeyRound className="size-4 text-primary" />
                <span>Assinatura Digital ICP-Brasil (PAdES em Nuvem)</span>
              </div>
              <p className="text-muted-foreground">
                Existe uma receita digital emitida aguardando assinatura com certificado digital.
              </p>

              <div className="space-y-2">
                <div className="space-y-1">
                  <Label htmlFor="psc-provider" className="text-xs">
                    Provedor PSC:
                  </Label>
                  <select
                    id="psc-provider"
                    value={pscProvider}
                    onChange={(e) => {
                      const novo = e.target.value;
                      setPscProvider(novo);
                      if (novo === "fake" && env.isDemoMode) {
                        setPscToken("demo-psc-token-123");
                      }
                    }}
                    className="w-full h-8 px-2 rounded-md border border-input bg-background text-xs"
                  >
                    {env.isDemoMode && (
                      <option value="fake">Simulador ICP-Brasil (Ambiente de Testes / Demo)</option>
                    )}
                    <option value="birdid">BirdID (Soluti)</option>
                    <option value="safeid">SafeID (Certisign)</option>
                    <option value="vidaas">VIDaaS (Valid)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="psc-token" className="text-xs">
                      Token OAuth2 / OTP do PSC:
                    </Label>
                    {env.isDemoMode && pscProvider === "fake" && (
                      <button
                        type="button"
                        onClick={() => setPscToken("demo-psc-token-123")}
                        className="text-[10px] text-primary hover:underline cursor-pointer"
                      >
                        Preencher Token Demo
                      </button>
                    )}
                  </div>
                  <Input
                    id="psc-token"
                    type="password"
                    placeholder="Cole seu token de autorização do PSC"
                    value={pscToken}
                    onChange={(e) => setPscToken(e.target.value)}
                    className="h-8 text-xs font-mono"
                  />
                </div>

                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={handleAssinarDocumento}
                  disabled={isSigning || !pscToken.trim()}
                  className="w-full text-xs h-8 gap-1.5"
                >
                  {isSigning ? (
                    <>
                      <Loader2 className="size-3.5 animate-spin" />
                      <span>Assinando via PSC…</span>
                    </>
                  ) : (
                    <>
                      <KeyRound className="size-3.5" />
                      <span>Assinar Documento Digitalmente</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}

          {documentoAssinado && (
            <Alert className="py-2 text-xs border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200">
              <CheckCircle className="size-4 text-emerald-600 mr-2 inline" />
              <AlertDescription className="text-xs inline">
                Documento clínico assinado digitalmente com sucesso (ICP-Brasil PAdES).
              </AlertDescription>
            </Alert>
          )}

          {erro && (
            <Alert variant="destructive" className="py-2 text-xs">
              <AlertCircle className="size-4" />
              <AlertDescription className="text-xs">{erro}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs h-8"
          >
            Cancelar
          </Button>

          <Button
            type="button"
            size="sm"
            onClick={handleConfirmarFinalizacao}
            disabled={!identidadeVerificada || precisaAssinar || isFinalizing}
            className="text-xs font-medium h-8 gap-1.5 bg-primary text-primary-foreground"
          >
            {isFinalizing ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span>Finalizando…</span>
              </>
            ) : (
              <>
                <Lock className="size-3.5" />
                <span>Confirmar Encerramento e Travar PEP</span>
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
