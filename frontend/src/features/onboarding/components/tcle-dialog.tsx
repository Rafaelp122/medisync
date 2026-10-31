import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export const TEXTO_TCLE_PADRAO = `TERMO DE CONSENTIMENTO LIVRE E ESCLARECIDO (TCLE) — TELEMEDICINA
MEDISYNC EXPRESS / RESOLUÇÃO CFM Nº 2.314/2022 E LEI Nº 13.709/2018 (LGPD)

1. NATUREZA DO ATENDIMENTO TELEMÉDICO:
Declaro estar ciente de que esta consulta será realizada por meio de tecnologias de informação e comunicação à distância (telemedicina), nos termos da Resolução CFM nº 2.314/2022. Fui informado(a) de que a teleconsulta possui limitações inerentes à ausência de exame físico presencial (palpação, ausculta e percussão direta).

2. AUTONOMIA E CONVERSÃO EM ATENDIMENTO PRESENCIAL:
Reconheço que tanto eu quanto o médico assistente temos a prerrogativa e autonomia de interromper a teleconsulta a qualquer momento caso seja identificada a necessidade de exame físico presencial, propedêutica armada ou diante de qualquer situação de instabilidade clínica ou urgência.

3. SITUAÇÕES DE EMERGÊNCIA CRÍTICA:
Fui expressamente orientado(a) de que o serviço de teleatendimento NÃO é voltado a emergências médicas com risco iminente de morte (tais como dor torácica aguda opressiva, perda súbita de consciência, parada cardiorrespiratória ou insuficiência respiratória grave). Em tais eventualidades, comprometo-me a acionar imediatamente o SAMU pelo número 192 ou dirigir-me ao serviço pré-hospitalar/hospitalar mais próximo.

4. PRIVACIDADE E PROTEÇÃO DE DADOS (LGPD):
Autorizo expressamente o tratamento dos meus dados pessoais de identificação civil e dados sensíveis de saúde pelo MediSync Express, exclusivamente para fins de triagem clínica, prontuário médico eletrônico, faturamento, emissão de receitas/atestados e auditoria sanitária, com fundamento no Art. 11 da Lei Geral de Proteção de Dados (LGPD).

5. REGISTRO IMUTÁVEL DO CONSENTIMENTO:
Estou ciente de que o aceite deste termo gera um carimbo temporal UTC e uma assinatura hash criptográfica SHA-256 vinculada de forma irretratável ao meu prontuário assistencial (RN07).`;

export interface TcleDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TcleDialog({ open, onOpenChange }: TcleDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Termo de Consentimento Livre e Esclarecido (TCLE)</DialogTitle>
          <DialogDescription>
            Conformidade obrigatória com a Resolução CFM nº 2.314/2022 e a LGPD.
          </DialogDescription>
        </DialogHeader>

        <section
          aria-label="Texto integral do TCLE"
          className="flex-1 overflow-y-auto rounded-md border p-4 bg-muted/40 font-mono text-xs leading-relaxed whitespace-pre-wrap select-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {TEXTO_TCLE_PADRAO}
        </section>

        <DialogFooter className="pt-2">
          <DialogClose asChild>
            <Button type="button" variant="default" className="w-full sm:w-auto">
              Entendido e Ciente
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
