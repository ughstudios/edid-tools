/**
 * In-app Tools page sections. Add an id here, a `tools.tabs.<id>` string,
 * and a branch in `ToolsPageTabs` to register a new tool.
 */
export const TOOLS_PAGE_TAB_IDS = ["led-bandwidth", "display-io", "edid-check", "project-planner"] as const;
export type ToolsPageTabId = (typeof TOOLS_PAGE_TAB_IDS)[number];
