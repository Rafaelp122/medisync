import { zodResolver } from "@hookform/resolvers/zod";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { getHumanizedErrorMessage, type HumanizedError, isProblemDetailsError } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { calcularHashTcle, mascararCNS, mascararCPF, mascararTelefoneBR } from "@/lib/validators";
import { useAdmitirPaciente } from "../api/use-admitir-paciente";
import { useIntakeFase1 } from "../api/use-intake-fase1";
import { type IntakeFase1FormData, intakeFase1Schema } from "../schemas/onboarding-schema";
import { PainScaleSelector } from "./pain-scale-selector";
import { SamuEmergencyModal } from "./samu-emergency-modal";
import { TcleDialog, TEXTO_TCLE_PADRAO } from "./tcle-dialog";

export const SINTOMAS_COMUNS = [
  { id: "febre", label: "Febre" },
  { id: "cefaleia", label: "Dor de cabeça" },
  { id: "tosse", label: "Tosse" },
  { id: "coriza", label: "Coriza / Congestão" },
  { id: "dor_de_garganta", label: "Dor de garganta" },
  { id: "nausea_vomito", label: "Náusea ou vômitos" },
  { id: "diarreia", label: "Diarreia" },
  { id: "mialgia", label: "Dores no corpo" },
];

export const SINAIS_ALARME_CRITICOS = [
  { id: "dor_toracica_irradiada", label: "Dor no peito irradiando para o braço ou pescoço" },
  { id: "inconsciencia", label: "Desmaio ou perda de consciência" },
  { id: "dispneia_grave", label: "Falta de ar severa / sensação de asfixia" },
  { id: "convulsao_em_curso", label: "Crise convulsiva em andamento" },
  { id: "hemorragia_grave", label: "Hemorragia abundante que não estanca" },
  { id: "anafilaxia", label: "Reação alérgica com inchaço nos lábios ou glote" },
];

export interface AcolhimentoConcluidoData {
  pacienteId: string;
  atendimentoId: string;
  token: string;
  prioridadeClinica: number;
  isNovoPaciente: boolean;
}

export interface AcolhimentoFase1FormProps {
  onAdmissaoConcluida: (data: AcolhimentoConcluidoData) => void;
  onVoltarParaLogin?: () => void;
}

export function AcolhimentoFase1Form({
  onAdmissaoConcluida,
  onVoltarParaLogin,
}: AcolhimentoFase1FormProps) {
  const [microEtapa, setMicroEtapa] = useState<"identificacao" | "triagem">("identificacao");
  const [tipoDoc, setTipoDoc] = useState<"cpf" | "cns">("cpf");
  const [sintomasSelecionados, setSintomasSelecionados] = useState<string[]>([]);
  const [sintomaAcidental, setSintomaAcidental] = useState<string | null>(null);
  const [escalaDor, setEscalaDor] = useState<number>(0);
  const [tcleAceito, setTcleAceito] = useState<boolean>(false);
  const [tcleDialogOpen, setTcleDialogOpen] = useState<boolean>(false);
  const [samuModalOpen, setSamuModalOpen] = useState<boolean>(false);
  const [orientacoesSamu, setOrientacoesSamu] = useState<string | null>(null);
  const [erroHumanizado, setErroHumanizado] = useState<HumanizedError | null>(null);
  const [encaminhadoPresencial, setEncaminhadoPresencial] = useState<boolean>(false);

  const errorBannerRef = useRef<HTMLDivElement>(null);
  const intakeMutation = useIntakeFase1();
  const admitirMutation = useAdmitirPaciente();

  const form = useForm<IntakeFase1FormData>({
    resolver: zodResolver(intakeFase1Schema),
    defaultValues: {
      nome_completo: "",
      data_nascimento: "",
      telefone: "",
      cpf: "",
      cns: "",
      nome_social: "",
      queixa_principal: "",
      tcle_hash: "0".repeat(64),
    },
  });

  const alternarParaCpf = () => {
    setTipoDoc("cpf");
    form.setValue("cns", "");
    form.clearErrors("cns");
  };

  const alternarParaCns = () => {
    setTipoDoc("cns");
    form.setValue("cpf", "");
    form.clearErrors("cpf");
  };

  const mudarMicroEtapa = (novaEtapa: "identificacao" | "triagem") => {
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (
      !prefersReducedMotion &&
      typeof document !== "undefined" &&
      "startViewTransition" in document
    ) {
      document.startViewTransition(() => {
        setMicroEtapa(novaEtapa);
      });
    } else {
      setMicroEtapa(novaEtapa);
    }
  };

  const avancarParaTriagem = async () => {
    setErroHumanizado(null);
    const camposParaValidar: Array<keyof IntakeFase1FormData> = [
      "nome_completo",
      "data_nascimento",
      "telefone",
      tipoDoc === "cpf" ? "cpf" : "cns",
    ];
    const valido = await form.trigger(camposParaValidar);
    if (valido) {
      mudarMicroEtapa("triagem");
    } else {
      errorBannerRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  };

  const voltarParaIdentificacao = () => {
    setErroHumanizado(null);
    mudarMicroEtapa("identificacao");
  };

  const toggleSintoma = (sintomaId: string, isCritico = false) => {
    if (isCritico) {
      setSintomaAcidental(sintomaId);
      setSamuModalOpen(true);
      return;
    }
    setSintomasSelecionados((prev) =>
      prev.includes(sintomaId) ? prev.filter((s) => s !== sintomaId) : [...prev, sintomaId],
    );
  };

  const onSubmit = async (values: IntakeFase1FormData) => {
    setErroHumanizado(null);

    if (!tcleAceito) {
      setErroHumanizado({
        title: "Termo de Consentimento obrigatório",
        detail:
          "É obrigatório concordar com o Termo de Consentimento (TCLE) para ingressar na fila virtual.",
        retryable: false,
      });
      errorBannerRef.current?.scrollIntoView({ behavior: "smooth" });
      return;
    }

    try {
      // 1. Cálculo criptográfico do hash TCLE
      const hashTcle = await calcularHashTcle(TEXTO_TCLE_PADRAO);

      // 2. Intake Fase 1
      const intakeRes = await intakeMutation.mutateAsync({
        nome_completo: values.nome_completo,
        data_nascimento: values.data_nascimento,
        telefone: values.telefone,
        cpf: tipoDoc === "cpf" ? values.cpf : undefined,
        cns: tipoDoc === "cns" ? values.cns : undefined,
        nome_social: values.nome_social || undefined,
        queixa_principal: values.queixa_principal,
        tcle_hash: hashTcle,
      });

      // 3. Admissão e Triagem Clínica na Fila Virtual
      const admissaoRes = await admitirMutation.mutateAsync({
        body: {
          paciente_id: intakeRes.paciente_id,
          queixa_principal: values.queixa_principal,
          sintomas: sintomasSelecionados,
          escala_dor: escalaDor,
          tcle_hash: hashTcle,
          cpf: tipoDoc === "cpf" ? values.cpf : undefined,
          cns: tipoDoc === "cns" ? values.cns : undefined,
        },
        token: intakeRes.token,
      });

      if (admissaoRes.alerta_samu_disparado || admissaoRes.prioridade_clinica === 1) {
        setOrientacoesSamu(admissaoRes.instrucoes || null);
        setSintomaAcidental(null);
        setSamuModalOpen(true);
        return;
      }

      onAdmissaoConcluida({
        pacienteId: intakeRes.paciente_id,
        atendimentoId: admissaoRes.atendimento_id,
        token: intakeRes.token,
        prioridadeClinica: admissaoRes.prioridade_clinica,
        isNovoPaciente: intakeRes.is_novo_paciente,
      });
    } catch (err: unknown) {
      if (isProblemDetailsError(err) && err.code === "EMERGENCIA_CRITICA_SAMU_192") {
        setOrientacoesSamu(err.detail || null);
        setSintomaAcidental(null);
        setSamuModalOpen(true);
      } else {
        const humanizado = getHumanizedErrorMessage(err);
        setErroHumanizado(humanizado);
        errorBannerRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  const reiniciarAcolhimento = () => {
    form.reset({
      nome_completo: "",
      data_nascimento: "",
      telefone: "",
      queixa_principal: "",
      tcle_hash: "0".repeat(64),
      cpf: "",
      cns: "",
      nome_social: "",
    });
    setSintomasSelecionados([]);
    setEscalaDor(0);
    setTcleAceito(false);
    setTipoDoc("cpf");
    setErroHumanizado(null);
    setSintomaAcidental(null);
    setOrientacoesSamu(null);
    setEncaminhadoPresencial(false);
    setSamuModalOpen(false);
    setMicroEtapa("identificacao");
  };

  const isSubmitting = intakeMutation.isPending || admitirMutation.isPending;

  if (encaminhadoPresencial) {
    return (
      <Card className="w-full max-w-xl mx-auto shadow-md border-destructive/50">
        <CardHeader className="text-center space-y-2">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <span className="text-3xl" aria-hidden="true">
              🚑
            </span>
          </div>
          <CardTitle className="text-xl font-bold text-destructive">
            Atendimento Presencial de Urgência Recomendado
          </CardTitle>
          <CardDescription className="text-base text-foreground/90 font-medium leading-relaxed">
            Seus sintomas ou queixas exigem avaliação clínica física imediata.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-left">
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-foreground space-y-2">
            <p className="font-semibold text-destructive">Instruções Importantes:</p>
            <p className="leading-relaxed">
              {orientacoesSamu ||
                "Dirija-se imediatamente à Unidade de Pronto Atendimento (UPA) ou Pronto-Socorro hospitalar mais próximo da sua região. Se houver desmaio, dor forte no peito ou piora súbita, ligue 192."}
            </p>
          </div>

          <Button asChild variant="destructive" size="lg" className="w-full font-bold shadow-md">
            <a href="tel:192" className="flex items-center justify-center gap-2">
              <span aria-hidden="true">📞</span>
              Ligar para o SAMU 192
            </a>
          </Button>

          <Button
            type="button"
            variant="outline"
            className="w-full text-xs text-muted-foreground"
            onClick={reiniciarAcolhimento}
          >
            🔄 Reiniciar Acolhimento do Início
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="w-full max-w-xl mx-auto shadow-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-primary">
              {microEtapa === "identificacao"
                ? "Acolhimento Rápido • Etapa 1 de 2: Identificação"
                : "Acolhimento Rápido • Etapa 2 de 2: Triagem Clínica"}
            </span>
            {onVoltarParaLogin && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onVoltarParaLogin}
                className="text-xs h-7 px-2"
              >
                Já tenho cadastro (Entrar via SMS)
              </Button>
            )}
          </div>
          <CardTitle className="text-2xl font-bold">Pronto Atendimento Virtual</CardTitle>
          <CardDescription>
            {microEtapa === "identificacao"
              ? "Preencha seus dados de identificação para triagem imediata."
              : "Conte-nos o que você está sentindo e informe a intensidade dos sintomas."}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {erroHumanizado && (
            <Alert variant="destructive" className="mb-4" ref={errorBannerRef} role="alert">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <AlertTitle className="font-bold">{erroHumanizado.title}</AlertTitle>
                  <AlertDescription className="mt-1 text-sm leading-relaxed">
                    {erroHumanizado.detail}
                  </AlertDescription>
                </div>
                {erroHumanizado.retryable && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={form.handleSubmit(onSubmit)}
                    disabled={isSubmitting}
                    className="text-xs shrink-0 border-destructive/40 hover:bg-destructive/10"
                  >
                    🔄 Tentar Novamente
                  </Button>
                )}
              </div>
            </Alert>
          )}

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              {/* MICRO-ETAPA 1: IDENTIFICAÇÃO RÁPIDA */}
              {microEtapa === "identificacao" && (
                <div className="space-y-4">
                  {/* Nome Completo */}
                  <FormField
                    control={form.control}
                    name="nome_completo"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Nome Completo</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="Ex: Juliana Santos Silva"
                            autoComplete="name"
                            disabled={isSubmitting}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {/* Data de Nascimento */}
                    <FormField
                      control={form.control}
                      name="data_nascimento"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Data de Nascimento</FormLabel>
                          <FormControl>
                            <Input type="date" disabled={isSubmitting} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    {/* Telefone Celular */}
                    <FormField
                      control={form.control}
                      name="telefone"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Telefone Celular com DDD</FormLabel>
                          <FormControl>
                            <Input
                              placeholder="(11) 98765-4321"
                              type="tel"
                              disabled={isSubmitting}
                              {...field}
                              onChange={(e) => field.onChange(mascararTelefoneBR(e.target.value))}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  {/* Seletor CPF ou CNS */}
                  {tipoDoc === "cpf" ? (
                    <FormField
                      control={form.control}
                      name="cpf"
                      render={({ field }) => (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>Documento de Identificação (CPF)</FormLabel>
                            <div className="flex gap-1.5 p-0.5 rounded-lg bg-muted border border-border">
                              <button
                                type="button"
                                aria-pressed={tipoDoc === "cpf"}
                                onClick={alternarParaCpf}
                                className={cn(
                                  "text-xs px-2.5 py-0.5 rounded-md font-semibold shadow-xs transition-colors",
                                  tipoDoc === "cpf"
                                    ? "bg-background text-foreground"
                                    : "text-muted-foreground hover:text-foreground",
                                )}
                              >
                                CPF
                              </button>
                              <button
                                type="button"
                                aria-pressed={tipoDoc === "cns"}
                                onClick={alternarParaCns}
                                className={cn(
                                  "text-xs px-2.5 py-0.5 rounded-md transition-colors",
                                  tipoDoc === "cns"
                                    ? "bg-background text-foreground font-semibold shadow-xs"
                                    : "text-muted-foreground hover:text-foreground",
                                )}
                              >
                                Cartão SUS (CNS)
                              </button>
                            </div>
                          </div>
                          <FormControl>
                            <Input
                              placeholder="000.000.000-00"
                              disabled={isSubmitting}
                              value={field.value || ""}
                              onChange={(e) => field.onChange(mascararCPF(e.target.value))}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ) : (
                    <FormField
                      control={form.control}
                      name="cns"
                      render={({ field }) => (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>Documento de Identificação (Cartão SUS)</FormLabel>
                            <div className="flex gap-1.5 p-0.5 rounded-lg bg-muted border border-border">
                              <button
                                type="button"
                                aria-pressed={tipoDoc === "cpf"}
                                onClick={alternarParaCpf}
                                className={cn(
                                  "text-xs px-2.5 py-0.5 rounded-md transition-colors",
                                  tipoDoc === "cpf"
                                    ? "bg-background text-foreground font-semibold shadow-xs"
                                    : "text-muted-foreground hover:text-foreground",
                                )}
                              >
                                CPF
                              </button>
                              <button
                                type="button"
                                aria-pressed={tipoDoc === "cns"}
                                onClick={alternarParaCns}
                                className={cn(
                                  "text-xs px-2.5 py-0.5 rounded-md font-semibold shadow-xs transition-colors",
                                  tipoDoc === "cns"
                                    ? "bg-background text-foreground"
                                    : "text-muted-foreground hover:text-foreground",
                                )}
                              >
                                Cartão SUS (CNS)
                              </button>
                            </div>
                          </div>
                          <FormControl>
                            <Input
                              placeholder="000 0000 0000 0000"
                              disabled={isSubmitting}
                              value={field.value || ""}
                              onChange={(e) => field.onChange(mascararCNS(e.target.value))}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <Button
                    type="button"
                    size="lg"
                    onClick={avancarParaTriagem}
                    className="w-full font-bold text-base h-11 mt-2"
                  >
                    Continuar para Triagem →
                  </Button>
                </div>
              )}

              {/* MICRO-ETAPA 2: TRIAGEM CLÍNICA & CONSENTIMENTO */}
              {microEtapa === "triagem" && (
                <div className="space-y-4">
                  {/* Queixa Principal */}
                  <FormField
                    control={form.control}
                    name="queixa_principal"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>O que você está sentindo? (Queixa Principal)</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="Ex: Febre alta há 2 dias com dor no corpo"
                            disabled={isSubmitting}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {/* Sintomas de Toque Rápido */}
                  <div className="space-y-1.5">
                    <FormLabel className="text-xs text-muted-foreground">
                      Sintomas comuns:
                    </FormLabel>
                    <div className="flex flex-wrap gap-1.5">
                      {SINTOMAS_COMUNS.map((s) => {
                        const ativo = sintomasSelecionados.includes(s.id);
                        return (
                          <button
                            key={s.id}
                            type="button"
                            aria-pressed={ativo}
                            onClick={() => toggleSintoma(s.id)}
                            className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${ativo ? "bg-primary text-primary-foreground border-primary font-medium" : "bg-background text-foreground hover:bg-muted border-border"}`}
                          >
                            {s.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Alerta Preventivo Acolhedor (Salvaguarda SAMU 192) */}
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                        <span aria-hidden="true">⚠️</span> Sintomas graves exigem socorro imediato
                      </p>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-snug">
                      Se você apresenta dor forte no peito, falta de ar severa ou desmaio, não
                      aguarde teleconsulta. Toque abaixo para socorro direto:
                    </p>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {SINAIS_ALARME_CRITICOS.map((critico) => (
                        <button
                          key={critico.id}
                          type="button"
                          onClick={() => toggleSintoma(critico.id, true)}
                          className="text-[11px] px-2.5 py-1 rounded-md border border-destructive/40 bg-background text-destructive hover:bg-destructive/10 text-left font-medium transition-colors"
                        >
                          {critico.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Escala de Dor */}
                  <div className="pt-1">
                    <PainScaleSelector value={escalaDor} onChange={setEscalaDor} />
                  </div>

                  {/* Checkbox TCLE */}
                  <div className="rounded-lg border p-3 bg-muted/20 space-y-2">
                    <div className="flex items-start gap-2.5">
                      <input
                        id="tcle_consentimento"
                        type="checkbox"
                        aria-label="Concordo com o Termo de Consentimento Livre e Esclarecido (TCLE)"
                        checked={tcleAceito}
                        onChange={(e) => setTcleAceito(e.target.checked)}
                        className="mt-1 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
                        disabled={isSubmitting}
                      />
                      <div className="text-xs leading-relaxed text-foreground select-none">
                        <label htmlFor="tcle_consentimento" className="cursor-pointer">
                          Li e concordo com os termos do{" "}
                        </label>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setTcleDialogOpen(true);
                          }}
                          className="font-semibold text-primary underline underline-offset-2 hover:opacity-80"
                        >
                          Termo de Consentimento Livre e Esclarecido (TCLE)
                        </button>
                        <label htmlFor="tcle_consentimento" className="cursor-pointer">
                          , autorizando a realização da teleconsulta e o tratamento dos meus dados
                          clínicos (LGPD Art. 11 e CFM 2.314/2022).
                        </label>
                      </div>
                    </div>
                    <FormDescription className="text-[11px] text-muted-foreground pl-6">
                      O aceite gera um hash forense SHA-256 anexado de forma imutável ao seu
                      prontuário.
                    </FormDescription>
                  </div>

                  {/* Barra de Ações: Voltar ou Submeter */}
                  <div className="flex items-center gap-3 pt-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={voltarParaIdentificacao}
                      disabled={isSubmitting}
                      className="w-1/3 h-11"
                    >
                      ← Voltar
                    </Button>
                    <Button
                      type="submit"
                      size="lg"
                      disabled={!tcleAceito || isSubmitting}
                      className="w-2/3 font-bold text-base h-11"
                    >
                      {isSubmitting ? "Avaliando e Ingressando..." : "Entrar na Fila Virtual"}
                    </Button>
                  </div>
                </div>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>

      <TcleDialog open={tcleDialogOpen} onOpenChange={setTcleDialogOpen} />

      <SamuEmergencyModal
        open={samuModalOpen}
        onOpenChange={setSamuModalOpen}
        orientacoes={orientacoesSamu}
        onCorrigirSintomas={
          sintomaAcidental
            ? () => {
                setSintomasSelecionados((prev) => prev.filter((s) => s !== sintomaAcidental));
                setSintomaAcidental(null);
                setSamuModalOpen(false);
              }
            : undefined
        }
        onConfirmarSaida={() => {
          setSamuModalOpen(false);
          setEncaminhadoPresencial(true);
        }}
      />
    </>
  );
}
