const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const cors = require('cors');

const router = express.Router();
router.use(cors());

router.post('/scrape-yelp', async (req, res) => {
  try {
    const { yelpUrl, businessName, businessAddress } = req.body || {};
    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_1/yelp_scraper.py');
    const pythonExecutable = path.join(venvPath, 'bin', 'python');

    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Yelp script not found at ${scriptPath}`);
    }
    if (!fs.existsSync(pythonExecutable)) {
      throw new Error(`Python executable not found at ${pythonExecutable}`);
    }

    // Ensure BBB profile data file exists so yelp_scraper.py doesn't exit early
    try {
      const bbbDir = path.join(projectRoot, 'public/data/output/individual/step_1/raw');
      const bbbPath = path.join(bbbDir, 'bbb_profile_data.json');
      if (!fs.existsSync(bbbPath)) {
        fs.mkdirSync(bbbDir, { recursive: true });
        const minimal = {
          business_name: typeof businessName === 'string' ? businessName : '',
          address: typeof businessAddress === 'string' ? businessAddress : ''
        };
        fs.writeFileSync(bbbPath, JSON.stringify(minimal, null, 2), 'utf-8');
        console.log('[backend] /scrape-yelp created minimal BBB profile at', bbbPath);
      }
    } catch (prepErr) {
      console.warn('[backend] /scrape-yelp failed to ensure BBB profile file:', prepErr?.message || prepErr);
    }

    const args = [scriptPath];
    if (yelpUrl && typeof yelpUrl === 'string' && yelpUrl.trim().length) {
      args.push('--yelp-url', yelpUrl);
    }
    const env = { ...process.env, MEMORY_ONLY: '1' };
    console.log('[backend] /scrape-yelp spawning', { args });
    const child = spawn(pythonExecutable, args, { cwd: projectRoot, env });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) {
        console.error('[backend] /scrape-yelp non-zero exit', { code, stderr });
        return res.status(500).json({ success: false, error: `Script exited with ${code}`, stderr });
      }
      const match = stdout.match(/YELP_RESULTS_START\n([\s\S]*?)\nYELP_RESULTS_END/);
      if (!match) {
        console.warn('[backend] /scrape-yelp no markers found');
        return res.status(200).json({ success: true, yelp: null, note: 'No results markers found' });
      }
      try {
        const payload = JSON.parse(match[1]);
        return res.json({ success: true, yelp: payload });
      } catch (e) {
        console.error('[backend] /scrape-yelp parse error', e);
        return res.status(500).json({ success: false, error: 'Failed to parse results' });
      }
    });
  } catch (err) {
    console.error('[backend] /scrape-yelp error', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;


