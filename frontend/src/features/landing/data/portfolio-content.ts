export interface AuthorLink {
  label: string;
  href: string;
}

export interface AuthorProfile {
  name: string;
  role: string;
  location: string;
  bio: string;
  highlights: string[];
  links: AuthorLink[];
}

export interface PortfolioProject {
  id: string;
  name: string;
  summary: string;
  stack: string[];
  href: string;
  statusLabel: string;
}

/**
 * Dados autorais exibidos na seção "Sobre Mim" da Landing Page de portfólio.
 */
export const AUTHOR_PROFILE: AuthorProfile = {
  name: "Rafael P.",
  role: "Engenheiro de Software Sênior · Arquitetura Backend & Sistemas Distribuídos",
  location: "Brasil · Remoto",
  bio: "Engenheiro de software especializado em sistemas distribuídos de alta confiabilidade, arquitetura hexagonal, modelagem clínica regulatória e experiências web acessíveis com tipagem estrita de ponta a ponta.",
  highlights: [
    "Python 3.12+ & FastAPI",
    "Arquitetura Hexagonal & DDD",
    "PostgreSQL 17 & Índices GiST",
    "Valkey / Redis & Concorrência Atômica",
    "React 19 & TypeScript Estrito",
  ],
  links: [
    {
      label: "GitHub",
      href: "https://github.com/Rafaelp122/medisync",
    },
    {
      label: "LinkedIn",
      href: "https://www.linkedin.com/in/rafaelp122",
    },
    {
      label: "Repositório MediSync",
      href: "https://github.com/Rafaelp122/medisync",
    },
  ],
};

/**
 * Lista de projetos complementares exibida na seção "Outros Projetos".
 */
export const OTHER_PROJECTS: PortfolioProject[] = [
  {
    id: "arquitetura-filas-valkey",
    name: "Orquestrador Atômico de Filas (Valkey + Lua)",
    summary:
      "Motor de alocação concorrente sem race conditions utilizando Sorted Sets e scripts Lua para priorização multicritério e janelas de expiração determinísticas.",
    stack: ["Python", "Valkey 8.0", "Lua"],
    href: "https://github.com/Rafaelp122/medisync",
    statusLabel: "Open Source",
  },
  {
    id: "contratos-openapi-heyapi",
    name: "Pipeline Zero-Mapper OpenAPI → React 19",
    summary:
      "Geração automatizada de SDK tipado, esquemas Zod de runtime e handlers MSW diretamente do contrato OpenAPI 3.1 do FastAPI sem duplicação de DTOs.",
    stack: ["TypeScript", "React 19", "Vitest"],
    href: "https://github.com/Rafaelp122/medisync",
    statusLabel: "Arquitetura",
  },
  {
    id: "governanca-modular-tach",
    name: "Governança Arquitetural & Auditoria Diátaxis",
    summary:
      "Conjunto de guardrails AST e CLI para impor fronteiras modulares estritas, routers finos e rastreabilidade bidirecional entre código, ADRs e user stories.",
    stack: ["AST", "Tach", "CI/CD"],
    href: "https://github.com/Rafaelp122/medisync",
    statusLabel: "Qualidade",
  },
];
