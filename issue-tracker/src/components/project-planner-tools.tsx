"use client";

import { useI18n } from "@/i18n/context";
import type { TranslateFn } from "@/i18n/create-translator";
import { RGB_BPC_PRESETS, totalBppRgbPacked, type RgbBitsPerChannel } from "@/lib/led-bandwidth";
import {
  PLANNER_INPUT_INTERFACE_IDS,
  RECEIVER_CARD_CATALOG,
  SENDER_PROCESSOR_CATALOG,
  cabinetPixelsFromResolution,
  cabinetsNeeded,
  cardsNeededByPixels,
  cardsPerCabinet,
  ledSignalMbps,
  outputModesForPreference,
  pickProcessorOutput,
  plannerPairingMeetsSignalLimits,
  portsNeededForMbps,
  processorHasAllowedOutputMode,
  processorHasSwappableBoards,
  PLANNER_OUTPUT_INTERFACE_IDS,
  boardSpecForPrimaryOutputPlanning,
  inferUsSeriesInputBoardSpecFromPlannerLines,
  isUsSeriesProcessorName,
  isVxSeriesProcessor,
  processorSupportsTarget,
  totalPlannedOutputPorts,
  recommendProcessorInputBoard,
  recommendProcessorOutputBoard,
  requiredPortsForProcessorOutput,
  receiverCardInPlannerCatalog,
  receiverSupportsTarget,
  totalInputConnectors,
  usableMbpsForPortSpeed,
  type PlannerInputInterfaceId,
  type PlannerInputLine,
  type PlannerOutputLine,
  type ProcessorOutputMode,
  type ProjectOutputPreference,
  type ReceiverCardCatalogItem,
  type ReceiverPortSpeed,
} from "@/lib/project-planner";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

const PLANNER_FALLBACK_TEXT: Record<string, string> = {
  "tools.projectPlanner.exactReason": "This pairing clears the signal, resolution, and receiver-card checks entered above.",
  "tools.projectPlanner.guideWhy": "Why it works",
  "tools.projectPlanner.guideInstall": "Install count",
  "tools.projectPlanner.guideSignal": "Signal plan",
  "tools.projectPlanner.guideVerify": "Before quoting",
  "tools.projectPlanner.outputCapacityLine": "{output}: needs {required} ports, has {available}, and supports {capacity} pixels.",
  "tools.projectPlanner.cardsInstallLine": "Plan {cards} receiver cards: {perCabinet} per cabinet, with {minimum} as the pixel-only minimum.",
  "tools.projectPlanner.bandwidthLine": "{gbps} Gbit/s active RGB payload, planned around {mode}.",
  "tools.projectPlanner.verifyCards": "Confirm scan type, cabinet wiring, calibration mode, and receiver-card version against the real cabinet design.",
  "tools.projectPlanner.verifyWhenNotExact":
    "Resolve the warnings above and confirm cabinet mapping, wiring, and datasheet limits before quoting.",
  "tools.projectPlanner.outputSourcesTitle": "Video outputs (planning)",
  "tools.projectPlanner.outputSourcesLeadUs":
    "Add RJ45 Ethernet (1G or 5G) and/or 10G fiber as you plan cabling to receivers. Count is planned ports (runs). The package below estimates output boards from signal math plus these rows.",
  "tools.projectPlanner.outputType": "Output link",
  "tools.projectPlanner.outputSummary": "Planned output ports (your rows): {total}. {list}",
  "tools.projectPlanner.outputSummaryEmpty": "No outputs listed.",
  "tools.projectPlanner.outputBandwidthHint":
    "Minimum ports from bandwidth at the chosen tier: about {required} (compare to your planned runs).",
  "tools.projectPlanner.outputAdd": "Add output row",
  "tools.projectPlanner.outputIf.ethernet_1g_rj45": "1G Ethernet (RJ45)",
  "tools.projectPlanner.outputIf.ethernet_5g_rj45": "5G Ethernet (RJ45)",
  "tools.projectPlanner.outputIf.fiber_10g": "10G fiber",
  "tools.projectPlanner.vxFixedChassisTitle": "VX Series — fixed chassis I/O",
  "tools.projectPlanner.vxFixedChassisLead":
    "All-in-one controller (no swappable input/output cards). Outputs use structured port counts from our catalog; inputs are listed when extracted for this SKU.",
  "tools.projectPlanner.vxSubOutputs": "Outputs to LED wall",
  "tools.projectPlanner.vxSubInputs": "Video inputs",
  "tools.projectPlanner.vxInputsNotInCatalog":
    "Input connector detail isn’t in our planner extract for this SKU yet—see the Colorlight datasheet.",
  "tools.projectPlanner.vxPortsWord": "ports",
};

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
  if (mode === "5g") return t("tools.projectPlanner.port5g");
  if (mode === "10g") return t("tools.projectPlanner.port10g");
  if (mode === "unknown") return t("tools.projectPlanner.port1gAssumed");
  return t("tools.projectPlanner.port1g");
}

function BoardLine({
  label,
  name,
  model,
  quantity,
  maxBoards,
  withinLimit,
}: {
  label: string;
  name: string;
  model: string;
  quantity: number;
  maxBoards: number;
  withinLimit: boolean;
}) {
  return (
    <p className={withinLimit ? "text-xs text-zinc-500 dark:text-zinc-400" : "text-xs text-red-700 dark:text-red-300"}>
      <span className="font-medium">{label}</span>{" "}
      {quantity} x {name} ({model}) - {quantity}/{maxBoards}
    </p>
  );
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

function LessonLine({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-1 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">{children}</dd>
    </div>
  );
}

function inputLineKey(line: PlannerInputLine, index: number): string {
  return `${line.interfaceId}-${index}`;
}

function outputLineKey(line: PlannerOutputLine, index: number): string {
  return `${line.interfaceId}-${index}`;
}

export function ProjectPlannerTools() {
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
  const [cabinetWpStr, setCabinetWpStr] = useState("480");
  const [cabinetHpStr, setCabinetHpStr] = useState("270");
  const [outputPreference, setOutputPreference] = useState<ProjectOutputPreference>("1g");

  const [processorName, setProcessorName] = useState(() => SENDER_PROCESSOR_CATALOG[0]?.name ?? "");
  const [cardName, setCardName] = useState("");
  const [outputLines, setOutputLines] = useState<PlannerOutputLine[]>([{ interfaceId: "ethernet_1g_rj45", count: 1 }]);
  const [inputLines, setInputLines] = useState<PlannerInputLine[]>([{ interfaceId: "hdmi20", count: 1 }]);

  const screenW = parsePositiveInt(screenWStr, 0);
  const screenH = parsePositiveInt(screenHStr, 0);
  const fps = parsePositiveFloat(fpsStr, 0);
  const cabinetWpx = parsePositiveInt(cabinetWpStr, 0);
  const cabinetHpx = parsePositiveInt(cabinetHpStr, 0);

  const totalPixels = screenW * screenH;
  const requiredMbps = ledSignalMbps(screenW, screenH, fps, rgbBpc);
  const ports1g = portsNeededForMbps(requiredMbps, usableMbpsForPortSpeed("1g"));
  const ports5g = portsNeededForMbps(requiredMbps, usableMbpsForPortSpeed("5g"));
  const cabinetPixels = cabinetPixelsFromResolution(cabinetWpx, cabinetHpx);
  const cabinetGrid = cabinetsNeeded(screenW, screenH, cabinetPixels.width, cabinetPixels.height);

  const plannerCards = useMemo(
    () => RECEIVER_CARD_CATALOG.filter((card) => receiverCardInPlannerCatalog(card, outputPreference)),
    [outputPreference],
  );

  useEffect(() => {
    if (plannerCards.length === 0) return;
    const valid = plannerCards.some((c) => c.name === cardName);
    if (!valid) setCardName(plannerCards[0].name);
  }, [outputPreference, plannerCards, cardName]);

  const selectedProcessor = useMemo(
    () => SENDER_PROCESSOR_CATALOG.find((p) => p.name === processorName) ?? null,
    [processorName],
  );
  const selectedCard = useMemo(() => plannerCards.find((c) => c.name === cardName) ?? null, [plannerCards, cardName]);
  const processorIsModular = selectedProcessor ? processorHasSwappableBoards(selectedProcessor) : false;
  /** VX and other all-in-one models: no swappable input boards. Until a processor is chosen, show modular input rows. */
  const showModularInputPlanner = !selectedProcessor || processorIsModular;

  const activeRow = useMemo(() => {
    if (!selectedProcessor || !selectedCard) return null;

    const card = selectedCard;
    const processor = selectedProcessor;
    const receiverSpeed = planningPortSpeed(card);
    const linkSetModes = outputModesForPreference(outputPreference);
    const outputMode = linkSetModes.includes(receiverSpeed) ? receiverSpeed : linkSetModes[0] ?? receiverSpeed;
    const support = receiverSupportsTarget(card, fps, rgbBpc);
    const perCabinet = cardsPerCabinet(cabinetPixels.pixels, card.maxCapacityPixels);
    const pixelMinimum = cardsNeededByPixels(totalPixels, card.maxCapacityPixels);
    const installedCards = cabinetGrid.total > 0 && perCabinet > 0 ? cabinetGrid.total * perCabinet : pixelMinimum;
    const receiverExact =
      card.maxCapacityPixels > 0 &&
      support.depthOk &&
      support.frameOk &&
      outputPreference === receiverSpeed;

    const plannedOutputBoardSpec = boardSpecForPrimaryOutputPlanning(outputLines, outputPreference);
    const modesForProcessorPick =
      isUsSeriesProcessorName(processor.name) && plannedOutputBoardSpec ? [plannedOutputBoardSpec.mode] : linkSetModes;

    const processorOutput = pickProcessorOutput(processor, totalPixels, requiredMbps, modesForProcessorPick);
    const requiredPorts = requiredPortsForProcessorOutput(processorOutput, requiredMbps);
    const processorSupport = processorSupportsTarget(processor, processorOutput, screenW, screenH, fps, rgbBpc);
    const exact = receiverExact && processorSupport.exact;

    const inputSpec = isUsSeriesProcessorName(processor.name) ? inferUsSeriesInputBoardSpecFromPlannerLines(inputLines) : undefined;
    const outputSpec =
      isUsSeriesProcessorName(processor.name) && processorOutput ? plannedOutputBoardSpec ?? undefined : undefined;

    const inputBoard = recommendProcessorInputBoard(processor, screenW, screenH, fps, inputSpec, inputLines);
    const outputBoard = recommendProcessorOutputBoard(processor, processorOutput, totalPixels, requiredPorts, outputSpec);

    return {
      card,
      processor,
      processorOutput,
      inputBoard,
      outputBoard,
      support,
      processorSupport,
      outputMode,
      requiredPorts,
      perCabinet,
      pixelMinimum,
      installedCards,
      exact,
    };
  }, [
    selectedProcessor,
    selectedCard,
    outputPreference,
    screenW,
    screenH,
    fps,
    rgbBpc,
    cabinetPixels.pixels,
    cabinetGrid.total,
    totalPixels,
    requiredMbps,
    inputLines,
    outputLines,
  ]);

  const issueLines = useMemo(() => {
    const lines: string[] = [];
    if (!selectedProcessor || !selectedCard || !activeRow) return lines;

    const { processor, processorOutput, processorSupport, support } = activeRow;
    const allowedModes = outputModesForPreference(outputPreference);

    if (!processorHasAllowedOutputMode(processor, allowedModes)) {
      lines.push(t("tools.projectPlanner.issue.linkSet"));
    } else if (!processorOutput) {
      lines.push(t("tools.projectPlanner.issue.outputShortfall"));
    }

    if (!processorSupport.widthOk) lines.push(t("tools.projectPlanner.issue.processorWidth"));
    if (!processorSupport.heightOk) lines.push(t("tools.projectPlanner.issue.processorHeight"));
    if (!processorSupport.frameOk) lines.push(t("tools.projectPlanner.issue.processorFps"));
    if (!processorSupport.depthOk) lines.push(t("tools.projectPlanner.issue.processorDepth"));

    if (!support.depthOk) lines.push(t("tools.projectPlanner.issue.receiverDepth"));
    if (!support.frameOk) lines.push(t("tools.projectPlanner.issue.receiverFps"));

    return lines;
  }, [selectedProcessor, selectedCard, activeRow, outputPreference, t]);

  const pairingOk =
    activeRow &&
    selectedCard &&
    plannerPairingMeetsSignalLimits({
      processorOutput: activeRow.processorOutput,
      card: selectedCard,
      support: activeRow.support,
      processorSupport: activeRow.processorSupport,
    });

  const inputConnectorTotal = totalInputConnectors(inputLines);
  const inputSummaryText = inputLines
    .filter((l) => l.count > 0)
    .map((l) => `${nf0.format(l.count)}× ${t(`tools.projectPlanner.inputIf.${l.interfaceId}`)}`)
    .join("; ");

  const translatedInputBoard = t("tools.projectPlanner.inputBoard");
  const translatedOutputBoard = t("tools.projectPlanner.outputBoard");
  const inputBoardLabel = translatedInputBoard === "tools.projectPlanner.inputBoard" ? "Input board" : translatedInputBoard;
  const outputBoardLabel = translatedOutputBoard === "tools.projectPlanner.outputBoard" ? "Output board" : translatedOutputBoard;

  function plannerText(path: string, vars?: Record<string, string>): string {
    const translated = t(path, vars);
    if (translated !== path) return translated;

    let fallback = PLANNER_FALLBACK_TEXT[path] ?? path;
    for (const [key, value] of Object.entries(vars ?? {})) {
      fallback = fallback.replaceAll(`{${key}}`, value);
    }
    return fallback;
  }

  function setInputLine(index: number, patch: Partial<PlannerInputLine>) {
    setInputLines((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addInputLine() {
    setInputLines((rows) => [...rows, { interfaceId: "hdmi20", count: 1 }]);
  }

  function removeInputLine(index: number) {
    setInputLines((rows) => (rows.length <= 1 ? rows : rows.filter((_, i) => i !== index)));
  }

  function setOutputLine(index: number, patch: Partial<PlannerOutputLine>) {
    setOutputLines((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addOutputLine() {
    setOutputLines((rows) => [...rows, { interfaceId: "ethernet_5g_rj45", count: 1 }]);
  }

  function removeOutputLine(index: number) {
    setOutputLines((rows) => (rows.length <= 1 ? rows : rows.filter((_, i) => i !== index)));
  }

  const plannedOutputPortTotal = totalPlannedOutputPorts(outputLines);
  const outputSummaryText = outputLines
    .filter((l) => l.count > 0)
    .map((l) => `${nf0.format(l.count)}× ${t(`tools.projectPlanner.outputIf.${l.interfaceId}`)}`)
    .join("; ");

  return (
    <div className="space-y-4">
      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectPlanner.title")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.projectPlanner.subtitle")}</p>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectPlanner.formTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.projectPlanner.formSubtitle")}</p>

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
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.labelRefresh")}</span>
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

        <div className="mt-6 grid gap-3 lg:grid-cols-3">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.labelCabinetWidthPx")}</span>
            <input className="input w-full" inputMode="numeric" value={cabinetWpStr} onChange={(e) => setCabinetWpStr(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.labelCabinetHeightPx")}</span>
            <input className="input w-full" inputMode="numeric" value={cabinetHpStr} onChange={(e) => setCabinetHpStr(e.target.value)} />
          </label>
          <fieldset className="block text-sm">
            <legend className="mb-1 font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.labelOutputPreference")}</legend>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
                <input
                  type="radio"
                  name="project-planner-output-set"
                  className="border-zinc-300 text-zinc-900"
                  checked={outputPreference === "1g"}
                  onChange={() => setOutputPreference("1g")}
                />
                {t("tools.projectPlanner.outputSet1g")}
              </label>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
                <input
                  type="radio"
                  name="project-planner-output-set"
                  className="border-zinc-300 text-zinc-900"
                  checked={outputPreference === "5g"}
                  onChange={() => setOutputPreference("5g")}
                />
                {t("tools.projectPlanner.outputSet5g")}
              </label>
            </div>
          </fieldset>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.labelProcessor")}</span>
            <select className="input w-full" value={processorName} onChange={(e) => setProcessorName(e.target.value)}>
              {SENDER_PROCESSOR_CATALOG.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.series})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.labelReceiverCard")}</span>
            <select className="input w-full" value={cardName} onChange={(e) => setCardName(e.target.value)} disabled={plannerCards.length === 0}>
              {plannerCards.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} · {c.series}
                </option>
              ))}
            </select>
          </label>
        </div>

        {selectedProcessor && isVxSeriesProcessor(selectedProcessor) ? (
          <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900/60">
            <p className="font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.vxFixedChassisTitle")}</p>
            <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.projectPlanner.vxFixedChassisLead")}</p>

            <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {t("tools.projectPlanner.vxSubOutputs")}
            </p>
            <ul className="mt-1.5 space-y-1.5 text-xs text-zinc-800 dark:text-zinc-200">
              {selectedProcessor.outputs.map((o) => (
                <li key={`${o.mode}-${o.ports}-${o.label}`} className="flex flex-wrap items-baseline gap-x-2 tabular-nums">
                  <span className="font-semibold">
                    {nf0.format(o.ports)} {t("tools.projectPlanner.vxPortsWord")}
                  </span>
                  <span className="text-zinc-500 dark:text-zinc-400">· {modeLabel(t, o.mode)}</span>
                  <span className="text-zinc-600 dark:text-zinc-300">— {o.label}</span>
                </li>
              ))}
            </ul>

            <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {t("tools.projectPlanner.vxSubInputs")}
            </p>
            {selectedProcessor.inputs && selectedProcessor.inputs.length > 0 ? (
              <ul className="mt-1.5 list-inside list-disc space-y-1 text-xs text-zinc-800 dark:text-zinc-200">
                {selectedProcessor.inputs.map((row, i) => (
                  <li key={`${row.label}-${i}`}>{row.label}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1.5 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">
                {t("tools.projectPlanner.vxInputsNotInCatalog")}
              </p>
            )}
          </div>
        ) : null}

        {/* VX: inputs are listed in the fixed chassis box above — hide this section to avoid duplicate "Video inputs" copy. */}
        {selectedProcessor && isVxSeriesProcessor(selectedProcessor) ? null : (
          <div className="mt-6">
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.inputSourcesTitle")}</p>
            {!showModularInputPlanner ? (
              <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.projectPlanner.inputSourcesLeadFixed")}</p>
            ) : (
              <>
                <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.projectPlanner.inputSourcesLeadModular")}</p>
                <div className="mt-3 space-y-2">
                  {inputLines.map((line, index) => (
                    <div key={inputLineKey(line, index)} className="flex flex-wrap items-end gap-2">
                      <label className="min-w-[200px] flex-1 text-sm">
                        <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.inputType")}</span>
                        <select
                          className="input w-full"
                          value={line.interfaceId}
                          onChange={(e) => setInputLine(index, { interfaceId: e.target.value as PlannerInputInterfaceId })}
                        >
                          {PLANNER_INPUT_INTERFACE_IDS.map((id) => (
                            <option key={id} value={id}>
                              {t(`tools.projectPlanner.inputIf.${id}`)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="w-28 text-sm">
                        <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.inputCount")}</span>
                        <input
                          className="input w-full"
                          inputMode="numeric"
                          min={1}
                          value={line.count}
                          onChange={(e) => setInputLine(index, { count: Math.max(1, parsePositiveInt(e.target.value, 1)) })}
                        />
                      </label>
                      <button
                        type="button"
                        className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
                        onClick={() => removeInputLine(index)}
                        disabled={inputLines.length <= 1}
                      >
                        {t("tools.projectPlanner.inputRemove")}
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  className="mt-2 rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-400 dark:hover:bg-zinc-900"
                  onClick={addInputLine}
                >
                  {t("tools.projectPlanner.inputAdd")}
                </button>
                <p className="mt-3 text-xs text-zinc-600 dark:text-zinc-400">
                  {t("tools.projectPlanner.inputSummary", {
                    total: nf0.format(inputConnectorTotal),
                    list: inputSummaryText || t("tools.projectPlanner.inputSummaryEmpty"),
                  })}
                </p>
              </>
            )}
          </div>
        )}

        {selectedProcessor && isUsSeriesProcessorName(selectedProcessor.name) ? (
          <div className="mt-6">
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.outputSourcesTitle")}</p>
            <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.projectPlanner.outputSourcesLeadUs")}</p>
            <div className="mt-3 space-y-2">
              {outputLines.map((line, index) => (
                <div key={outputLineKey(line, index)} className="flex flex-wrap items-end gap-2">
                  <label className="min-w-[220px] flex-1 text-sm">
                    <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.outputType")}</span>
                    <select
                      className="input w-full"
                      value={line.interfaceId}
                      onChange={(e) =>
                        setOutputLine(index, { interfaceId: e.target.value as PlannerOutputLine["interfaceId"] })
                      }
                    >
                      {PLANNER_OUTPUT_INTERFACE_IDS.map((id) => (
                        <option key={id} value={id}>
                          {t(`tools.projectPlanner.outputIf.${id}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="w-28 text-sm">
                    <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.inputCount")}</span>
                    <input
                      className="input w-full"
                      inputMode="numeric"
                      min={1}
                      value={line.count}
                      onChange={(e) => setOutputLine(index, { count: Math.max(1, parsePositiveInt(e.target.value, 1)) })}
                    />
                  </label>
                  <button
                    type="button"
                    className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
                    onClick={() => removeOutputLine(index)}
                    disabled={outputLines.length <= 1}
                  >
                    {t("tools.projectPlanner.inputRemove")}
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="mt-2 rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-400 dark:hover:bg-zinc-900"
              onClick={addOutputLine}
            >
              {t("tools.projectPlanner.outputAdd")}
            </button>
            <p className="mt-3 text-xs text-zinc-600 dark:text-zinc-400">
              {t("tools.projectPlanner.outputSummary", {
                total: nf0.format(plannedOutputPortTotal),
                list: outputSummaryText || t("tools.projectPlanner.outputSummaryEmpty"),
              })}
            </p>
            {activeRow ? (
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t("tools.projectPlanner.outputBandwidthHint", { required: nf0.format(activeRow.requiredPorts) })}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900/60">
          <p className="font-medium text-zinc-800 dark:text-zinc-200">{t("tools.projectPlanner.cabinetPixels")}</p>
          <p className="mt-1 tabular-nums text-zinc-600 dark:text-zinc-400">
            {t("tools.projectPlanner.cabinetPixelsValue", {
              w: nf0.format(cabinetPixels.width),
              h: nf0.format(cabinetPixels.height),
              pixels: nf0.format(cabinetPixels.pixels),
            })}
          </p>
          <p className="mt-1 tabular-nums text-zinc-600 dark:text-zinc-400">
            {t("tools.projectPlanner.cabinetGridValue", {
              across: nf0.format(cabinetGrid.across),
              tall: nf0.format(cabinetGrid.tall),
              total: nf0.format(cabinetGrid.total),
            })}
          </p>
        </div>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.projectPlanner.resultTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t("tools.projectPlanner.resultSummary", {
            w: nf0.format(screenW),
            h: nf0.format(screenH),
            fps: nf1.format(fps),
            bpc: nf0.format(rgbBpc),
            mbps: nf1.format(requiredMbps),
          })}
        </p>

        <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label={t("tools.projectPlanner.metricPixels")} value={nf0.format(totalPixels)} note={t("tools.projectPlanner.metricPixelsNote")} />
          <Metric label={t("tools.projectPlanner.metricBandwidth")} value={`${nf2.format(requiredMbps / 1000)} Gbit/s`} note={t("tools.projectPlanner.metricBandwidthNote")} />
          <Metric label={t("tools.projectPlanner.metricPorts")} value={`${nf0.format(ports1g)} / ${nf0.format(ports5g)}`} note={t("tools.projectPlanner.metricPortsNote")} />
          <Metric
            label={t("tools.projectPlanner.metricCabinets")}
            value={nf0.format(cabinetGrid.total)}
            note={t("tools.projectPlanner.metricCabinetsNote", {
              across: nf0.format(cabinetGrid.across),
              tall: nf0.format(cabinetGrid.tall),
            })}
          />
        </dl>

        {plannerCards.length === 0 ? (
          <p className="mt-4 text-sm text-amber-800 dark:text-amber-200">{t("tools.projectPlanner.noCardsForLinkSet")}</p>
        ) : null}

        {issueLines.length > 0 ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/60 dark:bg-amber-950/40">
            <p className="text-sm font-medium text-amber-900 dark:text-amber-100">{t("tools.projectPlanner.issueTitle")}</p>
            <ul className="mt-2 list-inside list-disc text-sm text-amber-900 dark:text-amber-100">
              {issueLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {issueLines.length === 0 && pairingOk && activeRow ? (
          <p className="mt-4 text-sm text-emerald-800 dark:text-emerald-200">{t("tools.projectPlanner.pairingOk")}</p>
        ) : null}

        {activeRow ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-950">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{t("tools.projectPlanner.bestProcessor")}</p>
              <h3 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{activeRow.processor.name}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{activeRow.processor.overview}</p>
              {activeRow.inputBoard || activeRow.outputBoard ? (
                <div className="mt-3 space-y-1">
                  {activeRow.inputBoard ? (
                    <BoardLine
                      label={inputBoardLabel}
                      name={activeRow.inputBoard.name}
                      model={activeRow.inputBoard.model}
                      quantity={activeRow.inputBoard.quantity}
                      maxBoards={activeRow.inputBoard.maxBoards}
                      withinLimit={activeRow.inputBoard.withinLimit}
                    />
                  ) : null}
                  {activeRow.outputBoard ? (
                    <BoardLine
                      label={outputBoardLabel}
                      name={activeRow.outputBoard.name}
                      model={activeRow.outputBoard.model}
                      quantity={activeRow.outputBoard.quantity}
                      maxBoards={activeRow.outputBoard.maxBoards}
                      withinLimit={activeRow.outputBoard.withinLimit}
                    />
                  ) : null}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-1">
                <CapabilityChip state={activeRow.processorSupport.exact ? "ok" : "bad"}>
                  {activeRow.processorOutput
                    ? t("tools.projectPlanner.processorOutput", {
                        mode: modeLabel(t, activeRow.processorOutput.mode),
                        ports: nf0.format(activeRow.processorOutput.ports),
                        capacity: nf0.format(activeRow.processorOutput.capacityPixels),
                      })
                    : t("tools.projectPlanner.noProcessorOutput")}
                </CapabilityChip>
                <CapabilityChip state={activeRow.processor.maxFrameRateHz === null || activeRow.processor.maxFrameRateHz >= fps ? "ok" : "bad"}>
                  {t("tools.projectPlanner.fpsBadge", { fps: nf1.format(activeRow.processor.maxFrameRateHz ?? fps) })}
                </CapabilityChip>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-950">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{t("tools.projectPlanner.bestReceiver")}</p>
              <h3 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{activeRow.card.name}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t("tools.projectPlanner.selectedCardLine", {
                  series: activeRow.card.series,
                  capacity: activeRow.card.maxCapacityLabel,
                  pixels: nf0.format(activeRow.card.maxCapacityPixels),
                })}
              </p>
              <div className="mt-3 flex flex-wrap gap-1">
                <CapabilityChip state={activeRow.support.depthOk ? "ok" : activeRow.support.depthKnown ? "bad" : "unknown"}>
                  {activeRow.support.depthKnown
                    ? t("tools.projectPlanner.depthBadge", { bpc: nf0.format(activeRow.card.maxColorDepthBpc ?? 0) })
                    : t("tools.projectPlanner.depthUnknown")}
                </CapabilityChip>
                <CapabilityChip state={activeRow.support.frameOk ? "ok" : activeRow.support.frameKnown ? "bad" : "unknown"}>
                  {activeRow.support.frameKnown
                    ? t("tools.projectPlanner.fpsBadge", { fps: nf1.format(activeRow.card.maxFrameRateHz ?? 0) })
                    : t("tools.projectPlanner.fpsUnknown")}
                </CapabilityChip>
                <CapabilityChip state="ok">{modeLabel(t, activeRow.card.portSpeed)}</CapabilityChip>
              </div>
            </div>
          </div>
        ) : null}

        {activeRow ? (
          <dl className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
            <LessonLine label={plannerText("tools.projectPlanner.guideWhy")}>
              {activeRow.processorOutput
                ? plannerText("tools.projectPlanner.outputCapacityLine", {
                    output: activeRow.processorOutput.label,
                    required: nf0.format(activeRow.requiredPorts),
                    available: nf0.format(activeRow.processorOutput.ports),
                    capacity: nf0.format(activeRow.processorOutput.capacityPixels),
                  })
                : t("tools.projectPlanner.noProcessorOutput")}
            </LessonLine>
            <LessonLine label={plannerText("tools.projectPlanner.guideInstall")}>
              {plannerText("tools.projectPlanner.cardsInstallLine", {
                cards: nf0.format(activeRow.installedCards),
                perCabinet: nf0.format(activeRow.perCabinet),
                minimum: nf0.format(activeRow.pixelMinimum),
              })}
            </LessonLine>
            <LessonLine label={plannerText("tools.projectPlanner.guideSignal")}>
              {plannerText("tools.projectPlanner.bandwidthLine", {
                gbps: nf2.format(requiredMbps / 1000),
                mode: modeLabel(t, activeRow.outputMode),
              })}
            </LessonLine>
            <LessonLine label={plannerText("tools.projectPlanner.guideVerify")}>
              {activeRow.exact
                ? plannerText("tools.projectPlanner.verifyCards")
                : plannerText("tools.projectPlanner.verifyWhenNotExact")}
            </LessonLine>
          </dl>
        ) : null}
      </section>
    </div>
  );
}
