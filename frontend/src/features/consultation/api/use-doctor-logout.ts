import { useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/api/client";
import { logoutApiV1AuthLogoutPost } from "@/api/generated/sdk.gen";
import { clearAccessToken } from "@/lib/auth-token";
import { clearStoredDoctorSession } from "@/lib/session-storage";

/**
 * Hook headless para encerramento seguro da sessão médica e expurgo do cache React Query.
 */
export function useDoctorLogout() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: async () => {
      try {
        await logoutApiV1AuthLogoutPost({ client, body: {} });
      } catch {
        // Falha de rede não impede expurgo local
      }
      clearAccessToken();
      clearStoredDoctorSession();
      queryClient.clear();
    },
  });
}
