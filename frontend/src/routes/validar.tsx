import { createRoute, lazyRouteComponent } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { rootRoute } from "./root";

const LazyDocumentValidationPage = lazyRouteComponent(
  () => import("@/features/consultation/pages/document-validation-page"),
  "DocumentValidationPage",
);

export const validarRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/validar",
  component: function ValidarRouteComponent() {
    return (
      <ClinicalPageLayout subtitle="Validação Pública de Documentos Clínicos ICP-Brasil">
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyDocumentValidationPage />
        </Suspense>
      </ClinicalPageLayout>
    );
  },
});
