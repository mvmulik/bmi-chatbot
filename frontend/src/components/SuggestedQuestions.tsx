type SuggestedQuestionsProps = {
  questions: readonly string[]
  disabled?: boolean
  onSelect: (question: string) => void
}

export function SuggestedQuestions({
  questions,
  disabled = false,
  onSelect,
}: SuggestedQuestionsProps) {
  return (
    <section className="suggestions" aria-label="Suggested questions">
      <h2>Try asking</h2>
      <div className="suggestion-list">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            className="suggestion-button"
            disabled={disabled}
            onClick={() => onSelect(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </section>
  )
}
