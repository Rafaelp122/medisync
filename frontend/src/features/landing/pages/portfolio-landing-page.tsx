import { AboutAuthorSection } from "@/features/landing/components/about-author-section";
import { ArchitectureShowcase } from "@/features/landing/components/architecture-showcase";
import { HeroSection } from "@/features/landing/components/hero-section";
import { LandingFooter } from "@/features/landing/components/landing-footer";
import { PublicLandingLayout } from "@/layouts/public-landing-layout";

export function PortfolioLandingPage() {
  return (
    <PublicLandingLayout footer={<LandingFooter />}>
      <HeroSection />
      <ArchitectureShowcase />
      <AboutAuthorSection />
    </PublicLandingLayout>
  );
}
