import { Cpu, Database, FileSignature, Layers, Lock, Video } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const ARCHITECTURE_PILLARS = [
  {
    id: "fastapi-granian",
    icon: Cpu,
    badge: "Runtime ASGI em Rust",
    title: "FastAPI + Granian",
    summary: "API Python 3.12+ assíncrona com routers finos e contratos OpenAPI 3.1.",
    details:
      "Servida sobre Granian para baixa latência e alta vazão em HTTP e WebSockets, com envelope de erros padronizado RFC 7807 e tipagem estrita via basedpyright.",
  },
  {
    id: "hexagonal-tach",
    icon: Layers,
    badge: "Modularidade Verificada",
    title: "Hexagonal Pragmático + Tach",
    summary: "Modelos ricos em SQLAlchemy 2.0 com portas typing.Protocol (PEP 544).",
    details:
      "Elimina o Mapper Hell preservando isolamento estrito entre bounded contexts. Fronteiras modulares e camadas são auditadas continuamente em tempo de build pelo Tach.",
  },
  {
    id: "valkey-lua",
    icon: Database,
    badge: "Concorrência Atômica",
    title: "Valkey 8.0 ZSET + Scripts Lua (< 200ms)",
    summary: "Alocação médico-paciente indivisível com desempate determinístico FIFO.",
    details:
      "Fila clínica indexada em Sorted Set de 64 bits com UUIDv7, locks duplos vinculados por script Lua e resolução determinística de No-Show via ring timeout de 45s no ARQ.",
  },
  {
    id: "rbac-anti-idor",
    icon: Lock,
    badge: "Defesa em Profundidade",
    title: "RBAC Estrito & Anti-IDOR por Titularidade",
    summary: "Autorização multicamada com posse clínica explícita e tokens JWT/HMAC.",
    details:
      "Cada operação verifica papéis assistenciais (PACIENTE, MEDICO, GESTOR_UNIDADE, FATURAMENTO) e posse do atendimento ou prontuário no serviço antes de ler ou mutar registros no PostgreSQL 17.",
  },
  {
    id: "livekit-webrtc",
    icon: Video,
    badge: "Mídia SRTP ≤ 150ms",
    title: "LiveKit SFU WebRTC",
    summary: "Salas efêmeras de teleconsulta desacopladas do editor clínico.",
    details:
      "Tokens emitidos sob demanda para médico e paciente com proteção contra re-renders da mídia durante a evolução do prontuário SOAP e geração de prescrições.",
  },
  {
    id: "icp-brasil-cfm",
    icon: FileSignature,
    badge: "Conformidade Regulatória",
    title: "ICP-Brasil PAdES & CFM nº 2.314/2022 + LGPD",
    summary: "Receitas e atestados em PDF/A assinados com guarda imutável S3/MinIO.",
    details:
      "Assinatura digital PAdES-LTV via PyHanko, validação pública por QR/código, trilha de auditoria append-only e tratamento de dados sensíveis conforme Art. 11 da LGPD.",
  },
] as const;

export function ArchitectureShowcase() {
  return (
    <section
      id="arquitetura"
      aria-labelledby="arquitetura-heading"
      className="mx-auto max-w-6xl px-4 sm:px-6 py-14 sm:py-16 space-y-10"
    >
      <div className="max-w-3xl space-y-3">
        <Badge variant="outline">Engenharia & Fundamentos Arquiteturais</Badge>
        <h2
          id="arquitetura-heading"
          className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground text-balance"
        >
          Diferenciais Reais de Engenharia
        </h2>
        <p className="text-base text-muted-foreground leading-relaxed text-pretty">
          Cada camada do MediSync Express foi projetada para resolver tensões reais de concorrência,
          controle de acesso por titularidade, estabilidade de mídia em tempo real e conformidade
          médico-legal.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {ARCHITECTURE_PILLARS.map((pillar) => {
          const Icon = pillar.icon;
          return (
            <Card
              key={pillar.id}
              className="flex flex-col justify-between border-border bg-card shadow-sm hover:border-primary/50 transition-colors motion-reduce:transition-none"
            >
              <CardHeader className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <Badge variant="secondary">{pillar.badge}</Badge>
                </div>
                <CardTitle className="text-lg leading-snug">{pillar.title}</CardTitle>
                <CardDescription className="text-sm text-foreground/85 font-medium">
                  {pillar.summary}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground leading-relaxed">{pillar.details}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
