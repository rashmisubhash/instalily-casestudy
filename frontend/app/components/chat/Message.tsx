'use client'

import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import ProductCard from './ProductCard'

interface MessageProps {
  role: 'user' | 'assistant'
  content?: string
  payload?: any
  confidence?: number
  timestamp: Date
}

function getConfidenceLabel(confidence?: number) {
  if (!confidence) return null
  if (confidence >= 0.8) return { label: "High confidence", color: "green" }
  if (confidence >= 0.6) return { label: "Likely solution", color: "blue" }
  if (confidence >= 0.4) return { label: "Possible solution", color: "orange" }
  return { label: "Needs clarification", color: "gray" }
}

export default function Message({ role, content, payload, confidence }: MessageProps) {

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

  return (
    <div className="message assistant">
      <div className="message-wrapper">

        {/* Confidence Label */}
        {confidenceInfo && (
          <div className={`confidence-badge ${confidenceInfo.color}`}>
            {confidenceInfo.label}
          </div>
        )}

        {/* Model Detected Tag */}
        {payload?.model_id && (
          <div className="model-tag">
            Model detected: {payload.model_id}
          </div>
        )}

        {/* Main Explanation */}
        {content && (
          <div className="message-content">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}

        {/* Installation / Diagnostic Steps */}
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

        {/* Recommended Parts */}
        {payload?.recommended_parts?.length > 0 &&
          payload.recommended_parts.map((part: any, idx: number) => (
            <ProductCard
              key={idx}
              partNumber={part.part_id}
              name={part.title}
              price={part.price && part.price !== "N/A" ? parseFloat(part.price.replace('$','')) : undefined}
              url={part.url}
              inStock={true}
              compatible={payload?.compatible}
            />
          ))}

        {/* Single Part (part_lookup case) */}
        {payload?.part && (
          <ProductCard
            partNumber={payload.part.part_id}
            name={payload.part.title}
            price={payload.part.price && payload.part.price !== "N/A"
              ? parseFloat(payload.part.price.replace('$',''))
              : undefined}
            url={payload.part.url}
            inStock={true}
            compatible={payload?.compatible}
          />
        )}

        {/* Helpful Tips */}
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

      </div>
    </div>
  )
}
