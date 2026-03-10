import type { StateCreator } from 'zustand'

export interface PolicyState {
  acceptThreshold: number | null
  warnThreshold: number | null
  fallbackStrategyOrder: string[] | null
  isSaving: boolean
  isDirty: boolean
  savedAt: string | null
  error: string | null
}

export interface PolicyActions {
  setAcceptThreshold: (threshold: number | null) => void
  setWarnThreshold: (threshold: number | null) => void
  setFallbackStrategyOrder: (order: string[] | null) => void
  setIsSaving: (saving: boolean) => void
  setIsDirty: (dirty: boolean) => void
  setSavedAt: (timestamp: string | null) => void
  setError: (error: string | null) => void
}

export type PolicySlice = PolicyState & PolicyActions

const initialPolicyState: PolicyState = {
  acceptThreshold: null,
  warnThreshold: null,
  fallbackStrategyOrder: null,
  isSaving: false,
  isDirty: false,
  savedAt: null,
  error: null,
}

export const createPolicySlice: StateCreator<PolicySlice, [], [], PolicySlice> = (set) => ({
  ...initialPolicyState,
  setAcceptThreshold: (threshold) => set({ acceptThreshold: threshold }),
  setWarnThreshold: (threshold) => set({ warnThreshold: threshold }),
  setFallbackStrategyOrder: (order) => set({ fallbackStrategyOrder: order }),
  setIsSaving: (saving) => set({ isSaving: saving }),
  setIsDirty: (dirty) => set({ isDirty: dirty }),
  setSavedAt: (timestamp) => set({ savedAt: timestamp }),
  setError: (error) => set({ error }),
})
