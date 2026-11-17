import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Loader2, UserPlus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { extractProblemDetail } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useCreateDependent } from "@/features/citizen/api/use-dependents";
import {
  type DependenteFormData,
  type DependenteFormInput,
  dependenteSchema,
} from "@/features/citizen/schemas/dependent-schema";
import { mascararCNS, mascararCPF, mascararTelefoneBR } from "@/lib/validators";

const GRAUS_PARENTESCO = [
  { value: "FILHO", label: "Filho(a)" },
  { value: "ENTEADO", label: "Enteado(a)" },
  { value: "TUTELADO", label: "Tutelado(a)" },
  { value: "CONJUGE", label: "Cônjuge / Companheiro(a)" },
  { value: "OUTRO", label: "Outro responsável legal" },
];

export interface DependentFormProps {
  pacienteId: string;
  token?: string;
}

/**
 * Formulário validado (Zod) para cadastro/vínculo de dependente legal ou menor.
 */
export function DependentForm({ pacienteId, token }: DependentFormProps) {
  const [erroForm, setErroForm] = useState<string | null>(null);
  const [sucessoMsg, setSucessoMsg] = useState<string | null>(null);
  const createDependentMutation = useCreateDependent(pacienteId);

  const form = useForm<DependenteFormInput, unknown, DependenteFormData>({
    resolver: zodResolver(dependenteSchema),
    defaultValues: {
      grau_parentesco: "FILHO",
      nome_completo: "",
      data_nascimento: "",
      cpf: "",
      cns: "",
      telefone: "",
    },
  });

  const onSubmit = async (values: DependenteFormData) => {
    setErroForm(null);
    setSucessoMsg(null);
    try {
      await createDependentMutation.mutateAsync({ body: values, token });
      setSucessoMsg("Dependente cadastrado e vinculado com sucesso.");
      form.reset({
        grau_parentesco: "FILHO",
        nome_completo: "",
        data_nascimento: "",
        cpf: "",
        cns: "",
        telefone: "",
      });
    } catch (err) {
      setErroForm(extractProblemDetail(err, "Não foi possível cadastrar o dependente."));
    }
  };

  return (
    <div className="pt-2 border-t border-border space-y-3">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
        <UserPlus className="h-4 w-4 text-primary" aria-hidden="true" />
        <span>Adicionar Novo Dependente</span>
      </h3>

      {sucessoMsg && (
        <Alert>
          <CheckCircle2 className="h-4 w-4 text-primary" aria-hidden="true" />
          <AlertTitle>Cadastro atualizado</AlertTitle>
          <AlertDescription>{sucessoMsg}</AlertDescription>
        </Alert>
      )}

      {erroForm && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>Erro no cadastro de dependente</AlertTitle>
          <AlertDescription>{erroForm}</AlertDescription>
        </Alert>
      )}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <FormField
              control={form.control}
              name="nome_completo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nome Completo do Dependente</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Ex: Lucas Oliveira Silva…"
                      disabled={createDependentMutation.isPending}
                      {...field}
                      value={field.value ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="grau_parentesco"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Grau de Parentesco</FormLabel>
                  <FormControl>
                    <select
                      {...field}
                      disabled={createDependentMutation.isPending}
                      className="flex min-h-[44px] h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {GRAUS_PARENTESCO.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <FormField
              control={form.control}
              name="data_nascimento"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Data de Nascimento</FormLabel>
                  <FormControl>
                    <Input
                      type="date"
                      disabled={createDependentMutation.isPending}
                      {...field}
                      value={field.value ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="cpf"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>CPF (Opcional)</FormLabel>
                  <FormControl>
                    <Input
                      inputMode="numeric"
                      placeholder="000.000.000-00…"
                      disabled={createDependentMutation.isPending}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(mascararCPF(e.target.value))}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="cns"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>CNS / Cartão SUS (Opcional)</FormLabel>
                  <FormControl>
                    <Input
                      inputMode="numeric"
                      placeholder="000 0000 0000 0000…"
                      disabled={createDependentMutation.isPending}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(mascararCNS(e.target.value))}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="telefone"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Telefone de Contato (Opcional)</FormLabel>
                <FormControl>
                  <Input
                    inputMode="tel"
                    placeholder="(11) 99999-9999…"
                    disabled={createDependentMutation.isPending}
                    value={field.value ?? ""}
                    onChange={(e) => field.onChange(mascararTelefoneBR(e.target.value))}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button
            type="submit"
            disabled={createDependentMutation.isPending}
            className="min-h-[44px] w-full sm:w-auto gap-2"
          >
            {createDependentMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <span>Cadastrando…</span>
              </>
            ) : (
              <>
                <UserPlus className="h-4 w-4" aria-hidden="true" />
                <span>Cadastrar Dependente</span>
              </>
            )}
          </Button>
        </form>
      </Form>
    </div>
  );
}
