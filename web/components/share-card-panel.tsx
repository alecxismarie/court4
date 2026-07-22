"use client";

import { Download, Share2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { AnalyticsReport, MatchIQReport } from "@/lib/api/types";
import {
  buildShareCardData,
  getShareCardFormat,
  SHARE_CARD_FORMATS,
  type ShareCardArtifact,
  type ShareCardFormatId,
} from "@/lib/share-card";
import { createShareCardPng, renderShareCardToCanvas } from "@/lib/share-card-renderer";
import { usePlayerProfile } from "@/lib/use-player-profile";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const DEFAULT_PLAYER_NAME = "Local Player";

export function ShareCardPanel({
  report,
  matchIQ,
}: {
  report: AnalyticsReport;
  matchIQ: MatchIQReport | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { profile, isLoaded } = usePlayerProfile();
  const [playerName, setPlayerName] = useState(DEFAULT_PLAYER_NAME);
  const [formatId, setFormatId] = useState<ShareCardFormatId>("story");
  const [artifact, setArtifact] = useState<ShareCardArtifact>("heatmap");
  const [includeResultsLink, setIncludeResultsLink] = useState(false);
  const [resultsUrl, setResultsUrl] = useState<string | undefined>();
  const [status, setStatus] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const format = getShareCardFormat(formatId);

  useEffect(() => {
    setResultsUrl(window.location.href);
  }, []);

  useEffect(() => {
    if (!isLoaded || !profile.displayName) {
      return;
    }
    setPlayerName((current) =>
      current === DEFAULT_PLAYER_NAME || current.trim() === "" ? profile.displayName : current,
    );
  }, [isLoaded, profile.displayName]);

  const cardData = useMemo(
    () =>
      buildShareCardData({
        analytics: report,
        matchIQ,
        playerName,
        artifact,
        resultsUrl: includeResultsLink ? resultsUrl : undefined,
      }),
    [artifact, includeResultsLink, matchIQ, playerName, report, resultsUrl],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    let active = true;
    setPreviewError(null);
    void renderShareCardToCanvas(canvas, cardData, format).catch(() => {
      if (active) {
        setPreviewError("Share card preview could not be rendered.");
      }
    });

    return () => {
      active = false;
    };
  }, [cardData, format]);

  async function handleDownload() {
    await exportCard(async (blob, filename) => {
      downloadBlob(blob, filename);
      setStatus("PNG downloaded.");
    });
  }

  async function handleNativeShare() {
    if (typeof navigator.share !== "function") {
      setStatus("Native sharing is not available in this browser.");
      return;
    }

    await exportCard(async (blob, filename) => {
      const file = new File([blob], filename, { type: "image/png" });
      const shareWithFile: ShareData = {
        files: [file],
        title: "Court4 Performance Card",
        text: `${cardData.playerName} Court4 movement results`,
      };

      if (typeof navigator.canShare === "function" && navigator.canShare(shareWithFile)) {
        await navigator.share(shareWithFile);
      } else {
        await navigator.share({
          title: "Court4 Performance Card",
          text: `${cardData.playerName} Court4 movement results`,
          url: cardData.resultsUrl,
        });
      }
      setStatus("Native share opened.");
    });
  }

  async function exportCard(onReady: (blob: Blob, filename: string) => Promise<void> | void) {
    setIsExporting(true);
    setStatus(null);
    try {
      const blob = await createShareCardPng(cardData, format);
      await onReady(blob, getShareCardFilename(report.analysis_id, format.id));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setStatus("Share canceled.");
      } else {
        setStatus("Court4 could not create the share card.");
      }
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <section id="share-card" className="rounded-md border border-court-line bg-white p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-court-green">
            Share card
          </p>
          <h2 className="mt-2 text-lg font-semibold text-court-ink">
            Share Performance Card
          </h2>
        </div>
        <span className="rounded-md bg-court-panel px-3 py-2 text-xs font-semibold uppercase tracking-wide text-court-green">
          PNG
        </span>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,380px)]">
        <div className="space-y-5">
          <label className="grid gap-2 text-sm font-semibold text-court-ink">
            Display name
            <input
              className="rounded-md border border-court-line px-3 py-2 text-sm font-medium"
              value={playerName}
              maxLength={36}
              onChange={(event) => setPlayerName(event.target.value)}
            />
          </label>

          <fieldset>
            <legend className="text-sm font-semibold text-court-ink">Format</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-3" role="group" aria-label="Share card format">
              {SHARE_CARD_FORMATS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={formatId === item.id}
                  className={cn(
                    "rounded-md border px-3 py-3 text-left text-sm font-semibold transition",
                    formatId === item.id
                      ? "border-court-green bg-green-50 text-court-green"
                      : "border-court-line bg-white text-court-ink hover:bg-court-panel",
                  )}
                  onClick={() => setFormatId(item.id)}
                >
                  <span className="block">{item.label}</span>
                  <span className="mt-1 block text-xs font-medium text-court-muted">
                    {item.sizeLabel}
                  </span>
                </button>
              ))}
            </div>
          </fieldset>

          <label className="grid gap-2 text-sm font-semibold text-court-ink">
            Movement image
            <select
              className="rounded-md border border-court-line px-3 py-2 text-sm"
              value={artifact}
              onChange={(event) => setArtifact(event.target.value as ShareCardArtifact)}
            >
              <option value="heatmap">Heatmap</option>
              <option value="trajectory">Trajectory</option>
              <option value="none">None</option>
            </select>
          </label>

          <label className="flex items-center gap-3 text-sm font-semibold text-court-ink">
            <input
              type="checkbox"
              checked={includeResultsLink}
              onChange={(event) => setIncludeResultsLink(event.target.checked)}
            />
            Include results link
          </label>

          <div className="flex flex-wrap gap-3">
            <Button type="button" onClick={handleDownload} disabled={isExporting}>
              <Download aria-hidden="true" className="h-4 w-4" />
              {isExporting ? "Creating PNG" : "Download PNG"}
            </Button>
            <Button type="button" variant="secondary" onClick={handleNativeShare} disabled={isExporting}>
              <Share2 aria-hidden="true" className="h-4 w-4" />
              Share
            </Button>
          </div>

          {status ? (
            <p className="text-sm font-medium text-court-muted" role="status">
              {status}
            </p>
          ) : null}
        </div>

        <div>
          <div className="rounded-md border border-court-line bg-court-panel p-3">
            {previewError ? (
              <div className="flex aspect-[9/16] items-center justify-center rounded-md bg-white px-4 text-center text-sm text-court-muted">
                {previewError}
              </div>
            ) : (
              <canvas
                ref={canvasRef}
                role="img"
                aria-label={`Court4 share card preview for ${cardData.playerName}`}
                className="block w-full rounded-md bg-white"
                style={{ aspectRatio: `${format.width} / ${format.height}` }}
              />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function getShareCardFilename(analysisId: string, formatId: ShareCardFormatId): string {
  const normalizedAnalysisId = analysisId.replace(/[^a-zA-Z0-9_-]/g, "-");
  return `court4-${normalizedAnalysisId}-${formatId}.png`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
