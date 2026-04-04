import { copyFileSync, cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';

const projectRoot = process.cwd();
const distDir = join(projectRoot, 'dist');
const picoRoot = join(projectRoot, '..', 'Pico');
const picoWwwDir = join(picoRoot, 'www');

if (!existsSync(distDir)) {
  console.error('Missing dist folder. Run `npm run build` first.');
  process.exit(1);
}

if (!existsSync(picoRoot)) {
  mkdirSync(picoRoot, { recursive: true });
}

rmSync(picoWwwDir, { recursive: true, force: true });
mkdirSync(picoWwwDir, { recursive: true });
cpSync(distDir, picoWwwDir, { recursive: true });

const hintPath = join(picoRoot, 'DEPLOYMENT.txt');
const hint = [
  'Pico deployment files generated.',
  '',
  'Upload these to your Pico W filesystem:',
  '- main.py',
  '- www/ (entire folder)',
  '',
  'Suggested commands (with mpremote):',
  'mpremote fs cp main.py :main.py',
  'mpremote fs cp -r www :www',
].join('\n');
writeFileSync(hintPath, hint + '\n', 'utf8');

console.log('Export complete. Copied website/dist -> ../Pico/www');
console.log('Next: upload ../Pico/main.py and ../Pico/www to Pico W.');
