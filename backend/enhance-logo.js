const express = require('express');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');
const cors = require('cors');

const router = express.Router();

// Enable CORS for this route
router.use(cors());

// POST /backend/enhance-logo
router.post('/enhance-logo', async (req, res) => {
  try {
    const { businessName, logoUrl } = req.body || {};

    console.log('Enhance Logo request received:', {
      businessName: businessName || '(not provided)',
      timestamp: new Date().toISOString()
    });

    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_4/enhance_logo.py');
    const pythonExecutable = path.join(venvPath, 'bin', 'python');
    const rawLogoDir = path.join(projectRoot, 'public/data/generation/webgen/raw_data/step_1');
    const rawLogoPath = path.join(rawLogoDir, 'logo.png');

    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Enhance script not found at ${scriptPath}`);
    }
    if (!fs.existsSync(pythonExecutable)) {
      throw new Error(`Python executable not found at ${pythonExecutable}`);
    }

    // If a logo URL is provided, download it to the expected raw path before enhancement
    const ensureDir = (dirPath) => {
      if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
      }
    };

    const downloadToFile = (url, destPath) => new Promise((resolve, reject) => {
      try {
        const client = url.startsWith('https') ? https : http;
        const request = client.get(url, (response) => {
          if (response.statusCode && response.statusCode >= 400) {
            return reject(new Error(`Failed to download image. HTTP ${response.statusCode}`));
          }
          const fileStream = fs.createWriteStream(destPath);
          response.pipe(fileStream);
          fileStream.on('finish', () => fileStream.close(() => resolve(destPath)));
          fileStream.on('error', (err) => reject(err));
        });
        request.on('error', (err) => reject(err));
      } catch (e) {
        reject(e);
      }
    });

    if (logoUrl && typeof logoUrl === 'string') {
      try {
        ensureDir(rawLogoDir);
        if (logoUrl.startsWith('data:image')) {
          console.log('[Enhance Logo] Writing data URL to raw path ->', rawLogoPath);
          const match = logoUrl.match(/^data:image\/(png|jpeg|jpg);base64,(.+)$/);
          if (!match) {
            throw new Error('Invalid data URL format for image');
          }
          const base64Data = match[2];
          const buffer = Buffer.from(base64Data, 'base64');
          fs.writeFileSync(rawLogoPath, buffer);
          console.log('[Enhance Logo] Data URL write complete');
        } else {
          console.log('[Enhance Logo] Downloading logo from URL to raw path:', logoUrl, '->', rawLogoPath);
          await downloadToFile(logoUrl, rawLogoPath);
          console.log('[Enhance Logo] Download complete');
        }
      } catch (downloadErr) {
        console.error('[Enhance Logo] Error downloading logo:', downloadErr);
        return res.status(400).json({ success: false, error: `Failed to download logo: ${downloadErr.message}` });
      }
    } else {
      console.log('[Enhance Logo] No logoUrl provided; will use existing raw file if present at', rawLogoPath);
    }

    console.log('[Enhance Logo] Executing:', pythonExecutable, scriptPath);

    // MEMORY_ONLY: propagate env to request base64 output from python
    const child = spawn(pythonExecutable, [scriptPath], {
      cwd: projectRoot,
      env: { ...process.env, MEMORY_ONLY: '1' }
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) {
        console.error('[Enhance Logo] Non-zero exit:', code, '\nSTDERR:', stderr);
        return res.status(500).json({
          success: false,
          error: `Enhance script failed (exit ${code})`,
          stderr,
          timestamp: new Date().toISOString()
        });
      }
      if (stderr) {
        console.error('[Enhance Logo] STDERR:', stderr);
      }
      console.log('[Enhance Logo] STDOUT:', stdout);

      const colorMatch = stdout.match(/ENHANCED_LOGO_COLOR_BASE64_START\n([\s\S]*?)\nENHANCED_LOGO_COLOR_BASE64_END/);
      const grayMatch = stdout.match(/ENHANCED_LOGO_GRAYSCALE_BASE64_START\n([\s\S]*?)\nENHANCED_LOGO_GRAYSCALE_BASE64_END/);
      if (colorMatch || grayMatch) {
        const colorDataUrl = colorMatch ? `data:image/png;base64,${colorMatch[1]}` : null;
        const grayDataUrl = grayMatch ? `data:image/png;base64,${grayMatch[1]}` : null;
        return res.json({ success: true, message: 'Logo enhanced (memory)', colorDataUrl, grayDataUrl, timestamp: new Date().toISOString() });
      }
      // Fallback path-based response
      const assetsPath = '/assets/images/hero/logo.png';
      return res.json({ success: true, message: 'Logo enhanced successfully', assetsPath, timestamp: new Date().toISOString() });
    });
  } catch (err) {
    console.error('[Enhance Logo] Endpoint error:', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

// POST /backend/persist-logo
// Persist provided data URLs (color/grayscale) to canonical generation paths
router.post('/persist-logo', async (req, res) => {
  try {
    const { colorDataUrl, grayDataUrl } = req.body || {};

    if (!colorDataUrl && !grayDataUrl) {
      return res.status(400).json({ success: false, error: 'Missing colorDataUrl or grayDataUrl' });
    }

    const projectRoot = path.resolve(__dirname, '..');
    const rawLogoDir = path.join(projectRoot, 'public/data/generation/webgen/raw_data/step_1');
    const rawColorPath = path.join(rawLogoDir, 'logo.png');
    const rawGrayPath = path.join(rawLogoDir, 'logo_gray.png');

    const ensureDir = (dirPath) => {
      if (!fs.existsSync(dirPath)) fs.mkdirSync(dirPath, { recursive: true });
    };

    const writeDataUrlToFile = (dataUrl, destPath) => {
      const match = (dataUrl || '').match(/^data:image\/(png|jpeg|jpg);base64,(.+)$/);
      if (!match) throw new Error('Invalid data URL format');
      const base64Data = match[2];
      const buffer = Buffer.from(base64Data, 'base64');
      fs.writeFileSync(destPath, buffer);
    };

    ensureDir(rawLogoDir);
    if (colorDataUrl) {
      writeDataUrlToFile(colorDataUrl, rawColorPath);
    }
    if (grayDataUrl) {
      writeDataUrlToFile(grayDataUrl, rawGrayPath);
    }

    const colorPublicPath = '/data/generation/webgen/raw_data/step_1/logo.png';
    const grayPublicPath = '/data/generation/webgen/raw_data/step_1/logo_gray.png';

    return res.status(200).json({
      success: true,
      persisted: true,
      colorPath: colorDataUrl ? colorPublicPath : null,
      grayPath: grayDataUrl ? grayPublicPath : null,
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    console.error('[Persist Logo] Endpoint error:', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;

