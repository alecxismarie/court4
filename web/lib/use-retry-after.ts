"use client";

import { useEffect, useState } from "react";
import { Court4ApiError } from "@/lib/api/client";

export function useRetryAfter(firstError: unknown, secondError?: unknown): number {
  const [remaining, setRemaining] = useState(0);
  const delays = [firstError, secondError].map((error) => error instanceof Court4ApiError && error.status === 429
    ? error.retryAfterMs : 0);
  const delay = Math.max(0, ...delays);

  useEffect(() => {
    const deadline = Date.now() + delay;
    const update = () => setRemaining(Math.ceil(Math.max(0, deadline - Date.now()) / 1000));
    update();
    if (delay === 0) return;
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [delay, firstError, secondError]);
  return remaining;
}
