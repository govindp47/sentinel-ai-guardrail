export type WebSocketMessageHandler = (event: MessageEvent) => void

export interface IWebSocketClient {
  connect: (requestId: string) => void
  disconnect: () => void
  onMessage: (handler: WebSocketMessageHandler) => void
}

/**
 * WebSocketClient stub.
 * Real implementation added in T-023 (usePipelineProgress hook).
 */
export class WebSocketClient implements IWebSocketClient {
  private socket: WebSocket | null = null
  private messageHandler: WebSocketMessageHandler | null = null
  private readonly wsBaseUrl: string

  constructor() {
    this.wsBaseUrl =
      import.meta.env.VITE_WS_URL ??
      (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(
        /^http/,
        'ws',
      )
  }

  connect(_requestId: string): void {
    // Stub — no-op until T-023
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.close()
      this.socket = null
    }
  }

  onMessage(handler: WebSocketMessageHandler): void {
    this.messageHandler = handler
  }

  /** @internal used by real implementation */
  protected getWsBaseUrl(): string {
    return this.wsBaseUrl
  }

  /** @internal used by real implementation */
  protected getMessageHandler(): WebSocketMessageHandler | null {
    return this.messageHandler
  }
}

export const wsClient = new WebSocketClient()
