import { createRoute } from "@tanstack/react-router";
import { PortfolioLandingPage } from "@/features/landing/pages/portfolio-landing-page";
import { rootRoute } from "./root";

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: PortfolioLandingPage,
});
