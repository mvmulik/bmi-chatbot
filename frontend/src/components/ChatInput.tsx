import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

type ChatInputProps = {
  disabled?: boolean
  onSend: (message: string) => void
}

export function ChatInput({ disabled = false, onSend }: ChatInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const node = textareaRef.current
    if (!node) {
      return
    }
    node.style.height = '0px'
    node.style.height = `${Math.min(node.scrollHeight, 160)}px`
  }, [value])

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) {
      return
    }
    onSend(trimmed)
    setValue('')
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="chat-input">
        Message
      </label>
      <textarea
        id="chat-input"
        ref={textareaRef}
        value={value}
        disabled={disabled}
        rows={1}
        placeholder="Ask a question about BMI Hub…"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="submit" className="send-button" disabled={disabled || !value.trim()}>
        Send
      </button>
      <p className="composer-hint">Enter to send · Shift+Enter for a new line</p>
    </form>
  )
}
