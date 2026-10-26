import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { AuthOtpCard } from "@/features/onboarding/components/auth-otp-card";

const queryClient = new QueryClient();

export function App() {
  const [session, setSession] = useState<VerificarOtpResponse | null>(null);

  return (
    <QueryClientProvider client={queryClient}>
      <main className="min-h-screen flex items-center justify-center p-4 bg-background text-foreground">
        {session ? (
          <div className="w-full max-w-md mx-auto p-6 bg-card rounded-xl border shadow text-center space-y-4">
            <h1 className="text-2xl font-bold text-primary">Acesso Autorizado</h1>
            <p className="text-sm text-muted-foreground">
              Sessão de paciente autenticada com sucesso via OTP.
            </p>
            <div className="p-3 bg-muted rounded-md text-xs font-mono text-left break-all">
              <p>
                <strong>Papel:</strong> {session.role}
              </p>
              <p>
                <strong>Paciente ID:</strong> {session.paciente_id}
              </p>
            </div>
          </div>
        ) : (
          <AuthOtpCard onAuthenticated={(data) => setSession(data)} />
        )}
      </main>
    </QueryClientProvider>
  );
}

export default App;
