import React from 'react'
import { Package, Wrench, Search, HelpCircle } from 'lucide-react'

interface QuickActionsProps {
  onActionClick: (action: string) => void
}

const QUICK_ACTIONS = [
  { 
    id: 'find-part', 
    icon: Search, 
    label: 'Find a Part',
    query: 'Help me find the right part'
  },
  { 
    id: 'check-compatibility', 
    icon: Package, 
    label: 'Check Compatibility',
    query: 'Check if this part is compatible with my model'
  },
  { 
    id: 'installation', 
    icon: Wrench, 
    label: 'Installation Help',
    query: 'How do I install this part?'
  },
  { 
    id: 'troubleshoot', 
    icon: HelpCircle, 
    label: 'Troubleshoot',
    query: 'My appliance is not working properly'
  }
]

export default function QuickActions({ onActionClick }: QuickActionsProps) {
  return (
    <div className="quick-actions">
      <p className="quick-actions-title">Quick Actions</p>
      <div className="quick-actions-grid">
        {QUICK_ACTIONS.map((action) => (
          <button
            key={action.id}
            className="quick-action-btn"
            onClick={() => onActionClick(action.query)}
          >
            <action.icon size={20} />
            <span>{action.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}