import { createRoute, lazyRouteComponent } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { rootRoute } from "./root";

const LazyDocumentValidationPage = lazyRouteComponent(
  () => import("@/features/consultation/pages/document-validation-page"),
  "DocumentValidationPage",
);

export const validarTokenRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/validar/$token",
  component: function ValidarTokenRouteComponent() {
    const { token } = validarTokenRoute.useParams();
    return (
      <ClinicalPageLayout subtitle="Validação Pública de Documentos Clínicos ICP-Brasil">
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyDocumentValidationPage initialToken={token} />
        </Suspense>
      </ClinicalPageLayout>
    );
  },
});
