import { createRoute } from "@tanstack/react-router";
import { DocumentValidationPage } from "@/features/consultation/pages/document-validation-page";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { rootRoute } from "./root";

export const validarTokenRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/validar/$token",
  component: function ValidarTokenRouteComponent() {
    const { token } = validarTokenRoute.useParams();
    return (
      <ClinicalPageLayout subtitle="Validação Pública de Documentos Clínicos ICP-Brasil">
        <DocumentValidationPage initialToken={token} />
      </ClinicalPageLayout>
    );
  },
});
