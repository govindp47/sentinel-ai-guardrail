import axios, { type AxiosError } from 'axios'

export interface ApiError {
  status: number
  code: string
  message: string
  requestId: string | null
}

function getSessionId(): string {
  const key = 'sentinel_session_id'
  let id = sessionStorage.getItem(key)
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem(key, id)
  }
  return id
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor — inject X-Session-ID
apiClient.interceptors.request.use((config) => {
  config.headers['X-Session-ID'] = getSessionId()
  return config
})

// Response interceptor — map HTTP errors to typed ApiError
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; code?: string }>) => {
    const apiError: ApiError = {
      status: error.response?.status ?? 0,
      code: error.response?.data?.code ?? 'UNKNOWN_ERROR',
      message:
        error.response?.data?.detail ??
        error.message ??
        'An unexpected error occurred',
      requestId: (error.response?.headers?.['x-request-id'] as string) ?? null,
    }
    return Promise.reject(apiError)
  },
)
