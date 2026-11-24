import { useQuery } from "@tanstack/react-query";
import { settings } from "@/config/settings";
import { limparDigitos, validarCEP } from "@/lib/validators";

export interface EnderecoViaCep {
  logradouro: string;
  bairro: string;
  cidade: string;
  estado: string;
}

function createCombinedSignal(externalSignal?: AbortSignal): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(settings.network.viaCepTimeoutMs);
  if (!externalSignal) {
    return timeoutSignal;
  }
  if (typeof AbortSignal.any === "function") {
    return AbortSignal.any([externalSignal, timeoutSignal]);
  }
  return externalSignal;
}

/**
 * Consulta a API pública do ViaCEP com proteção de timeout nativo, validação prévia e cancelamento via AbortSignal.
 * Em caso de erro, cancelamento, timeout ou CEP inexistente, retorna null com resiliência.
 * @see docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
 */
export async function buscarEnderecoPorCep(
  cep: string,
  signal?: AbortSignal,
): Promise<EnderecoViaCep | null> {
  if (signal?.aborted || !validarCEP(cep)) {
    return null;
  }
  const clean = limparDigitos(cep);

  try {
    const res = await fetch(`https://viacep.com.br/ws/${clean}/json/`, {
      signal: createCombinedSignal(signal),
    });
    if (!res.ok) {
      return null;
    }
    const data = await res.json();
    if (data && "erro" in data && (data.erro === true || data.erro === "true")) {
      return null;
    }

    return {
      logradouro: data.logradouro || "",
      bairro: data.bairro || "",
      cidade: data.localidade || "",
      estado: data.uf || "",
    };
  } catch {
    return null;
  }
}

/**
 * Query headless com TanStack Query para busca de endereço ViaCEP com cancelamento automático por AbortSignal.
 * @see docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
 */
export function useViaCepQuery(cep: string) {
  const valid = validarCEP(cep);
  const clean = valid ? limparDigitos(cep) : "";

  const query = useQuery({
    queryKey: ["onboarding", "viacep", clean],
    enabled: valid,
    staleTime: 1000 * 60 * 10,
    retry: false,
    queryFn: ({ signal }) => buscarEnderecoPorCep(clean, signal),
  });

  const erro =
    valid && query.isFetched && !query.isFetching && !query.data
      ? "CEP não localizado. Preencha o endereço manualmente."
      : null;

  return {
    endereco: valid ? (query.data ?? null) : null,
    isLoading: valid && query.isLoading,
    erro,
  };
}
