const fs = require('fs');
const path = require('path');

const src = '/home/manish/.gemini/antigravity/brain/c48bd6db-ec6c-4f09-8de4-6216de7a84aa/icon_1783947805559.png';
const dest = path.join(__dirname, 'public', 'icon.png');

try {
  fs.copyFileSync(src, dest);
  console.log(`Successfully copied icon from ${src} to ${dest}`);
} catch (err) {
  console.error('Failed to copy icon:', err);
}
