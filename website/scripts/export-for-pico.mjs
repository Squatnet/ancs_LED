import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const projectRoot = process.cwd();
const distDir = join(projectRoot, 'dist');
const picoRoot = join(projectRoot, '..', 'Pico');
const picoWwwDir = join(picoRoot, 'www');

if (!existsSync(distDir)) {
  console.error('ERROR: Missing dist folder. Run `npm run build` first.');
  process.exit(1);
}

if (!existsSync(picoRoot)) {
  mkdirSync(picoRoot, { recursive: true });
}

rmSync(picoWwwDir, { recursive: true, force: true });
mkdirSync(picoWwwDir, { recursive: true });
cpSync(distDir, picoWwwDir, { recursive: true });

console.log('Export complete. Copied website/dist -> ../Pico/www');
console.log('');

// Warn if wifi.json is missing
const wifiConfig = join(picoRoot, 'wifi.json');
if (!existsSync(wifiConfig)) {
  console.log('NOTE: No wifi.json found in Pico/');
  console.log('  Pico will boot in AP mode (SSID: ANCS, no password).');
  console.log('  To use STA mode, copy Pico/wifi.json.example -> Pico/wifi.json');
  console.log('  and fill in your credentials. (wifi.json is gitignored.)');
  console.log('');
}

console.log('Next steps:');
console.log('  mpremote fs cp Pico/main.py :main.py');
console.log('  mpremote fs cp -r Pico/www :www');
if (existsSync(wifiConfig)) {
  console.log('  mpremote fs cp Pico/wifi.json :wifi.json');
}
console.log('  mpremote reset');

