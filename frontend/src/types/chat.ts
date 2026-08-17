export type ChatSource = {
  title: string
  url: string
  section: string
  relevance: number
}

export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  sources?: ChatSource[]
  createdAt: string
  error?: boolean
}

export type ChatRequestPayload = {
  message: string
  conversationId?: string
}

export type ChatResponsePayload = {
  answer: string
  sources: ChatSource[]
}
