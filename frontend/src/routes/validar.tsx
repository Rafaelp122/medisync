import { createRoute } from "@tanstack/react-router";
import { DocumentValidationPage } from "@/features/consultation/pages/document-validation-page";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { rootRoute } from "./root";

export const validarRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/validar",
  component: function ValidarRouteComponent() {
    return (
      <ClinicalPageLayout subtitle="Validação Pública de Documentos Clínicos ICP-Brasil">
        <DocumentValidationPage />
      </ClinicalPageLayout>
    );
  },
});
