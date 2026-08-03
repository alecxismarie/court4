"use client";

import { ArrowRight, Menu, X } from "lucide-react";
import { type ReactNode, useState } from "react";

export function MobileLandingMenu({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="landing-mobile-menu">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="landing-mobile-navigation"
        aria-label={open ? "Close navigation menu" : "Open navigation menu"}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
      </button>
      {open ? (
        <nav id="landing-mobile-navigation" aria-label="Mobile landing navigation">
          {children}
        </nav>
      ) : null}
    </div>
  );
}

export function PlannedFeatureAction({
  children,
  message,
}: {
  children: ReactNode;
  message: string;
}) {
  const [status, setStatus] = useState<string | null>(null);
  return (
    <div className="landing-planned-action">
      <button type="button" className="landing-outline-button" onClick={() => setStatus(message)}>
        {children}
        <ArrowRight aria-hidden="true" />
      </button>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}

export function NewsletterForm() {
  return (
    <div className="landing-newsletter-form" aria-label="Newsletter unavailable">
      <div>
        <label className="sr-only" htmlFor="landing-newsletter-email">Email address</label>
        <input
          id="landing-newsletter-email"
          type="email"
          disabled
          placeholder="Enter your email"
        />
        <button type="button" disabled>Coming soon</button>
      </div>
      <p role="status">Newsletter signup is unavailable. No email is collected.</p>
    </div>
  );
}
