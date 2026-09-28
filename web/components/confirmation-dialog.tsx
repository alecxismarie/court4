"use client";

import { type ReactNode, useEffect, useRef } from "react";

export function ConfirmationDialog({ title, children, onClose, busy = false }: {
  title: string; children: ReactNode; onClose: () => void; busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => { dialog?.close(); trigger?.focus(); };
  }, []);
  return <dialog ref={ref} aria-label={title} tabIndex={-1} onKeyDown={event => {
    if (event.key !== "Tab") return;
    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]'));
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first) { event.preventDefault(); event.currentTarget.focus(); }
    else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }} onCancel={event => {
    event.preventDefault(); if (!busy) onClose();
  }} className="w-[calc(100%-2rem)] max-w-lg rounded-xl border border-court-line bg-white p-6 text-court-ink shadow-xl backdrop:bg-black/50">
    <h2 className="text-xl font-semibold">{title}</h2>
    {children}
  </dialog>;
}
