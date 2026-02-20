import React, { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'

interface MessageFeedbackProps {
  messageId: string
}

export default function MessageFeedback({ messageId }: MessageFeedbackProps) {
  const [feedback, setFeedback] = useState<'like' | 'dislike' | null>(null)

  const handleFeedback = (type: 'like' | 'dislike') => {
    setFeedback(type)
    // Here you would send feedback to your backend
    console.log(`Feedback for message ${messageId}:`, type)
  }

  return (
    <div className="message-feedback">
      <span className="feedback-label">Was this helpful?</span>
      <button
        className={`feedback-btn ${feedback === 'like' ? 'active' : ''}`}
        onClick={() => handleFeedback('like')}
        disabled={feedback !== null}
      >
        <ThumbsUp size={14} />
      </button>
      <button
        className={`feedback-btn ${feedback === 'dislike' ? 'active' : ''}`}
        onClick={() => handleFeedback('dislike')}
        disabled={feedback !== null}
      >
        <ThumbsDown size={14} />
      </button>
      {feedback && (
        <span className="feedback-thanks">Thanks for your feedback!</span>
      )}
    </div>
  )
}