# Step 3: Content Generation and Image Processing Scripts

This folder contains Python scripts that generate website content and process images for the roofing company website. These scripts build upon the data collected in Steps 1 and 2 to create structured content for various website sections.

## Files Overview

### 1. `generate_about_page.py`

This script generates professional content for the company's about page, including company history, mission statement, core values, and team information.

**Functionality:**
- Reads company data from previous steps (combined_data.json or bbb_profile_data.json)
- Generates professional, context-aware content sections:
  - Company history
  - Mission statement
  - Core values
  - Team member information
  - Company statistics
- Creates a structured JSON output with all about page content
- Includes a "steps" section for the company's process visualization

**Output:** `raw_data/step_3/about_page.json`
```json
{
  "title": "Company Name: City's Trusted Roofing Experts",
  "subtitle": "Building Strong Roofs, Stronger Relationships",
  "history": "Company history content...",
  "mission": "Mission statement...",
  "values": [
    {
      "title": "Value Name",
      "description": "Value description..."
    }
  ],
  "team": [...],
  "stats": [...],
  "steps": [
    {
      "title": "Step Name",
      "videoSrc": "/assets/videos/...",
      "href": "link",
      "scale": 1.0
    }
  ]
}
```

### 2. `generate_service_jsons.py`

This script creates detailed content for each roofing service offered by the company, using AI-powered content generation when available.

**Functionality:**
- Loads existing service data from previous steps
- Uses DeepSeek API (if available) to generate service-specific content
- Creates structured content for both residential and commercial services
- Generates SEO-friendly slugs for service pages
- Produces detailed service descriptions, benefits, and features
- Falls back to predefined content if AI generation is unavailable

**Dependencies:**
- DeepSeek API key (optional, in `.env.deepseek` file)
- `requests` library for API calls
- `python-dotenv` for environment variable management

**Output:** 
- `raw_data/step_2/roofing_services.json` (service definitions)
- `raw_data/step_3/services/*.json` (individual service content files)

### 3. `clipimage.py`

A utility script that processes the company logo for better web display by removing backgrounds and optimizing for transparency.

**Functionality:**
- Loads the original logo from step_1
- Converts the image to grayscale
- Applies thresholding to create transparency
- Preserves alpha channel information
- Outputs processed images in multiple locations for other scripts

**Dependencies:**
- OpenCV (`cv2`)
- NumPy

**Input:** `raw_data/step_1/logo.png`  
**Outputs:** 
- `raw_data/step_3/clipped.png`
- `raw_data/clipped.png` (copy for other scripts)

## Data Flow

1. **Input Data** (from previous steps):
   - `raw_data/step_1/bbb_profile_data.json`
   - `raw_data/step_1/logo.png`
   - `raw_data/step_4/combined_data.json` (if available)

2. **Processing** (Step 3 - Current Stage):
   - Generation of about page content
   - Creation of detailed service descriptions
   - Processing of company logo
   - AI-powered content enhancement (when available)

3. **Output Data** (for website generation):
   - About page content in JSON format
   - Service descriptions in JSON format
   - Processed logo images

## Dependencies

The scripts require these Python packages:
```
opencv-python
numpy
requests
python-dotenv
```

Install dependencies with:
```bash
pip install opencv-python numpy requests python-dotenv
```

## Usage

1. **Generate About Page Content:**
```bash
python generate_about_page.py
```

2. **Generate Service Content:**
```bash
python generate_service_jsons.py
```

3. **Process Logo Image:**
```bash
python clipimage.py
```

Note: For optimal results, run the scripts in order after completing steps 1 and 2. The scripts will automatically create necessary directories and handle missing data gracefully. 