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
  heroFeatures,
  journeySteps,
  landingStatistics,
  mapPins,
  partnerClubs,
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
                Court4 analyzes your pickleball matches so you can track progress,
                unlock insights, and become the player you aim to be.
              </p>

              <div className="landing-hero-features" aria-label="Court4 benefits">
                {heroFeatures.map((feature) => (
                  <div key={feature.label}>
                    <feature.icon aria-hidden="true" />
                    <span>{feature.label}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="landing-auth-placement">
              <LandingAuthPanel />
            </div>
          </div>
        </section>

        <div className="landing-content">
          <section className="landing-statistics" aria-label="Court4 statistics">
            {landingStatistics.map((statistic) => (
              <div key={statistic.label}>
                <statistic.icon aria-hidden="true" />
                <p>
                  <strong>{statistic.value}</strong>
                  <span>{statistic.label}</span>
                </p>
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
              src="/landing/court4-insights.png"
              alt="Court4 Match IQ score beside an analyzed pickleball court"
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
              src="/landing/court4-store.png"
              alt="Court4 cap, performance shirt, paddle, backpack, and pickleball"
              fill
              sizes="(max-width: 767px) 100vw, 70vw"
            />
            <div className="landing-store-shade" aria-hidden="true" />
            <div className="landing-feature-copy">
              <h2 id="store-heading">
                <strong>Court4</strong> apparel &amp; paddle store
              </h2>
              <p>Play the game. Live the game.</p>
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
              <h2 id="clubs-heading">Play more. Save more.</h2>
              <p>
                Exclusive hourly rate for Court4 users at our partner clubs.
              </p>
              <div className="landing-map" aria-label="Illustrative partner club map">
                {mapPins.map((pin, index) => (
                  <MapPin
                    key={`${pin.left}-${pin.top}`}
                    aria-label={`Illustrative club location ${index + 1}`}
                    style={{ left: pin.left, top: pin.top }}
                  />
                ))}
              </div>
              <PlannedFeatureAction message="The live partner-club directory is planned. The reference rates are shown here for preview.">
                View all partner clubs
              </PlannedFeatureAction>
            </div>

            <div className="landing-club-table-wrap">
              <table>
                <caption className="sr-only">
                  Reference Court4 partner club rates
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Club &amp; location</th>
                    <th scope="col">Standard hourly rate</th>
                    <th scope="col">Court4 user rate</th>
                  </tr>
                </thead>
                <tbody>
                  {partnerClubs.map((club) => (
                    <tr key={club.name}>
                      <th scope="row">
                        <MapPin aria-hidden="true" />
                        <span>
                          {club.name}
                          <small>{club.location}</small>
                        </span>
                      </th>
                      <td>{club.standardRate}</td>
                      <td>
                        <strong>{club.court4Rate}</strong>
                        <span>{club.discount}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="landing-reference-note">
                Reference rates for the approved design preview; availability is
                not yet live.
              </p>
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
                Get early news, product updates, and exclusive early-bird access
                to partner clubs and offers.
              </p>
            </div>
            <NewsletterForm />
          </section>
        </div>
      </main>

      <footer className="landing-footer" id="support">
        <div className="landing-footer-brand">
          <Court4Brand />
          <p>
            Court4 uses AI to analyze your pickleball matches and help you become
            the best version of your game.
          </p>
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
        width={1025}
        height={1367}
        priority
      />
    </a>
  );
}
