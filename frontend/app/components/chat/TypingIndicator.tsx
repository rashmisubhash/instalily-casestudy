import React, { useState, useEffect } from 'react'

export default function TypingIndicator() {
  const [dots, setDots] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setDots((prev) => (prev + 1) % 4)
    }, 500)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="message assistant">
      <div className="typing-indicator">
        <div className="typing-dots">
          <div className="typing-dot"></div>
          <div className="typing-dot"></div>
          <div className="typing-dot"></div>
        </div>
        <span className="typing-text">
          Thinking{'.'.repeat(dots + 1)}
        </span>
      </div>
    </div>
  )
}