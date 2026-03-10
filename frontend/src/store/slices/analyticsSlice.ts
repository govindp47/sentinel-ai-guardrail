import type { StateCreator } from 'zustand'

export interface AnalyticsState {
  dateRangeStart: string | null
  dateRangeEnd: string | null
  summaryMetrics: unknown | null
  hallucinationRateData: unknown[] | null
  decisionDistribution: unknown[] | null
  topFailingClaims: unknown[] | null
  isLoading: boolean
  error: string | null
}

export interface AnalyticsActions {
  setDateRangeStart: (date: string | null) => void
  setDateRangeEnd: (date: string | null) => void
  setSummaryMetrics: (metrics: unknown | null) => void
  setHallucinationRateData: (data: unknown[] | null) => void
  setDecisionDistribution: (data: unknown[] | null) => void
  setTopFailingClaims: (claims: unknown[] | null) => void
  setIsLoading: (loading: boolean) => void
  setError: (error: string | null) => void
}

export type AnalyticsSlice = AnalyticsState & AnalyticsActions

const initialAnalyticsState: AnalyticsState = {
  dateRangeStart: null,
  dateRangeEnd: null,
  summaryMetrics: null,
  hallucinationRateData: null,
  decisionDistribution: null,
  topFailingClaims: null,
  isLoading: false,
  error: null,
}

export const createAnalyticsSlice: StateCreator<AnalyticsSlice> = (set) => ({
  ...initialAnalyticsState,
  setDateRangeStart: (date) => set({ dateRangeStart: date }),
  setDateRangeEnd: (date) => set({ dateRangeEnd: date }),
  setSummaryMetrics: (metrics) => set({ summaryMetrics: metrics }),
  setHallucinationRateData: (data) => set({ hallucinationRateData: data }),
  setDecisionDistribution: (data) => set({ decisionDistribution: data }),
  setTopFailingClaims: (claims) => set({ topFailingClaims: claims }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
})
