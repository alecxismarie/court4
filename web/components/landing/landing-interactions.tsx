"use client";

import { ArrowRight, Menu, X } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

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
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(
      "Newsletter signup is coming soon. Your email was not stored or submitted.",
    );
  }

  return (
    <form className="landing-newsletter-form" onSubmit={submit}>
      <div>
        <label className="sr-only" htmlFor="landing-newsletter-email">Email address</label>
        <input
          id="landing-newsletter-email"
          type="email"
          required
          placeholder="Enter your email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <button type="submit">Join the List</button>
      </div>
      <small>No spam. Unsubscribe anytime.</small>
      {message ? <p role="status">{message}</p> : null}
    </form>
  );
}
