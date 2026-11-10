import { Loader2, Plus } from "lucide-react";
import { useState } from "react";
import type { ItemPrescricaoRequest } from "@/api/generated/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePrescricaoValidator } from "../../api/use-prescricao-validator";

export interface PrescriptionFormProps {
  atendimentoId: string;
  token?: string;
  isReadOnly?: boolean;
  onAddItem: (item: ItemPrescricaoRequest) => void;
  onError: (erro: string | null) => void;
}

/**
 * Formulário de inclusão de medicamentos e validação sanitária (Portaria SVS/MS 344/98).
 * Regras: RF-07, CFM nº 2.314/2022.
 */
export function PrescriptionForm({
  atendimentoId,
  token,
  isReadOnly = false,
  onAddItem,
  onError,
}: PrescriptionFormProps) {
  const [medicamento, setMedicamento] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [posologia, setPosologia] = useState("");
  const [duracao, setDuracao] = useState("");
  const [controleEspecial, setControleEspecial] = useState(false);

  const { mutate: validarMedicamento, isPending: isValidating } =
    usePrescricaoValidator(atendimentoId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isReadOnly) return;
    onError(null);

    const medTrim = medicamento.trim();
    const dosagemTrim = dosagem.trim();
    const posologiaTrim = posologia.trim();

    if (!medTrim || !dosagemTrim || !posologiaTrim) {
      onError("Preencha nome do medicamento, dosagem e posologia para adicionar.");
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
            onAddItem(novoItem);
            setMedicamento("");
            setDosagem("");
            setPosologia("");
            setDuracao("");
            setControleEspecial(false);
          }
        },
        onError: (err) => {
          const detail =
            err.detail ||
            `O medicamento '${medTrim}' exige talonário físico (Listas A/B da Portaria 344/98) e é proibido em telemedicina.`;
          onError(detail);
        },
      },
    );
  };

  if (isReadOnly) return null;

  return (
    <form
      onSubmit={handleSubmit}
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
          {isValidating ? <Loader2 className="size-3 animate-spin" /> : <Plus className="size-3" />}
          <span>Adicionar à Receita</span>
        </Button>
      </div>
    </form>
  );
}
