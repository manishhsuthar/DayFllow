const { app } = require('electron');
const path = require('path');
const fs = require('fs');

function windowStateKeeper(config) {
  const userDataPath = app.getPath('userData');
  const stateFilePath = path.join(userDataPath, 'window-state.json');
  
  let state = {
    width: config.defaultWidth || 1200,
    height: config.defaultHeight || 800,
    x: undefined,
    y: undefined
  };

  try {
    if (fs.existsSync(stateFilePath)) {
      state = JSON.parse(fs.readFileSync(stateFilePath, 'utf8'));
    }
  } catch (err) {
    // Fail silently, use defaults
  }

  function saveState(win) {
    if (!win.isDestroyed() && !win.isMaximized() && !win.isMinimized()) {
      const bounds = win.getBounds();
      state.x = bounds.x;
      state.y = bounds.y;
      state.width = bounds.width;
      state.height = bounds.height;
    }
    try {
      fs.writeFileSync(stateFilePath, JSON.stringify(state));
    } catch (err) {
      // Fail silently
    }
  }

  function manage(win) {
    win.on('resize', () => saveState(win));
    win.on('move', () => saveState(win));
    win.on('close', () => saveState(win));
  }

  return {
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    manage
  };
}

module.exports = windowStateKeeper;
