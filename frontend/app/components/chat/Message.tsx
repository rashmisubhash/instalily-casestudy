'use client'

import React from 'react'
import ReactMarkdown from 'react-markdown'
import ProductCard from './ProductCard'
import { CheckCircle, AlertCircle, Info, HelpCircle } from 'lucide-react'

interface MessageProps {
  role: 'user' | 'assistant'
  content?: string
  payload?: any
  confidence?: number
  timestamp: Date
  onQuickAction?: (text: string) => void
}

function getConfidenceLabel(confidence?: number) {
  if (!confidence) return null
  if (confidence >= 0.8) {
    return { label: "High Confidence", className: "confidence-high", icon: CheckCircle }
  }
  if (confidence >= 0.6) {
    return { label: "Likely Solution", className: "confidence-medium", icon: Info }
  }
  if (confidence >= 0.4) {
    return { label: "Possible Solution", className: "confidence-low", icon: AlertCircle }
  }
  return { label: "Needs Clarification", className: "confidence-uncertain", icon: HelpCircle }
}

function isErrorCopy(text?: string) {
  if (!text) return false
  const lower = text.toLowerCase()
  return (
    lower.includes("something went wrong") ||
    lower.includes("cannot connect") ||
    lower.includes("request timed out")
  )
}

function buildNextActions(payload: any, content?: string): string[] {
  if (payload?.type === "compatibility") {
    return [
      "Show 3 model-compatible alternatives",
      "Help me locate my exact model number"
    ]
  }
  if (payload?.type === "symptom_solution") {
    return [
      "Walk me through diagnostic checks step by step",
      "Show install steps for the top suggested part"
    ]
  }
  if (payload?.type === "part_lookup") {
    return [
      "Check this part against my model number",
      "Show related replacement options"
    ]
  }
  if (isErrorCopy(content)) {
    return [
      "Try that request again",
      "Start with model number lookup"
    ]
  }
  return []
}

function normalizeMarkdown(text?: string): string {
  if (!text) return ""
  // Preserve line breaks from backend plain-text responses in markdown renderer.
  return text.replace(/\n/g, "  \n")
}

export default function Message({ role, content, payload, confidence, onQuickAction }: MessageProps) {
  if (role === 'user') {
    return (
      <div className="message user">
        <div className="message-content">
          {content}
        </div>
      </div>
    )
  }

  const confidenceInfo = getConfidenceLabel(confidence)
  const ConfidenceIcon = confidenceInfo?.icon
  const nextActions = buildNextActions(payload, content)

  return (
    <div className="message assistant message-enter">
      <div className="message-wrapper">
        {confidenceInfo && (
          <div className={`confidence-badge ${confidenceInfo.className}`}>
            {ConfidenceIcon && <ConfidenceIcon size={14} />}
            <span>{confidenceInfo.label}</span>
          </div>
        )}

        {payload?.model_id && (
          <div className="model-tag">
            Model detected: {payload.model_id}
          </div>
        )}

        {content && (
          <div className="message-content">
            <h4 className="response-section-title">Answer</h4>
            <ReactMarkdown>{normalizeMarkdown(content)}</ReactMarkdown>
          </div>
        )}

        {payload?.diagnostic_steps?.length > 0 && (
          <div className="steps-section">
            <h4>Installation / Troubleshooting Steps</h4>
            <ol>
              {payload.diagnostic_steps.map((step: string, idx: number) => (
                <li key={idx}>{step}</li>
              ))}
            </ol>
          </div>
        )}

        {payload?.recommended_parts?.length > 0 && (
          <div className="response-block">
            <h4 className="response-section-title">Recommended Parts</h4>
            {payload.recommended_parts.map((part: any, idx: number) => (
              <div
                key={idx}
                className="product-card-enter"
                style={{ animationDelay: `${idx * 60}ms` }}
              >
                <ProductCard
                  partNumber={part.part_id}
                  name={part.title}
                  price={part.price && part.price !== "N/A" ? parseFloat(part.price.replace('$', '')) : undefined}
                  url={part.url}
                  inStock={true}
                  compatible={payload?.compatible}
                />
              </div>
            ))}
          </div>
        )}

        {payload?.alternative_parts?.length > 0 && (
          <div className="response-block">
            <h4 className="response-section-title">Likely Alternatives</h4>
            {payload.alternative_parts.map((part: any, idx: number) => (
              <div
                key={idx}
                className="product-card-enter"
                style={{ animationDelay: `${idx * 60}ms` }}
              >
                <ProductCard
                  partNumber={part.part_id}
                  name={part.title}
                  price={part.price && part.price !== "N/A" ? parseFloat(part.price.replace('$', '')) : undefined}
                  url={part.url}
                  inStock={true}
                  compatible={payload?.compatible}
                />
              </div>
            ))}
          </div>
        )}

        {payload?.part && (
          <div className="response-block">
            <h4 className="response-section-title">Part Details</h4>
            <div className="product-card-enter">
              <ProductCard
                partNumber={payload.part.part_id}
                name={payload.part.title}
                price={payload.part.price && payload.part.price !== "N/A"
                  ? parseFloat(payload.part.price.replace('$', ''))
                  : undefined}
                url={payload.part.url}
                inStock={true}
                compatible={payload?.compatible}
              />
            </div>
          </div>
        )}

        {payload?.helpful_tips?.length > 0 && (
          <div className="helpful-tips">
            <h4>Helpful Tips</h4>
            <ul>
              {payload.helpful_tips.map((tip: string, idx: number) => (
                <li key={idx}>{tip}</li>
              ))}
            </ul>
          </div>
        )}

        {nextActions.length > 0 && onQuickAction && (
          <div className="message-next-actions">
            <h4 className="response-section-title">Next Actions</h4>
            <div className="message-action-grid">
              {nextActions.map((action) => (
                <button
                  key={action}
                  type="button"
                  className="message-action-btn"
                  onClick={() => onQuickAction(action)}
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
