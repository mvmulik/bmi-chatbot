import { useCallback, useMemo, useRef, useState } from 'react'
import { ChatApiError, sendChatMessage } from '../api/chat'
import type { ChatMessage } from '../types/chat'

function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export const SUGGESTED_QUESTIONS = [
  'Where can I find BMI Hub safety guidance?',
  'What are the key steps in the onboarding process?',
  'How do I access project standards and templates?',
  'Who should I contact for BMI Hub support?',
] as const

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationId, setConversationId] = useState(() => createId())
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const canClear = messages.length > 0 || Boolean(error)

  const clearConversation = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setConversationId(createId())
    setIsLoading(false)
    setError(null)
  }, [])

  const sendMessage = useCallback(
    async (rawText: string) => {
      const text = rawText.trim()
      if (!text || isLoading) {
        return
      }

      setError(null)
      const userMessage: ChatMessage = {
        id: createId(),
        role: 'user',
        content: text,
        createdAt: new Date().toISOString(),
      }
      setMessages((current) => [...current, userMessage])
      setIsLoading(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const response = await sendChatMessage(
          {
            message: text,
            conversationId,
          },
          controller.signal,
        )

        const assistantMessage: ChatMessage = {
          id: createId(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources ?? [],
          createdAt: new Date().toISOString(),
        }
        setMessages((current) => [...current, assistantMessage])
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return
        }
        const message =
          err instanceof ChatApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : 'Something went wrong while contacting the assistant.'
        setError(message)
        setMessages((current) => [
          ...current,
          {
            id: createId(),
            role: 'assistant',
            content: `I could not complete that request. ${message}`,
            createdAt: new Date().toISOString(),
            error: true,
          },
        ])
      } finally {
        setIsLoading(false)
        abortRef.current = null
      }
    },
    [conversationId, isLoading],
  )

  return useMemo(
    () => ({
      messages,
      isLoading,
      error,
      canClear,
      sendMessage,
      clearConversation,
    }),
    [messages, isLoading, error, canClear, sendMessage, clearConversation],
  )
}
