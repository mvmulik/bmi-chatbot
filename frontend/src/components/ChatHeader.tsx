type ChatHeaderProps = {
  canClear: boolean
  onClear: () => void
}

export function ChatHeader({ canClear, onClear }: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div>
        <p className="brand">BMI Hub Assistant</p>
        <h1>Internal knowledge assistant</h1>
        <p className="subtitle">
          Answers are grounded in indexed BMI Hub content. Verify critical decisions with the
          source pages.
        </p>
      </div>
      <button type="button" className="ghost-button" disabled={!canClear} onClick={onClear}>
        Clear conversation
      </button>
    </header>
  )
}
