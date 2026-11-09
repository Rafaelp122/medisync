import { AlertCircle, FileCheck2, Loader2, Pill, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { DocumentoClinicoResponse, ItemPrescricaoRequest } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useEmitirDocumento } from "../api/use-emitir-documento";
import { usePrescricaoValidator } from "../api/use-prescricao-validator";

export interface PrescriptionBuilderProps {
  atendimentoId: string;
  identidadeVerificada: boolean;
  isReadOnly?: boolean;
  onPrescriptionIssued?: (doc: DocumentoClinicoResponse) => void;
  token?: string;
  duracaoSegundos?: number;
}

/**
 * Construtor de documentos clínicos digitais (Receita Digital e Atestado Médico).
 * Integra salvaguarda sanitária da Portaria SVS/MS 344/98 e trava temporal antifraude
 * para atestados com duração inferior a 180s sob a Resolução CFM nº 2.314/2022.
 * Regras: RF-07, US-10, CFM nº 2.314/2022.
 */
export function PrescriptionBuilder({
  atendimentoId,
  identidadeVerificada,
  isReadOnly = false,
  onPrescriptionIssued,
  token,
  duracaoSegundos,
}: PrescriptionBuilderProps) {
  const [tipoDocumento, setTipoDocumento] = useState<"RECEITA_SIMPLES" | "ATESTADO_MEDICO">(
    "RECEITA_SIMPLES",
  );
  const [justificativaTempoInferior, setJustificativaTempoInferior] = useState("");

  const [medicamento, setMedicamento] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [posologia, setPosologia] = useState("");
  const [duracao, setDuracao] = useState("");
  const [controleEspecial, setControleEspecial] = useState(false);

  const [itens, setItens] = useState<ItemPrescricaoRequest[]>([]);
  const [erroSanitario, setErroSanitario] = useState<string | null>(null);
  const [sucessoEmissao, setSucessoEmissao] = useState<string | null>(null);

  const { mutate: validarMedicamento, isPending: isValidating } =
    usePrescricaoValidator(atendimentoId);
  const { mutate: emitirDocumento, isPending: isEmitting } = useEmitirDocumento(atendimentoId);

  const isAtestado = tipoDocumento === "ATESTADO_MEDICO";
  const duracaoConsulta = duracaoSegundos ?? 0;
  const exigeJustificativa = isAtestado && duracaoConsulta < 180;
  const justificativaValida = !exigeJustificativa || justificativaTempoInferior.trim().length >= 15;

  const handleAdicionarItem = (e: React.FormEvent) => {
    e.preventDefault();
    if (isReadOnly) return;
    setErroSanitario(null);

    const medTrim = medicamento.trim();
    const dosagemTrim = dosagem.trim();
    const posologiaTrim = posologia.trim();

    if (!medTrim || !dosagemTrim || !posologiaTrim) {
      setErroSanitario("Preencha nome do medicamento, dosagem e posologia para adicionar.");
      return;
    }

    // Validação preliminar de salvaguardas farmacêuticas da Portaria SVS/MS 344/98
    validarMedicamento(
      { token, medicamento: medTrim },
      {
        onSuccess: (data) => {
          if (data.status === "PERMITIDO") {
            const novoItem: ItemPrescricaoRequest = {
              medicamento: medTrim,
              dosagem: dosagemTrim,
              posologia: posologiaTrim,
              duracao: duracao.trim() || undefined,
              controle_especial: controleEspecial,
            };
            setItens((prev) => [...prev, novoItem]);
            setMedicamento("");
            setDosagem("");
            setPosologia("");
            setDuracao("");
            setControleEspecial(false);
          }
        },
        onError: (err) => {
          // Erro com offending value interpolado
          const detail =
            err.detail ||
            `O medicamento '${medTrim}' exige talonário físico (Listas A/B da Portaria 344/98) e é proibido em telemedicina.`;
          setErroSanitario(detail);
        },
      },
    );
  };

  const handleRemoverItem = (index: number) => {
    if (isReadOnly) return;
    setItens((prev) => prev.filter((_, i) => i !== index));
  };

  const handleEmitirDocumento = () => {
    if (isReadOnly || !identidadeVerificada) return;
    setErroSanitario(null);
    setSucessoEmissao(null);

    if (!isAtestado && itens.length === 0) return;

    if (isAtestado && exigeJustificativa && !justificativaValida) {
      setErroSanitario(
        "A consulta durou menos de 180s. A justificativa médica circunstanciada deve conter no mínimo 15 caracteres (CFM nº 2.314/2022).",
      );
      return;
    }

    emitirDocumento(
      {
        token,
        tipo_documento: tipoDocumento,
        itens: isAtestado ? (itens.length > 0 ? itens : undefined) : itens,
        justificativa_tempo_inferior:
          isAtestado && exigeJustificativa ? justificativaTempoInferior.trim() : undefined,
      },
      {
        onSuccess: (doc) => {
          setSucessoEmissao(
            isAtestado
              ? `Atestado médico #${doc.id.substring(0, 8)} gerado com sucesso. Prossiga para assinatura ICP-Brasil.`
              : `Receita digital #${doc.id.substring(0, 8)} gerada com sucesso. Prossiga para assinatura ICP-Brasil.`,
          );
          if (!isAtestado) {
            setItens([]);
          }
          setJustificativaTempoInferior("");
          onPrescriptionIssued?.(doc);
        },
        onError: (err) => {
          setErroSanitario(err.detail || "Erro ao emitir documento clínico digital.");
        },
      },
    );
  };

  return (
    <Card className="border-border">
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Pill className="size-4 text-primary" />
            <span>
              {isAtestado
                ? "Atestado Médico & Justificativa Legal"
                : "Prescrição Digital & Salvaguardas Farmacêuticas"}
            </span>
          </CardTitle>
          <span className="text-[11px] text-muted-foreground">
            {isAtestado ? "CFM nº 2.314/2022" : "Portaria SVS/MS 344/98"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3.5">
        {/* Seletor do Tipo de Documento */}
        {!isReadOnly && (
          <div
            role="tablist"
            aria-label="Tipo de documento clínico"
            className="flex items-center gap-1 p-1 bg-muted rounded-md"
          >
            <button
              type="button"
              role="tab"
              aria-selected={!isAtestado}
              onClick={() => {
                setTipoDocumento("RECEITA_SIMPLES");
                setErroSanitario(null);
              }}
              className={cn(
                "flex-1 py-1 px-2.5 rounded text-xs font-medium transition-[background-color,color,box-shadow]",
                !isAtestado
                  ? "bg-background text-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Receita Simples
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isAtestado}
              onClick={() => {
                setTipoDocumento("ATESTADO_MEDICO");
                setErroSanitario(null);
              }}
              className={cn(
                "flex-1 py-1 px-2.5 rounded text-xs font-medium transition-[background-color,color,box-shadow]",
                isAtestado
                  ? "bg-background text-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Atestado Médico
            </button>
          </div>
        )}

        {/* Alerta de erro sanitário / substância proibida com offending value */}
        {erroSanitario && (
          <Alert variant="destructive" className="py-2 text-xs">
            <AlertCircle className="size-4" />
            <AlertTitle className="text-xs font-semibold">Bloqueio Sanitário Legal</AlertTitle>
            <AlertDescription className="text-xs">{erroSanitario}</AlertDescription>
          </Alert>
        )}

        {/* Mensagem de sucesso de emissão */}
        {sucessoEmissao && (
          <Alert className="py-2 text-xs border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200">
            <FileCheck2 className="size-4 text-emerald-600 mr-2 inline" />
            <AlertDescription className="text-xs inline">{sucessoEmissao}</AlertDescription>
          </Alert>
        )}

        {isAtestado ? (
          <div className="space-y-3">
            {exigeJustificativa && (
              <div className="space-y-1.5 p-2.5 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200">
                <div className="flex items-center gap-1.5 text-xs font-semibold">
                  <AlertCircle className="size-3.5 text-amber-600 dark:text-amber-400" />
                  <span>Trava Temporal Antifraude (CFM nº 2.314/2022)</span>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  A consulta durou {duracaoConsulta}s (inferior ao piso de 180s). É mandatória a
                  justificativa médica circunstanciando a emissão célere de atestado (mínimo de 15
                  caracteres).
                </p>
                <div className="space-y-1 pt-1">
                  <Label htmlFor="justificativa-tempo-inferior" className="text-xs">
                    Justificativa Médica:
                  </Label>
                  <Textarea
                    id="justificativa-tempo-inferior"
                    placeholder="Descreva a justificativa clínica circunstanciada para emissão em tempo inferior a 180s (mínimo 15 caracteres)..."
                    value={justificativaTempoInferior}
                    onChange={(e) => setJustificativaTempoInferior(e.target.value)}
                    className="text-xs min-h-[60px]"
                    disabled={isReadOnly}
                  />
                  {justificativaTempoInferior.trim().length > 0 &&
                    justificativaTempoInferior.trim().length < 15 && (
                      <p className="text-[11px] text-destructive">
                        Mínimo de 15 caracteres (atual: {justificativaTempoInferior.trim().length})
                      </p>
                    )}
                </div>
              </div>
            )}
            {!exigeJustificativa && (
              <p className="text-xs text-muted-foreground italic py-1">
                Emissão de atestado médico de afastamento com carimbo temporal e assinatura
                qualificada ICP-Brasil.
              </p>
            )}
          </div>
        ) : (
          <>
            {/* Formulário de adição de item */}
            {!isReadOnly && (
              <form
                onSubmit={handleAdicionarItem}
                className="space-y-2.5 p-2.5 rounded-md bg-muted/30 border border-border"
              >
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="item-medicamento" className="text-xs">
                      Medicamento / Princípio Ativo:
                    </Label>
                    <Input
                      id="item-medicamento"
                      placeholder="Ex: Amoxicilina 500mg"
                      value={medicamento}
                      onChange={(e) => setMedicamento(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>

                  <div className="space-y-1">
                    <Label htmlFor="item-dosagem" className="text-xs">
                      Dosagem:
                    </Label>
                    <Input
                      id="item-dosagem"
                      placeholder="Ex: 500mg, 1 cp"
                      value={dosagem}
                      onChange={(e) => setDosagem(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="item-posologia" className="text-xs">
                      Posologia (Instruções):
                    </Label>
                    <Input
                      id="item-posologia"
                      placeholder="Ex: 1 cápsula de 8 em 8 horas"
                      value={posologia}
                      onChange={(e) => setPosologia(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>

                  <div className="space-y-1">
                    <Label htmlFor="item-duracao" className="text-xs">
                      Duração (Opcional):
                    </Label>
                    <Input
                      id="item-duracao"
                      placeholder="Ex: 7 dias"
                      value={duracao}
                      onChange={(e) => setDuracao(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <Label className="flex items-center gap-1.5 cursor-pointer text-xs font-normal">
                    <input
                      type="checkbox"
                      checked={controleEspecial}
                      onChange={(e) => setControleEspecial(e.target.checked)}
                      className="size-3.5"
                    />
                    <span>Controle Especial (Lista C1)</span>
                  </Label>

                  <Button
                    type="submit"
                    size="sm"
                    variant="secondary"
                    disabled={isValidating}
                    className="h-7 text-xs gap-1"
                  >
                    {isValidating ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <Plus className="size-3" />
                    )}
                    <span>Adicionar à Receita</span>
                  </Button>
                </div>
              </form>
            )}

            {/* Tabela de itens inseridos */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-foreground">
                  Itens da Prescrição ({itens.length}):
                </span>
              </div>

              {itens.length === 0 ? (
                <p className="text-xs text-muted-foreground italic py-2">
                  Nenhum medicamento adicionado à receita até o momento.
                </p>
              ) : (
                <div className="divide-y divide-border border border-border rounded-md overflow-hidden text-xs">
                  {itens.map((item, idx) => (
                    <div
                      key={`${item.medicamento}-${item.dosagem}-${item.posologia}`}
                      className="flex items-center justify-between p-2 hover:bg-muted/30"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">{item.medicamento}</span>
                          <span className="text-muted-foreground">({item.dosagem})</span>
                          {item.controle_especial && (
                            <Badge variant="warning" className="text-[10px] py-0 px-1">
                              Controle Especial C1
                            </Badge>
                          )}
                        </div>
                        <p className="text-muted-foreground text-[11px]">
                          {item.posologia} {item.duracao ? `• Duração: ${item.duracao}` : ""}
                        </p>
                      </div>
                      {!isReadOnly && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoverItem(idx)}
                          aria-label={`Remover ${item.medicamento}`}
                          className="size-7 p-0 text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* Alerta explicativo se a identidade não estiver confirmada */}
        {!identidadeVerificada && !isReadOnly && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2 rounded border border-amber-200 dark:border-amber-800">
            A emissão da receita digital está bloqueada até a conclusão da conferência visual de
            identidade oficial (RG/CNH/CNS) sob o CFM nº 2.314/2022.
          </p>
        )}

        {/* Botão de Emissão */}
        {!isReadOnly && (
          <Button
            type="button"
            size="sm"
            onClick={handleEmitirDocumento}
            disabled={
              !identidadeVerificada ||
              isEmitting ||
              (!isAtestado && itens.length === 0) ||
              (isAtestado && exigeJustificativa && !justificativaValida)
            }
            className="w-full text-xs font-medium h-8 gap-1.5"
          >
            {isEmitting ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span>{isAtestado ? "Emitindo Atestado…" : "Emitindo Prescrição…"}</span>
              </>
            ) : (
              <>
                <FileCheck2 className="size-3.5" />
                <span>{isAtestado ? "Emitir Atestado Médico" : "Emitir Prescrição Digital"}</span>
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
