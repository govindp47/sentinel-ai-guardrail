import type { StateCreator } from 'zustand'

export interface PlaygroundState {
  // Input fields
  prompt: string | null
  selectedModel: string | null
  apiKey: string | null
  selectedKbId: string | null
  guardrailsEnabled: boolean

  // Pipeline result
  requestId: string | null
  isSubmitting: boolean
  pipelineStage: string | null
  finalResponse: string | null
  confidenceScore: number | null
  confidenceLabel: 'high' | 'medium' | 'low' | null
  decision: 'accept' | 'warn' | 'block' | 'retry' | null
  blockReason: string | null
  claimsResult: unknown | null
  traceStages: unknown[] | null
  selectedClaimIndex: number | null
  error: string | null
}

export interface PlaygroundActions {
  setPrompt: (prompt: string) => void
  setSelectedModel: (model: string) => void
  setApiKey: (key: string) => void
  setSelectedKbId: (id: string | null) => void
  setGuardrailsEnabled: (enabled: boolean) => void
  setIsSubmitting: (submitting: boolean) => void
  setPipelineStage: (stage: string | null) => void
  setFinalResponse: (response: string | null) => void
  setConfidenceScore: (score: number | null) => void
  setConfidenceLabel: (label: 'high' | 'medium' | 'low' | null) => void
  setDecision: (decision: 'accept' | 'warn' | 'block' | 'retry' | null) => void
  setBlockReason: (reason: string | null) => void
  setClaimsResult: (claims: unknown | null) => void
  setTraceStages: (stages: unknown[] | null) => void
  setSelectedClaimIndex: (index: number | null) => void
  setError: (error: string | null) => void
  resetResult: () => void
}

export type PlaygroundSlice = PlaygroundState & PlaygroundActions

const initialPlaygroundState: PlaygroundState = {
  prompt: null,
  selectedModel: null,
  apiKey: null,
  selectedKbId: null,
  guardrailsEnabled: true,
  requestId: null,
  isSubmitting: false,
  pipelineStage: null,
  finalResponse: null,
  confidenceScore: null,
  confidenceLabel: null,
  decision: null,
  blockReason: null,
  claimsResult: null,
  traceStages: null,
  selectedClaimIndex: null,
  error: null,
}

export const createPlaygroundSlice: StateCreator<PlaygroundSlice> = (set) => ({
  ...initialPlaygroundState,
  setPrompt: (prompt) => set({ prompt }),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setApiKey: (key) => set({ apiKey: key }),
  setSelectedKbId: (id) => set({ selectedKbId: id }),
  setGuardrailsEnabled: (enabled) => set({ guardrailsEnabled: enabled }),
  setIsSubmitting: (submitting) => set({ isSubmitting: submitting }),
  setPipelineStage: (stage) => set({ pipelineStage: stage }),
  setFinalResponse: (response) => set({ finalResponse: response }),
  setConfidenceScore: (score) => set({ confidenceScore: score }),
  setConfidenceLabel: (label) => set({ confidenceLabel: label }),
  setDecision: (decision) => set({ decision }),
  setBlockReason: (reason) => set({ blockReason: reason }),
  setClaimsResult: (claims) => set({ claimsResult: claims }),
  setTraceStages: (stages) => set({ traceStages: stages }),
  setSelectedClaimIndex: (index) => set({ selectedClaimIndex: index }),
  setError: (error) => set({ error }),
  resetResult: () =>
    set({
      requestId: null,
      isSubmitting: false,
      pipelineStage: null,
      finalResponse: null,
      confidenceScore: null,
      confidenceLabel: null,
      decision: null,
      blockReason: null,
      claimsResult: null,
      traceStages: null,
      selectedClaimIndex: null,
      error: null,
    }),
})
