import { createRoute, redirect } from "@tanstack/react-router";
import { HomeLanding } from "@/features/home/components/home-landing";
import { getStoredDoctorSession, getStoredManagerSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: (search: Record<string, unknown>) => ({
    mode: typeof search.mode === "string" ? search.mode : undefined,
  }),
  beforeLoad: ({ search }) => {
    // Retrocompatibilidade para deep links legados baseados em query params
    if (search.mode === "otp") {
      throw redirect({ to: "/otp" });
    }
    if (search.mode === "gestor" || search.mode === "manager") {
      throw redirect({ to: "/login", search: { perfil: "gestor" } });
    }
    if (
      search.mode === "login" ||
      search.mode === "doctor" ||
      search.mode === "medico" ||
      search.mode === "cadsus"
    ) {
      throw redirect({ to: "/login" });
    }

    const doctor = getStoredDoctorSession();
    if (doctor) throw redirect({ to: "/medico" });

    const manager = getStoredManagerSession();
    if (manager) throw redirect({ to: "/gestor" });
  },
  component: HomeLanding,
});
