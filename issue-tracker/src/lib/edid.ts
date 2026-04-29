export type EdidModeSource = "base-dtd" | "cta-dtd" | "cta-vic";

export type EdidTimingAxis = {
  active: number;
  blank: number;
  total: number;
  frontPorch: number;
  syncWidth: number;
  backPorch: number;
};

export type EdidTimingMode = {
  id: string;
  source: EdidModeSource;
  sourceLabel: string;
  name: string;
  native: boolean;
  interlaced: boolean;
  vic?: number;
  width: number;
  height: number;
  refreshHz: number;
  pixelClockMHz: number;
  horizontal: EdidTimingAxis;
  vertical: EdidTimingAxis;
  syncPolarity?: string;
};

export type EdidHdmiCapabilities = {
  maxTmdsClockMHz?: number;
  maxFrlGbps?: number;
  maxLinkGbps?: number;
  source: string[];
};

export type ParsedEdid = {
  manufacturerId?: string;
  productId?: string;
  serialNumber?: string;
  monitorName?: string;
  edidVersion?: string;
  declaredExtensionCount: number;
  parsedBlockCount: number;
  checksumValid: boolean;
  blockChecksums: boolean[];
  modes: EdidTimingMode[];
  hdmi: EdidHdmiCapabilities;
  highestParsedPixelClockMHz?: number;
  warnings: string[];
};

const EDID_HEADER = [0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00] as const;

const CTA_VIC_TIMINGS: Record<
  number,
  Omit<EdidTimingMode, "id" | "source" | "sourceLabel" | "name" | "native" | "vic">
> = {
  2: timing(720, 480, 59.94, 27.027, 16, 62, 60, 9, 6, 30),
  3: timing(720, 480, 59.94, 27.027, 16, 62, 60, 9, 6, 30),
  4: timing(1280, 720, 60, 74.25, 110, 40, 220, 5, 5, 20),
  16: timing(1920, 1080, 60, 148.5, 88, 44, 148, 4, 5, 36),
  17: timing(720, 576, 50, 27, 12, 64, 68, 5, 5, 39),
  18: timing(720, 576, 50, 27, 12, 64, 68, 5, 5, 39),
  19: timing(1280, 720, 50, 74.25, 440, 40, 220, 5, 5, 20),
  31: timing(1920, 1080, 50, 148.5, 528, 44, 148, 4, 5, 36),
  32: timing(1920, 1080, 24, 74.25, 638, 44, 148, 4, 5, 36),
  33: timing(1920, 1080, 25, 74.25, 528, 44, 148, 4, 5, 36),
  34: timing(1920, 1080, 30, 74.25, 88, 44, 148, 4, 5, 36),
  93: timing(3840, 2160, 24, 237.6, 1276, 88, 296, 8, 10, 72),
  94: timing(3840, 2160, 25, 297, 1056, 88, 296, 8, 10, 72),
  95: timing(3840, 2160, 30, 297, 176, 88, 296, 8, 10, 72),
  96: timing(3840, 2160, 50, 594, 1056, 88, 296, 8, 10, 72),
  97: timing(3840, 2160, 60, 594, 176, 88, 296, 8, 10, 72),
};

function timing(
  width: number,
  height: number,
  refreshHz: number,
  pixelClockMHz: number,
  hFrontPorch: number,
  hSyncWidth: number,
  hBackPorch: number,
  vFrontPorch: number,
  vSyncWidth: number,
  vBackPorch: number,
): Omit<EdidTimingMode, "id" | "source" | "sourceLabel" | "name" | "native" | "vic"> {
  return {
    width,
    height,
    refreshHz,
    pixelClockMHz,
    interlaced: false,
    horizontal: axis(width, hFrontPorch, hSyncWidth, hBackPorch),
    vertical: axis(height, vFrontPorch, vSyncWidth, vBackPorch),
  };
}

function axis(active: number, frontPorch: number, syncWidth: number, backPorch: number): EdidTimingAxis {
  const blank = frontPorch + syncWidth + backPorch;
  return { active, blank, total: active + blank, frontPorch, syncWidth, backPorch };
}

function headerOffset(bytes: Uint8Array): number {
  for (let i = 0; i <= bytes.length - EDID_HEADER.length; i += 1) {
    if (EDID_HEADER.every((b, idx) => bytes[i + idx] === b)) return i;
  }
  return -1;
}

function parseHexTextBytes(raw: Uint8Array): Uint8Array | null {
  const text = new TextDecoder("utf-8", { fatal: false }).decode(raw);
  const tokens = Array.from(text.matchAll(/\b(?:0x)?([0-9a-fA-F]{2})\b/g), (match) => Number.parseInt(match[1]!, 16));
  if (tokens.length >= 128) return Uint8Array.from(tokens);

  const compact = text.replaceAll(/[^0-9a-fA-F]/g, "");
  if (compact.length >= 256 && compact.length % 2 === 0) {
    const bytes: number[] = [];
    for (let i = 0; i < compact.length; i += 2) {
      bytes.push(Number.parseInt(compact.slice(i, i + 2), 16));
    }
    return Uint8Array.from(bytes);
  }

  return null;
}

function normalizedEdidBytes(raw: Uint8Array): { bytes?: Uint8Array; warning?: string } {
  const directOffset = headerOffset(raw);
  if (directOffset >= 0) return { bytes: raw.slice(directOffset) };

  const textBytes = parseHexTextBytes(raw);
  if (textBytes) {
    const textOffset = headerOffset(textBytes);
    if (textOffset >= 0) return { bytes: textBytes.slice(textOffset) };
  }

  return { warning: "Could not find a valid EDID header. Upload a binary EDID dump or a text file containing EDID hex bytes." };
}

function checksumOk(block: Uint8Array): boolean {
  return block.reduce((sum, byte) => sum + byte, 0) % 256 === 0;
}

function manufacturerId(bytes: Uint8Array): string | undefined {
  const word = (bytes[8]! << 8) | bytes[9]!;
  const chars = [10, 5, 0].map((shift) => String.fromCharCode(((word >> shift) & 0x1f) + 64)).join("");
  return /^[A-Z]{3}$/.test(chars) ? chars : undefined;
}

function descriptorText(block: Uint8Array, tag: number): string | undefined {
  for (const offset of [54, 72, 90, 108]) {
    if (block[offset] === 0x00 && block[offset + 1] === 0x00 && block[offset + 3] === tag) {
      const raw = block.slice(offset + 5, offset + 18);
      const text = new TextDecoder("ascii", { fatal: false }).decode(raw).replaceAll(/\u0000|\n|\r/g, "").trim();
      if (text) return text;
    }
  }
  return undefined;
}

function parseDetailedTiming(block: Uint8Array, offset: number, source: EdidModeSource, sourceLabel: string, native: boolean): EdidTimingMode | null {
  const pixelClockRaw = block[offset]! | (block[offset + 1]! << 8);
  if (pixelClockRaw <= 0) return null;

  const pixelClockMHz = pixelClockRaw / 100;
  const width = block[offset + 2]! | ((block[offset + 4]! & 0xf0) << 4);
  const hBlank = block[offset + 3]! | ((block[offset + 4]! & 0x0f) << 8);
  const height = block[offset + 5]! | ((block[offset + 7]! & 0xf0) << 4);
  const vBlank = block[offset + 6]! | ((block[offset + 7]! & 0x0f) << 8);
  const hFrontPorch = block[offset + 8]! | ((block[offset + 11]! & 0xc0) << 2);
  const hSyncWidth = block[offset + 9]! | ((block[offset + 11]! & 0x30) << 4);
  const vFrontPorch = ((block[offset + 10]! >> 4) & 0x0f) | ((block[offset + 11]! & 0x0c) << 2);
  const vSyncWidth = (block[offset + 10]! & 0x0f) | ((block[offset + 11]! & 0x03) << 4);
  const hBackPorch = Math.max(0, hBlank - hFrontPorch - hSyncWidth);
  const vBackPorch = Math.max(0, vBlank - vFrontPorch - vSyncWidth);
  const hTotal = width + hBlank;
  const vTotal = height + vBlank;
  const interlaced = (block[offset + 17]! & 0x80) !== 0;
  const refreshHz = hTotal > 0 && vTotal > 0 ? ((pixelClockMHz * 1_000_000) / (hTotal * vTotal)) * (interlaced ? 2 : 1) : 0;
  const hPolarity = (block[offset + 17]! & 0x02) !== 0 ? "+" : "-";
  const vPolarity = (block[offset + 17]! & 0x04) !== 0 ? "+" : "-";

  return {
    id: `${source}-${offset}-${width}-${height}-${pixelClockRaw}`,
    source,
    sourceLabel,
    name: `${width} x ${height} @ ${refreshHz.toFixed(2)} Hz${interlaced ? " interlaced" : ""}`,
    native,
    interlaced,
    width,
    height,
    refreshHz,
    pixelClockMHz,
    horizontal: {
      active: width,
      blank: hBlank,
      total: hTotal,
      frontPorch: hFrontPorch,
      syncWidth: hSyncWidth,
      backPorch: hBackPorch,
    },
    vertical: {
      active: height,
      blank: vBlank,
      total: vTotal,
      frontPorch: vFrontPorch,
      syncWidth: vSyncWidth,
      backPorch: vBackPorch,
    },
    syncPolarity: `${hPolarity}H / ${vPolarity}V`,
  };
}

function ctaVicMode(vic: number, native: boolean, index: number): EdidTimingMode | null {
  const preset = CTA_VIC_TIMINGS[vic];
  if (!preset) return null;
  return {
    ...preset,
    id: `cta-vic-${vic}-${index}`,
    source: "cta-vic",
    sourceLabel: `CTA VIC ${vic}`,
    name: `${preset.width} x ${preset.height} @ ${preset.refreshHz.toFixed(2)} Hz`,
    native,
    vic,
  };
}

function frlGbpsFromCode(code: number): number | undefined {
  switch (code) {
    case 1:
      return 9;
    case 2:
      return 18;
    case 3:
      return 24;
    case 4:
      return 32;
    case 5:
      return 40;
    case 6:
      return 48;
    default:
      return undefined;
  }
}

function parseCtaExtension(
  block: Uint8Array,
  blockIndex: number,
  modes: EdidTimingMode[],
  hdmi: EdidHdmiCapabilities,
  warnings: string[],
) {
  const dtdStart = block[2]!;
  const dataEnd = dtdStart >= 4 && dtdStart <= 127 ? dtdStart : 4;
  let cursor = 4;
  let svdIndex = 0;

  while (cursor < dataEnd) {
    const header = block[cursor]!;
    const tag = header >> 5;
    const length = header & 0x1f;
    const payloadStart = cursor + 1;
    const payloadEnd = payloadStart + length;
    if (payloadEnd > dataEnd) {
      warnings.push(`CTA block ${blockIndex} has a truncated data block.`);
      break;
    }

    const payload = block.slice(payloadStart, payloadEnd);
    if (tag === 2) {
      for (const byte of payload) {
        const native = (byte & 0x80) !== 0;
        const vic = byte & 0x7f;
        const mode = ctaVicMode(vic, native, svdIndex);
        if (mode) modes.push(mode);
        svdIndex += 1;
      }
    } else if (tag === 3 && payload.length >= 3) {
      const oui = `${payload[0]!.toString(16).padStart(2, "0")}${payload[1]!.toString(16).padStart(2, "0")}${payload[2]!
        .toString(16)
        .padStart(2, "0")}`;
      if (oui === "030c00") {
        if (payload.length >= 7 && payload[6]! > 0) {
          hdmi.maxTmdsClockMHz = Math.max(hdmi.maxTmdsClockMHz ?? 0, payload[6]! * 5);
          hdmi.source.push("HDMI VSDB Max TMDS Clock");
        }
      } else if (oui === "d85dc4") {
        if (payload.length >= 5 && payload[4]! > 0) {
          hdmi.maxTmdsClockMHz = Math.max(hdmi.maxTmdsClockMHz ?? 0, payload[4]! * 5);
          hdmi.source.push("HDMI Forum VSDB Max TMDS Character Rate");
        }
        if (payload.length >= 7) {
          const frlGbps = frlGbpsFromCode(payload[6]! & 0x0f);
          if (frlGbps) {
            hdmi.maxFrlGbps = Math.max(hdmi.maxFrlGbps ?? 0, frlGbps);
            hdmi.source.push("HDMI Forum VSDB FRL rate");
          }
        }
      }
    }

    cursor = payloadEnd;
  }

  if (dtdStart >= 4 && dtdStart <= 108) {
    for (let offset = dtdStart; offset <= 108; offset += 18) {
      const mode = parseDetailedTiming(block, offset, "cta-dtd", `CTA extension ${blockIndex}`, false);
      if (mode) modes.push(mode);
    }
  }
}

export function parseEdid(raw: Uint8Array): ParsedEdid {
  const warnings: string[] = [];
  const normalized = normalizedEdidBytes(raw);
  if (!normalized.bytes) {
    return {
      declaredExtensionCount: 0,
      parsedBlockCount: 0,
      checksumValid: false,
      blockChecksums: [],
      modes: [],
      hdmi: { source: [] },
      warnings: [normalized.warning ?? "No EDID data could be parsed."],
    };
  }

  const bytes = normalized.bytes;
  if (bytes.length < 128) {
    return {
      declaredExtensionCount: 0,
      parsedBlockCount: 0,
      checksumValid: false,
      blockChecksums: [],
      modes: [],
      hdmi: { source: [] },
      warnings: ["The EDID data is shorter than one 128-byte block."],
    };
  }

  const declaredExtensionCount = bytes[126]!;
  const availableBlockCount = Math.floor(bytes.length / 128);
  const parsedBlockCount = Math.max(1, Math.min(availableBlockCount, declaredExtensionCount + 1));
  if (declaredExtensionCount + 1 > availableBlockCount) {
    warnings.push(`EDID declares ${declaredExtensionCount} extension block(s), but the upload only contains ${availableBlockCount - 1}.`);
  }

  const baseBlock = bytes.slice(0, 128);
  const blockChecksums = Array.from({ length: parsedBlockCount }, (_, i) => checksumOk(bytes.slice(i * 128, i * 128 + 128)));
  const modes: EdidTimingMode[] = [];
  const hdmi: EdidHdmiCapabilities = { source: [] };

  for (const [descriptorIndex, offset] of [54, 72, 90, 108].entries()) {
    const mode = parseDetailedTiming(baseBlock, offset, "base-dtd", descriptorIndex === 0 ? "Base EDID preferred timing" : "Base EDID timing", descriptorIndex === 0);
    if (mode) modes.push(mode);
  }

  for (let blockIndex = 1; blockIndex < parsedBlockCount; blockIndex += 1) {
    const block = bytes.slice(blockIndex * 128, blockIndex * 128 + 128);
    if (block[0] === 0x02) {
      parseCtaExtension(block, blockIndex, modes, hdmi, warnings);
    }
  }

  const highestParsedPixelClockMHz = modes.reduce<number | undefined>(
    (highest, mode) => (highest === undefined ? mode.pixelClockMHz : Math.max(highest, mode.pixelClockMHz)),
    undefined,
  );
  const maxTmdsLineGbps = hdmi.maxTmdsClockMHz ? (hdmi.maxTmdsClockMHz * 30) / 1000 : undefined;
  hdmi.maxLinkGbps = Math.max(maxTmdsLineGbps ?? 0, hdmi.maxFrlGbps ?? 0) || undefined;

  return {
    manufacturerId: manufacturerId(baseBlock),
    productId: `0x${((baseBlock[11]! << 8) | baseBlock[10]!).toString(16).padStart(4, "0")}`,
    serialNumber: descriptorText(baseBlock, 0xff),
    monitorName: descriptorText(baseBlock, 0xfc),
    edidVersion: `${baseBlock[18]}.${baseBlock[19]}`,
    declaredExtensionCount,
    parsedBlockCount,
    checksumValid: blockChecksums.every(Boolean),
    blockChecksums,
    modes,
    hdmi,
    highestParsedPixelClockMHz,
    warnings,
  };
}

export function rgbPayloadGbpsForTiming(mode: EdidTimingMode, bitsPerPixel: number): number {
  if (mode.pixelClockMHz <= 0 || bitsPerPixel <= 0) return 0;
  return (mode.pixelClockMHz * bitsPerPixel) / 1000;
}

export function hdmiTmdsCharacterClockMHz(mode: EdidTimingMode, bitsPerChannel: number): number {
  if (mode.pixelClockMHz <= 0 || bitsPerChannel <= 0) return 0;
  return mode.pixelClockMHz * Math.max(1, bitsPerChannel / 8);
}

export function hdmiTmdsLineGbps(mode: EdidTimingMode, bitsPerChannel: number): number {
  return (hdmiTmdsCharacterClockMHz(mode, bitsPerChannel) * 30) / 1000;
}

export function bestEdidModeMatch(modes: EdidTimingMode[], width: number, height: number, refreshHz: number): EdidTimingMode | undefined {
  const candidates = modes
    .filter((mode) => mode.width === width && mode.height === height && Math.abs(mode.refreshHz - refreshHz) <= 0.75)
    .sort((a, b) => {
      if (a.native !== b.native) return a.native ? -1 : 1;
      if (a.source !== b.source) return a.source === "base-dtd" || a.source === "cta-dtd" ? -1 : 1;
      return Math.abs(a.refreshHz - refreshHz) - Math.abs(b.refreshHz - refreshHz);
    });
  return candidates[0];
}
