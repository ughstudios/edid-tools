"use client";

import { useI18n } from "@/i18n/context";
import {
  DEFAULT_USABLE_MBPS_1G,
  DEFAULT_USABLE_MBPS_5G,
  RGB_BPC_PRESETS,
  streamBandwidthMbps,
  totalBppRgbPacked,
  type RgbBitsPerChannel,
} from "@/lib/led-bandwidth";
import { useMemo, useState } from "react";

const ONE_PORT_CHECK_FPS = 60;

function parsePositiveInt(raw: string, fallback: number): number {
  const n = Number.parseInt(raw.replaceAll(/\s+/g, ""), 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

export function LedBandwidthTools() {
  const { t, locale } = useI18n();
  const nf0 = useMemo(
    () => new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 0 }),
    [locale],
  );
  const nf1 = useMemo(
    () => new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 1 }),
    [locale],
  );

  const [onePixelsStr, setOnePixelsStr] = useState("720000");
  const [oneBpc, setOneBpc] = useState<RgbBitsPerChannel>(8);
  const [oneLink, setOneLink] = useState<"1g" | "5g">("1g");

  const onePixels = parsePositiveInt(onePixelsStr, 0);
  const oneBpp = totalBppRgbPacked(oneBpc);
  const oneCapMbps = oneLink === "1g" ? DEFAULT_USABLE_MBPS_1G : DEFAULT_USABLE_MBPS_5G;
  const oneNeedMbps = streamBandwidthMbps(onePixels, ONE_PORT_CHECK_FPS, oneBpp);
  const onePortOk = oneNeedMbps <= oneCapMbps;

  return (
    <div className="space-y-4">
      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.disclaimerTitle")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{t("tools.disclaimerBody")}</p>
        <ul className="mt-2 list-inside list-disc text-sm text-zinc-600 dark:text-zinc-400">
          <li>{t("tools.disclaimerBullet1")}</li>
          <li>{t("tools.disclaimerBullet2")}</li>
          <li>{t("tools.disclaimerBullet3")}</li>
        </ul>
      </section>

      <section className="panel-surface rounded-xl p-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{t("tools.onePortTitle")}</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("tools.onePortSubtitle")}</p>

        <div className="mt-5 grid max-w-lg gap-6">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-800 dark:text-zinc-200">{t("tools.onePortLabelPixels")}</span>
            <input
              className="input w-full"
              inputMode="numeric"
              value={onePixelsStr}
              onChange={(e) => setOnePixelsStr(e.target.value)}
            />
          </label>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-zinc-800 dark:text-zinc-200">{t("tools.onePortLabelDepth")}</legend>
            <div className="flex flex-wrap gap-4">
              {RGB_BPC_PRESETS.map((bpc) => (
                <label key={bpc} className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="radio"
                    name="led-one-port-depth"
                    className="h-4 w-4 border-zinc-300 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900"
                    checked={oneBpc === bpc}
                    onChange={() => setOneBpc(bpc)}
                  />
                  <span className="tabular-nums">{bpc}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-zinc-800 dark:text-zinc-200">{t("tools.onePortLabelLink")}</legend>
            <div className="flex flex-wrap gap-4">
              <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="radio"
                  name="led-one-port-link"
                  className="h-4 w-4 border-zinc-300 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900"
                  checked={oneLink === "1g"}
                  onChange={() => setOneLink("1g")}
                />
                {t("tools.onePortLink1g")}
              </label>
              <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="radio"
                  name="led-one-port-link"
                  className="h-4 w-4 border-zinc-300 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900"
                  checked={oneLink === "5g"}
                  onChange={() => setOneLink("5g")}
                />
                {t("tools.onePortLink5g")}
              </label>
            </div>
          </fieldset>
        </div>

        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">{t("tools.onePortFpsNote")}</p>

        <div
          className={[
            "mt-6 rounded-xl border-2 px-4 py-5 text-center",
            onePortOk
              ? "border-emerald-300 bg-emerald-50/80 dark:border-emerald-800 dark:bg-emerald-950/40"
              : "border-red-300 bg-red-50/80 dark:border-red-900 dark:bg-red-950/40",
          ].join(" ")}
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-400">{t("tools.onePortResult")}</p>
          <p
            className={[
              "mt-2 text-3xl font-bold tracking-tight",
              onePortOk ? "text-emerald-800 dark:text-emerald-200" : "text-red-800 dark:text-red-200",
            ].join(" ")}
          >
            {onePortOk ? t("tools.onePortYay") : t("tools.onePortNay")}
          </p>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            {t("tools.onePortNeedLine", {
              need: nf1.format(oneNeedMbps),
              cap: nf0.format(oneCapMbps),
            })}
          </p>
        </div>
      </section>
    </div>
  );
}
