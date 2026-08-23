const { ipcMain, app, BrowserWindow } = require('electron');

function registerIpcHandlers() {
  ipcMain.on('window-minimize', (event) => {
    const webContents = event.sender;
    const win = BrowserWindow.fromWebContents(webContents);
    if (win) win.minimize();
  });

  ipcMain.on('window-maximize', (event) => {
    const webContents = event.sender;
    const win = BrowserWindow.fromWebContents(webContents);
    if (win) {
      if (win.isMaximized()) {
        win.unmaximize();
      } else {
        win.maximize();
      }
    }
  });

  ipcMain.on('window-close', (event) => {
    const webContents = event.sender;
    const win = BrowserWindow.fromWebContents(webContents);
    if (win) win.close();
  });

  ipcMain.handle('get-app-version', () => {
    return app.getVersion();
  });
}

module.exports = registerIpcHandlers;
