import React from 'react'
import { Search, X } from 'lucide-react'

interface SearchBarProps {
  searchQuery: string
  onSearchChange: (value: string) => void
  onClearSearch: () => void
  resultCount: number
}

export default function SearchBar({ 
  searchQuery, 
  onSearchChange, 
  onClearSearch,
  resultCount 
}: SearchBarProps) {
  return (
    <div className="search-bar">
      <div className="search-input-wrapper">
        <Search size={18} className="search-icon" />
        <input
          type="text"
          className="search-input"
          placeholder="Search messages..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {searchQuery && (
          <>
            <span className="search-count">
              {resultCount} {resultCount === 1 ? 'result' : 'results'}
            </span>
            <button
              className="search-clear"
              onClick={onClearSearch}
              title="Clear search"
            >
              <X size={16} />
            </button>
          </>
        )}
      </div>
    </div>
  )
}