import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { z } from "zod";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { getStoredDoctorSession, getStoredManagerSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const internalLoginSearchSchema = z.object({
  perfil: z.enum(["medico", "gestor"]).optional(),
});

const LazyInternalLoginPage = lazyRouteComponent(
  () => import("@/features/auth/pages/internal-login-page"),
  "InternalLoginPage",
);

export const internoLoginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/interno/login",
  validateSearch: (search: Record<string, unknown>) => internalLoginSearchSchema.parse(search),
  beforeLoad: () => {
    const doctor = getStoredDoctorSession();
    if (doctor && (!doctor.papel || doctor.papel === "MEDICO")) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager?.papel === "GESTOR_UNIDADE") {
      throw redirect({ to: "/gestor" });
    }
  },
  component: function InternoLoginRouteComponent() {
    const search = internoLoginRoute.useSearch();
    return (
      <ClinicalPageLayout subtitle="Portal Interno da Equipe Clínica e Regulação">
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyInternalLoginPage initialPerfil={search.perfil ?? "medico"} />
        </Suspense>
      </ClinicalPageLayout>
    );
  },
});
