export interface WorkloadProfile {
  product: string;
  users: string;
  requestsPerDay: number;
  latencySeconds: number;
  budgetMonthlyUsd: number;
  region: string;
  canSelfHost: boolean;
  privacy: "standard" | "sensitive" | "regulated";
  longContext: boolean;
  vision: boolean;
  toolCalling: boolean;
  structuredOutput: boolean;
  streaming: boolean;
  notes: string;
}

export interface RunRequest {
  profile: WorkloadProfile;
  prompts: string[];
}

export interface RecommendationReport {
  primary: {
    provider: string;
    model: string;
    hardware: string;
    deployment: string;
    estimatedLatencySeconds: number;
    estimatedMonthlyCostUsd: number;
    expectedQuality: string;
    confidence: number;
  };
  alternatives: Array<{
    label: string;
    provider: string;
    model: string;
    reason: string;
    monthlyCostUsd?: number;
    latencySeconds?: number;
  }>;
  routing: Array<{
    condition: string;
    target: string;
    reason: string;
  }>;
  architecture: string[];
  risks: string[];
  markdown: string;
}
