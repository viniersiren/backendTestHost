const express = require("express");
const bodyParser = require("body-parser");
const cors = require("cors");
const path = require('path');
require("dotenv").config(); // Load root .env
// Also load the generation .env to match webgen step_2/logogen.py behavior
try {
  const generationEnvPath = path.join(__dirname, '..', 'public', 'data', 'generation', '.env');
  require('dotenv').config({ path: generationEnvPath });
  if (process.env.OPENAI_API_KEY) {
    console.log('[Env] Loaded OPENAI_API_KEY from generation .env');
  }
} catch (e) {
  console.warn('[Env] Could not load generation .env:', e?.message || e);
}
const sgMail = require('@sendgrid/mail');
const { spawn } = require('child_process');
const { exec } = require('child_process');
const fs = require('fs');
const archiver = require('archiver');

// Import scraping route
const scrapeBbbRouter = require('./scrape-bbb');
// Import enhance logo route
const enhanceLogoRouter = require('./enhance-logo');
// Import generate logo route
const generateLogoRouter = require('./generate-logo');
// Import business search route
const businessSearchRouter = require('./business-search');
// Import extract colors route
const extractColorsRouter = require('./extract-colors');
// Import Yelp scrape route
const yelpScrapeRouter = require('./yelp-scrape');
// Import Reviews scrape route
const reviewsScrapeRouter = require('./reviews-scrape');

// Get SendGrid API key from environment
const sendgridApiKey = process.env.SENDGRID_API_KEY || process.env.CLOUDFLARE_SENDGRID_API_KEY;
if (!sendgridApiKey) {
  console.warn('SendGrid API key not found in environment variables - email functionality will be disabled');
} else {
  // Initialize SendGrid with your API key
  sgMail.setApiKey(sendgridApiKey);
}

const app = express();

// Allow all CORS origins
app.use(cors());

// Setup Python environment on startup
const setupPythonEnvironment = () => {
  const { exec } = require('child_process');
  const path = require('path');
  
  console.log('Setting up Python environment...');
  const setupScript = path.join(__dirname, '..', 'setup.sh');
  
  exec(`chmod +x ${setupScript} && ${setupScript}`, (error, stdout, stderr) => {
    if (error) {
      console.warn('Python environment setup failed:', error.message);
      console.warn('Python-dependent features may not work properly');
    } else {
      console.log('Python environment setup completed');
      console.log(stdout);
    }
  });
};

// Run Python setup (non-blocking)
setupPythonEnvironment();

// Track failed authentication attempts for rate limiting warnings
const authFailures = new Map();
const AUTH_FAILURE_LIMIT = 5;
const AUTH_FAILURE_WINDOW = 5 * 60 * 1000; // 5 minutes

// API Key Authentication Middleware
const authenticateApiKey = (req, res, next) => {
  const apiKey = req.headers['x-api-key'] || req.headers['authorization']?.replace('Bearer ', '');
  const validApiKey = process.env.API_SECRET_KEY;
  const clientIP = req.ip || req.connection.remoteAddress || req.headers['x-forwarded-for'] || 'unknown';
  const userAgent = req.headers['user-agent'] || 'unknown';
  const endpoint = `${req.method} ${req.path}`;
  
  console.log(`[AUTH] ${endpoint} - IP: ${clientIP} - User-Agent: ${userAgent.substring(0, 100)}`);
  
  if (!validApiKey) {
    console.warn('[AUTH] API_SECRET_KEY not set - authentication disabled');
    return next();
  }
  
  if (!apiKey) {
    // Track failed attempts
    const now = Date.now();
    const failures = authFailures.get(clientIP) || [];
    const recentFailures = failures.filter(time => now - time < AUTH_FAILURE_WINDOW);
    recentFailures.push(now);
    authFailures.set(clientIP, recentFailures);
    
    console.warn(`[AUTH] 401 - Missing API key for ${endpoint} from IP: ${clientIP}`);
    console.warn(`[AUTH] Headers received:`, {
      'x-api-key': req.headers['x-api-key'] ? '[PRESENT]' : '[MISSING]',
      'authorization': req.headers['authorization'] ? '[PRESENT]' : '[MISSING]',
      'content-type': req.headers['content-type'],
      'origin': req.headers['origin']
    });
    
    if (recentFailures.length >= AUTH_FAILURE_LIMIT) {
      console.error(`[AUTH] 🚨 RATE LIMIT WARNING - IP ${clientIP} has ${recentFailures.length} failed auth attempts in the last 5 minutes`);
    }
    
    return res.status(401).json({
      success: false,
      error: 'API key required. Include x-api-key header or Authorization: Bearer <key>',
      debug: {
        endpoint,
        ip: clientIP,
        timestamp: new Date().toISOString()
      }
    });
  }
  
  if (apiKey !== validApiKey) {
    // Track failed attempts
    const now = Date.now();
    const failures = authFailures.get(clientIP) || [];
    const recentFailures = failures.filter(time => now - time < AUTH_FAILURE_WINDOW);
    recentFailures.push(now);
    authFailures.set(clientIP, recentFailures);
    
    console.warn(`[AUTH] 403 - Invalid API key for ${endpoint} from IP: ${clientIP}`);
    console.warn(`[AUTH] Provided key length: ${apiKey.length}, Expected length: ${validApiKey.length}`);
    console.warn(`[AUTH] Key starts with: ${apiKey.substring(0, 8)}...`);
    console.warn(`[AUTH] Expected key starts with: ${validApiKey.substring(0, 8)}...`);
    
    if (recentFailures.length >= AUTH_FAILURE_LIMIT) {
      console.error(`[AUTH] 🚨 RATE LIMIT WARNING - IP ${clientIP} has ${recentFailures.length} failed auth attempts in the last 5 minutes`);
    }
    
    return res.status(403).json({
      success: false,
      error: 'Invalid API key',
      debug: {
        endpoint,
        ip: clientIP,
        timestamp: new Date().toISOString()
      }
    });
  }
  
  console.log(`[AUTH] ✅ Success - ${endpoint} from IP: ${clientIP}`);
  next();
};

// Parse JSON and URL-encoded bodies (increase limits for in-memory research payloads)
app.use(bodyParser.json({ limit: '12mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '12mb' }));

// Memory-only generation toggle for JSON persistence
const SHOULD_PERSIST = process.env.GEN_PERSIST === '1';
console.log('[Persist] Generation JSON persist enabled:', SHOULD_PERSIST);

// In-memory progress tracker for services JSON generation
let servicesJsonProgress = {
  active: false,
  total: 0,
  completed: 0,
  details: [], // [{ category, id, name, status: 'pending'|'in_progress'|'completed' }]
  runId: null
};

// In-memory active logo (enhanced color) data URL to keep nav/footer in sync and ZIP-ready
let activeColorLogoDataUrl = null;

/**
 * Endpoint to handle booking form submissions
 * 
 * This endpoint:
 * 1. Receives booking data from the frontend form
 * 2. Validates required fields
 * 3. Constructs an email with the booking details
 * 4. Sends the email using SendGrid
 * 5. Returns a success or error response
 */
app.post("/submit-booking", authenticateApiKey, async (req, res) => {
  try {
    // Extract form data from request body
    const { firstName, lastName, email, phone, service, message, contactEmail } = req.body;
    
    // Get the origin URL from the request headers
    const originUrl = req.headers.origin || 'Unknown Origin';
    console.log('Booking request received from:', originUrl);
    
    // Validate required fields
    if (!firstName || !lastName || !email || !phone || !service) {
      return res.status(400).json({
        success: false,
        message: "Missing required fields"
      });
    }

    // Construct email content with HTML formatting
    const primaryTo = (typeof contactEmail === 'string' && contactEmail.trim()) ? contactEmail.trim() : 'devinstuddard@gmail.com';
    const msg = {
      to: primaryTo, // Recipient email (overridden by contactEmail when provided)
      from: 'info@cowboy-vaqueros.com', // Verified sender email in SendGrid
      subject: `New Booking Request: ${service}`,
      html: `
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
          <h2 style="color: #333;">New Booking Request</h2>
          
          <p><strong>Name:</strong> ${firstName} ${lastName}</p>
          <p><strong>Email:</strong> <a href="mailto:${email}">${email}</a></p>
          <p><strong>Phone:</strong> <a href="tel:${phone}">${phone}</a></p>
          <p><strong>Service:</strong> ${service}</p>
          <p><strong>Message:</strong> ${message || "No message provided"}</p>
          <p><strong>Submitted from:</strong> ${originUrl}</p>
          
          <p style="color: #666; font-size: 14px; margin-top: 20px;">This booking request was submitted from your website.</p>
          <p style="color: #666; font-size: 14px;">Please respond to the client via email or phone. CC if necessary.</p>
        </div>
      `,
      // Also include plain text version for email clients that don't support HTML
      text: `
New Booking Request

Name: ${firstName} ${lastName}
Email: ${email}
Phone: ${phone}
Service: ${service}
Message: ${message || "No message provided"}
Submitted from: ${originUrl}

This booking request was submitted from your website.
Please respond to the client via email or phone. CC if necessary.
      `
    };

    // Send first email
    if (sendgridApiKey) {
      await sgMail.send(msg);
      
      // Send second email to rhettburnham64@gmail.com
      const secondMsg = {
        ...msg,
        to: 'tiredthoughtles@gmail.com',
      };
      await sgMail.send(secondMsg);
      
      console.log('Booking emails sent successfully');
    } else {
      console.log('SendGrid not configured - skipping email sending');
    }
    
    // Log success and return response
    res.status(200).json({
      success: true,
      message: "Booking submitted successfully"
    });
  } catch (error) {
    // Log error details and return error response
    console.error('Error submitting booking:', error);
    res.status(500).json({
      success: false,
      message: "Server error",
      error: error.message || "Unknown error"
    });
  }
});

let scraperProcess = null;
let filterProcess = null;
let bbbScraperProcess = null;

app.post('/api/start-scraper', (req, res) => {
  const scriptPath = 'public/data/generation/leads/googlemaps_search.py';
  
  // Check if the script is already running
  if (scraperProcess) {
    console.log('Scraper process is already running.');
    res.status(200).json({ success: true, message: 'Scraper process is already running.' });
    return;
  }

  const pythonPath = 'public/data/generation/myenv/bin/python';

  try {
    console.log(`Starting script: ${pythonPath} ${scriptPath}`);
    const scraperProcess = spawn(pythonPath, [scriptPath], {
      detached: true,
      stdio: 'ignore',
      cwd: process.cwd(),
    });

    scraperProcess.on('error', (err) => {
      console.error('Failed to start scraper process:', err);
    });

    scraperProcess.unref();

    res.status(202).json({ success: true, message: 'Scraper process started.' });
  } catch (error) {
    console.error('Error spawning scraper process:', error);
    res.status(500).json({ success: false, message: 'Failed to start scraper process.' });
  }
});

app.post('/api/start-google-scraper', (req, res) => {
  const scriptPath = 'public/data/generation/leads/google_search/main.py';

  if (googleScraperProcess) {
    return res.status(200).json({ success: true, message: 'Google Scraper process is already running.' });
  }

  const pythonPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');

  try {
    if (!fs.existsSync(pythonPath)) {
      throw new Error(`Python interpreter not found at ${pythonPath}`);
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Script not found at ${scriptPath}`);
    }

    googleScraperProcess = exec(`${pythonPath} ${scriptPath}`, (error, stdout, stderr) => {
      googleScraperProcess = null; // Reset process when it finishes
      if (error) {
        console.error(`exec error: ${error}`);
        return;
      }
      console.log(`stdout: ${stdout}`);
      console.error(`stderr: ${stderr}`);
    });

    res.status(200).json({ success: true, message: 'Google Scraper process started.' });

  } catch (err) {
    console.error(`Execution setup error: ${err.message}`);
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post('/api/start-filter', (req, res) => {
  const scriptPath = 'public/data/generation/leads/google_search/children/google_filter.py';

  if (filterProcess) {
    return res.status(200).json({ success: true, message: 'Filter process is already running.' });
  }

  const pythonPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');

  try {
    if (!fs.existsSync(pythonPath)) {
      throw new Error(`Python interpreter not found at ${pythonPath}`);
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Script not found at ${scriptPath}`);
    }

    filterProcess = exec(`${pythonPath} ${scriptPath}`, (error, stdout, stderr) => {
      filterProcess = null; // Reset process when it finishes
      if (error) {
        console.error(`exec error: ${error}`);
        return;
      }
      console.log(`stdout: ${stdout}`);
      console.error(`stderr: ${stderr}`);
    });

    res.status(200).json({ success: true, message: 'Filter process started.' });

  } catch (err) {
    console.error(`Execution setup error: ${err.message}`);
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post('/api/start-bbb-scraper', (req, res) => {
  const scriptPath = 'public/data/generation/leads/BBB/bbb_bus.py';

  if (bbbScraperProcess) {
    return res.status(200).json({ success: true, message: 'BBB Scraper process is already running.' });
  }

  const pythonPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');

  try {
    if (!fs.existsSync(pythonPath)) {
      throw new Error(`Python interpreter not found at ${pythonPath}`);
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Script not found at ${scriptPath}`);
    }

    bbbScraperProcess = exec(`${pythonPath} ${scriptPath}`, (error, stdout, stderr) => {
      bbbScraperProcess = null; // Reset process when it finishes
      if (error) {
        console.error(`exec error: ${error}`);
        return;
      }
      console.log(`stdout: ${stdout}`);
      console.error(`stderr: ${stderr}`);
    });

    res.status(200).json({ success: true, message: 'BBB Scraper process started.' });

  } catch (err) {
    console.error(`Execution setup error: ${err.message}`);
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post('/api/run-lead-pipeline', (req, res) => {
    const { stateAbbr, startZip, endZip } = req.body;

    if (!stateAbbr || !startZip || !endZip) {
        return res.status(400).json({ error: 'State abbreviation, start ZIP, and end ZIP are required.' });
    }

    // Send immediate response to frontend
    res.status(200).json({ 
        success: true, 
        message: 'Lead generation pipeline started successfully.',
        stateAbbr,
        startZip,
        endZip
    });

    // Run the Python process asynchronously
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python'); // Use absolute path
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'leads', 'run_pipeline.py');
    const args = [scriptPath, stateAbbr, String(startZip), String(endZip)];

    console.log(`Executing: ${pythonExecutable} ${args.join(' ')}`);
    
    // Check if Python executable exists
    if (!fs.existsSync(pythonExecutable)) {
        console.error(`Python executable not found at: ${pythonExecutable}`);
        return;
    }
    
    // Check if script exists
    if (!fs.existsSync(scriptPath)) {
        console.error(`Script not found at: ${scriptPath}`);
        return;
    }

    const pythonProcess = spawn(pythonExecutable, args);

    pythonProcess.stdout.on('data', (data) => {
        console.log(`Pipeline STDOUT: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`Pipeline STDERR: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Pipeline process exited with code ${code}`);
        if (code === 0) {
            console.log('Lead generation pipeline completed successfully.');
        } else {
            console.error(`Pipeline process failed with exit code ${code}.`);
        }
    });

    pythonProcess.on('error', (err) => {
        console.error('Failed to start subprocess.', err);
    });
});

// BBB scraping endpoint
app.post('/api/run-bbb-scraping', (req, res) => {
    const { businessName, bbbUrl, leadId, leadData } = req.body;

    if (!businessName || !bbbUrl) {
        return res.status(400).json({ error: 'Business name and BBB URL are required.' });
    }

    // Send immediate response to frontend
    res.status(200).json({ 
        success: true, 
        message: 'BBB scraping process started successfully.',
        businessName,
        bbbUrl,
        leadId
    });

    // Run the BBB scraping process asynchronously
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_1', 'ScrapeBBB.py');
    
    // Create a temporary JSON file with the lead data for the script to use
    const tempLeadFile = path.join(__dirname, '..', 'public', 'data', 'output', 'individual', 'step_1', 'temp_selected_lead.json');
    
    // Ensure the directory exists
    const tempDir = path.dirname(tempLeadFile);
    if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir, { recursive: true });
    }
    
    // Write the selected lead data to a temporary file
    const leadDataForScript = {
        selectedLead: {
            BusinessName: businessName,
            BBB_url: bbbUrl,
            id: leadId,
            ...leadData
        }
    };
    
    try {
        fs.writeFileSync(tempLeadFile, JSON.stringify(leadDataForScript, null, 2));
        console.log(`[BBB Scraping] Created temporary lead file: ${tempLeadFile}`);
    } catch (error) {
        console.error(`[BBB Scraping] Error creating temporary lead file:`, error);
        return;
    }

    const args = [scriptPath, '--selected-lead', tempLeadFile];

    console.log(`[BBB Scraping] Executing: ${pythonExecutable} ${args.join(' ')}`);

    // Check if Python executable exists
    if (!fs.existsSync(pythonExecutable)) {
        console.error(`[BBB Scraping] Python executable not found at: ${pythonExecutable}`);
        return;
    }
    
    // Check if script exists
    if (!fs.existsSync(scriptPath)) {
        console.error(`[BBB Scraping] Script not found at: ${scriptPath}`);
        return;
    }

    const pythonProcess = spawn(pythonExecutable, args, {
        // Set environment variables for the browser window positioning
        env: {
            ...process.env,
            BBB_BROWSER_POSITION: 'right-quarter', // Custom env var for browser positioning
            BBB_HEADLESS: 'false' // Ensure non-headless mode
        }
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[BBB Scraping] STDOUT: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[BBB Scraping] STDERR: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`[BBB Scraping] Process exited with code ${code}`);
        
        // Clean up temporary file
        try {
            if (fs.existsSync(tempLeadFile)) {
                fs.unlinkSync(tempLeadFile);
                console.log(`[BBB Scraping] Cleaned up temporary file: ${tempLeadFile}`);
            }
        } catch (error) {
            console.error(`[BBB Scraping] Error cleaning up temporary file:`, error);
        }
        
        if (code === 0) {
            console.log('[BBB Scraping] BBB scraping process completed successfully.');
        } else {
            console.error(`[BBB Scraping] BBB scraping process failed with exit code ${code}.`);
        }
    });

    pythonProcess.on('error', (err) => {
        console.error('[BBB Scraping] Failed to start subprocess.', err);
        
        // Clean up temporary file on error
        try {
            if (fs.existsSync(tempLeadFile)) {
                fs.unlinkSync(tempLeadFile);
            }
        } catch (cleanupError) {
            console.error(`[BBB Scraping] Error cleaning up temporary file:`, cleanupError);
        }
    });
});

// Add reviews scrape route FIRST to ensure memory-only handler takes precedence
app.use('/backend', authenticateApiKey, reviewsScrapeRouter);
// Add scraping route (BBB + legacy review variants)
app.use('/backend', authenticateApiKey, scrapeBbbRouter);
// Add enhance logo route
app.use('/backend', authenticateApiKey, enhanceLogoRouter);
// Add generate logo route
app.use('/backend', authenticateApiKey, generateLogoRouter);
// Add business search route
app.use('/backend', authenticateApiKey, businessSearchRouter);
// Add extract colors route
app.use('/backend', authenticateApiKey, extractColorsRouter);
// Add yelp scrape route
app.use('/backend', authenticateApiKey, yelpScrapeRouter);

// Generate services JSON (memory-only) via Python
app.post('/backend/generate-services-json', authenticateApiKey, (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    console.log('[Services JSON] Starting generation');
    console.log('[Services JSON] OPENAI key present:', !!openaiKey);
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_3', 'generate_service_jsons.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    // Memory-only: require research JSON in body (no disk fallback)
    let researchPayload = req.body && req.body.researchJson ? req.body.researchJson : null;
    if (!researchPayload) {
      return res.status(400).json({ success: false, error: 'Missing researchJson in request body (memory-only flow).' });
    }
    if (!researchPayload) {
      return res.status(400).json({ success: false, error: 'Missing researchJson. Run Research step first.' });
    }

    // Initialize in-memory progress for 8 services (4 residential + 4 commercial expected)
    try {
      const residential = Array.isArray(researchPayload.residential) ? researchPayload.residential : [];
      const commercial = Array.isArray(researchPayload.commercial) ? researchPayload.commercial : [];
      const details = [];
      residential.forEach((s) => details.push({ category: 'residential', id: s.id, name: s.name, status: 'pending' }));
      commercial.forEach((s) => details.push({ category: 'commercial', id: s.id, name: s.name, status: 'pending' }));
      const runId = Date.now().toString();
      servicesJsonProgress = {
        active: true,
        total: details.length,
        completed: 0,
        details,
        runId
      };
      console.log('[Services JSON] Progress initialized:', { total: servicesJsonProgress.total });
    } catch (e) {
      console.warn('[Services JSON] Failed to initialize progress tracker:', e);
    }

    const child = spawn(pythonExecutable, [scriptPath], {
      cwd: path.dirname(scriptPath),
      env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' }
    });

    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (data) => {
      const text = data.toString();
      stdoutBuf += text;
      // Stream-parse progress: detect service starts/completions
      try {
        // When a line announces generation for a service, mark it in_progress
        // Example: "  - Generating blocks for Shingling"
        const genMatch = text.match(/Generating blocks for\s+(.+)/);
        if (genMatch && genMatch[1]) {
          const name = genMatch[1].trim();
          const found = servicesJsonProgress.details.find((d) => d.name === name && d.status === 'pending');
          if (found) found.status = 'in_progress';
        }
        // When AI composed blocks for a service, mark completed
        // Example: "[AI] Composed 6 blocks for Shingling"
        const composedRegex = /\[AI\]\s*Composed\s*\d+\s*blocks\s*for\s*(.+)/;
        const compMatch = text.match(composedRegex);
        if (compMatch && compMatch[1]) {
          const name = compMatch[1].trim();
          const found = servicesJsonProgress.details.find((d) => d.name === name && d.status !== 'completed');
          if (found) {
            found.status = 'completed';
            servicesJsonProgress.completed = Math.min(
              servicesJsonProgress.details.filter((d) => d.status === 'completed').length,
              servicesJsonProgress.total
            );
          }
        }
      } catch (e) {
        // ignore parse errors
      }
    });
    child.stderr.on('data', (data) => { stderrBuf += data.toString(); });

    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });

    child.on('close', (code) => {
      console.log('[Services JSON] Python process exited with code:', code);
      servicesJsonProgress.active = false;
      // If process exited successfully but some items not marked, finalize
      if (code === 0) {
        try {
          servicesJsonProgress.details.forEach((d) => {
            if (d.status !== 'completed') d.status = 'completed';
          });
          servicesJsonProgress.completed = servicesJsonProgress.total;
        } catch {}
      }
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }

      try {
        const start = stdoutBuf.indexOf('SERVICE_JSON_START');
        const end = stdoutBuf.indexOf('SERVICE_JSON_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'SERVICE_JSON_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Persist to generation folder so it is included in ZIP
          try {
            if (SHOULD_PERSIST) {
              const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_3');
              const outPath = path.join(outDir, 'services.json');
              fs.mkdirSync(outDir, { recursive: true });
              fs.writeFileSync(outPath, JSON.stringify(parsed, null, 2), 'utf-8');
              console.log('[Services JSON] Persisted services.json to', outPath);
            } else {
              console.log('[Services JSON] Memory-only mode: skipping persist');
            }
          } catch (persistErr) {
            console.warn('[Services JSON] Failed to persist services.json:', persistErr?.message || persistErr);
          }
          return res.status(200).json({ success: true, servicesJson: parsed, chatApiPresent: !!openaiKey, raw: process.env.DEBUG_SERVICES_JSON === '1' ? stdoutBuf : undefined });
        }
        // Fallback: try raw parse
        const parsed = JSON.parse(stdoutBuf);
        // Persist to generation folder so it is included in ZIP
        try {
          if (SHOULD_PERSIST) {
            const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_3');
            const outPath = path.join(outDir, 'services.json');
            fs.mkdirSync(outDir, { recursive: true });
            fs.writeFileSync(outPath, JSON.stringify(parsed, null, 2), 'utf-8');
            console.log('[Services JSON] Persisted services.json to', outPath);
          } else {
            console.log('[Services JSON] Memory-only mode: skipping persist (raw parse path)');
          }
        } catch (persistErr) {
          console.warn('[Services JSON] Failed to persist services.json (raw parse path):', persistErr?.message || persistErr);
        }
        return res.status(200).json({ success: true, servicesJson: parsed, chatApiPresent: !!openaiKey });
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });

    // Feed research JSON to the Python script via STDIN and close it so Python can proceed
    try {
      child.stdin.write(JSON.stringify(researchPayload));
      child.stdin.end();
    } catch (e) {
      console.error('[Services JSON] Failed to write researchJson to stdin:', e);
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Memory-only: Assign icons to service names (categories and services)
app.post('/backend/assign-service-icons', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_2', 'assign_service_icons.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('SERVICE_ICONS_START');
        const end = stdoutBuf.indexOf('SERVICE_ICONS_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'SERVICE_ICONS_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          return res.status(200).json({ success: true, ...parsed });
        }
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse icon output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
      return res.status(500).json({ success: false, error: 'Missing SERVICE_ICONS markers', stdout: stdoutBuf, stderr: stderrBuf });
    });
    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Image generation: Employee avatars using in-memory combined JSON
app.post('/backend/generate-employee-images', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'img', 'generate_employee_images.py');
    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }
    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('EMPLOYEE_IMAGES_BASE64_START');
        const end = stdoutBuf.indexOf('EMPLOYEE_IMAGES_BASE64_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'EMPLOYEE_IMAGES_BASE64_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          return res.status(200).json({ success: true, images: parsed });
        }
      } catch (e) {}
      return res.status(200).json({ success: true, raw: stdoutBuf });
    });
    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Persist hero image (data URL) to canonical generation path
app.post('/backend/persist-hero-image', (req, res) => {
  try {
    const dataUrl = req.body && req.body.dataUrl ? req.body.dataUrl : null;
    const requestedVirtualPath = req.body && typeof req.body.virtualPath === 'string' ? req.body.virtualPath : null;
    if (!dataUrl || typeof dataUrl !== 'string' || !dataUrl.startsWith('data:image/')) {
      return res.status(400).json({ success: false, error: 'Missing or invalid dataUrl' });
    }

    const match = dataUrl.match(/^data:image\/(png|jpeg|jpg);base64,(.+)$/i);
    if (!match) {
      return res.status(400).json({ success: false, error: 'Unsupported or invalid image data URL format' });
    }
    const ext = match[1].toLowerCase() === 'jpeg' ? 'jpg' : match[1].toLowerCase();
    const base64Data = match[2];
    const buffer = Buffer.from(base64Data, 'base64');

    // Default location
    let publicPath = `/data/generation/webgen/img/output/hero.${ext}`;
    // If a specific virtual path under /data/generation/webgen is provided, honor it
    if (requestedVirtualPath && requestedVirtualPath.startsWith('/data/generation/webgen/')) {
      // Normalize double slashes and ensure extension matches
      const norm = requestedVirtualPath.replace(/\\+/g, '/');
      const baseDir = norm.split('/').slice(0, -1).join('/');
      const baseName = norm.split('/').pop() || `hero.${ext}`;
      const fileBase = baseName.includes('.') ? baseName.slice(0, baseName.lastIndexOf('.')) : baseName;
      publicPath = `${baseDir}/${fileBase}.${ext}`;
    }

    const outPath = path.join(__dirname, '..', 'public', publicPath.replace(/^\/+/, ''));
    const outDir = path.dirname(outPath);

    try { fs.mkdirSync(outDir, { recursive: true }); } catch {}
    fs.writeFileSync(outPath, buffer);

    return res.status(200).json({ success: true, path: publicPath, filename: path.basename(outPath) });
  } catch (err) {
    console.error('[persist-hero-image] Error:', err);
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Track and persist the active color logo (data URL) for nav/footer previews and ZIP inclusion
app.post('/backend/set-active-logo', (req, res) => {
  try {
    const dataUrl = req.body && typeof req.body.dataUrl === 'string' ? req.body.dataUrl : null;
    if (!dataUrl || !dataUrl.startsWith('data:image/')) {
      return res.status(400).json({ success: false, error: 'Missing or invalid dataUrl' });
    }
    activeColorLogoDataUrl = dataUrl;
    return res.status(200).json({ success: true });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Fetch the current active color logo (if any) for UI previews
app.get('/backend/get-active-logo', (req, res) => {
  try {
    return res.status(200).json({ success: true, dataUrl: activeColorLogoDataUrl || null });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Progress endpoint for services JSON generation
app.get('/backend/services-json-progress', (req, res) => {
  try {
    return res.status(200).json({ success: true, ...servicesJsonProgress });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Generate combined_data.json (step_4)
app.post('/backend/generate-combined-data', (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    try {
      console.log('[Combined] Starting generation');
      console.log('[Combined] OPENAI key present:', !!openaiKey);
      const bodyKeys = req.body ? Object.keys(req.body) : [];
      console.log('[Combined] Incoming payload keys:', bodyKeys);
    } catch (e) {}
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_4', 'generate_combined_data.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' } });
    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (data) => { const t = data.toString(); stdoutBuf += t; });
    child.stderr.on('data', (data) => { const t = data.toString(); stderrBuf += t; });

    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });

    child.on('close', (code) => {
      try {
        console.log('[Combined] Python exited with code:', code);
        console.log('[Combined] STDOUT length:', (stdoutBuf || '').length, 'STDERR length:', (stderrBuf || '').length);
        if (code !== 0) {
          console.error('[Combined] STDERR tail:', (stderrBuf || '').slice(-600));
          console.error('[Combined] STDOUT head:', (stdoutBuf || '').slice(0, 600));
          return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf, stdoutPreview: (stdoutBuf || '').slice(0, 800) });
        }
      } catch (e) {}
      try {
        const start = stdoutBuf.indexOf('COMBINED_JSON_START');
        const end = stdoutBuf.indexOf('COMBINED_JSON_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'COMBINED_JSON_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Persist combined_data.json for ZIP inclusion (optional)
          try {
            if (SHOULD_PERSIST) {
              const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_4');
              const outPath = path.join(outDir, 'combined_data.json');
              fs.mkdirSync(outDir, { recursive: true });
              fs.writeFileSync(outPath, JSON.stringify(parsed, null, 2), 'utf-8');
              console.log('[Combined Data] Persisted combined_data.json to', outPath);
              try {
                const head = JSON.stringify(parsed, null, 2).split('\n').slice(0, 20).join('\n');
                console.log('[Combined Data] Preview (first 20 lines):\n' + head);
              } catch (e) {
                console.warn('[Combined Data] Failed to log preview head:', e?.message || e);
              }
            } else {
              console.log('[Combined Data] Memory-only mode: skipping persist');
            }
          } catch (persistErr) {
            console.warn('[Combined Data] Failed to persist combined_data.json:', persistErr?.message || persistErr);
          }
          return res.status(200).json({ success: true, combinedData: parsed, chatApiPresent: !!openaiKey });
        }
        console.warn('[Combined] Missing COMBINED_JSON markers. STDOUT head:', (stdoutBuf || '').slice(0, 400));
        return res.status(500).json({ success: false, error: 'Missing COMBINED_JSON markers', stdout: stdoutBuf, stderr: stderrBuf });
      } catch (e) {
        console.error('[Combined] Exception parsing output:', e?.message || e);
        return res.status(500).json({ success: false, error: `Failed to parse combined output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });

    // Memory-only: forward metadata payload to stdin
    try {
      const payload = JSON.stringify(req.body || {});
      console.log('[Combined] Writing STDIN payload bytes:', payload.length);
      child.stdin.write(payload);
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Generate about_page.json (step_3)
app.post('/backend/generate-about-page', (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_3', 'generate_about_page.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' } });
    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (data) => { stdoutBuf += data.toString(); });
    child.stderr.on('data', (data) => { stderrBuf += data.toString(); });

    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });

    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('ABOUT_JSON_START');
        const end = stdoutBuf.indexOf('ABOUT_JSON_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'ABOUT_JSON_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Persist about_page.json for ZIP inclusion (optional)
          try {
            if (SHOULD_PERSIST) {
              const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_3');
              const outPath = path.join(outDir, 'about_page.json');
              fs.mkdirSync(outDir, { recursive: true });
              fs.writeFileSync(outPath, JSON.stringify(parsed, null, 2), 'utf-8');
              console.log('[About Page] Persisted about_page.json to', outPath);
            } else {
              console.log('[About Page] Memory-only mode: skipping persist');
            }
          } catch (persistErr) {
            console.warn('[About Page] Failed to persist about_page.json:', persistErr?.message || persistErr);
          }
          return res.status(200).json({ success: true, aboutPage: parsed, chatApiPresent: !!openaiKey });
        }
        return res.status(500).json({ success: false, error: 'Missing ABOUT_JSON markers', stdout: stdoutBuf, stderr: stderrBuf });
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse about output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });

    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Generate nav.json (step_4)
app.post('/backend/generate-nav', (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_4', 'generate_nav.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' } });
    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (data) => { stdoutBuf += data.toString(); });
    child.stderr.on('data', (data) => { stderrBuf += data.toString(); });

    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });

    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('NAV_JSON_START');
        const end = stdoutBuf.indexOf('NAV_JSON_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'NAV_JSON_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Persist nav.json for ZIP inclusion (optional)
          try {
            if (SHOULD_PERSIST) {
              const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_4');
              const outPath = path.join(outDir, 'nav.json');
              fs.mkdirSync(outDir, { recursive: true });
              fs.writeFileSync(outPath, JSON.stringify(parsed, null, 2), 'utf-8');
              console.log('[Nav] Persisted nav.json to', outPath);
            } else {
              console.log('[Nav] Memory-only mode: skipping persist');
            }
          } catch (persistErr) {
            console.warn('[Nav] Failed to persist nav.json:', persistErr?.message || persistErr);
          }
          return res.status(200).json({ success: true, nav: parsed, chatApiPresent: !!openaiKey });
        }
        return res.status(500).json({ success: false, error: 'Missing NAV_JSON markers', stdout: stdoutBuf, stderr: stderrBuf });
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse nav output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });

    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Generate footer.json (deterministic)
app.post('/backend/generate-footer', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_4', 'generate_footer.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('FOOTER_JSON_START');
        const end = stdoutBuf.indexOf('FOOTER_JSON_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'FOOTER_JSON_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Persist footer.json for ZIP inclusion (optional)
          try {
            if (SHOULD_PERSIST) {
              const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_4');
              const outPath = path.join(outDir, 'footer.json');
              fs.mkdirSync(outDir, { recursive: true });
              fs.writeFileSync(outPath, JSON.stringify(parsed, null, 2), 'utf-8');
              console.log('[Footer] Persisted footer.json to', outPath);
            } else {
              console.log('[Footer] Memory-only mode: skipping persist');
            }
          } catch (persistErr) {
            console.warn('[Footer] Failed to persist footer.json:', persistErr?.message || persistErr);
          }
          return res.status(200).json({ success: true, footer: parsed });
        }
        return res.status(500).json({ success: false, error: 'Missing FOOTER_JSON markers', stdout: stdoutBuf, stderr: stderrBuf });
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse footer output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });
    // Write request body to stdin so Python can read memory-only payload
    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Run services image generation pipeline (writes files to /personal/generation paths and updates JSON)
app.post('/backend/generate-service-images', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_5', 'generate_service_images_pipeline.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    // Memory-only mode: if servicesJson provided, run the pipeline with STDIN and markers, no disk IO
    const servicesJsonInline = req.body && typeof req.body.servicesJson === 'object' ? req.body.servicesJson : null;
    const filterServiceId = req.body && (req.body.serviceId || req.body.filterServiceId);
    const filterServiceName = req.body && (req.body.serviceName || req.body.filterServiceName);
    const filterCategory = req.body && req.body.category; // optional: 'residential' | 'commercial'
    const dryRun = !!(req.body && req.body.dryRun);

    if (servicesJsonInline) {
      try {
        // Optionally reduce to a single service in-memory
        let isFilteredRun = false;
        let baseJson = JSON.parse(JSON.stringify(servicesJsonInline));
        let pickedCategory = null;
        let pickedIndex = -1;
        if (filterServiceId || filterServiceName) {
          ['residential', 'commercial'].forEach((cat) => {
            if (pickedIndex !== -1) return;
            if (filterCategory && filterCategory !== cat) return;
            const arr = Array.isArray(baseJson[cat]) ? baseJson[cat] : [];
            const idx = arr.findIndex((svc) => {
              if (!svc) return false;
              if (filterServiceId && svc.id && String(svc.id) === String(filterServiceId)) return true;
              if (filterServiceName && typeof svc.name === 'string' && svc.name.trim() === String(filterServiceName).trim()) return true;
              return false;
            });
            if (idx >= 0) { pickedCategory = cat; pickedIndex = idx; }
          });
          if (pickedIndex === -1 || !pickedCategory) {
            return res.status(400).json({ success: false, error: 'Service not found for filter', serviceId: filterServiceId || null, serviceName: filterServiceName || null });
          }
          const filtered = { residential: [], commercial: [] };
          filtered[pickedCategory] = [baseJson[pickedCategory][pickedIndex]];
          baseJson = filtered;
          isFilteredRun = true;
        }

        const args = [scriptPath, '--stdin', '--memory-only'];
        if (dryRun) args.push('--dry-run');
        const env = { ...process.env, MEMORY_ONLY: '1' };
        const child = spawn(pythonExecutable, args, { cwd: path.dirname(scriptPath), env });
        let stdoutBuf = '';
        let stderrBuf = '';
        child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
        child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
        child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
        child.on('close', (code) => {
          if (code !== 0) {
            return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf, stdout: stdoutBuf });
          }
          try {
            const start = stdoutBuf.indexOf('SERVICE_IMAGES_PIPELINE_START');
            const end = stdoutBuf.indexOf('SERVICE_IMAGES_PIPELINE_END');
            if (start !== -1 && end !== -1 && end > start) {
              const jsonStr = stdoutBuf.substring(start + 'SERVICE_IMAGES_PIPELINE_START'.length, end).trim();
              const parsed = JSON.parse(jsonStr);
              const updatedServices = parsed.services || parsed;
              const assets = Array.isArray(parsed.assets) ? parsed.assets : [];
              let merged = updatedServices;
              if (isFilteredRun) {
                try {
                  const full = JSON.parse(JSON.stringify(servicesJsonInline));
                  const cats = ['residential', 'commercial'];
                  for (const cat of cats) {
                    const arrUpd = Array.isArray(updatedServices[cat]) ? updatedServices[cat] : [];
                    if (arrUpd.length === 1) {
                      const updatedSvc = arrUpd[0];
                      const arrFull = Array.isArray(full[cat]) ? full[cat] : [];
                      const idxFull = arrFull.findIndex((svc) => (updatedSvc && svc && ((svc.id && updatedSvc.id && String(svc.id) === String(updatedSvc.id)) || (typeof svc.name === 'string' && typeof updatedSvc.name === 'string' && svc.name.trim() === updatedSvc.name.trim()))));
                      if (idxFull >= 0) { full[cat][idxFull] = updatedSvc; }
                    }
                  }
                  merged = full;
                } catch {}
              }
              return res.status(200).json({ success: true, message: 'Service images pipeline (memory) completed', services: merged, assets, filtered: isFilteredRun });
            }
          } catch (e) {
            return res.status(500).json({ success: false, error: `Failed to parse memory-only output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
          }
          return res.status(500).json({ success: false, error: 'Missing SERVICE_IMAGES_PIPELINE markers', stdout: stdoutBuf, stderr: stderrBuf });
        });
        try {
          child.stdin.write(JSON.stringify(baseJson));
          child.stdin.end();
        } catch (e) {
          return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
        }
        return;
      } catch (errInner) {
        return res.status(500).json({ success: false, error: errInner.message || 'Unknown error (memory-only path)' });
      }
    }

    // Disk mode (existing behavior)
    // Default input: raw_data/step_3/services.json (recently generated). Allow override.
    const defaultInput = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_3', 'services.json');
    const inputPath = (req.body && req.body.inputPath) || defaultInput;
    const outputPath = (req.body && req.body.outputPath) || inputPath; // overwrite by default

    let effectiveInput = inputPath;
    let effectiveOutput = outputPath;
    let isFilteredRun = false;

    if (filterServiceId || filterServiceName) {
      try {
        const raw = fs.readFileSync(inputPath, 'utf-8');
        const json = JSON.parse(raw);
        let pickedCategory = null;
        let pickedIndex = -1;
        ['residential', 'commercial'].forEach((cat) => {
          if (pickedIndex !== -1) return;
          if (filterCategory && filterCategory !== cat) return;
          const arr = Array.isArray(json[cat]) ? json[cat] : [];
          const idx = arr.findIndex((svc) => {
            if (!svc) return false;
            if (filterServiceId && svc.id && String(svc.id) === String(filterServiceId)) return true;
            if (filterServiceName && typeof svc.name === 'string' && svc.name.trim() === String(filterServiceName).trim()) return true;
            return false;
          });
          if (idx >= 0) {
            pickedCategory = cat;
            pickedIndex = idx;
          }
        });
        if (pickedIndex === -1 || !pickedCategory) {
          return res.status(400).json({ success: false, error: 'Service not found for filter', serviceId: filterServiceId || null, serviceName: filterServiceName || null });
        }

        const filtered = { residential: [], commercial: [] };
        filtered[pickedCategory] = [json[pickedCategory][pickedIndex]];

        const ts = Date.now();
        const baseDir = path.dirname(inputPath);
        const tempInput = path.join(baseDir, `services_tmp_in_${ts}_${Math.random().toString(36).slice(2)}.json`);
        const tempOutput = path.join(baseDir, `services_tmp_out_${ts}_${Math.random().toString(36).slice(2)}.json`);
        fs.writeFileSync(tempInput, JSON.stringify(filtered, null, 2), 'utf-8');
        effectiveInput = tempInput;
        effectiveOutput = tempOutput;
        isFilteredRun = true;
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to prepare filtered input: ${e.message}` });
      }
    }

    const args = [scriptPath, '--input', effectiveInput];
    if (effectiveOutput) { args.push('--output', effectiveOutput); }
    if (dryRun) { args.push('--dry-run'); }

    const child = spawn(pythonExecutable, args, { cwd: path.dirname(scriptPath), env: { ...process.env } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}` , stderr: stderrBuf, stdout: stdoutBuf});
      }

      // If filtered run, merge the updated service back into the original JSON
      if (isFilteredRun && !dryRun) {
        try {
          const rawFull = fs.readFileSync(inputPath, 'utf-8');
          const fullJson = JSON.parse(rawFull);
          const rawUpdated = fs.readFileSync(effectiveOutput, 'utf-8');
          const updatedJson = JSON.parse(rawUpdated);

          const cats = ['residential', 'commercial'];
          for (const cat of cats) {
            const arrUpd = Array.isArray(updatedJson[cat]) ? updatedJson[cat] : [];
            if (arrUpd.length === 1) {
              const updatedSvc = arrUpd[0];
              const arrFull = Array.isArray(fullJson[cat]) ? fullJson[cat] : [];
              const idxFull = arrFull.findIndex((svc) => (updatedSvc && svc && ((svc.id && updatedSvc.id && String(svc.id) === String(updatedSvc.id)) || (typeof svc.name === 'string' && typeof updatedSvc.name === 'string' && svc.name.trim() === updatedSvc.name.trim()))));
              if (idxFull >= 0) {
                fullJson[cat][idxFull] = updatedSvc;
              }
            }
          }

          fs.writeFileSync(inputPath, JSON.stringify(fullJson, null, 2), 'utf-8');

          // Cleanup temp files
          try { fs.unlinkSync(effectiveInput); } catch {}
          try { fs.unlinkSync(effectiveOutput); } catch {}
        } catch (mergeErr) {
          return res.status(500).json({ success: false, error: `Post-merge failed: ${mergeErr.message}`, stdout: stdoutBuf, stderr: stderrBuf });
        }
      }

      return res.status(200).json({ success: true, message: 'Service images pipeline completed', stdout: stdoutBuf, filtered: isFilteredRun });
    });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Image generation: Hero transition (residential ↔ urban) using memory-only BBB/profile data
app.post('/backend/generate-hero-image', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'img', 'generate_hero_transition.py');
    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }
    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('HERO_IMAGES_BASE64_START');
        const end = stdoutBuf.indexOf('HERO_IMAGES_BASE64_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'HERO_IMAGES_BASE64_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          return res.status(200).json({ success: true, images: parsed });
        }
      } catch (e) {
        // fall through
      }
      return res.status(200).json({ success: true, raw: stdoutBuf });
    });
    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Image generation: Material swatch (e.g., shingles) using memory-only payload
app.post('/backend/generate-swatch', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'img', 'generate_swatch.py');
    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }
    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('SWATCH_IMAGE_BASE64_START');
        const end = stdoutBuf.indexOf('SWATCH_IMAGE_BASE64_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'SWATCH_IMAGE_BASE64_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          return res.status(200).json({ success: true, image: parsed.output });
        }
      } catch (e) {}
      return res.status(200).json({ success: true, raw: stdoutBuf });
    });
    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Image generation: House with sign using memory-only BBB/profile data
app.post('/backend/generate-house-sign', (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'img', 'generate_house_with_sign.py');
    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }
    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('HOUSE_IMAGE_BASE64_START');
        const end = stdoutBuf.indexOf('HOUSE_IMAGE_BASE64_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'HOUSE_IMAGE_BASE64_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          return res.status(200).json({ success: true, image: parsed.output });
        }
      } catch (e) {}
      return res.status(200).json({ success: true, raw: stdoutBuf });
    });
    try {
      child.stdin.write(JSON.stringify(req.body || {}));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Generic image generation via Python helper (memory-only)
app.post('/backend/generate-generic-image', async (req, res) => {
  try {
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'img', 'generate_generic_image.py');
    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }
    const { prompt, size = '1024x1024', quality = 'medium', model = 'gpt-image-1' } = req.body || {};
    if (!prompt || typeof prompt !== 'string') {
      return res.status(400).json({ success: false, error: 'Missing prompt' });
    }
    const child = spawn(pythonExecutable, [scriptPath], { stdio: ['pipe', 'pipe', 'pipe'] });
    const payload = JSON.stringify({ prompt, size, quality, model });
    child.stdin.write(payload);
    child.stdin.end();
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: stderr || `Script exited with code ${code}` });
      }
      const start = stdout.indexOf('GENERIC_IMAGE_START');
      const end = stdout.indexOf('GENERIC_IMAGE_END');
      if (start === -1 || end === -1 || end <= start) {
        return res.status(500).json({ success: false, error: 'No image markers in output', stdout, stderr });
      }
      const jsonStr = stdout.slice(start + 'GENERIC_IMAGE_START'.length, end).trim();
      try {
        const parsed = JSON.parse(jsonStr);
        return res.json({ success: true, image: parsed.output });
      } catch (e) {
        return res.status(500).json({ success: false, error: 'Failed to parse image JSON', jsonStr });
      }
    });
  } catch (e) {
    return res.status(500).json({ success: false, error: e.message });
  }
});
// Image generation: Before/After batch (memory-only) using serviceNames context
app.post('/backend/generate-before-after-batch', (req, res) => {
  try {
    const openaiKeyPresent = !!process.env.OPENAI_API_KEY;
    try {
      console.log('[BeforeAfterBatch] OPENAI key present:', openaiKeyPresent);
      const svcLen = req.body && req.body.serviceNames ? JSON.stringify(req.body.serviceNames).length : 0;
      console.log('[BeforeAfterBatch] Incoming payload summary:', {
        hasServiceNames: !!req.body?.serviceNames,
        serviceNamesSize: svcLen,
        hasBBB: !!req.body?.bbbProfile,
        count: req.body?.count,
        quality: req.body?.quality,
        size: req.body?.size
      });
    } catch (e) {}
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'img', 'generate_before_after_batch.py');
    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }
    const child = spawn(pythonExecutable, [scriptPath], { cwd: path.dirname(scriptPath), env: { ...process.env, MEMORY_ONLY: '1' } });
    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` }));
    child.on('close', (code) => {
      if (code !== 0) {
      console.error('[BeforeAfterBatch] Python exited non-zero:', code);
      return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('BEFORE_AFTER_BATCH_START');
        const end = stdoutBuf.indexOf('BEFORE_AFTER_BATCH_END');
        if (start !== -1 && end !== -1 && end > start) {
        const jsonStr = stdoutBuf.substring(start + 'BEFORE_AFTER_BATCH_START'.length, end).trim();
        const parsed = JSON.parse(jsonStr);
        const items = Array.isArray(parsed.items) ? parsed.items : [];
        if (!items.length) {
          console.warn('[BeforeAfterBatch] Parsed markers but no items returned.');
        } else {
          console.log('[BeforeAfterBatch] Items returned:', items.length);
        }
        // Attach small debug previews to help diagnose silently-empty results
        const debug = {
          stderr: (stderrBuf || '').slice(-800),
          stdoutPreview: (stdoutBuf || '').slice(0, 400),
          stdoutTail: (stdoutBuf || '').slice(-800)
        };
        return res.status(200).json({ success: true, items, debug });
        }
      console.warn('[BeforeAfterBatch] Missing output markers. First 200 chars of stdout:', (stdoutBuf || '').slice(0, 200));
    } catch (e) {
      console.error('[BeforeAfterBatch] Exception parsing output:', e?.message || e);
    }
    // No markers — return structured error with previews for easier troubleshooting
    return res.status(500).json({ success: false, error: 'Missing BEFORE_AFTER markers', stderr: stderrBuf, stdoutPreview: (stdoutBuf || '').slice(0, 800) });
    });
    try {
      // Accept serviceNames, optional bbbProfile, desired count and quality
      let payload = {
        serviceNames: req.body && req.body.serviceNames ? req.body.serviceNames : null,
        bbbProfile: req.body && req.body.bbbProfile ? req.body.bbbProfile : null,
        count: req.body && req.body.count ? Number(req.body.count) : 60,
        quality: req.body && req.body.quality ? String(req.body.quality) : 'low',
        size: req.body && req.body.size ? String(req.body.size) : '1024x768'
      };
      // If serviceNames missing or empty, inject 8 random roofing services to allow LLM vetting to pass
      const ensureServiceNames = (sn) => {
        try {
          if (sn && typeof sn === 'object') return sn;
          const defaults = [
            'Shingling', 'Roof Repair', 'Roof Inspection', 'Gutter Installation',
            'Skylights', 'Metal Roofing', 'TPO Roofing', 'Coatings'
          ];
          const pick = (arr) => arr.map((name, i) => ({ id: i + 1, name }));
          return {
            universal: {
              residential: { services: pick(defaults.slice(0, 4)) },
              commercial: { services: pick(defaults.slice(4, 8)) }
            }
          };
        } catch {
          return sn;
        }
      };
      payload.serviceNames = ensureServiceNames(payload.serviceNames);
      child.stdin.write(JSON.stringify(payload));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Research services (step_2) - runs research_services.py
app.post('/backend/research-services', (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    console.log('[Research Services] Starting research');
    console.log('[Research Services] OPENAI key present:', !!openaiKey);
    try {
      const sn = req.body && req.body.serviceNames ? req.body.serviceNames : null;
      const li = req.body && req.body.locationInfo ? req.body.locationInfo : null;
      const resArr = Array.isArray(sn?.universal?.residential?.services) ? sn.universal.residential.services : [];
      const comArr = Array.isArray(sn?.universal?.commercial?.services) ? sn.universal.commercial.services : [];
      console.log('[Research Services] Incoming summary:', {
        hasServiceNames: !!sn,
        residentialCount: resArr.length,
        commercialCount: comArr.length,
        residentialIds: resArr.map((x) => x?.id).filter((v) => v != null),
        commercialIds: comArr.map((x) => x?.id).filter((v) => v != null),
        hasLocationInfo: !!li,
        locationInfoKeys: li ? Object.keys(li) : []
      });
      if (!li) {
        console.warn('[Research Services] locationInfo is null (frontend provided none). This will cause the Python script to error.');
      }
    } catch (e) {
      console.warn('[Research Services] Failed to log incoming summary:', e?.message || e);
    }
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_2', 'research_services.py');
    // Accept edited service names and feed to Python via stdin (memory-only)
    const editedNames = req.body && req.body.serviceNames ? req.body.serviceNames : null;
    const locationInfo = req.body && req.body.locationInfo ? req.body.locationInfo : null;

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const args = [scriptPath];
    const child = spawn(pythonExecutable, args, {
      env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' }
    });

    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (data) => { stdoutBuf += data.toString(); });
    child.stderr.on('data', (data) => { stderrBuf += data.toString(); });

    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });

    child.on('close', (code) => {
      console.log('[Research Services] Python process exited with code:', code);
      if (code !== 0) {
        console.error('[Research Services] STDERR tail:', (stderrBuf || '').slice(-800));
        console.error('[Research Services] STDOUT head:', (stdoutBuf || '').slice(0, 600));
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf, stdoutPreview: (stdoutBuf || '').slice(0, 800) });
      }
      // Attempt to parse research JSON from stdout; fall back to raw stdout
      let researchJson = null;
      try {
        // Try direct JSON parse first
        researchJson = JSON.parse(stdoutBuf);
      } catch (e1) {
        // Optional: look for markers if the script emits them
        try {
          const start = stdoutBuf.indexOf('RESEARCH_JSON_START');
          const end = stdoutBuf.indexOf('RESEARCH_JSON_END');
          if (start !== -1 && end !== -1 && end > start) {
            const jsonStr = stdoutBuf.substring(start + 'RESEARCH_JSON_START'.length, end).trim();
            researchJson = JSON.parse(jsonStr);
          }
        } catch (e2) {}
      }
      // Persist research JSON for step_3 fallback loader
      try {
        if (researchJson) {
          const outDir = path.join(__dirname, '..', 'public', 'data', 'output', 'individual', 'step_2');
          const outPath = path.join(outDir, 'services_research.json');
          fs.mkdirSync(outDir, { recursive: true });
          fs.writeFileSync(outPath, JSON.stringify(researchJson, null, 2), 'utf-8');
          console.log('[Research Services] Persisted research JSON to', outPath);
        }
      } catch (persistErr) {
        console.error('[Research Services] Failed to persist research JSON:', persistErr);
      }
      return res.status(200).json({ success: true, researchJson, stdout: stdoutBuf, stderr: stderrBuf, chatApiPresent: !!openaiKey });
    });

    // Write edited service names to stdin (memory-only flow)
    try {
      const payload = { serviceNames: editedNames, locationInfo };
      child.stdin.write(JSON.stringify(payload));
      child.stdin.end();
    } catch (e) {
      console.error('[Research Services] Failed to write to stdin:', e);
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Test DeepSeek API key presence (and optional live ping if fetch is available)
app.get('/backend/test-deepseek', async (req, res) => {
  try {
    const key = process.env.DEEPSEEK_API_KEY || process.env.DEEPSEEK_KEY;
    const present = !!key;
    let ping = null;
    if (present && typeof fetch === 'function') {
      try {
        const resp = await fetch('https://api.deepseek.com/v1/models', {
          method: 'GET',
          headers: { Authorization: `Bearer ${key}` }
        });
        ping = { ok: resp.ok, status: resp.status };
      } catch (e) {
        ping = { ok: false, error: e.message };
      }
    }
    return res.status(200).json({ success: true, present, ping });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Generate AI colors (memory-only). Optionally analyzes a provided chosenLogoUrl via vision.
app.post('/backend/generate-ai-colors', (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_2', 'generate_colors_with_ai.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], {
      cwd: path.dirname(scriptPath),
      env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' }
    });

    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', (d) => { stdoutBuf += d.toString(); });
    child.stderr.on('data', (d) => { stderrBuf += d.toString(); });
    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });
    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('AI_COLORS_JSON_START');
        const end = stdoutBuf.indexOf('AI_COLORS_JSON_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'AI_COLORS_JSON_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Persist colors to raw_data for ZIP inclusion
          try {
            const outDir = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data', 'step_2');
            const outPath = path.join(outDir, 'colors_output.json');
            fs.mkdirSync(outDir, { recursive: true });
            fs.writeFileSync(outPath, JSON.stringify(parsed.colors, null, 2), 'utf-8');
            console.log('[AI Colors] Persisted colors_output.json to', outPath);
          } catch (persistErr) {
            console.warn('[AI Colors] Failed to persist colors_output.json:', persistErr?.message || persistErr);
          }
          return res.status(200).json({ success: true, colors: parsed.colors, chatApiPresent: !!openaiKey });
        }
        // Fallback: try raw parse
        const parsed = JSON.parse(stdoutBuf);
        return res.status(200).json({ success: true, colors: parsed.colors || parsed, chatApiPresent: !!openaiKey });
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse AI colors output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });

    // Send chosen logo and optional business data to stdin
    try {
      const payload = {
        chosenLogoUrl: req.body && req.body.chosenLogoUrl ? req.body.chosenLogoUrl : null,
        businessData: req.body && req.body.businessData ? req.body.businessData : null
      };
      child.stdin.write(JSON.stringify(payload));
      child.stdin.end();
    } catch (e) {
      console.error('[AI Colors] Failed to write stdin payload:', e);
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Memory-only service names generation (runs Python with STDIN/STDOUT)
app.post('/backend/create-service-names', (req, res) => {
  try {
    const openaiKey = process.env.OPENAI_API_KEY;
    console.log('[Service Names] Starting generation');
    console.log('[Service Names] OPENAI key present:', !!openaiKey);
    const inputPayload = {
      yelpData: req.body && req.body.yelpData ? req.body.yelpData : {},
      bbbData: req.body && req.body.bbbData ? req.body.bbbData : {}
    };

    const pythonExecutable = path.join(__dirname, '..', 'public', 'data', 'generation', 'myenv', 'bin', 'python');
    const scriptPath = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'step_2', 'create_service_names.py');

    if (!fs.existsSync(pythonExecutable)) {
      return res.status(500).json({ success: false, error: `Python executable not found at ${pythonExecutable}` });
    }
    if (!fs.existsSync(scriptPath)) {
      return res.status(500).json({ success: false, error: `Script not found at ${scriptPath}` });
    }

    const child = spawn(pythonExecutable, [scriptPath], {
      cwd: path.dirname(scriptPath),
      env: { ...process.env, MEMORY_ONLY: '1', CHAT_API_PRESENT: openaiKey ? '1' : '0' }
    });
    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (data) => { stdoutBuf += data.toString(); });
    child.stderr.on('data', (data) => { stderrBuf += data.toString(); });

    child.on('error', (err) => {
      return res.status(500).json({ success: false, error: `Failed to start Python process: ${err.message}` });
    });

    child.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ success: false, error: `Python exited with code ${code}`, stderr: stderrBuf });
      }
      try {
        const start = stdoutBuf.indexOf('SERVICE_NAMES_START');
        const end = stdoutBuf.indexOf('SERVICE_NAMES_END');
        if (start !== -1 && end !== -1 && end > start) {
          const jsonStr = stdoutBuf.substring(start + 'SERVICE_NAMES_START'.length, end).trim();
          const parsed = JSON.parse(jsonStr);
          // Optional meta block
          let meta = null;
          const mStart = stdoutBuf.indexOf('SERVICE_NAMES_META_START');
          const mEnd = stdoutBuf.indexOf('SERVICE_NAMES_META_END');
          if (mStart !== -1 && mEnd !== -1 && mEnd > mStart) {
            try {
              const mStr = stdoutBuf.substring(mStart + 'SERVICE_NAMES_META_START'.length, mEnd).trim();
              meta = JSON.parse(mStr);
            } catch {}
          }
          return res.status(200).json({ success: true, serviceNames: parsed, meta, raw: process.env.DEBUG_SERVICE_NAMES === '1' ? stdoutBuf : undefined });
        }
        // Fallback: try raw parse
        const parsed = JSON.parse(stdoutBuf);
        return res.status(200).json({ success: true, serviceNames: parsed });
      } catch (e) {
        return res.status(500).json({ success: false, error: `Failed to parse output: ${e.message}`, stdout: stdoutBuf, stderr: stderrBuf });
      }
    });

    // Write input JSON to stdin and close
    try {
      child.stdin.write(JSON.stringify(inputPayload));
      child.stdin.end();
    } catch (e) {
      return res.status(500).json({ success: false, error: `Failed to write to stdin: ${e.message}` });
    }
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Analyze reviews via Python (memory-only)
app.post('/backend/analyze-reviews', (req, res) => {
  try {
    const reviews = req.body && Array.isArray(req.body.reviews) ? req.body.reviews : null;
    if (!reviews) {
      return res.status(400).json({ success: false, error: 'Missing reviews array in request body' });
    }

    // In-memory JS sentiment analysis (no Python dependency)
    const toNumber = (v) => {
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    };

    const analyzeOne = (r) => {
      const text = ((r && r.review_text) || '').toString();
      const ratingNum = toNumber(r && r.rating);

      // Keyword heuristic
      const lc = text.toLowerCase();
      const pos = ['great','excellent','good','amazing','love','awesome','fantastic','perfect','satisfied','recommend','professional'];
      const neg = ['bad','terrible','poor','awful','hate','horrible','worst','disappointed','unprofessional','late','rude'];
      let score = 0;
      pos.forEach((w) => { if (lc.includes(w)) score += 1; });
      neg.forEach((w) => { if (lc.includes(w)) score -= 1; });

      // Map rating to polarity contribution
      let ratingPol = 0;
      if (ratingNum !== null) {
        if (ratingNum >= 4) ratingPol = 0.6;
        else if (ratingNum <= 2) ratingPol = -0.6;
        else ratingPol = 0.0;
      }

      // Combine keyword score and rating
      const keywordPol = score > 0 ? 0.4 : score < 0 ? -0.4 : 0.0;
      const polarity = Math.max(-1, Math.min(1, ratingPol + keywordPol));

      let sentiment = 'neutral';
      if (polarity > 0.05) sentiment = 'positive';
      else if (polarity < -0.05) sentiment = 'negative';

      return {
        name: (r && r.name) || 'N/A',
        rating: (r && r.rating) || 'N/A',
        date: (r && r.date) || 'N/A',
        review_text: text,
        sentiment,
        polarity
      };
    };

    const analysis = reviews.map(analyzeOne);
    return res.status(200).json({ success: true, analysis });
  } catch (err) {
    console.error('[AnalyzeReviews] Unexpected server error:', err);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

// Health check endpoint (no auth required)
app.get("/health", (req, res) => {
  res.status(200).json({ status: "ok" });
});

// Test endpoint for lead generation
app.get("/api/test-lead-pipeline", authenticateApiKey, (req, res) => {
  res.status(200).json({ 
    success: true, 
    message: 'Lead generation test endpoint is working.',
    timestamp: new Date().toISOString()
  });
});

// Persist colors_output.json for generation ZIP
app.post('/backend/save-colors', (req, res) => {
  try {
    const colors = req.body && req.body.colors ? req.body.colors : null;
    if (!colors || typeof colors !== 'object') {
      return res.status(400).json({ success: false, error: 'Missing or invalid colors payload' });
    }

    const outDir = path.join(__dirname, '..', 'public', 'personal', 'generation', 'jsons');
    const outPath = path.join(outDir, 'colors_output.json');
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(colors, null, 2), 'utf-8');
    return res.status(200).json({ success: true, path: outPath });
  } catch (err) {
    console.error('[save-colors] Error:', err);
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Save service_names.json to generation folder
app.post('/backend/save-service-names', (req, res) => {
  try {
    const serviceNames = req.body && req.body.serviceNames ? req.body.serviceNames : null;
    if (!serviceNames || typeof serviceNames !== 'object') {
      return res.status(400).json({ success: false, error: 'Missing or invalid serviceNames payload' });
    }
    const outDir = path.join(__dirname, '..', 'public', 'personal', 'generation', 'jsons');
    const outPath = path.join(outDir, 'service_names.json');
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(serviceNames, null, 2), 'utf-8');
    return res.status(200).json({ success: true, path: outPath });
  } catch (err) {
    console.error('[save-service-names] Error:', err);
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Download a ZIP of the generation folder
app.get('/backend/download-generation-zip', async (req, res) => {
  try {
    // Prepare canonical JSONs in personal/generation/jsons before streaming
    const canonicalDir = path.join(__dirname, '..', 'public', 'personal', 'generation', 'jsons');
    const rawBase = path.join(__dirname, '..', 'public', 'data', 'generation', 'webgen', 'raw_data');
    const mappings = [
      { src: path.join(rawBase, 'step_4', 'combined_data.json'), dest: path.join(canonicalDir, 'combined_data.json') },
      { src: path.join(rawBase, 'step_3', 'about_page.json'), dest: path.join(canonicalDir, 'about_page.json') },
      { src: path.join(rawBase, 'step_4', 'nav.json'), dest: path.join(canonicalDir, 'nav.json') },
      { src: path.join(rawBase, 'step_4', 'footer.json'), dest: path.join(canonicalDir, 'footer.json') },
      // Include generated services JSON (but intentionally exclude research outputs)
      { src: path.join(rawBase, 'step_3', 'services.json'), dest: path.join(canonicalDir, 'services.json') },
    ];
    try {
      fs.mkdirSync(canonicalDir, { recursive: true });
      mappings.forEach(({ src, dest }) => {
        try {
          if (fs.existsSync(src)) {
            fs.copyFileSync(src, dest);
          }
        } catch (e) {
          console.warn('[ZIP prepare] Failed to copy', src, '->', dest, e?.message || e);
        }
      });
    } catch (prepErr) {
      console.warn('[ZIP prepare] Could not prepare canonical jsons:', prepErr?.message || prepErr);
    }

    const generationDir = path.join(__dirname, '..', 'public', 'data', 'generation');
    if (!fs.existsSync(generationDir)) {
      return res.status(404).json({ success: false, error: `Generation folder not found at ${generationDir}` });
    }

    const now = new Date();
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const timeStr = `${String(now.getHours()).padStart(2, '0')}-${String(now.getMinutes()).padStart(2, '0')}`;
    const filename = `generation_${dateStr}_${timeStr}.zip`;

    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);

    const archive = archiver('zip', { zlib: { level: 9 } });
    archive.on('error', (err) => {
      console.error('[Download ZIP] Archiver error:', err);
      // Avoid sending headers twice
      if (!res.headersSent) {
        res.status(500).json({ success: false, error: err.message || 'Archiver error' });
      } else {
        res.end();
      }
    });

    archive.pipe(res);
    archive.directory(generationDir, 'generation');

    // If an active color logo is present, include it under generation/img/nav/logo.svg and generation/img/footer/logo.svg
    try {
      if (activeColorLogoDataUrl && typeof activeColorLogoDataUrl === 'string' && activeColorLogoDataUrl.startsWith('data:image/')) {
        const match = activeColorLogoDataUrl.match(/^data:image\/(png|jpeg|jpg|svg\+xml);base64,(.+)$/i);
        if (match) {
          const ext = match[1].toLowerCase() === 'jpeg' ? 'jpg' : (match[1].toLowerCase().startsWith('svg') ? 'svg' : match[1].toLowerCase());
          const buffer = Buffer.from(match[2], 'base64');
          const logoFilename = `logo.${ext}`;
          archive.append(buffer, { name: `generation/img/nav/${logoFilename}` });
          archive.append(buffer, { name: `generation/img/footer/${logoFilename}` });
        }
      }
    } catch (e) {
      console.warn('[Download ZIP] Failed to embed active logo:', e?.message || e);
    }
    await archive.finalize();
  } catch (err) {
    console.error('[Download ZIP] Unexpected error:', err);
    return res.status(500).json({ success: false, error: err.message || 'Unknown error' });
  }
});

// Start the server
const PORT = process.env.PORT || 5001;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Using SendGrid for email delivery`);
});

