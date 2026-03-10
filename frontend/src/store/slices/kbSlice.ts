import type { StateCreator } from 'zustand'

export interface KbState {
  documents: unknown[] | null
  uploadProgress: number | null
  uploadError: string | null
  isUploading: boolean
  isLoading: boolean
  error: string | null
}

export interface KbActions {
  setDocuments: (documents: unknown[] | null) => void
  setUploadProgress: (progress: number | null) => void
  setUploadError: (error: string | null) => void
  setIsUploading: (uploading: boolean) => void
  setIsLoading: (loading: boolean) => void
  setError: (error: string | null) => void
}

export type KbSlice = KbState & KbActions

const initialKbState: KbState = {
  documents: null,
  uploadProgress: null,
  uploadError: null,
  isUploading: false,
  isLoading: false,
  error: null,
}

export const createKbSlice: StateCreator<KbSlice, [], [], KbSlice> = (set) => ({
  ...initialKbState,
  setDocuments: (documents) => set({ documents }),
  setUploadProgress: (progress) => set({ uploadProgress: progress }),
  setUploadError: (error) => set({ uploadError: error }),
  setIsUploading: (uploading) => set({ isUploading: uploading }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
})
