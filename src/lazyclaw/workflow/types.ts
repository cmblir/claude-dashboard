export interface WorkflowNode<I = unknown, O = unknown> {
  id: string;
  type: string;
  execute(input: I): Promise<O>;
  cleanup?(): Promise<void> | void;
}

export interface NodeRunRecord {
  id: string;
  duration: number;
  output: unknown;
  status: 'success' | 'failed';
}

export interface RunResult {
  success: boolean;
  results: NodeRunRecord[];
  error?: Error;
  failedAt?: string;
  session: Record<string, unknown>;
}
