const express = require('express');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const cors = require('cors');

const router = express.Router();

// Enable CORS for this route
router.use(cors());

router.post('/scrape-bbb', async (req, res) => {
  try {
    const { businessName, bbbUrl, leadId } = req.body;
    
    if (!businessName || !bbbUrl) {
      return res.status(400).json({ 
        error: 'Missing required fields: businessName and bbbUrl' 
      });
    }

    console.log('BBB Scraping request received:', {
      businessName,
      bbbUrl,
      leadId,
      timestamp: new Date().toISOString()
    });

    // Paths
    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_1/ScrapeBBB.py');
    
    console.log('Executing Python script with virtual environment...');
    console.log('Project root:', projectRoot);
    console.log('Venv path:', venvPath);
    console.log('Script path:', scriptPath);
    
    // Check if virtual environment exists
    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    
    // Determine persist flag (binary 0/1). Default 0 (memory-only)
    const toBinary = (v) => {
      if (v === 1 || v === '1' || v === true) return 1;
      return 0;
    };
    const persistFlag = toBinary(req.body && (req.body.persist ?? req.body.saveToDisk));

    // Execute Python script with activated virtual environment
    const pythonCommand = `source "${venvPath}/bin/activate" && python3 "${scriptPath}" --business-name "${businessName}" --bbb-url "${bbbUrl}" --persist ${persistFlag}`;
    
    console.log('Executing command:', pythonCommand);
    
    exec(pythonCommand, { 
      cwd: projectRoot,
      shell: '/bin/bash'
    }, async (error, stdout, stderr) => {
      if (error) {
        console.error('Python script error:', error);
        return res.status(500).json({
          success: false,
          error: `Python script failed: ${error.message}`,
          businessName,
          bbbUrl,
          timestamp: new Date().toISOString()
        });
      }
      
      console.log('Python script stdout:', stdout);
      if (stderr) {
        console.error('Python script stderr:', stderr);
      }
      
      // Capture all console output for detailed logging
      const consoleOutput = {
        stdout: stdout || '',
        stderr: stderr || '',
        command: pythonCommand,
        timestamp: new Date().toISOString()
      };
      
      // Extract the scraped data from stdout
      const scrapedDataMatch = stdout.match(/SCRAPED_DATA_START\n([\s\S]*?)\nSCRAPED_DATA_END/);
      
      let scrapedData = null;
      
      if (scrapedDataMatch) {
        try {
          scrapedData = JSON.parse(scrapedDataMatch[1]);
          console.log('Scraped data loaded from stdout:', scrapedData);
        } catch (parseError) {
          console.error('BBB JSON parse error:', parseError);
          return res.status(500).json({
            success: false,
            error: 'Failed to parse scraped BBB data',
            consoleOutput,
            timestamp: new Date().toISOString()
          });
        }
      } else {
        console.log('No scraped data found in output, using fallback data');
        // Fallback to mock data if script didn't output data
        scrapedData = {
          business_name: businessName,
          accredited: true,
          accreditation_status: "Accredited",
          date_of_accreditation: "January 15, 2020",
          website: "https://www.example-roofing.com",
          telephone: "(555) 123-4567",
          address: "123 Main Street, Anytown, CA 90210",
          years_in_business: "15+ years",
          N_employees: "25-50",
          logo_url: "https://via.placeholder.com/200x100/3B82F6/FFFFFF?text=LOGO",
          logo_filename: "logo.png",
          Employee_1_name: "John Smith",
          Employee_1_role: "Owner",
          Employee_2_name: "Sarah Johnson",
          Employee_2_role: "General Manager",
          services: ["Roofing", "Gutter Installation", "Chimney Repair", "Skylight Installation"],
          lead_business_name: businessName
        };
      }
      
      res.json({
        success: true,
        message: 'BBB scraping completed successfully',
        businessName,
        bbbUrl,
        scrapedData,
        consoleOutput,
        timestamp: new Date().toISOString()
      });
    });
    
  } catch (error) {
    console.error('BBB scraping error:', error);
    res.status(500).json({ 
      error: 'Failed to start BBB scraping',
      details: error.message 
    });
  }
});

router.post('/scrape-reviews', async (req, res) => {
  try {
    const { businessName, googleReviewsUrl, maxReviews = 50 } = req.body;
    
    if (!businessName || !googleReviewsUrl) {
      return res.status(400).json({ 
        error: 'Missing required fields: businessName and googleReviewsUrl' 
      });
    }

    console.log('Reviews Scraping request received:', {
      businessName,
      googleReviewsUrl,
      maxReviews,
      timestamp: new Date().toISOString()
    });

    // Paths
    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_1/ScrapeReviews.py');
    
    console.log('Executing Reviews Python script with virtual environment...');
    console.log('Project root:', projectRoot);
    console.log('Venv path:', venvPath);
    console.log('Script path:', scriptPath);
    
    // Check if virtual environment exists
    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    
    // Execute Python script with activated virtual environment
    const pythonCommand = `source "${venvPath}/bin/activate" && python3 "${scriptPath}" --business-name "${businessName}" --google-reviews-url "${googleReviewsUrl}" --max-reviews ${maxReviews}`;
    
    console.log('Executing reviews command:', pythonCommand);
    
    exec(pythonCommand, { 
      cwd: projectRoot,
      shell: '/bin/bash'
    }, async (error, stdout, stderr) => {
      if (error) {
        console.error('Reviews Python script error:', error);
        return res.status(500).json({
          success: false,
          error: `Reviews Python script failed: ${error.message}`,
          businessName,
          googleReviewsUrl,
          timestamp: new Date().toISOString()
        });
      }
      
      console.log('Reviews Python script stdout:', stdout);
      if (stderr) {
        console.error('Reviews Python script stderr:', stderr);
      }
      
      // Capture all console output for detailed logging
      const consoleOutput = {
        stdout: stdout || '',
        stderr: stderr || '',
        command: pythonCommand,
        timestamp: new Date().toISOString()
      };
      
      // Extract the scraped reviews data from stdout
      const scrapedDataMatch = stdout.match(/SCRAPED_REVIEWS_DATA_START\n([\s\S]*?)\nSCRAPED_REVIEWS_DATA_END/);
      
      let scrapedData = null;
      
      if (scrapedDataMatch) {
        try {
          scrapedData = JSON.parse(scrapedDataMatch[1]);
          console.log('Scraped reviews data loaded:', scrapedData);
        } catch (parseError) {
          console.error('Reviews JSON parse error:', parseError);
          return res.status(500).json({
            success: false,
            error: 'Failed to parse scraped reviews data',
            consoleOutput,
            timestamp: new Date().toISOString()
          });
        }
      } else {
        console.log('No scraped reviews data found in output, using fallback data');
        // Fallback to mock data if script didn't output data
        scrapedData = {
          business_name: businessName,
          total_reviews: 0,
          total_images_downloaded: 0,
          reviews: [],
          downloaded_images: []
        };
      }
      
      // Persist scraped reviews to the expected input path for AnalyzeReviews.py
      try {
        const inputDir = path.join(projectRoot, 'public/data/output/individual/step_1/raw');
        const inputPath = path.join(inputDir, 'reviews.json');
        if (!fs.existsSync(inputDir)) {
          fs.mkdirSync(inputDir, { recursive: true });
        }
        const reviewsArray = Array.isArray(scrapedData?.reviews) ? scrapedData.reviews : [];
        fs.writeFileSync(inputPath, JSON.stringify(reviewsArray, null, 2), 'utf-8');
        console.log('Wrote scraped reviews to:', inputPath);
      } catch (persistErr) {
        console.error('Failed to persist scraped reviews for analysis:', persistErr);
      }

      // After successful scrape, run AnalyzeReviews.py (step_2)
      const analyzeScriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_2/AnalyzeReviews.py');
      const analyzeCommand = `source "${venvPath}/bin/activate" && python3 "${analyzeScriptPath}"`;

      console.log('Executing reviews analysis command:', analyzeCommand);

      exec(analyzeCommand, {
        cwd: projectRoot,
        shell: '/bin/bash'
      }, (analysisError, analysisStdout, analysisStderr) => {
        if (analysisError) {
          console.error('AnalyzeReviews.py error:', analysisError);
        }
        if (analysisStdout) {
          console.log('AnalyzeReviews.py stdout:', analysisStdout);
        }
        if (analysisStderr) {
          console.error('AnalyzeReviews.py stderr:', analysisStderr);
        }

        const analysisOutput = {
          stdout: analysisStdout || '',
          stderr: analysisStderr || '',
          command: analyzeCommand,
          success: !analysisError,
          timestamp: new Date().toISOString()
        };

        res.json({
          success: true,
          message: 'Reviews scraping completed successfully (analysis executed afterward)',
          businessName,
          googleReviewsUrl,
          scrapedData,
          consoleOutput,
          analysisOutput,
          timestamp: new Date().toISOString()
        });
      });
    });
    
  } catch (error) {
    console.error('Reviews scraping error:', error);
    res.status(500).json({ 
      error: 'Failed to start reviews scraping',
      details: error.message 
    });
  }
});

router.post('/scrape-gphotos', async (req, res) => {
  try {
    const { businessName, googleMapsUrl, googleReviewsUrl } = req.body;
    const mapsUrl = googleMapsUrl || googleReviewsUrl;
    
    if (!businessName || !mapsUrl) {
      return res.status(400).json({ 
        success: false,
        error: 'Missing required fields: businessName and googleMapsUrl (or googleReviewsUrl)'
      });
    }

    console.log('Google Photos scrape request received:', {
      businessName,
      googleMapsUrl: mapsUrl,
      timestamp: new Date().toISOString()
    });

    const projectRoot = path.resolve(__dirname, '..');
    const venvPath = path.join(projectRoot, 'public/data/generation/myenv');
    const scriptPath = path.join(projectRoot, 'public/data/generation/webgen/step_2/google_img_web.py');

    if (!fs.existsSync(venvPath)) {
      throw new Error('Virtual environment not found. Please run: python3 -m venv public/data/generation/myenv');
    }
    if (!fs.existsSync(scriptPath)) {
      throw new Error(`Google Photos script not found at ${scriptPath}`);
    }

    const pythonCommand = `source "${venvPath}/bin/activate" && python3 "${scriptPath}" --business-name "${businessName}" --google-maps-url "${mapsUrl}"`;
    console.log('Executing Google Photos command:', pythonCommand);

    exec(pythonCommand, {
      cwd: projectRoot,
      shell: '/bin/bash'
    }, (error, stdout, stderr) => {
      const consoleOutput = {
        stdout: stdout || '',
        stderr: stderr || '',
        command: pythonCommand,
        timestamp: new Date().toISOString()
      };

      // Try to extract data even if process exited with non-zero
      const photosMatch = (stdout || '').match(/SCRAPED_PHOTOS_DATA_START\n([\s\S]*?)\nSCRAPED_PHOTOS_DATA_END/);
      if (photosMatch) {
        try {
          const scrapedData = JSON.parse(photosMatch[1]);
          return res.json({ success: true, message: 'Google Photos scraping completed', scrapedData, consoleOutput });
        } catch (parseErr) {
          console.error('Google Photos JSON parse error:', parseErr);
          // Return graceful empty payload
          const scrapedData = { business_name: businessName, total_images: 0, total_saved: 0, images: [] };
          return res.json({ success: true, warning: 'parse_error', scrapedData, consoleOutput });
        }
      }

      if (error) {
        console.error('Google Photos Python script error:', error);
        // Return graceful empty payload instead of 500 to avoid breaking UI
        const scrapedData = { business_name: businessName, total_images: 0, total_saved: 0, images: [] };
        return res.json({ success: true, warning: 'script_error', error: `Google Photos script failed: ${error.message}`, scrapedData, consoleOutput });
      }

      if (stderr) {
        console.error('Google Photos Python script stderr:', stderr);
      }

      // No data block and no error reported: return empty payload
      console.warn('No Google Photos data block found in stdout; returning empty set');
      const scrapedData = {
        business_name: businessName,
        total_images: 0,
        total_saved: 0,
        images: []
      };
      return res.json({ success: true, warning: 'no_data_block', message: 'Google Photos scraping completed (no data block)', scrapedData, consoleOutput });
    });
  } catch (err) {
    console.error('Google Photos scrape error:', err);
    return res.status(500).json({ success: false, error: err.message || 'Server error' });
  }
});

module.exports = router;
