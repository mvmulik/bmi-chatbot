import { ChatHeader } from './components/ChatHeader'
import { ChatInput } from './components/ChatInput'
import { MessageList } from './components/MessageList'
import { SuggestedQuestions } from './components/SuggestedQuestions'
import { SUGGESTED_QUESTIONS, useChat } from './hooks/useChat'
import './App.css'

function App() {
  const { messages, isLoading, error, canClear, sendMessage, clearConversation } = useChat()
  const showSuggestions = messages.length === 0 && !isLoading

  return (
    <div className="app-shell">
      <div className="app-frame">
        <ChatHeader canClear={canClear} onClear={clearConversation} />

        <main className="chat-panel">
          {showSuggestions ? (
            <div className="empty-state">
              <p>
                Ask about processes, standards, and guidance published on BMI Hub. Responses include
                source links whenever available.
              </p>
              <SuggestedQuestions
                questions={SUGGESTED_QUESTIONS}
                disabled={isLoading}
                onSelect={(question) => void sendMessage(question)}
              />
            </div>
          ) : (
            <MessageList messages={messages} isLoading={isLoading} />
          )}
        </main>

        {error ? (
          <div className="error-banner" role="alert">
            {error}
          </div>
        ) : null}

        <ChatInput disabled={isLoading} onSend={(message) => void sendMessage(message)} />
      </div>
    </div>
  )
}

export default App
