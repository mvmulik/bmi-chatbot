import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../types/chat'
import { MessageItem } from './MessageItem'

type MessageListProps = {
  messages: ChatMessage[]
  isLoading: boolean
}

export function MessageList({ messages, isLoading }: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isLoading])

  return (
    <div className="message-list" role="log" aria-live="polite">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      {isLoading ? (
        <div className="loading-row" aria-label="Assistant is thinking">
          <span className="loading-dot" />
          <span className="loading-dot" />
          <span className="loading-dot" />
          <span>Searching BMI Hub…</span>
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  )
}
