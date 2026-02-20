import React from 'react'
import { HelpCircle } from 'lucide-react'

interface SuggestedQuestionsProps {
  questions: string[]
  onQuestionClick: (question: string) => void
}

export default function SuggestedQuestions({ questions, onQuestionClick }: SuggestedQuestionsProps) {
  if (questions.length === 0) return null

  return (
    <div className="suggested-questions">
      <div className="suggested-questions-header">
        <HelpCircle size={16} />
        <span>Suggested questions:</span>
      </div>
      <div className="suggested-questions-list">
        {questions.map((question, index) => (
          <button
            key={index}
            className="suggested-question-btn"
            onClick={() => onQuestionClick(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}