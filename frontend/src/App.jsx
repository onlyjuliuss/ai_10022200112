import { useState } from 'react'

const exampleQuestions = [
  {
    label: '🗳️ Election Results',
    text: 'Who won the 2020 presidential election in Ghana?'
  },
  {
    label: '📊 Voter Turnout',
    text: 'What is the voter turnout trend over the years?'
  },
  {
    label: '💰 Budget Revenue',
    text: 'What are the main revenue sources in the 2025 budget?'
  },
  {
    label: '🏛️ Political Parties',
    text: 'How have the major political parties performed in recent elections?'
  },
  {
    label: '📈 Budget Spending',
    text: 'What is the projected expenditure for 2025?'
  },
  {
    label: '🌍 Regional Results',
    text: 'What were the election results by region in 2020?'
  }
]

function App() {
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const sendQuery = async (text) => {
    if (!text || !text.trim()) return

    const nextMessages = [
      ...messages,
      { role: 'user', text: text.trim() }
    ]
    setMessages(nextMessages)
    setQuery('')
    setLoading(true)
    setError('')

    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text.trim() })
      })

      if (!response.ok) {
        const body = await response.json()
        throw new Error(body.detail || 'Server error')
      }

      const data = await response.json()
      setMessages((prev) => [...prev, { role: 'assistant', text: data.response }])
    } catch (err) {
      setError(err.message || 'Unable to query backend')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    sendQuery(query)
  }

  const clearConversation = () => {
    setMessages([])
    setError('')
  }

  return (
    <div className="app-layout">
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <h2>Menu</h2>
          <button 
            className="toggle-btn"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          >
            {sidebarOpen ? '✕' : '☰'}
          </button>
        </div>

        <button className="new-conversation-btn" onClick={clearConversation}>
          ➕ New Conversation
        </button>

        <div className="sidebar-section">
          <h3>Try These Questions</h3>
          <div className="example-questions">
            {exampleQuestions.map((item) => (
              <button
                key={item.label}
                className="example-btn"
                onClick={() => sendQuery(item.text)}
                disabled={loading}
                title={item.text}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          <p>💡 Powered by RAG • Ghana Data</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button 
            className="menu-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            ☰
          </button>
          <div className="topbar-content">
            <h1>intelli-J</h1>
            <p>Your AI companion for Ghana's election & budget insights</p>
          </div>
        </header>

        <div className="chat-container">
          <div className="chat-window">
            {messages.length === 0 ? (
              <div className="empty-state">
                <p>👋 Ask me anything about Ghana's elections or 2025 budget!</p>
              </div>
            ) : (
              messages.map((message, index) => (
                <div
                  key={index}
                  className={`message ${message.role === 'user' ? 'message-user' : 'message-bot'}`}
                >
                  <span className="message-role">
                    {message.role === 'user' ? 'You' : 'intelli-J'}
                  </span>
                  <p>{message.text}</p>
                </div>
              ))
            )}
          </div>

          {error && <div className="status error">⚠️ {error}</div>}
          {loading && <div className="status loading">🤔 intelli-J is thinking...</div>}

          <form className="chat-form" onSubmit={handleSubmit}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about elections, budgets, or policy..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !query.trim()}>
              Send
            </button>
          </form>
        </div>
      </main>
    </div>
  )
}

export default App
