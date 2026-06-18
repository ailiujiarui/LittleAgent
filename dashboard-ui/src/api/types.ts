export interface DashboardStatus {
  workspace: string;
  running: boolean;
  mcp?: {
    connected?: Record<string, string[]>;
    failed?: Record<string, string>;
  };
}

export interface MemoryFilesResponse {
  files: string[];
}

export interface MemoryFileResponse {
  name: string;
  content: string;
}

export interface SaveMemoryResponse {
  saved: boolean;
  backup: string;
}

export interface SessionSummary {
  id: string;
  channel: string;
  chat_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SessionsResponse {
  sessions: SessionSummary[];
}

export interface RuntimeEventRecord {
  kind: "runtime";
  id: number;
  event_type: string;
  payload: unknown;
  created_at: string;
}

export interface ToolEventRecord {
  kind: "tool";
  id: number;
  session_id: string;
  tool_name: string;
  arguments: unknown;
  result: unknown;
  created_at: string;
}

export type EventRecord = RuntimeEventRecord | ToolEventRecord;

export interface EventsResponse {
  events: EventRecord[];
}

export interface ProactiveItem {
  id: number;
  source: string;
  item_key: string;
  title: string;
  url: string;
  judged_at: string;
  pushed_at: string | null;
}

export interface ProactiveResponse {
  items: ProactiveItem[];
}

export interface DriftRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  summary: string;
}

export interface DriftResponse {
  runs: DriftRun[];
}

export interface PluginRecord {
  id: string;
  source: string;
  name: string;
  enabled: boolean;
  loaded: boolean;
  locked: boolean;
  tool_count: number;
  event_count: number;
  last_error: string;
  updated_at: string;
  requires_restart: boolean;
}

export interface PluginListResponse {
  mode: "runtime" | "standalone";
  plugins: PluginRecord[];
}

export interface PluginActionResponse {
  ok: boolean;
  plugin: PluginRecord;
  requires_restart: boolean;
  message: string;
}
