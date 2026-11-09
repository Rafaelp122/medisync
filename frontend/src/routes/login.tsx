import { createRoute, redirect } from "@tanstack/react-router";
import { LoginPage } from "@/features/auth/pages/login-page";
import { loginSearchSchema } from "@/features/auth/schemas/login-search-schema";
import { getStoredDoctorSession, getStoredManagerSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (search: Record<string, unknown>) => loginSearchSchema.parse(search),
  beforeLoad: () => {
    const doctor = getStoredDoctorSession();
    if (doctor) throw redirect({ to: "/medico" });

    const manager = getStoredManagerSession();
    if (manager) throw redirect({ to: "/gestor" });
  },
  component: function RouteComponent() {
    const search = loginRoute.useSearch();
    return <LoginPage initialPerfil={search.perfil ?? "medico"} />;
  },
});
