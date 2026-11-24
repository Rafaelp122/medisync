import { ExternalLink, FolderGit2, MapPin, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AUTHOR_PROFILE, OTHER_PROJECTS } from "@/features/landing/data/portfolio-content";

export function AboutAuthorSection() {
  return (
    <div className="border-t border-border/70 bg-muted/20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-14 sm:py-16 space-y-16">
        <section id="sobre" aria-labelledby="sobre-heading" className="space-y-6">
          <div className="space-y-2">
            <Badge variant="outline">Autoria & Portfólio</Badge>
            <h2
              id="sobre-heading"
              className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground"
            >
              Sobre Mim
            </h2>
          </div>

          <Card className="border-border bg-card shadow-sm">
            <CardHeader className="space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div className="flex items-center gap-3">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <User className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div>
                    <CardTitle className="text-xl">{AUTHOR_PROFILE.name}</CardTitle>
                    <CardDescription className="text-sm font-medium text-foreground/80">
                      {AUTHOR_PROFILE.role}
                    </CardDescription>
                  </div>
                </div>
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                  <span>{AUTHOR_PROFILE.location}</span>
                </span>
              </div>
            </CardHeader>

            <CardContent className="space-y-5">
              <p className="text-sm sm:text-base text-muted-foreground leading-relaxed text-pretty">
                {AUTHOR_PROFILE.bio}
              </p>

              <ul className="flex flex-wrap gap-2" aria-label="Especialidades técnicas">
                {AUTHOR_PROFILE.highlights.map((skill) => (
                  <li key={skill}>
                    <Badge variant="secondary">{skill}</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>

            <CardFooter className="flex flex-wrap gap-3 border-t border-border/60 pt-4">
              {AUTHOR_PROFILE.links.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md border border-input bg-background px-3.5 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span>{link.label}</span>
                  <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                </a>
              ))}
            </CardFooter>
          </Card>
        </section>

        <section id="projetos" aria-labelledby="projetos-heading" className="space-y-6">
          <div className="max-w-3xl space-y-2">
            <Badge variant="outline">Mais Trabalhos</Badge>
            <h2
              id="projetos-heading"
              className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground"
            >
              Outros Projetos
            </h2>
            <p className="text-sm sm:text-base text-muted-foreground">
              Arquiteturas hexagonais, plataformas de alta concorrência e ferramentas de engenharia
              voltadas à saúde digital.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {OTHER_PROJECTS.map((project) => (
              <Card
                key={project.id}
                className="flex flex-col justify-between border-border bg-card shadow-sm hover:border-primary/50 transition-colors motion-reduce:transition-none"
              >
                <CardHeader className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
                      <FolderGit2 className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <Badge variant="outline">{project.statusLabel}</Badge>
                  </div>
                  <CardTitle className="text-lg">{project.name}</CardTitle>
                  <CardDescription className="text-sm leading-relaxed">
                    {project.summary}
                  </CardDescription>
                </CardHeader>

                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {project.stack.map((tech) => (
                      <Badge key={tech} variant="secondary">
                        {tech}
                      </Badge>
                    ))}
                  </div>
                </CardContent>

                <CardFooter className="pt-2">
                  <a
                    href={project.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span>Ver Projeto</span>
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                </CardFooter>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
