import React from 'react'
import { ExternalLink, ShoppingCart, Check, AlertCircle } from 'lucide-react'

interface ProductCardProps {
  partNumber: string
  name: string
  price?: number
  image?: string
  inStock: boolean
  url: string
  compatibility?: string[]
  compatible?: boolean
}

export default function ProductCard({
  partNumber,
  name,
  price,
  image,
  inStock,
  url,
  compatibility,
  compatible
}: ProductCardProps) {
  return (
    <div className="product-card">

      {/* Compatibility Badge */}
      {compatible === true && (
        <div className="compat-badge success">
          <Check size={14} /> Compatible with your model
        </div>
      )}

      {compatible === false && (
        <div className="compat-badge warning">
          <AlertCircle size={14} /> Not compatible
        </div>
      )}

      <div className="product-card-header">
        <div className="product-image">
          {image ? (
            <img src={image} alt={name} />
          ) : (
            <div className="product-placeholder">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
            </div>
          )}
        </div>

        <div className="product-info">
          <h4 className="product-name">{name}</h4>
          <p className="product-part-number">Part #{partNumber}</p>

          <div className="product-meta">
            {price !== undefined && !isNaN(price) && (
              <span className="product-price">${price.toFixed(2)}</span>
            )}

            <span className={`product-stock ${inStock ? 'in-stock' : 'out-of-stock'}`}>
              {inStock ? (
                <>
                  <Check size={14} /> In Stock
                </>
              ) : (
                'Out of Stock'
              )}
            </span>
          </div>
        </div>
      </div>

      {compatibility && compatibility.length > 0 && (
        <div className="product-compatibility">
          <strong>Compatible with:</strong> {compatibility.slice(0, 3).join(', ')}
          {compatibility.length > 3 && ` +${compatibility.length - 3} more`}
        </div>
      )}

      <div className="product-actions">
        <a 
          href={url} 
          target="_blank" 
          rel="noopener noreferrer"
          className="btn-view-product"
        >
          <ExternalLink size={16} />
          View Details
        </a>

        {inStock && (
          <button className="btn-add-to-cart">
            <ShoppingCart size={16} />
            Add to Cart
          </button>
        )}
      </div>
    </div>
  )
}
