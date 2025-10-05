const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const cors = require('cors');

const router = express.Router();
router.use(cors());

router.post('/search-business', async (req, res) => {
  try {
    const { businessName, businessAddress } = req.body || {};
    console.log('[backend] /search-business request', { businessName, businessAddress });
    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_1/search_business.py');
    const pythonExecutable = path.join(venvPath, 'bin', 'python');

    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Search script not found at ${scriptPath}`);
    }
    if (!fs.existsSync(pythonExecutable)) {
      throw new Error(`Python executable not found at ${pythonExecutable}`);
    }

    const args = [scriptPath];
    if (businessName) {
      args.push('--business-name', businessName);
    }
    if (businessAddress) {
      args.push('--business-address', businessAddress);
    }

    const env = { ...process.env, MEMORY_ONLY: '1' };
    const child = spawn(pythonExecutable, args, { cwd: projectRoot, env });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { const s = d.toString(); stdout += s; });
    child.stderr.on('data', (d) => { const s = d.toString(); stderr += s; });
    child.on('close', (code) => {
      if (code !== 0) {
        console.error('[backend] /search-business python exit non-zero', { code, stderr });
        return res.status(500).json({ success: false, error: `Script exited with ${code}`, stderr });
      }
      const match = stdout.match(/WEBSEARCH_RESULTS_START\n([\s\S]*?)\nWEBSEARCH_RESULTS_END/);
      if (!match) {
        console.warn('[backend] /search-business no markers found');
        return res.status(200).json({ success: true, results: { base_search: null, social_media_search: {} }, note: 'No results markers found' });
      }
      let results = {};
      try {
        results = JSON.parse(match[1]);
      } catch (e) {
        console.error('[backend] /search-business parse error', e);
        return res.status(500).json({ success: false, error: 'Failed to parse results', stderr });
      }
      const social = results?.social_media_search || {};
      const sites = Object.keys(social);
      const foundCount = sites.filter((s) => Array.isArray(social[s]?.items) && social[s].items.length > 0).length;
      console.log('[backend] /search-business parsed', { sitesCount: sites.length, foundCount });
      return res.json({ success: true, results });
    });
  } catch (err) {
    console.error('[backend] /search-business error', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;


