import './app-paths'
import { app } from 'electron'
import { setupCSP } from './csp'
import { registerExportHandlers } from './export/export-handler'
import { checkMediaToolCapabilities, stopExportProcess } from './export/ffmpeg-utils'
import { registerAppHandlers } from './ipc/app-handlers'
import { registerFileHandlers } from './ipc/file-handlers'
import { registerLogHandlers } from './ipc/log-handlers'
import { registerVideoProcessingHandlers } from './ipc/video-processing-handlers'
import { logger } from './logger'
import { initSessionLog } from './logging-management'
import { stopPythonBackend } from './python-backend'
import { createWindow, getMainWindow } from './window'

function logAppVersion(): void {
  if (!app.isPackaged) {
    logger.info('[H3 Director Desktop] Running in development mode')
  } else {
    logger.info(`[H3 Director Desktop] Version ${app.getVersion()}`)
  }
}

const gotLock = app.requestSingleInstanceLock()

if (!gotLock) {
  app.quit()
} else {
  initSessionLog()
  logAppVersion()

  registerAppHandlers()
  registerFileHandlers()
  registerLogHandlers()
  registerExportHandlers()
  registerVideoProcessingHandlers()

  app.on('second-instance', () => {
    const mainWindow = getMainWindow()
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore()
      }
      if (!mainWindow.isVisible()) {
        mainWindow.show()
      }
      mainWindow.focus()
      return
    }
    if (app.isReady()) {
      createWindow()
    }
  })

  app.whenReady().then(async () => {
    setupCSP()
    const mediaTools = checkMediaToolCapabilities()
    logger.info(`[media-tools] ffmpeg: ${JSON.stringify(mediaTools.ffmpeg)}`)
    logger.info(`[media-tools] ffprobe: ${JSON.stringify(mediaTools.ffprobe)}`)
    if (!mediaTools.ffmpeg.available || !mediaTools.ffprobe.available) {
      logger.error('[media-tools] Local FFmpeg capability is incomplete; media export/probing is blocked')
    }
    createWindow()
    // Python setup + backend start are now driven by the renderer via IPC

  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      stopPythonBackend()
      app.quit()
    }
  })

  app.on('activate', () => {
    if (getMainWindow() === null) {
      createWindow()
    }
  })

  app.on('before-quit', () => {
    stopExportProcess()
    stopPythonBackend()
  })
}
