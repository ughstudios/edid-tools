"use client";

import { useI18n } from "@/i18n/context";
import type { TranslateFn } from "@/i18n/create-translator";
import { RGB_BPC_PRESETS, totalBppRgbPacked, type RgbBitsPerChannel } from "@/lib/led-bandwidth";
import {
  RECEIVER_CARD_CATALOG,
  SENDER_PROCESSOR_CATALOG,
  cabinetPixelSize,
  cabinetsNeeded,
  cardsNeededByPixels,
  cardsPerCabinet,
  ledSignalMbps,
  outputModesForPreference,
  pickProcessorOutput,
  portsNeededForMbps,
  processorMeetsRequirement,
  processorSupportsTarget,
  receiverMeetsRequirement,
  receiverSupportsTarget,
  usableMbpsForPortSpeed,
  type ProcessorOutputMode,
  type ProjectOutputPreference,
  type ProjectRequirement,
  type ReceiverCardCatalogItem,
  type ReceiverPortSpeed,
} from "@/lib/receiver-card-planner";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

const REQUIREMENTS: ProjectRequirement[] = ["hdr", "lowLatency", "redundancy", "monitoring"];

function parsePositiveInt(raw: string, fallback: number): number {
  const n = Number.parseInt(raw.replaceAll(/\s+/g, ""), 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

function parsePositiveFloat(raw: string, fallback: number): number {
  const n = Number.parseFloat(raw.replaceAll(/\s+/g, "").replaceAll(",", "."));
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

function depthSelectLabel(t: TranslateFn, bpc: RgbBitsPerChannel): string {
  return t("tools.depthOptionFmt", {
    bpc: String(bpc),
    bpp: String(totalBppRgbPacked(bpc)),
  });
}

function planningPortSpeed(card: ReceiverCardCatalogItem): Exclude<ReceiverPortSpeed, "unknown"> {
  return card.portSpeed === "5g" ? "5g" : "1g";
}

function modeLabel(t: TranslateFn, mode: ProcessorOutputMode | ReceiverPortSpeed): string {
  if (mode === "5g") return t("tools.receiverPlanner.port5g");
  if (mode === "10g") return t("tools.projectSuggestor.port10g");
  if (mode === "unknown") return t("tools.receiverPlanner.port1gAssumed");
  return t("tools.receiverPlanner.port1g");
}

function CapabilityChip({
  children,
  state,
}: {
  children: ReactNode;
  state: "ok" | "bad" | "unknown";
}) {
  const className =
    state === "ok"
      ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"
      : state === "bad"
        ? "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200"
        : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";

  return <span className={["inline-flex rounded-full px-2 py-0.5 text-xs font-semibold", className].join(" ")}>{children}</span>;
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-900/60">
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">{value}</dd>
      <dd className="mt-1 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{note}</dd>
    </div>
  );
}

export function ReceiverCardPlannerTools() {
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

  const [screenWStr, setScreenWStr] = useState("7680");
  const [screenHStr, setScreenHStr] = useState("2160");
  const [fpsStr, setFpsStr] = useState("120");
  const [rgbBpc, setRgbBpc] = useState<RgbBitsPerChannel>(10);
  const [cabinetWStr, setCabinetWStr] = useState("600");
  const [cabinetHStr, setCabinetHStr] = useState("337.5");
  const [pitchStr, setPitchStr] = useState("1.25");
  const [outputPreference, setOutputPreference] = useState<ProjectOutputPreference>("auto");
  const [requirements, setRequirements] = useState<ProjectRequirement[]>(["hdr", "lowLatency"]);

  const screenW = parsePositiveInt(screenWStr, 0);
  const screenH = parsePositiveInt(screenHStr, 0);
  const fps = parsePositiveFloat(fpsStr, 0);
  const cabinetWmm = parsePositiveFloat(cabinetWStr, 0);
  const cabinetHmm = parsePositiveFloat(cabinetHStr, 0);
  const pitchMm = parsePositiveFloat(pitchStr, 0);

  const totalPixels = screenW * screenH;
  const requiredMbps = ledSignalMbps(screenW, screenH, fps, rgbBpc);
  const ports1g = portsNeededForMbps(requiredMbps, usableMbpsForPortSpeed("1g"));
  const ports5g = portsNeededForMbps(requiredMbps, usableMbpsForPortSpeed("5g"));
  const cabinetPixels = cabinetPixelSize(cabinetWmm, cabinetHmm, pitchMm);
  const cabinetGrid = cabinetsNeeded(screenW, screenH, cabinetPixels.width, cabinetPixels.height);

  const projectRows = RECEIVER_CARD_CATALOG.flatMap((card) => {
    const receiverSpeed = planningPortSpeed(card);
    const allowedModes = outputModesForPreference(outputPreference, card.portSpeed);
    const outputMode = allowedModes.includes(receiverSpeed) ? receiverSpeed : allowedModes[0] ?? receiverSpeed;
    const requiredPorts = portsNeededForMbps(requiredMbps, usableMbpsForPortSpeed(outputMode === "5g" ? "5g" : "1g"));
    const support = receiverSupportsTarget(card, fps, rgbBpc);
    const perCabinet = cardsPerCabinet(cabinetPixels.pixels, card.maxCapacityPixels);
    const pixelMinimum = cardsNeededByPixels(totalPixels, card.maxCapacityPixels);
    const installedCards = cabinetGrid.total > 0 && perCabinet > 0 ? cabinetGrid.total * perCabinet : pixelMinimum;
    const receiverRequirementHits = requirements.filter((requirement) => receiverMeetsRequirement(card, requirement)).length;
    const receiverExact =
      card.maxCapacityPixels > 0 &&
      support.depthOk &&
      support.frameOk &&
      receiverRequirementHits === requirements.length &&
      (outputPreference === "auto" || outputPreference === receiverSpeed);

    return SENDER_PROCESSOR_CATALOG.map((processor) => {
      const processorOutput = pickProcessorOutput(processor, totalPixels, requiredPorts, allowedModes);
      const processorSupport = processorSupportsTarget(processor, processorOutput, screenW, screenH, fps, rgbBpc);
      const processorRequirementHits = requirements.filter((requirement) => processorMeetsRequirement(processor, requirement)).length;
      const exact = receiverExact && processorSupport.exact && processorRequirementHits === requirements.length;
      const requirementMisses = requirements.length * 2 - receiverRequirementHits - processorRequirementHits;

      return {
        card,
        processor,
        processorOutput,
        support,
        processorSupport,
        outputMode,
        requiredPorts,
        perCabinet,
        pixelMinimum,
        installedCards,
        exact,
        requirementMisses,
      };
    });
  });

  const viableRows = projectRows.filter((row) => row.processorOutput && row.card.maxCapacityPixels > 0);
  const recommendationRows = (viableRows.length > 0 ? viableRows : projectRows)
    .sort((a, b) => {
      if (a.exact !== b.exact) return a.exact ? -1 : 1;
      if (a.processorSupport.exact !== b.processorSupport.exact) return a.processorSupport.exact ? -1 : 1;
      if (a.requirementMisses !== b.requirementMisses) return a.requirementMisses - b.requirementMisses;
      if (a.installedCards !== b.installedCards) return a.installedCards - b.installedCards;
      if (a.requiredPorts !== b.requiredPorts) return a.requiredPorts - b.requiredPorts;
      if ((a.processorOutput?.capacityPixels ?? 0) !== (b.processorOutput?.capacityPixels ?? 0)) {
        return (a.processorOutput?.capacityPixels ?? Number.MAX_SAFE_INTEGER) - (b.processorOutput?.capacityPixels ?? Number.MAX_SAFE_INTEGER);
      }
      return `${a.processor.name} ${a.card.name}`.localeCompare(`${b.processor.name} ${b.card.name}`, undefined, { numeric: true });
    })
    .slice(0, 10);

  const best = recommendationRows[0];
  const hasExactRecommendations = recommendationRows.some((row) => row.exact);

  function toggleRequirement(requirement: ProjectRequirement) {
    setRequirements((current) =>
      current.includes(requirement) ? current.filter((item) => item !== requirement) : [...current, requirement],
    );
  }

  return (
    <div className="space-y-4">
      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectSuggestor.title")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.projectSuggestor.subtitle")}</p>
        <ul className="mt-2 list-inside list-disc text-sm text-zinc-600 dark:text-zinc-400">
          <li>{t("tools.projectSuggestor.sourceNote")}</li>
          <li>{t("tools.receiverPlanner.disclaimerBulletPorts")}</li>
          <li>{t("tools.receiverPlanner.disclaimerBulletCards")}</li>
        </ul>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectSuggestor.formTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.projectSuggestor.formSubtitle")}</p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.labelWidth")}</span>
            <input className="input w-full" inputMode="numeric" value={screenWStr} onChange={(e) => setScreenWStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.labelHeight")}</span>
            <input className="input w-full" inputMode="numeric" value={screenHStr} onChange={(e) => setScreenHStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.receiverPlanner.labelRefresh")}</span>
            <input className="input w-full" inputMode="decimal" value={fpsStr} onChange={(e) => setFpsStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.labelColorDepth")}</span>
            <select className="input w-full" value={rgbBpc} onChange={(e) => setRgbBpc(Number(e.target.value) as RgbBitsPerChannel)}>
              {RGB_BPC_PRESETS.map((bpc) => (
                <option key={bpc} value={bpc}>
                  {depthSelectLabel(t, bpc)}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-6 grid gap-3 lg:grid-cols-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.receiverPlanner.labelCabinetWidth")}</span>
            <input className="input w-full" inputMode="decimal" value={cabinetWStr} onChange={(e) => setCabinetWStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.receiverPlanner.labelCabinetHeight")}</span>
            <input className="input w-full" inputMode="decimal" value={cabinetHStr} onChange={(e) => setCabinetHStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.receiverPlanner.labelPixelPitch")}</span>
            <input className="input w-full" inputMode="decimal" value={pitchStr} onChange={(e) => setPitchStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectSuggestor.labelOutputPreference")}</span>
            <select className="input w-full" value={outputPreference} onChange={(e) => setOutputPreference(e.target.value as ProjectOutputPreference)}>
              <option value="auto">{t("tools.projectSuggestor.outputAuto")}</option>
              <option value="1g">{t("tools.receiverPlanner.port1g")}</option>
              <option value="5g">{t("tools.receiverPlanner.port5g")}</option>
            </select>
          </label>
        </div>

        <fieldset className="mt-4">
          <legend className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectSuggestor.requirements")}</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {REQUIREMENTS.map((requirement) => (
              <label
                key={requirement}
                className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300"
              >
                <input
                  type="checkbox"
                  checked={requirements.includes(requirement)}
                  onChange={() => toggleRequirement(requirement)}
                />
                {t(`tools.projectSuggestor.requirement.${requirement}`)}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900/60">
          <p className="font-medium text-zinc-800 dark:text-zinc-200">{t("tools.receiverPlanner.cabinetPixels")}</p>
          <p className="mt-1 tabular-nums text-zinc-600 dark:text-zinc-400">
            {t("tools.receiverPlanner.cabinetPixelsValue", {
              w: nf0.format(cabinetPixels.width),
              h: nf0.format(cabinetPixels.height),
              pixels: nf0.format(cabinetPixels.pixels),
            })}
          </p>
          <p className="mt-1 tabular-nums text-zinc-600 dark:text-zinc-400">
            {t("tools.receiverPlanner.cabinetGridValue", {
              across: nf0.format(cabinetGrid.across),
              tall: nf0.format(cabinetGrid.tall),
              total: nf0.format(cabinetGrid.total),
            })}
          </p>
        </div>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectSuggestor.resultTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t("tools.receiverPlanner.resultSummary", {
            w: nf0.format(screenW),
            h: nf0.format(screenH),
            fps: nf1.format(fps),
            bpc: nf0.format(rgbBpc),
            mbps: nf1.format(requiredMbps),
          })}
        </p>

        <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label={t("tools.receiverPlanner.metricPixels")} value={nf0.format(totalPixels)} note={t("tools.receiverPlanner.metricPixelsNote")} />
          <Metric label={t("tools.receiverPlanner.metricBandwidth")} value={`${nf2.format(requiredMbps / 1000)} Gbit/s`} note={t("tools.receiverPlanner.metricBandwidthNote")} />
          <Metric label={t("tools.receiverPlanner.metricPorts")} value={`${nf0.format(ports1g)} / ${nf0.format(ports5g)}`} note={t("tools.receiverPlanner.metricPortsNote")} />
          <Metric
            label={t("tools.receiverPlanner.metricCabinets")}
            value={nf0.format(cabinetGrid.total)}
            note={t("tools.receiverPlanner.metricCabinetsNote", {
              across: nf0.format(cabinetGrid.across),
              tall: nf0.format(cabinetGrid.tall),
            })}
          />
        </dl>

        {best ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-950">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{t("tools.projectSuggestor.bestProcessor")}</p>
              <h3 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{best.processor.name}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{best.processor.overview}</p>
              <div className="mt-3 flex flex-wrap gap-1">
                <CapabilityChip state={best.processorSupport.exact ? "ok" : "bad"}>
                  {best.processorOutput
                    ? t("tools.projectSuggestor.processorOutput", {
                        mode: modeLabel(t, best.processorOutput.mode),
                        ports: nf0.format(best.processorOutput.ports),
                        capacity: nf0.format(best.processorOutput.capacityPixels),
                      })
                    : t("tools.projectSuggestor.noProcessorOutput")}
                </CapabilityChip>
                <CapabilityChip state={best.processor.maxFrameRateHz === null || best.processor.maxFrameRateHz >= fps ? "ok" : "bad"}>
                  {t("tools.receiverPlanner.fpsBadge", { fps: nf1.format(best.processor.maxFrameRateHz ?? fps) })}
                </CapabilityChip>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-950">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{t("tools.projectSuggestor.bestReceiver")}</p>
              <h3 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{best.card.name}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t("tools.receiverPlanner.selectedCardLine", {
                  series: best.card.series,
                  capacity: best.card.maxCapacityLabel,
                  pixels: nf0.format(best.card.maxCapacityPixels),
                })}
              </p>
              <div className="mt-3 flex flex-wrap gap-1">
                <CapabilityChip state={best.support.depthOk ? "ok" : best.support.depthKnown ? "bad" : "unknown"}>
                  {best.support.depthKnown
                    ? t("tools.receiverPlanner.depthBadge", { bpc: nf0.format(best.card.maxColorDepthBpc ?? 0) })
                    : t("tools.receiverPlanner.depthUnknown")}
                </CapabilityChip>
                <CapabilityChip state={best.support.frameOk ? "ok" : best.support.frameKnown ? "bad" : "unknown"}>
                  {best.support.frameKnown
                    ? t("tools.receiverPlanner.fpsBadge", { fps: nf1.format(best.card.maxFrameRateHz ?? 0) })
                    : t("tools.receiverPlanner.fpsUnknown")}
                </CapabilityChip>
                <CapabilityChip state="ok">{modeLabel(t, best.card.portSpeed)}</CapabilityChip>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectSuggestor.recommendationsTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {hasExactRecommendations ? t("tools.projectSuggestor.recommendationsSubtitle") : t("tools.projectSuggestor.noExactRecommendations")}
        </p>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-[980px] w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
              <tr>
                <th className="py-2 pr-3 font-semibold">{t("tools.projectSuggestor.tableProcessor")}</th>
                <th className="px-3 py-2 font-semibold">{t("tools.receiverPlanner.tableCard")}</th>
                <th className="px-3 py-2 font-semibold">{t("tools.projectSuggestor.tableOutput")}</th>
                <th className="px-3 py-2 font-semibold">{t("tools.receiverPlanner.tableCards")}</th>
                <th className="px-3 py-2 font-semibold">{t("tools.receiverPlanner.tableCapability")}</th>
                <th className="py-2 pl-3 font-semibold">{t("tools.projectSuggestor.tableFit")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {recommendationRows.map((row) => (
                <tr key={`${row.processor.name}-${row.card.name}-${row.processorOutput?.mode ?? "none"}`} className="align-top">
                  <td className="py-3 pr-3">
                    <p className="font-semibold text-zinc-900 dark:text-zinc-100">{row.processor.name}</p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">{row.processor.series}</p>
                  </td>
                  <td className="px-3 py-3">
                    <p className="font-semibold text-zinc-900 dark:text-zinc-100">{row.card.name}</p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">{row.card.series}</p>
                  </td>
                  <td className="px-3 py-3 tabular-nums">
                    {row.processorOutput ? (
                      <>
                        <p className="font-medium text-zinc-900 dark:text-zinc-100">{row.processorOutput.label}</p>
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">
                          {t("tools.projectSuggestor.outputBreakdown", {
                            required: nf0.format(row.requiredPorts),
                            available: nf0.format(row.processorOutput.ports),
                            capacity: nf0.format(row.processorOutput.capacityPixels),
                          })}
                        </p>
                      </>
                    ) : (
                      <p className="text-red-700 dark:text-red-300">{t("tools.projectSuggestor.noProcessorOutput")}</p>
                    )}
                  </td>
                  <td className="px-3 py-3 tabular-nums">
                    <p className="font-medium text-zinc-900 dark:text-zinc-100">{nf0.format(row.installedCards)}</p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t("tools.receiverPlanner.cardsBreakdown", {
                        perCabinet: nf0.format(row.perCabinet),
                        minimum: nf0.format(row.pixelMinimum),
                      })}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1">
                      <CapabilityChip state={row.support.depthOk ? "ok" : row.support.depthKnown ? "bad" : "unknown"}>
                        {row.support.depthKnown
                          ? t("tools.receiverPlanner.depthBadge", { bpc: nf0.format(row.card.maxColorDepthBpc ?? 0) })
                          : t("tools.receiverPlanner.depthUnknown")}
                      </CapabilityChip>
                      <CapabilityChip state={row.support.frameOk ? "ok" : row.support.frameKnown ? "bad" : "unknown"}>
                        {row.support.frameKnown
                          ? t("tools.receiverPlanner.fpsBadge", { fps: nf1.format(row.card.maxFrameRateHz ?? 0) })
                          : t("tools.receiverPlanner.fpsUnknown")}
                      </CapabilityChip>
                    </div>
                  </td>
                  <td className="py-3 pl-3">
                    <CapabilityChip state={row.exact ? "ok" : row.processorSupport.outputOk ? "unknown" : "bad"}>
                      {row.exact ? t("tools.projectSuggestor.fitExact") : row.processorSupport.outputOk ? t("tools.projectSuggestor.fitReview") : t("tools.projectSuggestor.fitNoOutput")}
                    </CapabilityChip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
