import { useEffect, useState } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'
import { ProjectProvider } from './contexts/ProjectContext'
import { ViewProvider, useView } from './contexts/ViewContext'
import { AppSettingsProvider } from './contexts/AppSettingsContext'
import { KeyboardShortcutsProvider } from './contexts/KeyboardShortcutsContext'
import { Home } from './views/Home'
import { Project } from './views/Project'
import { PythonSetup } from './components/PythonSetup'
import { useBackend } from './hooks/use-backend'
import { logger } from './lib/logger'

function AppContent() {
  const { connected, processStatus, isLoading } = useBackend()
  const { currentView } = useView()
  const [pythonReady, setPythonReady] = useState<boolean | null>(null)
  const [backendStarted, setBackendStarted] = useState(false)

  useEffect(() => {
    void window.electronAPI.checkPythonReady()
      .then(result => setPythonReady(result.ready))
      .catch(() => setPythonReady(true))
  }, [])

  useEffect(() => {
    if (pythonReady !== true || backendStarted) return
    setBackendStarted(true)
    void window.electronAPI.startPythonBackend().catch(error => {
      logger.error(`Failed to start the local H3 backend: ${String(error)}`)
    })
  }, [backendStarted, pythonReady])

  if (pythonReady === false) {
    return <PythonSetup onReady={() => setPythonReady(true)} />
  }

  if (processStatus === 'dead') {
    return (
      <div className="flex h-screen items-center justify-center bg-[#07090d] p-8 text-zinc-100">
        <div className="max-w-lg rounded-2xl border border-red-500/30 bg-red-950/20 p-8 text-center">
          <AlertCircle className="mx-auto mb-4 h-10 w-10 text-red-400" />
          <h1 className="text-xl font-semibold">The local H3 backend stopped</h1>
          <p className="mt-2 text-sm text-zinc-400">Restart H3 Director Desktop and review the local logs if the problem continues.</p>
        </div>
      </div>
    )
  }

  if (pythonReady === null || isLoading || !connected) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#07090d] text-zinc-100">
        <div className="text-center">
          <Loader2 className="mx-auto mb-5 h-10 w-10 animate-spin text-amber-300" />
          <h1 className="text-xl font-semibold tracking-wide">Starting H3 Director Desktop</h1>
          <p className="mt-2 text-sm text-zinc-500">Preparing the local creative engine</p>
        </div>
      </div>
    )
  }

  return currentView === 'project' ? <Project /> : <Home />
}

export default function App() {
  return (
    <ProjectProvider>
      <AppSettingsProvider><KeyboardShortcutsProvider><ViewProvider><AppContent /></ViewProvider></KeyboardShortcutsProvider></AppSettingsProvider>
    </ProjectProvider>
  )
}
