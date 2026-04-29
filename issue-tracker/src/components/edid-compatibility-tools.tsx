"use client";

import { useI18n } from "@/i18n/context";
import { DISPLAY_INTERFACE_MAX_GBPS, type DisplayInterfaceId } from "@/lib/display-interface-specs";
import {
  bestEdidModeMatch,
  hdmiTmdsCharacterClockMHz,
  hdmiTmdsLineGbps,
  parseEdid,
  rgbPayloadGbpsForTiming,
  type EdidTimingMode,
  type ParsedEdid,
} from "@/lib/edid";
import { RGB_BPC_PRESETS, totalBppRgbPacked, type RgbBitsPerChannel } from "@/lib/led-bandwidth";
import { useMemo, useState } from "react";

const HDMI_IDS: DisplayInterfaceId[] = ["hdmi-1-4", "hdmi-2-0", "hdmi-2-1"];
const DP_IDS: DisplayInterfaceId[] = ["dp-1-2", "dp-1-4", "dp-2-0"];

function parsePositiveInt(raw: string, fallback: number): number {
  const n = Number.parseInt(raw.replaceAll(/\s+/g, ""), 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

function parsePositiveFloat(raw: string, fallback: number): number {
  const n = Number.parseFloat(raw.replaceAll(/\s+/g, "").replaceAll(",", "."));
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

function statusClass(state: "ok" | "bad" | "unknown"): string {
  if (state === "ok") return "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200";
  if (state === "bad") return "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200";
  return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
}

function AxisSummary({ axis, unit }: { axis: EdidTimingMode["horizontal"]; unit: string }) {
  return (
    <span className="tabular-nums">
      {axis.active} + {axis.frontPorch} + {axis.syncWidth} + {axis.backPorch} = {axis.total} {unit}
    </span>
  );
}

function ModeTimingDetails({ mode }: { mode: EdidTimingMode }) {
  return (
    <dl className="mt-3 grid gap-2 rounded-lg border border-zinc-200 bg-white p-3 text-xs dark:border-zinc-700 dark:bg-zinc-950 sm:grid-cols-2">
      <div>
        <dt className="font-medium text-zinc-500 dark:text-zinc-400">Horizontal active + front + sync + back</dt>
        <dd className="mt-1 text-zinc-800 dark:text-zinc-200">
          <AxisSummary axis={mode.horizontal} unit="px" />
        </dd>
      </div>
      <div>
        <dt className="font-medium text-zinc-500 dark:text-zinc-400">Vertical active + front + sync + back</dt>
        <dd className="mt-1 text-zinc-800 dark:text-zinc-200">
          <AxisSummary axis={mode.vertical} unit="lines" />
        </dd>
      </div>
    </dl>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-900/60">
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">{value}</dd>
      <dd className="mt-1 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{note}</dd>
    </div>
  );
}

function modeSort(a: EdidTimingMode, b: EdidTimingMode): number {
  if (a.native !== b.native) return a.native ? -1 : 1;
  if (a.width !== b.width) return b.width - a.width;
  if (a.height !== b.height) return b.height - a.height;
  return b.refreshHz - a.refreshHz;
}

export function EdidCompatibilityTools() {
  const { t, locale } = useI18n();
  const nf0 = useMemo(
    () => new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 0 }),
    [locale],
  );
  const nf1 = useMemo(
    () => new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 1 }),
    [locale],
  );
  const nf2 = useMemo(
    () => new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 2 }),
    [locale],
  );

  const [fileName, setFileName] = useState("");
  const [parsed, setParsed] = useState<ParsedEdid | null>(null);
  const [readError, setReadError] = useState("");
  const [wStr, setWStr] = useState("3840");
  const [hStr, setHStr] = useState("2160");
  const [hzStr, setHzStr] = useState("60");
  const [iface, setIface] = useState<DisplayInterfaceId>("hdmi-2-0");
  const [rgbBpc, setRgbBpc] = useState<RgbBitsPerChannel>(8);

  const width = parsePositiveInt(wStr, 0);
  const height = parsePositiveInt(hStr, 0);
  const hz = parsePositiveFloat(hzStr, 60);
  const bpp = totalBppRgbPacked(rgbBpc);
  const maxGbps = DISPLAY_INTERFACE_MAX_GBPS[iface];
  const isHdmiSelected = iface.startsWith("hdmi");
  const matchedMode = parsed ? bestEdidModeMatch(parsed.modes, width, height, hz) : undefined;
  const modeRows = useMemo(() => [...(parsed?.modes ?? [])].sort(modeSort).slice(0, 20), [parsed]);

  const payloadGbps = matchedMode ? rgbPayloadGbpsForTiming(matchedMode, bpp) : 0;
  const tmdsClockMHz = matchedMode ? hdmiTmdsCharacterClockMHz(matchedMode, rgbBpc) : 0;
  const tmdsLineGbps = matchedMode ? hdmiTmdsLineGbps(matchedMode, rgbBpc) : 0;
  const maxTmdsClockMHz = parsed?.hdmi.maxTmdsClockMHz;
  const maxLinkGbps = parsed?.hdmi.maxLinkGbps;
  const interfaceState = !matchedMode ? "unknown" : payloadGbps <= maxGbps ? "ok" : "bad";
  const tmdsClockState = !matchedMode || !maxTmdsClockMHz ? "unknown" : tmdsClockMHz <= maxTmdsClockMHz ? "ok" : "bad";
  const linkState = !matchedMode || !maxLinkGbps ? "unknown" : tmdsLineGbps <= maxLinkGbps ? "ok" : "bad";

  async function handleFile(file: File | undefined) {
    setReadError("");
    setParsed(null);
    setFileName(file?.name ?? "");
    if (!file) return;

    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      setParsed(parseEdid(bytes));
    } catch {
      setReadError(t("tools.edid.readFailed"));
    }
  }

  return (
    <div className="space-y-4">
      <section className="panel-surface rounded-xl border-2 border-emerald-300 bg-emerald-50/60 p-4 dark:border-emerald-800 dark:bg-emerald-950/30">
        <h2 className="text-base font-semibold text-emerald-950 dark:text-emerald-100">{t("tools.edid.title")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-emerald-900 dark:text-emerald-200">{t("tools.edid.subtitle")}</p>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.edid.uploadTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.edid.uploadHelp")}</p>
        <label className="mt-4 block max-w-xl text-sm">
          <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.edid.fileLabel")}</span>
          <input
            className="input w-full file:mr-3 file:rounded-md file:border-0 file:bg-zinc-900 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white dark:file:bg-zinc-100 dark:file:text-zinc-900"
            type="file"
            accept=".bin,.dat,.edid,.txt"
            onChange={(e) => void handleFile(e.target.files?.[0])}
          />
        </label>
        {fileName ? <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">{t("tools.edid.fileLoaded", { name: fileName })}</p> : null}
        {readError ? <p className="mt-2 text-sm text-red-700 dark:text-red-300">{readError}</p> : null}
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.edid.targetTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.edid.targetHelp")}</p>
        <div className="mt-4 grid max-w-2xl gap-3 sm:grid-cols-2">
          <label className="block text-sm sm:col-span-2">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.displayIo.labelInterface")}</span>
            <select className="input w-full" value={iface} onChange={(e) => setIface(e.target.value as DisplayInterfaceId)}>
              <optgroup label={t("tools.displayIo.groupHdmi")}>
                {HDMI_IDS.map((id) => (
                  <option key={id} value={id}>
                    {t(`tools.displayIo.ifaces.${id}`)}
                  </option>
                ))}
              </optgroup>
              <optgroup label={t("tools.displayIo.groupDp")}>
                {DP_IDS.map((id) => (
                  <option key={id} value={id}>
                    {t(`tools.displayIo.ifaces.${id}`)}
                  </option>
                ))}
              </optgroup>
            </select>
            <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
              {t("tools.edid.interfaceCeilingHint", { gbps: nf2.format(maxGbps) })}
            </span>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.labelWidth")}</span>
            <input className="input w-full" inputMode="numeric" value={wStr} onChange={(e) => setWStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.labelHeight")}</span>
            <input className="input w-full" inputMode="numeric" value={hStr} onChange={(e) => setHStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.displayIo.labelHz")}</span>
            <input className="input w-full" inputMode="decimal" value={hzStr} onChange={(e) => setHzStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.labelColorDepth")}</span>
            <select className="input w-full" value={rgbBpc} onChange={(e) => setRgbBpc(Number(e.target.value) as RgbBitsPerChannel)}>
              {RGB_BPC_PRESETS.map((bpcPreset) => (
                <option key={bpcPreset} value={bpcPreset}>
                  {t("tools.depthOptionFmt", { bpc: String(bpcPreset), bpp: String(totalBppRgbPacked(bpcPreset)) })}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.edid.resultTitle")}</h2>
        {!parsed ? (
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.edid.noEdid")}</p>
        ) : (
          <div className="mt-3 space-y-4">
            <div className="flex flex-wrap gap-2">
              <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-semibold", statusClass(parsed.checksumValid ? "ok" : "bad")].join(" ")}>
                {parsed.checksumValid ? t("tools.edid.checksumOk") : t("tools.edid.checksumBad")}
              </span>
              <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-semibold", statusClass(matchedMode ? "ok" : "bad")].join(" ")}>
                {matchedMode ? t("tools.edid.matchOk") : t("tools.edid.matchNo")}
              </span>
              <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-semibold", statusClass(interfaceState)].join(" ")}>
                {matchedMode
                  ? t("tools.edid.interfaceCompare", { need: nf2.format(payloadGbps), max: nf2.format(maxGbps) })
                  : t("tools.edid.interfaceUnknown")}
              </span>
              {isHdmiSelected ? (
              <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-semibold", statusClass(tmdsClockState)].join(" ")}>
                {maxTmdsClockMHz
                  ? t("tools.edid.tmdsCompare", { need: nf1.format(tmdsClockMHz), max: nf0.format(maxTmdsClockMHz) })
                  : t("tools.edid.tmdsUnknown")}
              </span>
              ) : null}
              {isHdmiSelected ? (
              <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-semibold", statusClass(linkState)].join(" ")}>
                {maxLinkGbps ? t("tools.edid.linkCompare", { need: nf2.format(tmdsLineGbps), max: nf2.format(maxLinkGbps) }) : t("tools.edid.linkUnknown")}
              </span>
              ) : null}
            </div>

            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Metric
                label={t("tools.edid.metricSink")}
                value={parsed.monitorName || parsed.manufacturerId || t("common.unknown")}
                note={t("tools.edid.metricSinkNote", {
                  version: parsed.edidVersion ?? t("common.unknown"),
                  blocks: nf0.format(parsed.parsedBlockCount),
                })}
              />
              <Metric
                label={t("tools.edid.metricParsedModes")}
                value={nf0.format(parsed.modes.length)}
                note={t("tools.edid.metricParsedModesNote", {
                  extensions: nf0.format(parsed.declaredExtensionCount),
                })}
              />
              <Metric
                label={t("tools.edid.metricMaxPixelClock")}
                value={maxTmdsClockMHz ? `${nf0.format(maxTmdsClockMHz)} MHz` : `${nf1.format(parsed.highestParsedPixelClockMHz ?? 0)} MHz`}
                note={maxTmdsClockMHz ? t("tools.edid.metricMaxPixelClockDeclared") : t("tools.edid.metricMaxPixelClockParsed")}
              />
              <Metric
                label={t("tools.edid.metricMaxBandwidth")}
                value={maxLinkGbps ? `${nf2.format(maxLinkGbps)} Gbit/s` : t("common.unknown")}
                note={parsed.hdmi.source.length > 0 ? parsed.hdmi.source.join(", ") : t("tools.edid.metricMaxBandwidthNote")}
              />
            </dl>

            {matchedMode ? (
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-900/60">
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.edid.matchedTimingTitle")}</h3>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {t("tools.edid.matchedTimingSummary", {
                    mode: matchedMode.name,
                    source: matchedMode.sourceLabel,
                  })}
                </p>
                <dl className={["mt-3 grid gap-3", isHdmiSelected ? "sm:grid-cols-3" : "sm:grid-cols-2"].join(" ")}>
                  <Metric label={t("tools.edid.pixelClock")} value={`${nf2.format(matchedMode.pixelClockMHz)} MHz`} note={t("tools.edid.pixelClockNote")} />
                  <Metric label={t("tools.edid.payloadBandwidth")} value={`${nf2.format(payloadGbps)} Gbit/s`} note={t("tools.edid.payloadBandwidthNote")} />
                  {isHdmiSelected ? (
                    <Metric label={t("tools.edid.tmdsBandwidth")} value={`${nf2.format(tmdsLineGbps)} Gbit/s`} note={t("tools.edid.tmdsBandwidthNote")} />
                  ) : null}
                </dl>
                <ModeTimingDetails mode={matchedMode} />
              </div>
            ) : (
              <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
                {t("tools.edid.noExactMode")}
              </p>
            )}

            {parsed.warnings.length > 0 ? (
              <ul className="list-inside list-disc text-sm text-amber-700 dark:text-amber-300">
                {parsed.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </section>

      {modeRows.length > 0 ? (
        <section className="panel-surface rounded-xl p-4">
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.edid.modesTitle")}</h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.edid.modesHelp")}</p>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                <tr>
                  <th className="py-2 pr-3">{t("tools.edid.tableMode")}</th>
                  <th className="py-2 pr-3">{t("tools.edid.tableClock")}</th>
                  <th className="py-2 pr-3">{t("tools.edid.tableHorizontal")}</th>
                  <th className="py-2 pr-3">{t("tools.edid.tableVertical")}</th>
                  <th className="py-2 pr-3">{t("tools.edid.tableSource")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {modeRows.map((mode) => (
                  <tr key={mode.id}>
                    <td className="py-2 pr-3 font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
                      {mode.name}
                      {mode.native ? <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200">native</span> : null}
                    </td>
                    <td className="py-2 pr-3 tabular-nums text-zinc-700 dark:text-zinc-300">{nf2.format(mode.pixelClockMHz)} MHz</td>
                    <td className="py-2 pr-3 text-xs text-zinc-600 dark:text-zinc-400">
                      <AxisSummary axis={mode.horizontal} unit="px" />
                    </td>
                    <td className="py-2 pr-3 text-xs text-zinc-600 dark:text-zinc-400">
                      <AxisSummary axis={mode.vertical} unit="lines" />
                    </td>
                    <td className="py-2 pr-3 text-zinc-600 dark:text-zinc-400">{mode.sourceLabel}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
