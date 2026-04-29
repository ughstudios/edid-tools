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
export type ProjectOutputPreference = "1g" | "5g";
export type ProjectRequirement = "hdr" | "lowLatency" | "redundancy" | "monitoring";

/** User-selected physical input connectors for planning notes (maps to typical Colorlight input boards). */
export const PLANNER_INPUT_INTERFACE_IDS = [
  "hdmi20",
  "hdmi21",
  "dp12",
  "dp14",
  "sdi3g",
  "sdi6g",
  "sdi12g",
  "threeInOne",
  "st2110",
] as const;
export type PlannerInputInterfaceId = (typeof PLANNER_INPUT_INTERFACE_IDS)[number];

export type PlannerInputLine = { interfaceId: PlannerInputInterfaceId; count: number };

export function totalInputConnectors(lines: PlannerInputLine[]): number {
  return lines.reduce((sum, line) => sum + Math.max(0, Math.trunc(line.count)), 0);
}

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

type RawProcessorFixedInput = {
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
  /** Fixed chassis video inputs (e.g. VX all-in-one); optional until extracted per SKU. */
  inputs?: RawProcessorFixedInput[];
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

/** Fixed on-board video inputs (VX etc.), when present in the sender JSON extract. */
export type ProcessorFixedInput = {
  label: string;
};

export type ProcessorBoardSuggestion = {
  name: string;
  model: string;
  quantity: number;
  portsPerBoard?: number;
  capacityPixelsPerBoard?: number;
  maxBoards: number;
  note: string;
  withinLimit: boolean;
};

export type SenderProcessorCatalogItem = {
  name: string;
  series: string;
  overview: string;
  maxWidth: number | null;
  maxHeight: number | null;
  maxFrameRateHz: number | null;
  maxColorDepthBpc: number | null;
  inputs?: ProcessorFixedInput[];
  outputs: ProcessorOutput[];
  features: string[];
};

export function processorHasAllowedOutputMode(
  processor: SenderProcessorCatalogItem,
  allowedModes: ProcessorOutputMode[],
): boolean {
  return processor.outputs.some((o) => allowedModes.includes(o.mode));
}

/** True when the catalog marks the sender as modular (swappable input/output boards). VX all-in-one models omit this. */
export function processorHasSwappableBoards(processor: SenderProcessorCatalogItem): boolean {
  return processor.features.includes("modular");
}

/** All-in-one VX controllers: fixed Ethernet outputs on the chassis (see catalog labels). */
export function isVxSeriesProcessor(processor: SenderProcessorCatalogItem): boolean {
  return processor.series === "VX Series";
}

export type CabinetPixelSize = {
  width: number;
  height: number;
  pixels: number;
};

const rawCards = (receiverCardsData as ReceiverCardsJson).cards;
const rawProcessors = (senderProcessorsData as SenderProcessorsJson).processors;

const U_SERIES_BOARD_LIMITS: Record<string, { maxInputBoards: number; maxOutputBoards: number }> = {
  "U15 Max": { maxInputBoards: 30, maxOutputBoards: 20 },
  "U9 Max": { maxInputBoards: 18, maxOutputBoards: 10 },
  "U6 Max": { maxInputBoards: 10, maxOutputBoards: 5 },
};

/** Swappable U-series input boards (staffing uses 4K@60-equivalent per connector). */
export type UsSeriesInputBoardSpec = {
  id: string;
  name: string;
  model: string;
  inputsPerBoard: number;
  sourcePixelRatePerInput: number;
};

export const US_SERIES_INPUT_BOARD_OPTIONS: readonly UsSeriesInputBoardSpec[] = [
  {
    id: "2hdmi2dp12",
    name: "U_2xHDMI 2.0+2xDP 1.2 input board",
    model: "U_IN_2HDMI20_2DP12",
    inputsPerBoard: 2,
    sourcePixelRatePerInput: 4096 * 2160 * 60,
  },
  {
    id: "2hdmi20",
    name: "U_2xHDMI 2.0 input board",
    model: "U_IN_2HDMI20",
    inputsPerBoard: 2,
    sourcePixelRatePerInput: 4096 * 2160 * 60,
  },
  {
    id: "2dp12",
    name: "U_2xDP 1.2 input board",
    model: "U_IN_2DP12",
    inputsPerBoard: 2,
    sourcePixelRatePerInput: 4096 * 2160 * 60,
  },
  {
    id: "2sdi12g",
    name: "U_2x12G-SDI input board",
    model: "U_IN_2SDI12G",
    inputsPerBoard: 2,
    sourcePixelRatePerInput: 4096 * 2160 * 60,
  },
];

/** Swappable U-series output boards by link mode (matches sender hardware options). */
export type UsSeriesOutputBoardSpec = {
  id: string;
  mode: ProcessorOutputMode;
  name: string;
  model: string;
  portsPerBoard: number;
  capacityPixelsPerBoard: number;
};

export const US_SERIES_OUTPUT_BOARD_OPTIONS: readonly UsSeriesOutputBoardSpec[] = [
  {
    id: "20x1g",
    mode: "1g",
    name: "U_20x1G Ethernet output board",
    model: "U_OUT_20x1G_RJ45",
    portsPerBoard: 20,
    capacityPixelsPerBoard: 13000000,
  },
  {
    id: "8x5g",
    mode: "5g",
    name: "U_8x5G Ethernet output board",
    model: "U_OUT_8x5G_RJ45",
    portsPerBoard: 8,
    capacityPixelsPerBoard: 23600000,
  },
  {
    id: "4x10g",
    mode: "10g",
    name: "U_4x10G fiber output board",
    model: "U_OUT_4x10G_FIBER",
    portsPerBoard: 4,
    capacityPixelsPerBoard: 26000000,
  },
];

export function isUsSeriesProcessorName(name: string): boolean {
  return Object.prototype.hasOwnProperty.call(U_SERIES_BOARD_LIMITS, name);
}

export function getUsSeriesInputBoardById(id: string): UsSeriesInputBoardSpec | undefined {
  return US_SERIES_INPUT_BOARD_OPTIONS.find((b) => b.id === id);
}

/**
 * Picks a representative U-series input board SKU from the connector mix in planning rows
 * (same checklist as the video-inputs UI — no separate board dropdown).
 */
export function inferUsSeriesInputBoardSpecFromPlannerLines(lines: PlannerInputLine[]): UsSeriesInputBoardSpec {
  const active = lines.filter((l) => l.count > 0);
  if (active.length === 0) return US_SERIES_INPUT_BOARD_OPTIONS[0];

  const ids = new Set(active.map((l) => l.interfaceId));
  const hasHdmi = [...ids].some((id) => id === "hdmi20" || id === "hdmi21");
  const hasDp = [...ids].some((id) => id === "dp12" || id === "dp14");
  const hasSdi = [...ids].some((id) => id === "sdi3g" || id === "sdi6g" || id === "sdi12g");
  const needsCombo = ids.has("threeInOne") || ids.has("st2110");

  if (needsCombo || (hasHdmi && hasDp)) {
    return getUsSeriesInputBoardById("2hdmi2dp12") ?? US_SERIES_INPUT_BOARD_OPTIONS[0];
  }
  if (hasHdmi && !hasDp && !hasSdi) {
    return getUsSeriesInputBoardById("2hdmi20") ?? US_SERIES_INPUT_BOARD_OPTIONS[0];
  }
  if (hasDp && !hasHdmi && !hasSdi) {
    return getUsSeriesInputBoardById("2dp12") ?? US_SERIES_INPUT_BOARD_OPTIONS[0];
  }
  if (hasSdi && !hasHdmi && !hasDp) {
    return getUsSeriesInputBoardById("2sdi12g") ?? US_SERIES_INPUT_BOARD_OPTIONS[0];
  }
  return getUsSeriesInputBoardById("2hdmi2dp12") ?? US_SERIES_INPUT_BOARD_OPTIONS[0];
}

export function listUsSeriesOutputBoardsForMode(mode: ProcessorOutputMode): UsSeriesOutputBoardSpec[] {
  return US_SERIES_OUTPUT_BOARD_OPTIONS.filter((b) => b.mode === mode);
}

export function getUsSeriesOutputBoardById(id: string): UsSeriesOutputBoardSpec | undefined {
  return US_SERIES_OUTPUT_BOARD_OPTIONS.find((b) => b.id === id);
}

/** Planned downlink to receivers (RJ45 Ethernet vs fiber). Maps 1:1 to U-series output board SKUs. */
export const PLANNER_OUTPUT_INTERFACE_IDS = ["ethernet_1g_rj45", "ethernet_5g_rj45", "fiber_10g"] as const;
export type PlannerOutputInterfaceId = (typeof PLANNER_OUTPUT_INTERFACE_IDS)[number];

export type PlannerOutputLine = { interfaceId: PlannerOutputInterfaceId; count: number };

export function totalPlannedOutputPorts(lines: PlannerOutputLine[]): number {
  return lines.reduce((sum, line) => sum + Math.max(0, Math.trunc(line.count)), 0);
}

export function usOutputBoardSpecFromPlanningInterface(id: PlannerOutputInterfaceId): UsSeriesOutputBoardSpec | undefined {
  const boardIdByInterface: Record<PlannerOutputInterfaceId, string> = {
    ethernet_1g_rj45: "20x1g",
    ethernet_5g_rj45: "8x5g",
    fiber_10g: "4x10g",
  };
  return getUsSeriesOutputBoardById(boardIdByInterface[id]);
}

export function primaryProcessorModeFromOutputPlanningLines(
  lines: PlannerOutputLine[],
  linkPreference: ProjectOutputPreference,
): ProcessorOutputMode | null {
  let sum1g = 0;
  let sum5g = 0;
  let sumFiber = 0;
  for (const line of lines) {
    const c = Math.max(0, Math.trunc(line.count));
    if (line.interfaceId === "ethernet_1g_rj45") sum1g += c;
    if (line.interfaceId === "ethernet_5g_rj45") sum5g += c;
    if (line.interfaceId === "fiber_10g") sumFiber += c;
  }
  if (sum1g === 0 && sum5g === 0 && sumFiber === 0) return null;
  if (sumFiber > 0) return "10g";
  if (sum5g > 0 && sum1g === 0) return "5g";
  if (sum1g > 0 && sum5g === 0) return "1g";
  return linkPreference === "5g" ? "5g" : "1g";
}

function planningInterfaceIdForMode(mode: ProcessorOutputMode): PlannerOutputInterfaceId {
  if (mode === "10g") return "fiber_10g";
  if (mode === "5g") return "ethernet_5g_rj45";
  return "ethernet_1g_rj45";
}

/** Board SKU used for staffing when rows imply a primary link tier (mixed RJ45 rows follow receiver link preference). */
export function boardSpecForPrimaryOutputPlanning(
  lines: PlannerOutputLine[],
  linkPreference: ProjectOutputPreference,
): UsSeriesOutputBoardSpec | undefined {
  const mode = primaryProcessorModeFromOutputPlanningLines(lines, linkPreference);
  if (!mode) return undefined;
  return usOutputBoardSpecFromPlanningInterface(planningInterfaceIdForMode(mode));
}

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
  const inputs =
    processor.inputs
      ?.map((row) => ({ label: cleanText(row.label) }))
      .filter((row) => row.label.length > 0) ?? [];

  return {
    name: cleanText(processor.name) || "Unknown",
    series: cleanText(processor.series) || "Uncategorized",
    overview: cleanText(processor.overview),
    maxWidth: Number.isFinite(processor.max_width) ? processor.max_width ?? null : null,
    maxHeight: Number.isFinite(processor.max_height) ? processor.max_height ?? null : null,
    maxFrameRateHz: Number.isFinite(processor.max_frame_rate_hz) ? processor.max_frame_rate_hz ?? null : null,
    maxColorDepthBpc: Number.isFinite(processor.max_color_depth_bpc) ? processor.max_color_depth_bpc ?? null : null,
    inputs: inputs.length > 0 ? inputs : undefined,
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

const PLANNER_EXCLUDED_RECEIVER_NAMES = new Set(["k10_lv", "k5a"]);

/** Which receiver cards appear in the project planner for the selected link set (5A-* and E-series models excluded). */
export function receiverCardInPlannerCatalog(card: ReceiverCardCatalogItem, preference: ProjectOutputPreference): boolean {
  const name = card.name;
  if (/^5A-/i.test(name)) return false;
  if (/^E\d/i.test(name)) return false;
  if (PLANNER_EXCLUDED_RECEIVER_NAMES.has(name.toLowerCase())) return false;
  if (preference === "5g") {
    return name === "HC5" || name === "RV5000";
  }
  return /^[kK]/.test(name);
}

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

export function usableMbpsForProcessorOutputMode(mode: ProcessorOutputMode): number {
  if (mode === "5g") return DEFAULT_USABLE_MBPS_5G;
  if (mode === "10g") return DEFAULT_USABLE_MBPS_1G * 10;
  return DEFAULT_USABLE_MBPS_1G;
}

export function portsNeededForMbps(requiredMbps: number, usableMbps: number): number {
  if (requiredMbps <= 0 || usableMbps <= 0) return 0;
  return Math.ceil(requiredMbps / usableMbps);
}

/** Single-cabinet pixel grid when width × height in px are known (preferred over mm ÷ pitch). */
export function cabinetPixelsFromResolution(widthPx: number, heightPx: number): CabinetPixelSize {
  const width = Math.max(0, Math.trunc(widthPx));
  const height = Math.max(0, Math.trunc(heightPx));
  if (width <= 0 || height <= 0) return { width: 0, height: 0, pixels: 0 };
  return { width, height, pixels: width * height };
}

/** Legacy: derive cabinet pixels from cabinet mm size and pitch (approximate). Prefer {@link cabinetPixelsFromResolution}. */
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

export function outputModesForPreference(preference: ProjectOutputPreference): ProcessorOutputMode[] {
  return preference === "1g" ? ["1g"] : ["5g"];
}

export function pickProcessorOutput(
  processor: SenderProcessorCatalogItem,
  totalPixels: number,
  requiredMbps: number,
  allowedModes: ProcessorOutputMode[],
): ProcessorOutput | null {
  const usableOutputs = processor.outputs
    .filter((output) => allowedModes.includes(output.mode))
    .filter((output) => {
      const requiredPorts = portsNeededForMbps(requiredMbps, usableMbpsForProcessorOutputMode(output.mode));
      return output.capacityPixels >= totalPixels && output.ports >= requiredPorts;
    })
    .sort((a, b) => {
      const modeCompare = allowedModes.indexOf(a.mode) - allowedModes.indexOf(b.mode);
      if (modeCompare !== 0) return modeCompare;
      if (a.capacityPixels !== b.capacityPixels) return a.capacityPixels - b.capacityPixels;
      if (a.ports !== b.ports) return a.ports - b.ports;
      return 0;
    });

  return usableOutputs[0] ?? null;
}

export function requiredPortsForProcessorOutput(output: ProcessorOutput | null, requiredMbps: number): number {
  if (!output) return 0;
  return portsNeededForMbps(requiredMbps, usableMbpsForProcessorOutputMode(output.mode));
}

export function recommendProcessorInputBoard(
  processor: SenderProcessorCatalogItem,
  width: number,
  height: number,
  fps: number,
  inputBoardSpec?: UsSeriesInputBoardSpec,
  connectorLines?: PlannerInputLine[],
): ProcessorBoardSuggestion | null {
  const limits = U_SERIES_BOARD_LIMITS[processor.name];
  if (!limits) return null;

  const spec = inputBoardSpec ?? US_SERIES_INPUT_BOARD_OPTIONS[0];
  const sourcePixelRate = Math.max(0, width) * Math.max(0, height) * Math.max(0, fps);
  const sourceInputs = sourcePixelRate > 0 ? Math.ceil(sourcePixelRate / spec.sourcePixelRatePerInput) : 0;
  const quantityBySignal = Math.max(0, Math.ceil(sourceInputs / spec.inputsPerBoard));
  const plannedConnectors =
    connectorLines && connectorLines.length > 0 ? totalInputConnectors(connectorLines) : 0;
  const quantityByConnectors =
    plannedConnectors > 0 ? Math.ceil(plannedConnectors / spec.inputsPerBoard) : 0;
  const quantity = Math.max(1, quantityBySignal, quantityByConnectors);

  const parts: string[] = [];
  parts.push(`${sourceInputs} 4K60-equivalent source input${sourceInputs === 1 ? "" : "s"}`);
  if (plannedConnectors > 0) {
    parts.push(`${plannedConnectors} planned connector${plannedConnectors === 1 ? "" : "s"}`);
  }

  return {
    name: spec.name,
    model: spec.model,
    quantity,
    portsPerBoard: spec.inputsPerBoard,
    maxBoards: limits.maxInputBoards,
    note: parts.join("; "),
    withinLimit: quantity <= limits.maxInputBoards,
  };
}

export function recommendProcessorOutputBoard(
  processor: SenderProcessorCatalogItem,
  output: ProcessorOutput | null,
  totalPixels: number,
  requiredPorts: number,
  outputBoardSpec?: UsSeriesOutputBoardSpec,
): ProcessorBoardSuggestion | null {
  const limits = U_SERIES_BOARD_LIMITS[processor.name];
  if (!limits || !output) return null;

  const modeOptions = listUsSeriesOutputBoardsForMode(output.mode);
  const board = outputBoardSpec ?? modeOptions[0];
  if (!board) return null;

  const quantityByPorts = requiredPorts > 0 ? Math.ceil(requiredPorts / board.portsPerBoard) : 0;
  const quantityByPixels = totalPixels > 0 ? Math.ceil(totalPixels / board.capacityPixelsPerBoard) : 0;
  const quantity = Math.max(1, quantityByPorts, quantityByPixels);
  const maxBoardsByPublishedPorts = Math.floor(output.ports / board.portsPerBoard);
  const maxBoards = Math.min(limits.maxOutputBoards, maxBoardsByPublishedPorts || limits.maxOutputBoards);

  return {
    name: board.name,
    model: board.model,
    quantity,
    portsPerBoard: board.portsPerBoard,
    capacityPixelsPerBoard: board.capacityPixelsPerBoard,
    maxBoards,
    note: `${quantityByPorts} by ports, ${quantityByPixels} by pixels`,
    withinLimit: quantity <= maxBoards,
  };
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
  const depthOk =
    processor.maxColorDepthBpc !== null && bitsPerChannel <= processor.maxColorDepthBpc;

  return {
    outputOk: output !== null,
    widthOk,
    heightOk,
    frameOk,
    depthOk,
    exact: output !== null && widthOk && heightOk && frameOk && depthOk,
  };
}

/** True when both sides publish enough bit depth, frame rate, and canvas size, and the processor has a matching output. */
export function plannerPairingMeetsSignalLimits(args: {
  processorOutput: ProcessorOutput | null;
  card: ReceiverCardCatalogItem;
  support: ReturnType<typeof receiverSupportsTarget>;
  processorSupport: ReturnType<typeof processorSupportsTarget>;
}): boolean {
  const { processorOutput, card, support, processorSupport } = args;
  return (
    processorOutput !== null &&
    card.maxCapacityPixels > 0 &&
    support.depthOk &&
    support.frameOk &&
    processorSupport.depthOk &&
    processorSupport.frameOk &&
    processorSupport.widthOk &&
    processorSupport.heightOk
  );
}
