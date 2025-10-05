const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const cors = require('cors');

const router = express.Router();
router.use(cors());

router.post('/scrape-reviews', async (req, res) => {
  try {
    const { businessName, googleReviewsUrl, maxReviews = 50, headless } = req.body || {};

    if (!googleReviewsUrl || typeof googleReviewsUrl !== 'string' || !googleReviewsUrl.trim()) {
      return res.status(400).json({ success: false, error: 'Missing googleReviewsUrl' });
    }

    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public', 'data', 'generation', 'myenv');
    const scriptPath = path.join(projectRoot, 'public', 'data', 'generation', 'webgen', 'step_1', 'ScrapeReviews.py');
    const pythonExecutable = path.join(venvPath, 'bin', 'python');

    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please create venv at public/data/generation/myenv');
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Reviews script not found at ${scriptPath}`);
    }
    if (!fs.existsSync(pythonExecutable)) {
      throw new Error(`Python executable not found at ${pythonExecutable}`);
    }

    const args = [
      scriptPath,
      '--business-name', businessName || 'Unknown Business',
      '--google-reviews-url', googleReviewsUrl,
      '--max-reviews', String(Number(maxReviews) || 50)
    ];
    // NOTE: ScrapeReviews.py uses argparse type=bool for --headless which is unreliable.
    // Omit --headless entirely unless explicitly requested true.
    if (headless === true) {
      args.splice(3, 0, '--headless');
      args.splice(4, 0, 'true');
    }

    const child = spawn(pythonExecutable, args, { cwd: projectRoot, env: { ...process.env } });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });

    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Script exited with ${code}`, stderr });
      }
      try {
        const match = stdout.match(/SCRAPED_REVIEWS_DATA_START\n([\s\S]*?)\nSCRAPED_REVIEWS_DATA_END/);
        if (match) {
          const payload = JSON.parse(match[1]);
          return res.json({ success: true, scrapedData: payload, analysisData: null });
        }
        const parsed = JSON.parse(stdout);
        return res.json({ success: true, scrapedData: parsed, analysisData: null });
      } catch (e) {
        return res.status(200).json({ success: true, scrapedData: null, analysisData: null, note: 'No structured output parsed', stdout, stderr });
      }
    });
  } catch (err) {
    console.error('[backend] /scrape-reviews error', err);
    return res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;


