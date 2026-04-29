import receiverCardsData from "@/data/receiver-cards.json";
import senderProcessorsData from "@/data/sender-processors.json";
import {
  DEFAULT_USABLE_MBPS_1G,
  DEFAULT_USABLE_MBPS_5G,
  streamBandwidthMbps,
  totalBppRgbPacked,
} from "@/lib/led-bandwidth";

export type ReceiverPortSpeed = "1g" | "5g" | "unknown";
export type ProcessorOutputMode = "1g" | "5g" | "10g";
export type ProjectOutputPreference = "auto" | "1g" | "5g";
export type ProjectRequirement = "hdr" | "lowLatency" | "redundancy" | "monitoring";

type RawReceiverCard = {
  name?: string;
  series?: string;
  loading_capacity?: string | null;
  features?: {
    display_effect?: string[] | null;
  } | null;
  performance?: {
    control_area_per_card?: string | null;
  } | null;
  hardware?: {
    transmission_rate?: string | null;
  } | null;
  comparison_features?: {
    loading_capacity?: string | null;
    color_depth?: string | null;
    dynamic_frame_rate?: string | null;
    data_group?: string | null;
    hdr?: boolean | null;
    low_latency?: boolean | null;
    loop_backup?: boolean | null;
    receiving_card_backup?: boolean | null;
    cabinet_monitoring?: boolean | null;
    network_cable_detection?: boolean | null;
  } | null;
};

type ReceiverCardsJson = {
  cards: RawReceiverCard[];
};

type RawProcessorOutput = {
  mode?: string;
  ports?: number;
  capacity_pixels?: number;
  label?: string;
};

type RawSenderProcessor = {
  name?: string;
  series?: string;
  overview?: string;
  max_width?: number | null;
  max_height?: number | null;
  max_frame_rate_hz?: number | null;
  max_color_depth_bpc?: number | null;
  outputs?: RawProcessorOutput[];
  features?: string[];
};

type SenderProcessorsJson = {
  processors: RawSenderProcessor[];
};

export type ReceiverCardCapacity = {
  width: number;
  height: number;
  pixels: number;
  label: string;
};

export type ReceiverCardCatalogItem = {
  name: string;
  series: string;
  capacityOptions: ReceiverCardCapacity[];
  maxCapacityPixels: number;
  maxCapacityLabel: string;
  capacityText: string;
  dataGroupText: string;
  maxColorDepthBpc: number | null;
  maxFrameRateHz: number | null;
  portSpeed: ReceiverPortSpeed;
  transmissionRateText: string;
  supportsHdr: boolean;
  supportsLowLatency: boolean;
  supportsRedundancy: boolean;
  supportsMonitoring: boolean;
};

export type ProcessorOutput = {
  mode: ProcessorOutputMode;
  ports: number;
  capacityPixels: number;
  label: string;
};

export type SenderProcessorCatalogItem = {
  name: string;
  series: string;
  overview: string;
  maxWidth: number | null;
  maxHeight: number | null;
  maxFrameRateHz: number | null;
  maxColorDepthBpc: number | null;
  outputs: ProcessorOutput[];
  features: string[];
};

export type CabinetPixelSize = {
  width: number;
  height: number;
  pixels: number;
};

const rawCards = (receiverCardsData as ReceiverCardsJson).cards;
const rawProcessors = (senderProcessorsData as SenderProcessorsJson).processors;

function cleanText(raw: string | null | undefined): string {
  return raw?.replaceAll(/\s+/g, " ").trim() ?? "";
}

function parseDimensionNumber(raw: string): number {
  return Number.parseInt(raw.replaceAll(",", ""), 10);
}

function extractCapacityOptions(...texts: Array<string | null | undefined>): ReceiverCardCapacity[] {
  const options = new Map<string, ReceiverCardCapacity>();

  for (const rawText of texts) {
    const text = cleanText(rawText);
    const matches = text.matchAll(/(\d[\d,]*)\s*(?:x|X|\*|\u00d7)\s*(\d[\d,]*)/g);
    for (const match of matches) {
      const width = parseDimensionNumber(match[1]);
      const height = parseDimensionNumber(match[2]);
      if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) continue;

      const key = `${width}x${height}`;
      options.set(key, {
        width,
        height,
        pixels: width * height,
        label: key,
      });
    }
  }

  return [...options.values()].sort((a, b) => b.pixels - a.pixels);
}

function extractMaxColorDepthBpc(raw: string | null | undefined): number | null {
  const text = cleanText(raw);
  if (!text) return null;

  const values = [...text.matchAll(/\d+(?:\.\d+)?/g)]
    .map((match) => Number.parseFloat(match[0]))
    .filter((n) => Number.isFinite(n) && n >= 6 && n <= 16);

  return values.length > 0 ? Math.max(...values) : null;
}

function extractMaxFrameRateHz(raw: string | null | undefined): number | null {
  const text = cleanText(raw);
  if (!text) return null;

  const values = [...text.matchAll(/(\d+(?:\.\d+)?)\s*(?=Hz)/gi)]
    .map((match) => Number.parseFloat(match[1]))
    .filter((n) => Number.isFinite(n) && n > 0);

  return values.length > 0 ? Math.max(...values) : null;
}

function detectPortSpeed(transmissionRateText: string, series: string): ReceiverPortSpeed {
  const text = `${transmissionRateText} ${series}`.toLowerCase();
  if (/\b5\s*g/.test(text)) return "5g";
  if (/\b1\s*g|\bgigabit\b/.test(text)) return "1g";
  return "unknown";
}

function hasComparisonFlag(card: RawReceiverCard, key: keyof NonNullable<RawReceiverCard["comparison_features"]>): boolean {
  return card.comparison_features?.[key] === true;
}

function normalizeReceiverCard(card: RawReceiverCard): ReceiverCardCatalogItem {
  const name = cleanText(card.name) || "Unknown";
  const series = cleanText(card.series) || "Uncategorized";
  const capacityText =
    cleanText(card.performance?.control_area_per_card) ||
    cleanText(card.comparison_features?.loading_capacity) ||
    cleanText(card.loading_capacity);
  const capacityOptions = extractCapacityOptions(
    card.performance?.control_area_per_card,
    card.comparison_features?.loading_capacity,
    card.loading_capacity,
  );
  const maxCapacity = capacityOptions[0];
  const transmissionRateText = cleanText(card.hardware?.transmission_rate);

  return {
    name,
    series,
    capacityOptions,
    maxCapacityPixels: maxCapacity?.pixels ?? 0,
    maxCapacityLabel: maxCapacity?.label ?? "Unknown",
    capacityText,
    dataGroupText: cleanText(card.comparison_features?.data_group),
    maxColorDepthBpc: extractMaxColorDepthBpc(card.comparison_features?.color_depth),
    maxFrameRateHz: extractMaxFrameRateHz(card.comparison_features?.dynamic_frame_rate),
    portSpeed: detectPortSpeed(transmissionRateText, series),
    transmissionRateText,
    supportsHdr: hasComparisonFlag(card, "hdr"),
    supportsLowLatency: hasComparisonFlag(card, "low_latency"),
    supportsRedundancy: hasComparisonFlag(card, "loop_backup") || hasComparisonFlag(card, "receiving_card_backup"),
    supportsMonitoring: hasComparisonFlag(card, "cabinet_monitoring") || hasComparisonFlag(card, "network_cable_detection"),
  };
}

function isProcessorOutputMode(mode: string | undefined): mode is ProcessorOutputMode {
  return mode === "1g" || mode === "5g" || mode === "10g";
}

function normalizeProcessor(processor: RawSenderProcessor): SenderProcessorCatalogItem {
  return {
    name: cleanText(processor.name) || "Unknown",
    series: cleanText(processor.series) || "Uncategorized",
    overview: cleanText(processor.overview),
    maxWidth: Number.isFinite(processor.max_width) ? processor.max_width ?? null : null,
    maxHeight: Number.isFinite(processor.max_height) ? processor.max_height ?? null : null,
    maxFrameRateHz: Number.isFinite(processor.max_frame_rate_hz) ? processor.max_frame_rate_hz ?? null : null,
    maxColorDepthBpc: Number.isFinite(processor.max_color_depth_bpc) ? processor.max_color_depth_bpc ?? null : null,
    outputs: (processor.outputs ?? [])
      .filter((output): output is RawProcessorOutput & { mode: ProcessorOutputMode } => isProcessorOutputMode(output.mode))
      .map((output) => ({
        mode: output.mode,
        ports: Math.max(0, Math.trunc(output.ports ?? 0)),
        capacityPixels: Math.max(0, Math.trunc(output.capacity_pixels ?? 0)),
        label: cleanText(output.label) || output.mode.toUpperCase(),
      }))
      .sort((a, b) => a.capacityPixels - b.capacityPixels),
    features: processor.features?.map(cleanText).filter(Boolean) ?? [],
  };
}

export const RECEIVER_CARD_CATALOG: ReceiverCardCatalogItem[] = rawCards
  .map(normalizeReceiverCard)
  .sort((a, b) => {
    const seriesCompare = a.series.localeCompare(b.series);
    return seriesCompare === 0 ? a.name.localeCompare(b.name, undefined, { numeric: true }) : seriesCompare;
  });

export const SENDER_PROCESSOR_CATALOG: SenderProcessorCatalogItem[] = rawProcessors
  .map(normalizeProcessor)
  .sort((a, b) => {
    const seriesCompare = a.series.localeCompare(b.series);
    return seriesCompare === 0 ? a.name.localeCompare(b.name, undefined, { numeric: true }) : seriesCompare;
  });

export function ledSignalMbps(width: number, height: number, fps: number, bitsPerChannel: number): number {
  return streamBandwidthMbps(Math.max(0, width) * Math.max(0, height), Math.max(0, fps), totalBppRgbPacked(bitsPerChannel));
}

export function usableMbpsForPortSpeed(speed: Exclude<ReceiverPortSpeed, "unknown">): number {
  return speed === "5g" ? DEFAULT_USABLE_MBPS_5G : DEFAULT_USABLE_MBPS_1G;
}

export function portsNeededForMbps(requiredMbps: number, usableMbps: number): number {
  if (requiredMbps <= 0 || usableMbps <= 0) return 0;
  return Math.ceil(requiredMbps / usableMbps);
}

export function cabinetPixelSize(widthMm: number, heightMm: number, pixelPitchMm: number): CabinetPixelSize {
  if (widthMm <= 0 || heightMm <= 0 || pixelPitchMm <= 0) {
    return { width: 0, height: 0, pixels: 0 };
  }

  const width = Math.max(1, Math.round(widthMm / pixelPitchMm));
  const height = Math.max(1, Math.round(heightMm / pixelPitchMm));
  return { width, height, pixels: width * height };
}

export function cabinetsNeeded(screenWidth: number, screenHeight: number, cabinetWidth: number, cabinetHeight: number) {
  if (screenWidth <= 0 || screenHeight <= 0 || cabinetWidth <= 0 || cabinetHeight <= 0) {
    return { across: 0, tall: 0, total: 0 };
  }

  const across = Math.ceil(screenWidth / cabinetWidth);
  const tall = Math.ceil(screenHeight / cabinetHeight);
  return { across, tall, total: across * tall };
}

export function cardsNeededByPixels(totalPixels: number, receiverCapacityPixels: number): number {
  if (totalPixels <= 0 || receiverCapacityPixels <= 0) return 0;
  return Math.ceil(totalPixels / receiverCapacityPixels);
}

export function cardsPerCabinet(cabinetPixels: number, receiverCapacityPixels: number): number {
  if (cabinetPixels <= 0 || receiverCapacityPixels <= 0) return 0;
  return Math.max(1, Math.ceil(cabinetPixels / receiverCapacityPixels));
}

export function receiverSupportsTarget(card: ReceiverCardCatalogItem, fps: number, bitsPerChannel: number) {
  const maxColorDepthBpc = card.maxColorDepthBpc;
  const maxFrameRateHz = card.maxFrameRateHz;
  const depthKnown = maxColorDepthBpc !== null;
  const frameKnown = maxFrameRateHz !== null;

  return {
    depthKnown,
    frameKnown,
    depthOk: maxColorDepthBpc !== null ? maxColorDepthBpc >= bitsPerChannel : false,
    frameOk: maxFrameRateHz !== null ? maxFrameRateHz >= fps : false,
  };
}

export function receiverMeetsRequirement(card: ReceiverCardCatalogItem, requirement: ProjectRequirement): boolean {
  switch (requirement) {
    case "hdr":
      return card.supportsHdr;
    case "lowLatency":
      return card.supportsLowLatency;
    case "redundancy":
      return card.supportsRedundancy;
    case "monitoring":
      return card.supportsMonitoring;
  }
}

export function processorMeetsRequirement(processor: SenderProcessorCatalogItem, requirement: ProjectRequirement): boolean {
  switch (requirement) {
    case "hdr":
      return processor.features.includes("hdr");
    case "lowLatency":
      return processor.features.includes("low_latency");
    case "redundancy":
      return processor.features.includes("redundancy");
    case "monitoring":
      return processor.features.includes("monitoring");
  }
}

export function outputModesForPreference(
  preference: ProjectOutputPreference,
  receiverPortSpeed: ReceiverPortSpeed,
): ProcessorOutputMode[] {
  if (preference === "1g") return ["1g"];
  if (preference === "5g") return ["5g"];
  if (receiverPortSpeed === "5g") return ["5g", "1g", "10g"];
  return ["1g", "5g", "10g"];
}

export function pickProcessorOutput(
  processor: SenderProcessorCatalogItem,
  totalPixels: number,
  requiredPorts: number,
  allowedModes: ProcessorOutputMode[],
): ProcessorOutput | null {
  const usableOutputs = processor.outputs
    .filter((output) => allowedModes.includes(output.mode))
    .filter((output) => output.capacityPixels >= totalPixels && output.ports >= requiredPorts)
    .sort((a, b) => {
      const modeCompare = allowedModes.indexOf(a.mode) - allowedModes.indexOf(b.mode);
      if (modeCompare !== 0) return modeCompare;
      if (a.capacityPixels !== b.capacityPixels) return a.capacityPixels - b.capacityPixels;
      if (a.ports !== b.ports) return a.ports - b.ports;
      return 0;
    });

  return usableOutputs[0] ?? null;
}

export function processorSupportsTarget(
  processor: SenderProcessorCatalogItem,
  output: ProcessorOutput | null,
  width: number,
  height: number,
  fps: number,
  bitsPerChannel: number,
) {
  const widthOk = processor.maxWidth === null || width <= processor.maxWidth;
  const heightOk = processor.maxHeight === null || height <= processor.maxHeight;
  const frameOk = processor.maxFrameRateHz === null || fps <= processor.maxFrameRateHz;
  const depthOk = processor.maxColorDepthBpc === null || bitsPerChannel <= processor.maxColorDepthBpc;

  return {
    outputOk: output !== null,
    widthOk,
    heightOk,
    frameOk,
    depthOk,
    exact: output !== null && widthOk && heightOk && frameOk && depthOk,
  };
}
