"use client";

import { type ImgHTMLAttributes, useEffect, useState } from "react";

import { authenticatedFetch } from "@/lib/api/client";

export function AuthenticatedImage({
  src,
  alt,
  onError,
  ...props
}: Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> & { src: string; alt: string }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    setFailed(false);
    authenticatedFetch(src, { headers: { Accept: "image/*" } })
      .then((response) => {
        if (!response.ok) throw new Error("Artifact image is unavailable.");
        return response.blob();
      })
      .then((blob) => {
        if (!active) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
      setObjectUrl(null);
    };
  }, [src]);

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...props}
      src={objectUrl ?? (failed ? "/__court4_missing_artifact__" : src)}
      alt={alt}
      onError={objectUrl || failed ? onError : undefined}
    />
  );
}
