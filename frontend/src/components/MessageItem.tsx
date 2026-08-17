import { useState } from 'react'
import type { ChatMessage } from '../types/chat'
import { SourcesList } from './SourcesList'

type MessageItemProps = {
  message: ChatMessage
}

export function MessageItem({ message }: MessageItemProps) {
  const [copied, setCopied] = useState(false)
  const isAssistant = message.role === 'assistant'

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <article
      className={`message message-${message.role}${message.error ? ' message-error' : ''}`}
      aria-label={`${message.role} message`}
    >
      <div className="message-meta">
        <span className="message-role">{isAssistant ? 'Assistant' : 'You'}</span>
        {isAssistant ? (
          <button type="button" className="ghost-button" onClick={() => void handleCopy()}>
            {copied ? 'Copied' : 'Copy answer'}
          </button>
        ) : null}
      </div>
      <div className="message-body">{message.content}</div>
      {isAssistant && message.sources ? <SourcesList sources={message.sources} /> : null}
    </article>
  )
}
