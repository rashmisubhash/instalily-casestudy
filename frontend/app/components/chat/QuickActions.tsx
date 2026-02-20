import React from 'react'
import { Package, Wrench, Search, HelpCircle } from 'lucide-react'

interface QuickActionsProps {
  onActionClick: (action: string) => void
}

const QUICK_ACTIONS = [
  { 
    id: 'find-part', 
    icon: Search, 
    label: 'Find Part',
    query: 'Help me find the correct replacement part'
  },
  { 
    id: 'check-compatibility', 
    icon: Package, 
    label: 'Verify Fit',
    query: 'Check if this part fits my appliance model'
  },
  { 
    id: 'installation', 
    icon: Wrench, 
    label: 'Install Help',
    query: 'Show installation steps for this part'
  },
  { 
    id: 'troubleshoot', 
    icon: HelpCircle, 
    label: 'Diagnose Issue',
    query: 'My appliance has a symptom. Help me diagnose the likely part issue'
  }
]

export default function QuickActions({ onActionClick }: QuickActionsProps) {
  return (
    <div className="quick-actions">
      <p className="quick-actions-title">Start Faster</p>
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
