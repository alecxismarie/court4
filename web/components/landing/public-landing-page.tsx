import {
  ArrowRight,
  Facebook,
  Instagram,
  MapPin,
  Music2,
  Youtube,
} from "lucide-react";
import Image from "next/image";

import {
  footerGroups,
  journeySteps,
  landingBenefits,
  mapPins,
} from "@/lib/landing-content";
import { LandingAuthPanel } from "@/components/landing/landing-auth-panel";
import {
  MobileLandingMenu,
  NewsletterForm,
  PlannedFeatureAction,
} from "@/components/landing/landing-interactions";

const primaryNavigation = [
  { label: "About", href: "#about" },
  { label: "Features", href: "#features" },
  { label: "For Clubs", href: "#partner-clubs" },
  { label: "Support", href: "#support" },
] as const;

export function PublicLandingPage() {
  return (
    <div className="landing-page">
      <a className="landing-skip-link" href="#landing-main">
        Skip to main content
      </a>

      <header className="landing-header">
        <Court4Brand />
        <nav className="landing-desktop-nav" aria-label="Primary navigation">
          {primaryNavigation.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
        <MobileLandingMenu>
          {primaryNavigation.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
            </a>
          ))}
        </MobileLandingMenu>
      </header>

      <main id="landing-main">
        <section className="landing-hero" id="about" aria-labelledby="landing-title">
          <Image
            className="landing-hero-art"
            src="/landing/court4-hero.png"
            alt=""
            fill
            sizes="100vw"
            priority
          />
          <div className="landing-hero-shade" aria-hidden="true" />
          <div className="landing-hero-layout">
            <div className="landing-hero-copy">
              <h1 id="landing-title">
                <span>Know</span>
                <span>Your Game.</span>
                <strong>Elevate</strong>
                <strong>Every Match.</strong>
              </h1>
              <p className="landing-hero-summary">
                Court 4 analyzes your matches so you can track progress,
                unlock insights, and become the player you aim to be.
              </p>
            </div>

            <div className="landing-auth-placement">
              <LandingAuthPanel />
            </div>
          </div>
        </section>

        <div className="landing-content">
          <section className="landing-benefits" aria-label="Why players use Court4">
            {landingBenefits.map((benefit) => (
              <div key={benefit.title}>
                <benefit.icon aria-hidden="true" />
                <div>
                  <h2>{benefit.title}</h2>
                  <p>{benefit.description}</p>
                </div>
              </div>
            ))}
          </section>

          <section
            className="landing-panel landing-journey"
            id="journey"
            aria-labelledby="journey-heading"
          >
            <h2 id="journey-heading">
              Your journey with <em>Court4</em>
            </h2>
            <ol>
              {journeySteps.map((step) => (
                <li key={step.number}>
                  <div className="landing-step-icon">
                    <step.icon aria-hidden="true" />
                  </div>
                  <h3>
                    {step.number}. {step.title}
                  </h3>
                  <p>{step.copy}</p>
                </li>
              ))}
            </ol>
          </section>

          <section
            className="landing-panel landing-insights"
            id="features"
            aria-labelledby="insights-heading"
          >
            <Image
              src="/landing/court4-insights-rally-v3.png"
              alt="Court4 Match IQ score beside two players rallying on a marked pickleball court"
              fill
              sizes="(max-width: 767px) 100vw, 70vw"
            />
            <div className="landing-insights-shade" aria-hidden="true" />
            <div className="landing-feature-copy">
              <h2 id="insights-heading">
                Data that drives
                <strong>real improvement.</strong>
              </h2>
              <p>
                From movement and positioning to consistency and court coverage,
                Court4 turns your match videos into powerful, easy-to-understand
                insights.
              </p>
              <a className="landing-outline-link" href="#journey">
                See features <ArrowRight aria-hidden="true" />
              </a>
            </div>
          </section>

          <section
            className="landing-panel landing-store"
            aria-labelledby="store-heading"
          >
            <Image
              src="/landing/apparel-store-navy.png"
              alt="Court4 performance shirt, cap, paddle, backpack, and pickleball"
              fill
              sizes="(max-width: 767px) 100vw, 70vw"
            />
            <div className="landing-store-shade" aria-hidden="true" />
            <div className="landing-feature-copy">
              <h2 id="store-heading">
                <strong>Court4</strong> apparel &amp; paddle store
              </h2>
              <PlannedFeatureAction message="The Court4 store is planned and is not accepting orders yet.">
                Shop now
              </PlannedFeatureAction>
            </div>
          </section>

          <section
            className="landing-panel landing-clubs"
            id="partner-clubs"
            aria-labelledby="clubs-heading"
          >
            <div className="landing-clubs-intro">
              <h2 id="clubs-heading">Partner program in development</h2>
              <div className="landing-map" aria-label="Illustrative partner club map">
                {mapPins.map((pin, index) => (
                  <MapPin
                    key={`${pin.left}-${pin.top}`}
                    aria-label={`Illustrative club location ${index + 1}`}
                    style={{ left: pin.left, top: pin.top }}
                  />
                ))}
              </div>
              <PlannedFeatureAction message="The partner program is planned. No club partnerships or discounts are currently offered.">
                View all partner clubs
              </PlannedFeatureAction>
            </div>

            <div className="landing-club-table-wrap" id="alpha-status">
              <h3>Private-alpha status</h3>
              <p>Access is limited to approved testers.</p>
            </div>
          </section>

          <section
            className="landing-panel landing-newsletter"
            id="newsletter"
            aria-labelledby="newsletter-heading"
          >
            <div>
              <h2 id="newsletter-heading">Stay ahead of the game.</h2>
              <p>
                Newsletter signup is not available during the private alpha.
              </p>
            </div>
            <NewsletterForm />
          </section>
        </div>
      </main>

      <footer className="landing-footer" id="support">
        <div className="landing-footer-brand">
          <Court4Brand />
          <div className="landing-social-links" aria-label="Social media">
            <a href="#support" aria-label="Instagram, coming soon"><Instagram aria-hidden="true" /></a>
            <a href="#support" aria-label="Facebook, coming soon"><Facebook aria-hidden="true" /></a>
            <a href="#support" aria-label="YouTube, coming soon"><Youtube aria-hidden="true" /></a>
            <a href="#support" aria-label="TikTok, coming soon"><Music2 aria-hidden="true" /></a>
          </div>
        </div>
        <div className="landing-footer-groups">
          {footerGroups.map((group) => (
            <section key={group.title}>
              <h2>{group.title}</h2>
              {group.links.map((link) => (
                <a key={`${group.title}-${link.label}`} href={link.href}>
                  {link.label}
                </a>
              ))}
            </section>
          ))}
        </div>
        <p className="landing-copyright">© 2026 Court4. All rights reserved.</p>
      </footer>
    </div>
  );
}

function Court4Brand() {
  return (
    <a className="landing-brand" href="#landing-main" aria-label="Court4 home">
      <Image
        src="/brand/court4-logo.png"
        alt="Court4"
        width={1080}
        height={1350}
        priority
      />
    </a>
  );
}
