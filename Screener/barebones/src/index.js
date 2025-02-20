'use strict'

const { app, BrowserWindow } = require('electron')

const url = require("url")
const path = require("path")

const isDevelopment = false; //process.env.NODE_ENV !== 'production'

// global reference to mainWindow (necessary to prevent window from being garbage collected)
let mainWindow

function createWindow() {
  const window = new BrowserWindow({webPreferences: {nodeIntegration: true}})

  if (isDevelopment) {
    window.webContents.openDevTools()
  }

  if (isDevelopment) {
    window.loadURL(`http://localhost:${process.env.ELECTRON_WEBPACK_WDS_PORT}`)
  }
  else {
    window.loadURL(url.format({
      pathname: path.join(__dirname, 'index.html'),
      protocol: 'file',
      slashes: true
    }))
  }

  window.on('closed', () => {
    mainWindow = null
  })

  window.webContents.on('devtools-opened', () => {
    window.focus()
    setImmediate(() => {
      window.focus()
    })
  })

  return window
}
     
app.on('window-all-closed', () => {
     if (process.platform !== 'darwin') app.quit()
})

app.whenReady().then(() => {
    mainWindow = createWindow()
     
    app.on('activate', () => {
       if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow()
    })
})

