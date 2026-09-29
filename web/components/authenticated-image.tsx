"use client";

import { type ImgHTMLAttributes, useEffect, useState } from "react";

import { loadArtifactImage } from "@/lib/artifact-image-loader";

type Props = Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "srcSet"> & { src: string; alt: string };

export function AuthenticatedImage(props: Props) {
  // A different private source must never render the previous source's blob.
  return <ArtifactImage key={props.src} {...props} />;
}

function ArtifactImage({
  src,
  alt,
  onError,
  ...props
}: Props) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    const controller = new AbortController();
    loadArtifactImage(src, controller.signal)
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
      controller.abort();
      if (createdUrl) URL.revokeObjectURL(createdUrl);
      setObjectUrl(null);
    };
  }, [src]);

  // No network image source while pending. A failed inline image preserves the
  // existing native error callbacks without making another unauthenticated GET.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...props}
      src={objectUrl ?? (failed ? "data:image/png;base64," : undefined)}
      alt={alt}
      onError={objectUrl || failed ? onError : undefined}
    />
  );
}
