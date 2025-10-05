const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');
const cors = require('cors');

const router = express.Router();

// Enable CORS for this route
router.use(cors());

// POST /backend/extract-colors
// Input: { logoUrl: string } (can be http(s) URL or data URL)
// Output: { success, colors, outputPath }
router.post('/extract-colors', async (req, res) => {
  try {
    const { logoUrl } = req.body || {};
    if (!logoUrl || typeof logoUrl !== 'string' || logoUrl.trim() === '') {
      return res.status(400).json({ success: false, error: 'Missing logoUrl' });
    }

    const projectRoot = path.resolve(__dirname, '..');

    // Paths aligned with public/data/generation/webgen/step_2/color_extractor.py expectations
    const outputDir = path.join(projectRoot, 'public', 'data', 'output', 'individual', 'step_2');
    const inputDir = path.join(projectRoot, 'public', 'data', 'output', 'individual', 'step_1', 'raw');
    const logoPath = path.join(inputDir, 'logo.png');
    const colorsOutputPath = path.join(outputDir, 'colors_output.json');

    // Ensure directories exist
    fs.mkdirSync(outputDir, { recursive: true });
    fs.mkdirSync(inputDir, { recursive: true });

    // Write provided logoUrl into logoPath (supports http(s) and data URL)
    const writeDataUrlToFile = (dataUrl, destPath) => {
      const match = dataUrl.match(/^data:image\/(png|jpeg|jpg);base64,(.+)$/);
      if (!match) throw new Error('Invalid data URL format for image');
      const base64Data = match[2];
      const buffer = Buffer.from(base64Data, 'base64');
      fs.writeFileSync(destPath, buffer);
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

    try {
      if (logoUrl.startsWith('data:image')) {
        writeDataUrlToFile(logoUrl, logoPath);
      } else {
        await downloadToFile(logoUrl, logoPath);
      }
    } catch (e) {
      return res.status(400).json({ success: false, error: `Failed to materialize logo: ${e.message}` });
    }

    // Spawn python process within venv to extract colors using colorthief
    const pythonExecutable = path.join(projectRoot, 'public', 'data', 'generation', 'myenv', 'bin', 'python');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(logoPath)) {
      return res.status(500).json({ success: false, error: `Logo not found at ${logoPath}` });
    }

    // Inline Python script: read logoPath, extract palette, generate 4 distinct colors and write JSON
    const pyCode = `\n\
import json, sys, os\n\
from colorthief import ColorThief\n\
def rgb_to_hex(rgb):\n\
    return "#%02x%02x%02x" % tuple(rgb)\n\
def color_distance(c1, c2):\n\
    return sum((a-b)**2 for a,b in zip(c1,c2)) ** 0.5\n\
def generate_unique_colors(palette_rgb, num_colors=4):\n\
    if len(palette_rgb) >= num_colors:\n\
        selected = [palette_rgb[0]]\n\
        for _ in range(num_colors-1):\n\
            best = None\n\
            max_min = -1\n\
            for col in palette_rgb:\n\
                if col in selected:\n\
                    continue\n\
                md = min(color_distance(col, s) for s in selected)\n\
                if md > max_min:\n\
                    max_min = md\n\
                    best = col\n\
            if best:\n\
                selected.append(best)\n\
        return selected\n\
    return palette_rgb[:num_colors]\n\
logo_path = sys.argv[1]\n\
output_path = sys.argv[2]\n\
thief = ColorThief(logo_path)\n\
palette = thief.get_palette(color_count=8, quality=1)\n\
unique = generate_unique_colors(palette, 4)\n\
colors = {\n\
    "accent": rgb_to_hex(unique[0] if len(unique)>0 else (43,76,126)),\n\
    "banner": rgb_to_hex(unique[1] if len(unique)>1 else (211,47,47)),\n\
    "faint-color": rgb_to_hex(unique[2] if len(unique)>2 else (224,247,250)),\n\
    "second-accent": rgb_to_hex(unique[3] if len(unique)>3 else (255,160,0)),\n\
}\n\
with open(output_path, 'w', encoding='utf-8') as f:\n\
    json.dump(colors, f, indent=2)\n\
print(json.dumps(colors))\n`;

    const child = spawn(pythonExecutable, ['-c', pyCode, logoPath, colorsOutputPath], {
      cwd: projectRoot,
      env: { ...process.env },
    });

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: 'Color extraction failed', details: stderr });
      }
      let colors = null;
      try {
        colors = JSON.parse(stdout || '{}');
      } catch (e) {
        // ignore parse error, still return path
      }
      return res.json({ success: true, colors, outputPath: colorsOutputPath });
    });
  } catch (err) {
    console.error('[Extract Colors] Endpoint error:', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;

// POST /backend/save-colors
// Input: { colors: { accent, banner, 'faint-color', 'second-accent' } }
router.post('/save-colors', async (req, res) => {
  try {
    const { colors } = req.body || {};
    if (!colors || typeof colors !== 'object') {
      return res.status(400).json({ success: false, error: 'Missing colors object' });
    }

    const projectRoot = path.resolve(__dirname, '..');
    const outputDir = path.join(projectRoot, 'public', 'data', 'output', 'individual', 'step_2');
    const colorsOutputPath = path.join(outputDir, 'colors_output.json');
    fs.mkdirSync(outputDir, { recursive: true });

    fs.writeFileSync(colorsOutputPath, JSON.stringify(colors, null, 2), 'utf-8');
    return res.json({ success: true, outputPath: colorsOutputPath });
  } catch (err) {
    console.error('[Save Colors] Endpoint error:', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

// POST /backend/generate-ai-colors
// Generates a color palette using Python module functions without starting any HTML server
router.post('/generate-ai-colors', async (req, res) => {
  try {
    const projectRoot = path.resolve(__dirname, '..');
    const pythonExecutable = path.join(projectRoot, 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const moduleDir = path.join(projectRoot, 'public', 'data', 'generation', 'webgen', 'step_2');
    const inputDir = path.join(projectRoot, 'public', 'data', 'output', 'individual', 'step_1', 'raw');
    const outputDir = path.join(projectRoot, 'public', 'data', 'output', 'individual', 'step_2');
    const bbbProfilePath = path.join(inputDir, 'bbb_profile_data.json');
    const colorsOutputPath = path.join(outputDir, 'colors_output.json');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(moduleDir)) {
      return res.status(500).json({ success: false, error: `Module dir not found at ${moduleDir}` });
    }
    fs.mkdirSync(outputDir, { recursive: true });

    // Inline Python to import functions and generate colors without starting servers
    const pyCode = [
      'import os, json, sys',
      `sys.path.insert(0, r'${moduleDir}')`,
      'from generate_colors_with_ai import generate_prompt, generate_colors_with_ai',
      `bbb_path = r'${bbbProfilePath}'`,
      `out_path = r'${colorsOutputPath}'`,
      'business_data = {}',
      'try:',
      '  with open(bbb_path, "r", encoding="utf-8") as f:',
      '    business_data = json.load(f)',
      'except Exception as e:',
      '  business_data = {}',
      'prompt = generate_prompt(business_data if isinstance(business_data, dict) else {})',
      'api_key = os.environ.get("OPENAI_API_KEY")',
      'colors = generate_colors_with_ai(api_key, prompt)',
      'with open(out_path, "w", encoding="utf-8") as f:',
      '  json.dump(colors, f, indent=2)',
      'print(json.dumps(colors))'
    ].join('\n');

    const child = spawn(pythonExecutable, ['-c', pyCode], {
      cwd: projectRoot,
      env: { ...process.env },
    });

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: 'AI color generation failed', details: stderr });
      }
      let colors = null;
      try {
        colors = JSON.parse(stdout || '{}');
      } catch (e) {}
      return res.json({ success: true, colors, outputPath: colorsOutputPath });
    });
  } catch (err) {
    console.error('[Generate AI Colors] Endpoint error:', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});


