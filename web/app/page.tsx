import { PublicLandingPage } from "@/components/landing/public-landing-page";
import { LandingSessionBoundary } from "@/components/landing/landing-session-boundary";

export default function LandingPage() {
  return (
    <LandingSessionBoundary>
      <PublicLandingPage />
    </LandingSessionBoundary>
  );
}
