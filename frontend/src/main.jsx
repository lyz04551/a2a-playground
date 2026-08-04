import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ConsoleSettingsProvider } from './context/ConsoleSettingsContext'
import './styles/tokens.css'
import './styles/workspace.css'
import './styles/shell.css'
import './styles/dashboard.css'
import './styles/agents.css'
import './styles/events.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ConsoleSettingsProvider>
        <App />
      </ConsoleSettingsProvider>
    </BrowserRouter>
  </React.StrictMode>
)
