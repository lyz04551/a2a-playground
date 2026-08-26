import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import {
  DEFAULT_SETTINGS,
  SETTINGS_STORAGE_KEY,
  parseSettings,
  serializeSettings,
} from '../state/consoleSettings'

const ConsoleSettingsContext = createContext(null)

function readStoredSettings() {
  if (typeof window === 'undefined') return { ...DEFAULT_SETTINGS }
  return parseSettings(window.localStorage.getItem(SETTINGS_STORAGE_KEY))
}

export function ConsoleSettingsProvider({ children }) {
  const [settings, setSettings] = useState(readStoredSettings)

  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = settings.theme
    root.dataset.density = settings.density
    root.lang = settings.language
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, serializeSettings(settings))
  }, [settings])

  const value = useMemo(() => ({
    settings,
    updateSettings(patch) {
      setSettings(current => ({ ...current, ...patch }))
    },
    resetSettings() {
      setSettings({ ...DEFAULT_SETTINGS })
    },
  }), [settings])

  return <ConsoleSettingsContext.Provider value={value}>{children}</ConsoleSettingsContext.Provider>
}

export function useConsoleSettings() {
  const context = useContext(ConsoleSettingsContext)
  if (!context) throw new Error('useConsoleSettings must be used inside ConsoleSettingsProvider')
  return context
}
