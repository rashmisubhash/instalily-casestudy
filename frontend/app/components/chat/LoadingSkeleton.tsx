import React from 'react'

export default function LoadingSkeleton() {
  return (
    <div className="message assistant">
      <div className="message-wrapper">
        <div className="skeleton-badge"></div>
        <div className="skeleton-content">
          <div className="skeleton-line"></div>
          <div className="skeleton-line short"></div>
        </div>
        <div className="skeleton-product-card">
          <div className="skeleton-product-header">
            <div className="skeleton-image"></div>
            <div className="skeleton-product-info">
              <div className="skeleton-line"></div>
              <div className="skeleton-line short"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
