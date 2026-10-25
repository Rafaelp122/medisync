# Frontend first feature

> Guia prático passo a passo: construindo uma fatia vertical completa no padrão Feature-Driven com Hey API, TanStack Query, Zod e Troféu de Testes ([ADR-011](../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)).

## Visão geral

Neste tutorial, você aprenderá a construir uma nova fatia vertical de frontend no MediSync Express seguindo os princípios de design da [ADR-011](../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md):
- **Zero DTO Duplication**: Consumo de tipos estritos gerados diretamente do OpenAPI do FastAPI via Hey API (`@hey-api/openapi-ts`).
- **Desacoplamento Headless**: Isolamento de lógica de rede e estado em Custom Hooks do TanStack Query.
- **Formulários Acessíveis e Tipados**: Validação em runtime com `react-hook-form` + `zod`.
- **Componentes Compostos**: Primitivas visuais sem boolean props abusivas (`shadcn/ui`).
- **Troféu de Testes**: Teste de integração de tela montando componentes reais com simulação de rede via Mock Service Worker (MSW).

Utilizaremos como exemplo canônico o fluxo de solicitação de OTP de onboarding do paciente ([US-02](../user-stories/US-02-autenticacao-passwordless-otp.md)) na pasta `frontend/src/features/onboarding/`.

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

O Hey API é configurado em `frontend/openapi-ts.config.ts` com os 4 plugins oficiais:

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
pnpm generate:api
```

Isso gera automaticamente em `frontend/src/api/generated/`:
- `types.gen.ts`: Interfaces estritas dos schemas Pydantic (ex.: `SolicitarOtpPacienteRequest`).
- `zod.gen.ts`: Schemas Zod convertidos automaticamente dos models Pydantic (ex.: `zSolicitarOtpPacienteRequest`).
- `msw.gen.ts`: Factories de mock tipadas para MSW v2 (ex.: `solicitarOtpPacienteMock`).
- `services.gen.ts`: Funções de chamada HTTP tipadas (`solicitarOtpPaciente`).

> **Regra Pétrea:** Proibido redigitar ou criar interfaces manuais ou schemas Zod do zero para dados que vêm do backend. Use sempre os tipos e schemas gerados em `@/api/generated`.

---

## Passo 2: Estender o schema Zod gerado para o formulário

Em vez de redeclarar o schema Zod manualmente, importe o schema correspondente gerado pelo plugin `zod` em `frontend/src/api/generated/zod.gen` e apenas refine com mensagens em português e validações algorítmicas locais:

Em `frontend/src/features/onboarding/schemas/onboarding-schema.ts`:

```typescript
import { z } from 'zod';
import { zSolicitarOtpPacienteRequest } from '@/api/generated/zod.gen';
import { validarTelefoneBR } from '@/lib/validators';

// Estende o schema Zod gerado automaticamente pelo Hey API a partir do Pydantic:
export const solicitarOtpSchema = zSolicitarOtpPacienteRequest.extend({
  telefone: zSolicitarOtpPacienteRequest.shape.telefone.refine(
    validarTelefoneBR,
    'Telefone inválido; informe DDD + 9 dígitos'
  ),
});

export type SolicitarOtpFormData = z.infer<typeof solicitarOtpSchema>;
```

---

## Passo 3: Implementar o Custom Hook Headless

Em `frontend/src/features/onboarding/api/use-solicitar-otp.ts`, encapsule a mutação do TanStack Query. O hook gerencia o ciclo de vida, loading e interceptação de erros RFC 7807 (evitando barrel imports da raiz):

```typescript
import { useMutation } from '@tanstack/react-query';
import { solicitarOtpPaciente } from '@/api/generated/services.gen';
import type { SolicitarOtpPacienteResponse } from '@/api/generated/types.gen';

export function useSolicitarOtp() {
  return useMutation<SolicitarOtpPacienteResponse, Error, { telefone: string }>({
    mutationFn: async ({ telefone }) => {
      const response = await solicitarOtpPaciente({
        body: { telefone },
      });
      if (response.error) {
        throw new Error(response.error.detail || 'Falha ao solicitar código SMS');
      }
      return response.data;
    },
  });
}
```

---

## Passo 4: Criar o Componente Visual com `shadcn/ui`

Em `frontend/src/features/onboarding/components/solicitar-otp-form.tsx`, implemente a camada visual utilizando `react-hook-form` e primitivas do `shadcn/ui`:

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { solicitarOtpSchema, type SolicitarOtpFormData } from '../schemas/onboarding-schema';
import { useSolicitarOtp } from '../api/use-solicitar-otp';

interface SolicitarOtpFormProps {
  onSuccess: (telefone: string) => void;
}

export function SolicitarOtpForm({ onSuccess }: SolicitarOtpFormProps) {
  const form = useForm<SolicitarOtpFormData>({
    resolver: zodResolver(solicitarOtpSchema),
    defaultValues: { telefone: '' },
  });

  const { mutate, isPending, error } = useSolicitarOtp();

  function onSubmit(values: SolicitarOtpFormData) {
    mutate(values, {
      onSuccess: () => onSuccess(values.telefone),
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="telefone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Celular (com DDD)</FormLabel>
              <FormControl>
                <Input placeholder="(11) 98765-4321" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {error ? (
          <div role="alert" className="text-sm font-medium text-destructive">
            {error.message}
          </div>
        ) : null}

        <Button type="submit" disabled={isPending} className="w-full">
          {isPending ? 'Enviando código...' : 'Receber código SMS'}
        </Button>
      </form>
    </Form>
  );
}
```

---

## Passo 5: Teste de Integração de Tela com MSW

Em `frontend/src/features/onboarding/tests/solicitar-otp-form.test.tsx`, monte o componente real e interaja como o usuário, simulando a rede via Mock Service Worker:

```tsx
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server } from '@/mocks/server';
import { solicitarOtpPacienteMock } from '@/api/generated/msw.gen';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SolicitarOtpForm } from '../components/solicitar-otp-form';

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('SolicitarOtpForm', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('avança no fluxo com sucesso ao submeter telefone válido', async () => {
    const onSuccess = vi.fn();

    // Mock tipado gerado automaticamente pelo Hey API (plugin msw):
    server.use(
      solicitarOtpPacienteMock({
        response: {
          status: 200,
          data: { mensagem: 'OTP enviado com sucesso', expira_em_segundos: 300 },
        },
      })
    );

    renderWithClient(<SolicitarOtpForm onSuccess={onSuccess} />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/celular/i), '11987654321');
    await user.click(screen.getByRole('button', { name: /receber código/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith('11987654321');
    });
  });

  it('exibe erro de validação Zod para telefone inválido sem bater na rede', async () => {
    renderWithClient(<SolicitarOtpForm onSuccess={vi.fn()} />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/celular/i), '123');
    await user.click(screen.getByRole('button', { name: /receber código/i }));

    expect(await screen.findByText(/telefone inválido/i)).toBeInTheDocument();
  });
});
```

---

## Verificação

Execute o portão de qualidade do frontend via `justfile`:

```bash
just frontend-check
just frontend-test
```
