import type { ChatRequestPayload, ChatResponsePayload } from '../types/chat'

const DEFAULT_BASE_URL = ''

export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined
  return (raw ?? DEFAULT_BASE_URL).replace(/\/$/, '')
}

export class ChatApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ChatApiError'
    this.status = status
  }
}

export async function sendChatMessage(
  payload: ChatRequestPayload,
  signal?: AbortSignal,
): Promise<ChatResponsePayload> {
  const response = await fetch(`${getApiBaseUrl()}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const data = (await response.json()) as { detail?: string }
      if (typeof data.detail === 'string' && data.detail.trim()) {
        detail = data.detail
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new ChatApiError(detail, response.status)
  }

  return (await response.json()) as ChatResponsePayload
}
