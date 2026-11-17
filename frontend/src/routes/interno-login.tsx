import { createRoute, redirect } from "@tanstack/react-router";
import { z } from "zod";
import { InternalLoginPage } from "@/features/auth/pages/internal-login-page";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { getStoredDoctorSession, getStoredManagerSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const internalLoginSearchSchema = z.object({
  perfil: z.enum(["medico", "gestor"]).optional(),
});

export const internoLoginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/interno/login",
  validateSearch: (search: Record<string, unknown>) => internalLoginSearchSchema.parse(search),
  beforeLoad: () => {
    const doctor = getStoredDoctorSession();
    if (doctor) throw redirect({ to: "/medico" });

    const manager = getStoredManagerSession();
    if (manager) throw redirect({ to: "/gestor" });
  },
  component: function InternoLoginRouteComponent() {
    const search = internoLoginRoute.useSearch();
    return (
      <ClinicalPageLayout subtitle="Portal Interno da Equipe Clínica e Regulação">
        <InternalLoginPage initialPerfil={search.perfil ?? "medico"} />
      </ClinicalPageLayout>
    );
  },
});
