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
 * Dados editáveis da seção "Sobre Mim".
 * Substitua os campos marcados abaixo pelas suas informações pessoais e links reais.
 */
export const AUTHOR_PROFILE: AuthorProfile = {
  name: "Rafael (Placeholder — Editar Nome Completo)",
  role: "Engenheiro de Software Sênior · Arquitetura Backend & Sistemas Distribuídos",
  location: "Brasil · Remoto",
  bio: "Espaço reservado para sua biografia profissional. Descreva aqui sua trajetória em engenharia de software, foco em arquitetura limpa, alta concorrência, observabilidade e produtos digitais com impacto social.",
  highlights: [
    "Python 3.12+ & FastAPI",
    "Arquitetura Hexagonal & DDD",
    "PostgreSQL & Row-Level Security",
    "Valkey / Redis & Concorrência Atômica",
    "React 19 & TypeScript Estrito",
  ],
  links: [
    {
      label: "GitHub (Editar perfil)",
      href: "https://github.com/Rafaelp122/medisync",
    },
    {
      label: "LinkedIn (Adicionar URL)",
      href: "https://www.linkedin.com",
    },
    {
      label: "Contato (Editar e-mail)",
      href: "mailto:contato@exemplo.dev",
    },
  ],
};

/**
 * Lista editável da seção "Outros Projetos".
 * Adicione, remova ou atualize os cartões abaixo com seus projetos de portfólio.
 */
export const OTHER_PROJECTS: PortfolioProject[] = [
  {
    id: "projeto-placeholder-1",
    name: "Projeto de Portfólio 01 (Editar Título)",
    summary:
      "Espaço reservado para descrever outro sistema ou biblioteca desenvolvida por você, destacando o problema resolvido, arquitetura e métricas de resultado.",
    stack: ["Python", "PostgreSQL", "Docker"],
    href: "https://github.com/Rafaelp122",
    statusLabel: "Placeholder Editável",
  },
  {
    id: "projeto-placeholder-2",
    name: "Projeto de Portfólio 02 (Editar Título)",
    summary:
      "Espaço reservado para um segundo estudo de caso técnico — por exemplo, APIs de baixa latência, pipelines assíncronos ou ferramentas CLI.",
    stack: ["TypeScript", "React", "Vitest"],
    href: "https://github.com/Rafaelp122",
    statusLabel: "Placeholder Editável",
  },
  {
    id: "projeto-placeholder-3",
    name: "Projeto de Portfólio 03 (Editar Título)",
    summary:
      "Espaço reservado para um terceiro projeto open source, artigo técnico ou contribuição relevante para a comunidade de engenharia.",
    stack: ["Open Source", "CI/CD", "Observabilidade"],
    href: "https://github.com/Rafaelp122",
    statusLabel: "Placeholder Editável",
  },
];
