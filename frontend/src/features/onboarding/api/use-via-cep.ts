import { useEffect, useState } from "react";
import { limparDigitos, validarCEP } from "@/lib/validators";

export interface EnderecoViaCep {
  logradouro: string;
  bairro: string;
  cidade: string;
  estado: string;
}

/**
 * Consulta a API pública do ViaCEP com proteção de timeout nativo e validação prévia.
 * Em caso de erro, timeout ou CEP inexistente, retorna null com resiliência.
 */
export async function buscarEnderecoPorCep(cep: string): Promise<EnderecoViaCep | null> {
  if (!validarCEP(cep)) {
    return null;
  }
  const clean = limparDigitos(cep);

  try {
    const res = await fetch(`https://viacep.com.br/ws/${clean}/json/`, {
      signal: AbortSignal.timeout(5000),
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
 * Hook headless para busca e autopreenchimento dinâmico de endereço a partir de CEP.
 */
export function useViaCep(cep: string) {
  const [endereco, setEndereco] = useState<EnderecoViaCep | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    if (!validarCEP(cep)) {
      setEndereco(null);
      setErro(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setErro(null);

    buscarEnderecoPorCep(cep).then((resultado) => {
      if (!active) return;
      setIsLoading(false);
      if (resultado) {
        setEndereco(resultado);
        setErro(null);
      } else {
        setEndereco(null);
        setErro("CEP não localizado. Preencha o endereço manualmente.");
      }
    });

    return () => {
      active = false;
    };
  }, [cep]);

  return {
    endereco,
    isLoading,
    erro,
  };
}
