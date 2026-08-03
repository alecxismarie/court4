import type { ShareCardData, ShareCardFormat } from "@/lib/share-card";
import { authenticatedFetch } from "@/lib/api/client";

const LOGO_URL = "/brand/court4-logo-192.png";

const COLORS = {
  background: "#eef4f0",
  surface: "#ffffff",
  panel: "#f7faf8",
  ink: "#17211b",
  muted: "#5c6f64",
  line: "#d8e1dc",
  green: "#176b4d",
  lime: "#9cbf33",
  navy: "#061f38",
  blue: "#245c9f",
};

type LoadedImage = {
  image: HTMLImageElement;
  cleanup: () => void;
};

type LayoutScale = {
  padding: number;
  gap: number;
  titleFont: number;
  bodyFont: number;
  smallFont: number;
  metricFont: number;
  artifactHeight: number;
  summaryLines: number;
  maxInsights: number;
  maxInsightsWithArtifact: number;
  insightLines: number;
  focusLines: number;
};

export async function renderShareCardToCanvas(
  canvas: HTMLCanvasElement,
  data: ShareCardData,
  format: ShareCardFormat,
): Promise<void> {
  canvas.width = format.width;
  canvas.height = format.height;

  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas rendering is not available.");
  }

  const [logo, artifact] = await Promise.all([
    loadOptionalImage(LOGO_URL),
    data.artifactUrl ? loadOptionalImage(data.artifactUrl) : Promise.resolve(null),
  ]);

  try {
    drawShareCard(context, data, format, logo?.image ?? null, artifact?.image ?? null);
  } finally {
    logo?.cleanup();
    artifact?.cleanup();
  }
}

export async function createShareCardPng(
  data: ShareCardData,
  format: ShareCardFormat,
): Promise<Blob> {
  const canvas = document.createElement("canvas");
  await renderShareCardToCanvas(canvas, data, format);
  return canvasToBlob(canvas);
}

function drawShareCard(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  format: ShareCardFormat,
  logo: HTMLImageElement | null,
  artifact: HTMLImageElement | null,
) {
  const layout = getLayoutScale(format);
  const contentWidth = format.width - layout.padding * 2;
  let y = layout.padding;

  context.clearRect(0, 0, format.width, format.height);
  context.fillStyle = COLORS.background;
  context.fillRect(0, 0, format.width, format.height);
  drawCourtLines(context, format.width, format.height);

  context.fillStyle = COLORS.surface;
  roundedRect(
    context,
    layout.padding * 0.55,
    layout.padding * 0.55,
    format.width - layout.padding * 1.1,
    format.height - layout.padding * 1.1,
    8,
  );
  context.fill();

  y = drawHeader(context, data, logo, layout, format.width, y);
  y = drawPlayerBlock(context, data, layout, contentWidth, y);
  y = drawMetricBlock(context, data, layout, contentWidth, y);
  y = drawZoneBlock(context, data, layout, contentWidth, y);

  if (artifact) {
    y = drawArtifactBlock(context, data, artifact, layout, contentWidth, y);
  }

  y = drawMatchIQBlock(context, data, layout, contentWidth, y);
  drawFooter(context, data, layout, format);
}

function getLayoutScale(format: ShareCardFormat): LayoutScale {
  if (format.id === "story") {
    return {
      padding: 72,
      gap: 28,
      titleFont: 68,
      bodyFont: 30,
      smallFont: 24,
      metricFont: 86,
      artifactHeight: 520,
      summaryLines: 3,
      maxInsights: 2,
      maxInsightsWithArtifact: 1,
      insightLines: 2,
      focusLines: 2,
    };
  }
  if (format.id === "portrait") {
    return {
      padding: 64,
      gap: 22,
      titleFont: 58,
      bodyFont: 28,
      smallFont: 22,
      metricFont: 76,
      artifactHeight: 280,
      summaryLines: 2,
      maxInsights: 2,
      maxInsightsWithArtifact: 1,
      insightLines: 2,
      focusLines: 2,
    };
  }
  return {
    padding: 56,
    gap: 18,
    titleFont: 50,
    bodyFont: 24,
    smallFont: 19,
    metricFont: 64,
    artifactHeight: 190,
    summaryLines: 1,
    maxInsights: 1,
    maxInsightsWithArtifact: 1,
    insightLines: 1,
    focusLines: 1,
  };
}

function drawHeader(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  logo: HTMLImageElement | null,
  layout: LayoutScale,
  canvasWidth: number,
  y: number,
): number {
  const logoSize = layout.padding * 1.2;
  const x = layout.padding;
  if (logo) {
    drawContainedImage(context, logo, x, y, logoSize, logoSize);
  } else {
    context.fillStyle = COLORS.green;
    roundedRect(context, x, y, logoSize, logoSize, 8);
    context.fill();
    context.fillStyle = COLORS.surface;
    context.font = `700 ${layout.bodyFont}px Arial, Helvetica, sans-serif`;
    context.fillText("C4", x + logoSize * 0.28, y + logoSize * 0.62);
  }

  context.fillStyle = COLORS.green;
  context.font = `700 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
  context.textAlign = "right";
  context.fillText("COURT4", canvasWidth - layout.padding, y + layout.smallFont);
  context.fillStyle = COLORS.muted;
  context.font = `700 ${layout.smallFont * 0.78}px Arial, Helvetica, sans-serif`;
  context.fillText("KNOW YOUR GAME", canvasWidth - layout.padding, y + layout.smallFont * 2.05);
  context.textAlign = "left";

  return y + logoSize + layout.gap * 0.7;
}

function drawPlayerBlock(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  layout: LayoutScale,
  contentWidth: number,
  y: number,
): number {
  const x = layout.padding;
  context.fillStyle = COLORS.green;
  context.font = `700 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
  context.fillText("PERFORMANCE CARD", x, y);
  y += layout.titleFont * 1.05;

  context.fillStyle = COLORS.ink;
  context.font = `700 ${layout.titleFont}px Arial, Helvetica, sans-serif`;
  y = drawWrappedText(context, data.playerName, x, y, contentWidth, layout.titleFont * 1.1, 2);

  if (data.matchDate) {
    y += layout.bodyFont * 0.9;
    context.fillStyle = COLORS.muted;
    context.font = `400 ${layout.bodyFont}px Arial, Helvetica, sans-serif`;
    context.fillText(data.matchDate, x, y);
    y += layout.bodyFont * 1.25;
  }

  return y + layout.gap * 0.35;
}

function drawMetricBlock(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  layout: LayoutScale,
  contentWidth: number,
  y: number,
): number {
  const panelHeight = layout.metricFont * 1.75;
  const x = layout.padding;
  context.fillStyle = COLORS.panel;
  roundedRect(context, x, y, contentWidth, panelHeight, 8);
  context.fill();
  context.strokeStyle = COLORS.line;
  context.lineWidth = 2;
  context.stroke();

  context.fillStyle = COLORS.muted;
  context.font = `700 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
  context.fillText("TOTAL DISTANCE", x + layout.gap, y + layout.gap + layout.smallFont);

  const distance = data.totalDistance
    ? `${data.totalDistance.value.toFixed(1)} ${data.totalDistance.unit}`
    : "Unavailable";
  context.fillStyle = COLORS.ink;
  context.font = `700 ${layout.metricFont}px Arial, Helvetica, sans-serif`;
  context.fillText(distance, x + layout.gap, y + layout.gap + layout.smallFont + layout.metricFont);

  return y + panelHeight + layout.gap;
}

function drawZoneBlock(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  layout: LayoutScale,
  contentWidth: number,
  y: number,
): number {
  const x = layout.padding;
  const zoneHeight = layout.bodyFont * 4.25;
  context.fillStyle = COLORS.ink;
  context.font = `700 ${layout.bodyFont}px Arial, Helvetica, sans-serif`;
  context.fillText("Zone Occupancy", x, y + layout.bodyFont);
  y += layout.bodyFont * 1.55;

  const zones = [
    { label: "Kitchen", value: data.zones?.kitchen, color: COLORS.green },
    { label: "Transition", value: data.zones?.transition, color: COLORS.lime },
    { label: "Baseline", value: data.zones?.baseline, color: COLORS.blue },
  ];
  const columnGap = layout.gap * 0.75;
  const columnWidth = (contentWidth - columnGap * 2) / 3;
  zones.forEach((zone, index) => {
    const columnX = x + index * (columnWidth + columnGap);
    context.fillStyle = COLORS.panel;
    roundedRect(context, columnX, y, columnWidth, zoneHeight, 8);
    context.fill();
    context.strokeStyle = COLORS.line;
    context.stroke();

    context.fillStyle = COLORS.muted;
    context.font = `700 ${layout.smallFont * 0.85}px Arial, Helvetica, sans-serif`;
    context.fillText(zone.label, columnX + layout.gap * 0.65, y + layout.smallFont * 1.5);

    context.fillStyle = zone.color;
    context.font = `700 ${layout.bodyFont * 1.15}px Arial, Helvetica, sans-serif`;
    context.fillText(
      typeof zone.value === "number" ? `${zone.value.toFixed(1)}%` : "N/A",
      columnX + layout.gap * 0.65,
      y + zoneHeight - layout.gap,
    );
  });

  return y + zoneHeight + layout.gap;
}

function drawArtifactBlock(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  artifact: HTMLImageElement,
  layout: LayoutScale,
  contentWidth: number,
  y: number,
): number {
  const x = layout.padding;
  context.fillStyle = COLORS.ink;
  context.font = `700 ${layout.bodyFont}px Arial, Helvetica, sans-serif`;
  context.fillText(data.artifactLabel ?? "Movement Map", x, y + layout.bodyFont);
  y += layout.bodyFont * 1.45;

  context.fillStyle = COLORS.panel;
  roundedRect(context, x, y, contentWidth, layout.artifactHeight, 8);
  context.fill();
  context.strokeStyle = COLORS.line;
  context.stroke();
  drawContainedImage(
    context,
    artifact,
    x + layout.gap,
    y + layout.gap,
    contentWidth - layout.gap * 2,
    layout.artifactHeight - layout.gap * 2,
  );

  return y + layout.artifactHeight + layout.gap;
}

function drawMatchIQBlock(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  layout: LayoutScale,
  contentWidth: number,
  y: number,
): number {
  const x = layout.padding;
  context.fillStyle = COLORS.ink;
  context.font = `700 ${layout.bodyFont}px Arial, Helvetica, sans-serif`;
  context.fillText("Match IQ", x, y + layout.bodyFont);
  y += layout.bodyFont * 2.2;

  if (data.summary) {
    context.fillStyle = COLORS.muted;
    context.font = `400 ${layout.bodyFont}px Arial, Helvetica, sans-serif`;
    y = drawWrappedText(
      context,
      data.summary,
      x,
      y,
      contentWidth,
      layout.bodyFont * 1.35,
      layout.summaryLines,
    );
    y += layout.gap * 0.45;
  }

  const maxInsights = data.artifactUrl ? layout.maxInsightsWithArtifact : layout.maxInsights;
  const insights = data.insights.slice(0, maxInsights);
  for (const insight of insights) {
    context.fillStyle = COLORS.panel;
    roundedRect(context, x, y, contentWidth, layout.bodyFont * (layout.insightLines + 2.4), 8);
    context.fill();
    context.strokeStyle = COLORS.line;
    context.stroke();

    const textX = x + layout.gap;
    let textY = y + layout.gap + layout.smallFont;
    context.fillStyle = COLORS.ink;
    context.font = `700 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
    textY = drawWrappedText(
      context,
      insight.title,
      textX,
      textY,
      contentWidth - layout.gap * 2,
      layout.smallFont * 1.2,
      1,
    );
    context.fillStyle = COLORS.muted;
    context.font = `400 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
    drawWrappedText(
      context,
      insight.statement,
      textX,
      textY + layout.smallFont * 0.25,
      contentWidth - layout.gap * 2,
      layout.smallFont * 1.2,
      layout.insightLines,
    );
    y += layout.bodyFont * (layout.insightLines + 2.4) + layout.gap * 0.6;
  }

  if (data.focus) {
    context.fillStyle = COLORS.green;
    context.font = `700 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
    context.fillText("FOCUS", x, y + layout.smallFont);
    context.fillStyle = COLORS.muted;
    context.font = `400 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
    y = drawWrappedText(
      context,
      data.focus,
      x,
      y + layout.smallFont * 2.45,
      contentWidth,
      layout.smallFont * 1.25,
      layout.focusLines,
    );
  }

  return y;
}

function drawFooter(
  context: CanvasRenderingContext2D,
  data: ShareCardData,
  layout: LayoutScale,
  format: ShareCardFormat,
) {
  const x = layout.padding;
  const footerY = format.height - layout.padding - layout.smallFont * 1.6;
  const y = footerY;

  context.strokeStyle = COLORS.line;
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(x, y - layout.gap * 0.7);
  context.lineTo(format.width - layout.padding, y - layout.gap * 0.7);
  context.stroke();

  context.fillStyle = COLORS.green;
  context.font = `700 ${layout.smallFont}px Arial, Helvetica, sans-serif`;
  context.fillText("Court4", x, y);
  context.fillStyle = COLORS.muted;
  context.font = `400 ${layout.smallFont * 0.85}px Arial, Helvetica, sans-serif`;
  context.textAlign = "right";
  context.fillText(
    data.resultsUrl ? trimUrl(data.resultsUrl) : "Movement facts only",
    format.width - layout.padding,
    y,
  );
  context.textAlign = "left";
}

function drawCourtLines(
  context: CanvasRenderingContext2D,
  canvasWidth: number,
  canvasHeight: number,
) {
  context.strokeStyle = "rgba(23, 107, 77, 0.12)";
  context.lineWidth = 4;
  const courtWidth = canvasWidth * 0.82;
  const courtHeight = canvasHeight * 0.52;
  const x = canvasWidth * 0.09;
  const y = canvasHeight * 0.34;
  context.strokeRect(x, y, courtWidth, courtHeight);
  context.beginPath();
  context.moveTo(x + courtWidth / 2, y);
  context.lineTo(x + courtWidth / 2, y + courtHeight);
  context.moveTo(x, y + courtHeight * 0.34);
  context.lineTo(x + courtWidth, y + courtHeight * 0.34);
  context.moveTo(x, y + courtHeight * 0.5);
  context.lineTo(x + courtWidth, y + courtHeight * 0.5);
  context.stroke();
}

function drawWrappedText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number,
): number {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = "";

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (context.measureText(candidate).width <= maxWidth) {
      line = candidate;
      continue;
    }
    if (line) {
      lines.push(line);
    }
    line = word;
    if (lines.length === maxLines) {
      break;
    }
  }
  if (line && lines.length < maxLines) {
    lines.push(line);
  }

  if (words.length > 0 && lines.length === maxLines) {
    const fullText = words.join(" ");
    if (lines.join(" ").length < fullText.length) {
      lines[maxLines - 1] = ellipsizeLine(context, lines[maxLines - 1], maxWidth);
    }
  }

  lines.forEach((item, index) => {
    context.fillText(item, x, y + index * lineHeight);
  });
  return y + lines.length * lineHeight;
}

function ellipsizeLine(
  context: CanvasRenderingContext2D,
  value: string,
  maxWidth: number,
): string {
  let candidate = `${value}...`;
  while (candidate.length > 3 && context.measureText(candidate).width > maxWidth) {
    candidate = `${candidate.slice(0, -4)}...`;
  }
  return candidate;
}

function drawContainedImage(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
  const drawWidth = image.naturalWidth * scale;
  const drawHeight = image.naturalHeight * scale;
  const drawX = x + (width - drawWidth) / 2;
  const drawY = y + (height - drawHeight) / 2;
  context.drawImage(image, drawX, drawY, drawWidth, drawHeight);
}

function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
}

async function loadOptionalImage(url: string): Promise<LoadedImage | null> {
  try {
    return await loadImage(url);
  } catch {
    return null;
  }
}

async function loadImage(url: string): Promise<LoadedImage> {
  try {
    return await loadImageDirect(url);
  } catch {
    return loadImageFromBlob(url);
  }
}

async function loadImageFromBlob(url: string): Promise<LoadedImage> {
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    throw new Error("Image could not be loaded.");
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const loadedImage = new Image();
    loadedImage.onload = () => resolve(loadedImage);
    loadedImage.onerror = () => reject(new Error("Image could not be decoded."));
    loadedImage.src = objectUrl;
  });
  return {
    image,
    cleanup: () => URL.revokeObjectURL(objectUrl),
  };
}

async function loadImageDirect(url: string): Promise<LoadedImage> {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const loadedImage = new Image();
    loadedImage.crossOrigin = "anonymous";
    loadedImage.onload = () => resolve(loadedImage);
    loadedImage.onerror = () => reject(new Error("Image could not be decoded."));
    loadedImage.src = url;
  });
  return {
    image,
    cleanup: () => undefined,
  };
}

async function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
        return;
      }
      reject(new Error("PNG export failed."));
    }, "image/png");
  });
}

function trimUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.host}${url.pathname}`;
  } catch {
    return value;
  }
}
