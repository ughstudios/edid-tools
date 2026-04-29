"use client";

import { HdmiDpCompatibilityTools } from "@/components/hdmi-dp-compatibility-tools";
import { EdidCompatibilityTools } from "@/components/edid-compatibility-tools";
import { LedBandwidthTools } from "@/components/led-bandwidth-tools";
import { ProjectPlannerTools } from "@/components/project-planner-tools";
import { useI18n } from "@/i18n/context";
import { TOOLS_PAGE_TAB_IDS, type ToolsPageTabId } from "@/lib/tools-page-tabs";
import { useId, useState } from "react";

const DISABLED_TOOL_TAB_IDS = new Set<ToolsPageTabId>(["edid-check"]);

function tabLabelKey(id: ToolsPageTabId): string {
  return `tools.tabs.${id}`;
}

function disabledTabTooltipKey(id: ToolsPageTabId): string {
  return `tools.disabledTabs.${id}`;
}

function renderToolPanel(id: ToolsPageTabId) {
  switch (id) {
    case "led-bandwidth":
      return <LedBandwidthTools />;
    case "display-io":
      return <HdmiDpCompatibilityTools />;
    case "edid-check":
      return <EdidCompatibilityTools />;
    case "project-planner":
      return <ProjectPlannerTools />;
    default:
      return null;
  }
}

export function ToolsPageTabs() {
  const { t } = useI18n();
  const baseId = useId();
  const [active, setActive] = useState<ToolsPageTabId>(TOOLS_PAGE_TAB_IDS[0]);
  const showTabBar = TOOLS_PAGE_TAB_IDS.length > 1;

  if (!showTabBar) {
    const only = TOOLS_PAGE_TAB_IDS[0];
    return <div className="min-w-0">{renderToolPanel(only)}</div>;
  }

  return (
    <div className="panel-surface min-w-0 overflow-hidden rounded-xl">
      <div
        role="tablist"
        aria-label={t("tools.pageTabListAria")}
        className="flex flex-wrap gap-1 rounded-t-xl bg-zinc-100/90 p-1.5 dark:bg-zinc-950/60 sm:p-2"
      >
        {TOOLS_PAGE_TAB_IDS.map((id) => {
          const selected = active === id;
          const disabled = DISABLED_TOOL_TAB_IDS.has(id);
          const panelId = `${baseId}-panel-${id}`;
          const tabId = `${baseId}-tab-${id}`;
          return (
            <span
              key={id}
              className="group relative flex-1 sm:flex-none"
              title={disabled ? t(disabledTabTooltipKey(id)) : undefined}
            >
              <button
                id={tabId}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={panelId}
                aria-describedby={disabled ? `${tabId}-tooltip` : undefined}
                aria-disabled={disabled || undefined}
                disabled={disabled}
                tabIndex={selected && !disabled ? 0 : -1}
                onClick={() => {
                  if (!disabled) setActive(id);
                }}
                className={[
                  "min-h-10 w-full rounded-lg px-3 py-2 text-center text-sm font-medium transition-colors sm:w-auto sm:px-4",
                  disabled
                    ? "cursor-not-allowed border border-amber-300/70 bg-amber-50 text-amber-700 opacity-80 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-300"
                    : selected
                      ? "bg-zinc-900 text-white shadow-sm dark:bg-zinc-100 dark:text-zinc-900"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800",
                ].join(" ")}
              >
                {t(tabLabelKey(id))}
              </button>
              {disabled ? (
                <span
                  id={`${tabId}-tooltip`}
                  role="tooltip"
                  className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 hidden w-max max-w-56 -translate-x-1/2 rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white shadow-lg group-hover:block dark:bg-zinc-100 dark:text-zinc-900"
                >
                  {t(disabledTabTooltipKey(id))}
                </span>
              ) : null}
            </span>
          );
        })}
      </div>
      <div className="border-t border-zinc-200/80 p-4 dark:border-zinc-700/80 sm:p-5">
        {TOOLS_PAGE_TAB_IDS.map((id) => {
          const panelId = `${baseId}-panel-${id}`;
          const tabId = `${baseId}-tab-${id}`;
          const isActive = active === id;
          return (
            <div
              key={id}
              id={panelId}
              role="tabpanel"
              aria-labelledby={tabId}
              hidden={!isActive}
            >
              {isActive ? renderToolPanel(id) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
