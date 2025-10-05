const express = require('express');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const cors = require('cors');

const router = express.Router();

// Enable CORS for this route
router.use(cors());

router.post('/generate-logo', async (req, res) => {
  try {
    const { businessName, leadId } = req.body;
    
    if (!businessName) {
      return res.status(400).json({ 
        error: 'Missing required field: businessName' 
      });
    }

    console.log('Logo Generation request received:', {
      businessName,
      leadId,
      timestamp: new Date().toISOString()
    });

    // Paths
    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_2/logogen.py');
    
    console.log('[generate-logo] Executing Python script with virtual environment...');
    console.log('Project root:', projectRoot);
    console.log('Venv path:', venvPath);
    console.log('Script path:', scriptPath);

    // Check if virtual environment exists
    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    
    // Prefer spawn to avoid stdout maxBuffer issues
    const pyEnv = { ...process.env, MEMORY_ONLY: '1', LOGO_PREVIEW_SIZE: '512x512' };
    const pyBin = path.join(venvPath, 'bin', 'python');
    console.log('[generate-logo] Spawning:', pyBin, scriptPath, 'env MEMORY_ONLY=', pyEnv.MEMORY_ONLY, 'LOGO_PREVIEW_SIZE=', pyEnv.LOGO_PREVIEW_SIZE);
    const child = spawn(pyBin, [scriptPath], { cwd: projectRoot, env: pyEnv });

    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => {
      const chunk = d.toString();
      stdoutBuf += chunk;
      if (chunk.includes('LOGO_VARIANTS_BASE64_START')) console.log('[generate-logo] Detected START marker');
      if (chunk.includes('LOGO_VARIANTS_BASE64_END')) console.log('[generate-logo] Detected END marker');
    });
    child.stderr.on('data', (d) => {
      const chunk = d.toString();
      stderrBuf += chunk;
      console.warn('[generate-logo] STDERR chunk:', chunk.slice(0, 200));
    });
    child.on('error', (err) => {
      console.error('Spawn error:', err);
    });
    child.on('close', (code) => {
      const consoleOutput = {
        stdout: stdoutBuf,
        stderr: stderrBuf,
        command: `${pyBin} ${scriptPath}`,
        exitCode: code,
        timestamp: new Date().toISOString()
      };

      if (code !== 0) {
        console.error('Python script exited with code', code);
        return res.status(500).json({ success: false, error: `Python script failed (exit ${code})`, businessName, leadId, consoleOutput });
      }

      console.log('[generate-logo] stdout length:', stdoutBuf.length);
      const variantsMatch = stdoutBuf.match(/LOGO_VARIANTS_BASE64_START\n([\s\S]*?)\nLOGO_VARIANTS_BASE64_END/);
      if (variantsMatch) {
        try {
          const variants = JSON.parse(variantsMatch[1]);
          console.log('[generate-logo] Parsed memoryVariants count:', Array.isArray(variants) ? variants.length : -1);
          return res.json({ success: true, memoryVariants: variants, businessName, leadId, consoleOutput, timestamp: new Date().toISOString() });
        } catch (e) {
          console.error('Failed to parse LOGO_VARIANTS_BASE64 JSON:', e);
          return res.status(500).json({ success: false, error: 'Failed to parse generated logos', businessName, leadId, consoleOutput });
        }
      }

      if (stdoutBuf.includes('Successfully generated') && stdoutBuf.includes('logo variations')) {
        return res.json({ success: true, memoryVariants: [], businessName, leadId, consoleOutput, timestamp: new Date().toISOString() });
      }

      console.log('Logo generation did not complete successfully');
      return res.status(500).json({ success: false, error: 'Logo generation failed or did not complete successfully', consoleOutput, businessName, leadId, timestamp: new Date().toISOString() });
    });
    
  } catch (error) {
    console.error('Logo generation endpoint error:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      businessName: req.body.businessName,
      leadId: req.body.leadId,
      timestamp: new Date().toISOString()
    });
  }
});

// Endpoint to move original logo to selected folder
router.post('/move-logo', async (req, res) => {
  try {
    const { originalLogoUrl, selectedLogoPath, businessName } = req.body;
    
    if (!originalLogoUrl || !selectedLogoPath) {
      return res.status(400).json({ 
        error: 'Missing required fields: originalLogoUrl and selectedLogoPath' 
      });
    }

    console.log('Move logo request received:', {
      originalLogoUrl,
      selectedLogoPath,
      businessName,
      timestamp: new Date().toISOString()
    });

    // Paths
    const projectRoot = path.resolve(__dirname, '..');
    const selectedFolder = path.join(projectRoot, 'public/data/output/leads/final/logo/selected');
    
    // Create selected folder if it doesn't exist
    if (!fs.existsSync(selectedFolder)) {
      fs.mkdirSync(selectedFolder, { recursive: true });
    }
    
    // Extract filename from original logo URL
    const originalLogoFilename = path.basename(originalLogoUrl);
    const selectedLogoFilename = path.basename(selectedLogoPath);
    
    // Source and destination paths
    const originalLogoPath = path.join(projectRoot, 'public/data/output/individual/step_1/raw', originalLogoFilename);
    const destinationPath = path.join(selectedFolder, `original_${businessName.replace(/[^a-zA-Z0-9]/g, '_')}_${originalLogoFilename}`);
    
    // Move the original logo to selected folder
    if (fs.existsSync(originalLogoPath)) {
      fs.copyFileSync(originalLogoPath, destinationPath);
      console.log(`Original logo moved to: ${destinationPath}`);
      
      return res.json({
        success: true,
        message: 'Original logo moved to selected folder',
        originalPath: originalLogoPath,
        destinationPath: destinationPath,
        timestamp: new Date().toISOString()
      });
    } else {
      console.log(`Original logo not found at: ${originalLogoPath}`);
      return res.json({
        success: true,
        message: 'Original logo not found, but selection completed',
        timestamp: new Date().toISOString()
      });
    }
    
  } catch (error) {
    console.error('Move logo endpoint error:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
