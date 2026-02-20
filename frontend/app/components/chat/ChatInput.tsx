import React from 'react'
import { Send, Trash2 } from 'lucide-react'

interface ChatInputProps {
  input: string
  isLoading: boolean
  hasMessages: boolean
  onInputChange: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  onClear: () => void
  onExport: () => void
}

export default function ChatInput({
  input,
  isLoading,
  hasMessages,
  onInputChange,
  onSubmit,
  onClear,
  onExport
}: ChatInputProps) {
  return (
    <div className="input-section">
      <form onSubmit={onSubmit}>
        <div className="input-wrapper">
          <input
            type="text"
            className="chat-input"
            placeholder="Enter part number, model number, or symptom... (Ctrl+Enter to send)"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            disabled={isLoading}
          />
          <button
            type="button"
            className="btn-export"
            onClick={onExport}
            disabled={!hasMessages}
            title="Export chat"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
          <button
            type="button"
            className="btn-clear"
            onClick={onClear}
            disabled={!hasMessages}
            title="Clear chat"
          >
            <Trash2 size={18} />
          </button>
          <button
            type="submit"
            className="btn-send"
            disabled={isLoading || !input.trim()}
          >
            <Send size={18} />
            Send
          </button>
        </div>
      </form>
      <p className="disclaimer">
        Use exact model numbers for the most accurate compatibility results.
      </p>
    </div>
  )
}
