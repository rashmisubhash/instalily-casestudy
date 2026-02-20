import React from 'react'
import QuickActions from './QuickActions'

interface WelcomeScreenProps {
  onExampleClick: (question: string) => void
}

const EXAMPLE_QUESTIONS = [
  'How can I install part number PS11752778?',
  'Is this part compatible with my WDT780SAEM1 model?',
  'The ice maker on my Whirlpool fridge is not working. How can I fix it?',
  'What are common causes of refrigerator water leaks?',
  'How do I replace a door shelf bin on my Frigidaire refrigerator?'
]

export default function WelcomeScreen({ onExampleClick }: WelcomeScreenProps) {
  return (
    <div className="welcome-section">
      <h2 className="welcome-title">
        Welcome to PartSelect Customer Support!
      </h2>
      <p className="welcome-description">
        I'm your AI assistant, here to help you find the right parts
        for your appliances and guide you through repairs. Ask me
        anything about refrigerator or dishwasher parts, installation
        instructions, or troubleshooting tips.
      </p>

      <QuickActions onActionClick={onExampleClick} />

      <div className="example-questions">
        <h3>Or try these example questions:</h3>
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