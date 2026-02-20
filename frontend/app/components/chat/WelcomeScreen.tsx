import React from 'react'
import QuickActions from './QuickActions'

interface WelcomeScreenProps {
  onExampleClick: (question: string) => void
}

const EXAMPLE_QUESTIONS = [
  'How can I install part number PS11752778?',
  'Is this part compatible with my WDT780SAEM1 model?',
  'The ice maker on my Whirlpool fridge is not working. How can I fix it?',
  'My dishwasher is not draining. Which parts should I check first?',
  'How do I replace a refrigerator door shelf bin?'
]

export default function WelcomeScreen({ onExampleClick }: WelcomeScreenProps) {
  return (
    <div className="welcome-section">
      <h2 className="welcome-title">
        PartSelect Parts Assistant
      </h2>
      <p className="welcome-description">
        I can help you identify refrigerator and dishwasher parts, verify compatibility,
        and walk through repair steps. Share a part number, model number, or symptom to begin.
      </p>

      <QuickActions onActionClick={onExampleClick} />

      <div className="example-questions">
        <h3>Try one of these:</h3>
        <ul>
          {EXAMPLE_QUESTIONS.map((question, index) => (
            <li
              key={index}
              onClick={() => onExampleClick(question)}
            >
              • {question}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
