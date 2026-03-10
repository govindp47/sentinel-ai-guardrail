import type { StateCreator } from 'zustand'

export interface RequestsState {
  requests: unknown[] | null
  selectedRequestId: string | null
  selectedRequestDetail: unknown | null
  searchQuery: string | null
  filterDecision: string | null
  filterDateStart: string | null
  filterDateEnd: string | null
  currentPage: number
  totalPages: number | null
  isLoading: boolean
  isDetailLoading: boolean
  error: string | null
}

export interface RequestsActions {
  setRequests: (requests: unknown[] | null) => void
  setSelectedRequestId: (id: string | null) => void
  setSelectedRequestDetail: (detail: unknown | null) => void
  setSearchQuery: (query: string | null) => void
  setFilterDecision: (decision: string | null) => void
  setFilterDateStart: (date: string | null) => void
  setFilterDateEnd: (date: string | null) => void
  setCurrentPage: (page: number) => void
  setTotalPages: (total: number | null) => void
  setIsLoading: (loading: boolean) => void
  setIsDetailLoading: (loading: boolean) => void
  setError: (error: string | null) => void
}

export type RequestsSlice = RequestsState & RequestsActions

const initialRequestsState: RequestsState = {
  requests: null,
  selectedRequestId: null,
  selectedRequestDetail: null,
  searchQuery: null,
  filterDecision: null,
  filterDateStart: null,
  filterDateEnd: null,
  currentPage: 1,
  totalPages: null,
  isLoading: false,
  isDetailLoading: false,
  error: null,
}

export const createRequestsSlice: StateCreator<RequestsSlice> = (set) => ({
  ...initialRequestsState,
  setRequests: (requests) => set({ requests }),
  setSelectedRequestId: (id) => set({ selectedRequestId: id }),
  setSelectedRequestDetail: (detail) => set({ selectedRequestDetail: detail }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setFilterDecision: (decision) => set({ filterDecision: decision }),
  setFilterDateStart: (date) => set({ filterDateStart: date }),
  setFilterDateEnd: (date) => set({ filterDateEnd: date }),
  setCurrentPage: (page) => set({ currentPage: page }),
  setTotalPages: (total) => set({ totalPages: total }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  setIsDetailLoading: (loading) => set({ isDetailLoading: loading }),
  setError: (error) => set({ error }),
})
