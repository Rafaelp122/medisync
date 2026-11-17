import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, Loader2, Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { getHumanizedErrorMessage } from "@/api/errors";
import type { DisponibilidadeResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DIAS_SEMANA_OPCOES } from "@/lib/formatters";
import { useCadastrarDisponibilidade } from "../api/use-agenda-profissional";
import {
  type CriarDisponibilidadeFormData,
  criarDisponibilidadeFormSchema,
} from "../schemas/scheduling-schema";

export interface DisponibilidadeFormDialogProps {
  token?: string;
  onSuccess?: (disponibilidade: DisponibilidadeResponse) => void;
}

const SELECT_CLASSES =
  "flex min-h-[44px] h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background transition-[border-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm";

/**
 * Modal com formulário validado via Zod para cadastro de janela semanal de agenda do profissional.
 */
export function DisponibilidadeFormDialog({ token, onSuccess }: DisponibilidadeFormDialogProps) {
  const [open, setOpen] = useState(false);

  const {
    mutate: cadastrarDisponibilidade,
    isPending,
    error,
    reset: resetMutation,
  } = useCadastrarDisponibilidade();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CriarDisponibilidadeFormData>({
    resolver: zodResolver(criarDisponibilidadeFormSchema),
    defaultValues: {
      especialidade: "PSICOLOGIA",
      dia_semana: 0,
      hora_inicio: "08:00",
      hora_fim: "12:00",
      duracao_minutos: 50,
    },
  });

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      resetMutation();
    }
  };

  const onSubmit = (data: CriarDisponibilidadeFormData) => {
    cadastrarDisponibilidade(
      { body: data, token },
      {
        onSuccess: (created) => {
          reset();
          setOpen(false);
          onSuccess?.(created);
        },
      },
    );
  };

  const erroHumanizado = error ? getHumanizedErrorMessage(error) : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className="min-h-[44px] gap-1.5">
          <Plus className="size-4" aria-hidden="true" />
          <span>Cadastrar Disponibilidade</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cadastrar Janela de Disponibilidade</DialogTitle>
          <DialogDescription>
            Defina o dia da semana, faixa horária e duração padrão de cada atendimento programado.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {erroHumanizado && (
            <Alert variant="destructive" role="alert">
              <AlertCircle className="size-4" aria-hidden="true" />
              <AlertTitle>{erroHumanizado.title}</AlertTitle>
              <AlertDescription>{erroHumanizado.detail}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="disp-especialidade">Especialidade</Label>
            <select
              id="disp-especialidade"
              className={SELECT_CLASSES}
              aria-invalid={Boolean(errors.especialidade)}
              {...register("especialidade")}
            >
              <option value="PSICOLOGIA">Psicologia</option>
              <option value="NUTRICAO">Nutrição</option>
            </select>
            {errors.especialidade && (
              <p className="text-xs text-destructive">{errors.especialidade.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="disp-dia-semana">Dia da semana</Label>
            <select
              id="disp-dia-semana"
              className={SELECT_CLASSES}
              aria-invalid={Boolean(errors.dia_semana)}
              {...register("dia_semana", { valueAsNumber: true })}
            >
              {DIAS_SEMANA_OPCOES.map((dia) => (
                <option key={dia.valor} value={dia.valor}>
                  {dia.label}
                </option>
              ))}
            </select>
            {errors.dia_semana && (
              <p className="text-xs text-destructive">{errors.dia_semana.message}</p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="disp-hora-inicio">Horário inicial</Label>
              <Input
                id="disp-hora-inicio"
                type="time"
                aria-invalid={Boolean(errors.hora_inicio)}
                {...register("hora_inicio")}
              />
              {errors.hora_inicio && (
                <p className="text-xs text-destructive">{errors.hora_inicio.message}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="disp-hora-fim">Horário final</Label>
              <Input
                id="disp-hora-fim"
                type="time"
                aria-invalid={Boolean(errors.hora_fim)}
                {...register("hora_fim")}
              />
              {errors.hora_fim && (
                <p className="text-xs text-destructive">{errors.hora_fim.message}</p>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="disp-duracao-minutos">Duração do atendimento (minutos)</Label>
            <Input
              id="disp-duracao-minutos"
              type="number"
              min={15}
              max={120}
              aria-invalid={Boolean(errors.duracao_minutos)}
              {...register("duracao_minutos", { valueAsNumber: true })}
            />
            {errors.duracao_minutos && (
              <p className="text-xs text-destructive">{errors.duracao_minutos.message}</p>
            )}
          </div>

          <DialogFooter className="gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={isPending}
              onClick={() => handleOpenChange(false)}
              className="min-h-[44px]"
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending} className="min-h-[44px] gap-1.5">
              {isPending && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
              <span>{isPending ? "Salvando…" : "Salvar Disponibilidade"}</span>
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
