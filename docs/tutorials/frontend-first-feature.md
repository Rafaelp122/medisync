# Frontend first feature

> Guia prático passo a passo: construindo uma fatia vertical completa no padrão Feature-Driven com Hey API, TanStack Query, Zod e Troféu de Testes ([ADR-011](../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)).

## Visão geral

Neste tutorial, você aprenderá a construir uma nova fatia vertical de frontend no MediSync Express seguindo os princípios de design da [ADR-011](../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md):
- **Zero DTO Duplication**: Consumo de tipos estritos gerados diretamente do OpenAPI do FastAPI via Hey API (`@hey-api/openapi-ts`).
- **Desacoplamento Headless**: Isolamento de lógica de rede e estado em Custom Hooks do TanStack Query.
- **Formulários Acessíveis e Tipados**: Validação em runtime com `zod` (derivado de `zod.gen.ts`).
- **Componentes Compostos**: Primitivas visuais sem boolean props abusivas (`shadcn/ui`).
- **Troféu de Testes**: Teste de integração de tela montando componentes reais com simulação de rede via Mock Service Worker (MSW).

Utilizaremos como exemplo canônico o fluxo de identificação única do cidadão (IAM Híbrido — [US-02](../user-stories/US-02-autenticacao-passwordless-otp.md)) na pasta `frontend/src/features/auth/`.

---

## Passo 1: Atualizar contratos de API via Hey API

### Dependências e Plugins

As dependências necessárias para suporte à geração automática, formulários Zod e testes com MSW são gerenciadas via `pnpm`:

```bash
# Dependências de produção (runtime, validação e estado de servidor)
pnpm add @hey-api/client-fetch @tanstack/react-query zod react-hook-form @hookform/resolvers

# Dependências de desenvolvimento (gerador OpenAPI-TS e simulador de rede MSW)
pnpm add -D @hey-api/openapi-ts msw
```

### Configuração do Hey API

O Hey API é configurado em `frontend/openapi-ts.config.ts` gerando tipos, SDK, validadores Zod e handlers MSW:

```typescript
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: 'src/api/generated',
  plugins: [
    '@hey-api/client-fetch',
    '@tanstack/react-query',
    'zod',
    'msw',
  ],
});
```

Sempre que o backend FastAPI adicionar ou modificar endpoints, execute:

```bash
just frontend-generate
```

Isso gera automaticamente em `frontend/src/api/generated/` (sempre importados diretamente dos arquivos `.gen`, proibindo barrel imports):
- `types.gen.ts`: Interfaces estritas dos schemas Pydantic (ex.: `IdentificarPacienteRequest`).
- `zod.gen.ts`: Schemas Zod convertidos automaticamente dos models Pydantic (ex.: `zIdentificarPacienteRequest`).
- `sdk.gen.ts`: Funções tipadas de requisição baseadas em `@hey-api/client-fetch` (ex.: `postAuthPatientIdentify`).
- `msw.gen.ts`: Factories tipadas de interceptação MSW para testes (ex.: `handlePostAuthPatientIdentify`).

---

## Passo 2: Definir Schema de Validação Zod (Derivado de `zod.gen.ts`)

Em vez de duplicar regras manualmente, estenda o schema gerado pelo backend em `frontend/src/features/auth/schemas/patient-hybrid-auth-schemas.ts`:

```typescript
import { z } from "zod";
import { zIdentificarPacienteRequest } from "@/api/generated/zod.gen";
import { validarCPF } from "@/lib/validators";

const EMAIL_SCHEMA = z.string().email("Informe um endereço de e-mail válido.");

export const patientIdentifySchema = zIdentificarPacienteRequest.extend({
  identificador: z
    .string()
    .trim()
    .min(3, "Informe seu CPF (11 dígitos) ou e-mail cadastrado.")
    .refine(
      (val) => (val.includes("@") ? EMAIL_SCHEMA.safeParse(val).success : validarCPF(val)),
      { message: "Informe um CPF válido (11 dígitos) ou um e-mail válido." },
    ),
});
```

---

## Passo 3: Criar Custom Hook com TanStack Query

Encapsule a mutação HTTP em `frontend/src/features/auth/api/use-patient-identify.ts`. Nenhum componente React faz `fetch` direto:

```typescript
import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { postAuthPatientIdentify } from "@/api/generated/sdk.gen";
import type {
  IdentificarPacienteRequest,
  IdentificarPacienteResponse,
} from "@/api/generated/types.gen";

export function usePatientIdentify(
  options?: UseMutationOptions<
    IdentificarPacienteResponse,
    ProblemDetailsError,
    IdentificarPacienteRequest
  >,
) {
  return useMutation<IdentificarPacienteResponse, ProblemDetailsError, IdentificarPacienteRequest>({
    mutationFn: async (body: IdentificarPacienteRequest) => {
      try {
        const response = await postAuthPatientIdentify({
          client,
          body,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
```

---

## Passo 4: Criar o Componente Visual com `shadcn/ui`

Em `frontend/src/features/auth/components/patient-identify-form.tsx`, implemente a camada visual consumindo `usePatientIdentify` e primitivas do `shadcn/ui` com alvos mínimos de `44px`:

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { IdentificarPacienteResponse } from "@/api/generated/types.gen";
import { usePatientIdentify } from "../api/use-patient-identify";
import {
  normalizarIdentificadorCidadao,
  patientIdentifySchema,
} from "../schemas/patient-hybrid-auth-schemas";

export function PatientIdentifyForm({
  onIdentified,
}: {
  onIdentified: (payload: { identificador: string; response: IdentificarPacienteResponse }) => void;
}) {
  const [identificador, setIdentificador] = useState("");
  const identifyMutation = usePatientIdentify({
    onSuccess: (response) =>
      onIdentified({ identificador: normalizarIdentificadorCidadao(identificador), response }),
  });

  // Valida via patientIdentifySchema e chama identifyMutation.mutate(...)
  return (
    <form className="space-y-4" noValidate>
      <Label htmlFor="patient-identificador">CPF ou E-mail</Label>
      <Input
        id="patient-identificador"
        value={identificador}
        onChange={(e) => setIdentificador(e.target.value)}
      />
      <Button type="submit" disabled={identifyMutation.isPending} className="w-full min-h-[44px]">
        Continuar
      </Button>
    </form>
  );
}
```

---

## Passo 5: Escrever Teste de Integração de Tela com MSW

Em `frontend/src/features/auth/tests/patient-hybrid-auth.test.tsx`, teste a tela montada usando a factory tipada `handlePostAuthPatientIdentify` gerada em `msw.gen.ts`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { handlePostAuthPatientIdentify } from "@/api/generated/msw.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PatientHybridAuthCard } from "../components/patient-hybrid-auth-card";

describe("PatientHybridAuthCard", () => {
  it("identifica cidadão por CPF usando MSW v2", async () => {
    let identifiedCpf = "";
    server.use(
      handlePostAuthPatientIdentify(async ({ request }) => {
        const body = await request.json();
        identifiedCpf = body.identificador;
        return HttpResponse.json({
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha", "passkey"],
          telefone_mascarado: "(11) 9****-4321",
          govbr_habilitado: false,
        });
      }),
    );

    renderWithProviders(<PatientHybridAuthCard onAuthenticated={vi.fn()} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/cpf ou e-mail/i), "52998224725");
    await user.click(screen.getByRole("button", { name: /continuar/i }));

    await waitFor(() => expect(identifiedCpf).toBe("52998224725"));
  });
});
```

---

## Verificação

Execute o portão de qualidade do frontend via `justfile`:

```bash
just frontend-check
just audit-frontend
just frontend-test
```
