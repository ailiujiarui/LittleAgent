export interface DashboardStatus {
  workspace: string;
  running: boolean;
  mcp?: {
    connected?: Record<string, string[]>;
    failed?: Record<string, string>;
  };
}
