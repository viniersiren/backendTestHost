# Complete Website Generation Process

This README documents the comprehensive website generation process for roofing companies. The process consists of two distinct phases: **Lead Generation** and **Website Generation**.

## Overview

The generation system creates professional roofing company websites from minimal initial data by:
1. Generating qualified business leads
2. Scraping business data from various sources
3. Processing and enhancing the data using AI
4. Generating complete website content and configurations

---

## Prerequisites: Virtual Environment Setup (REQUIRED)

**CRITICAL FIRST STEP**: Before running any generation scripts, you MUST activate the Python virtual environment:

```bash
cd /Users/rhettburnham/Desktop/projects/roofing-co/public/data/generation
source myenv/bin/activate
```

This virtual environment contains all required Python packages and dependencies for both lead generation and website generation phases.

**Note**: All subsequent commands and scripts in this README assume the virtual environment is activated. If you encounter import errors or missing packages, ensure the virtual environment is properly activated.

---

## Phase 1: Lead Generation (`data/generation/leads/`)

The lead generation phase identifies and qualifies potential roofing businesses that lack professional websites. These businesses become prime candidates for website generation services.

### Directory Structure
```
data/generation/leads/
├── google_search/
│   ├── main.py                    # Orchestrates Google Maps search and filtering
│   └── children/
│       ├── googlemaps_search.py   # Scrapes roofing businesses from Google Maps
│       └── google_filter.py       # Filters businesses without websites
├── BBB/
│   ├── bbb_bus.py                 # Searches BBB for business profiles
│   └── filtering_for_bbb.py       # Final filtering for BBB-verified businesses
├── run_pipeline.py                # Main entry point for lead generation
└── README.md                      # Lead generation documentation
```

### Process Flow

#### Step 1: Google Maps Business Discovery
- **Script**: `google_search/main.py`
- **Function**: Discovers roofing businesses in specified ZIP code ranges
- **Input**: State abbreviation, ZIP code range
- **Process**:
  1. `googlemaps_search.py` searches Google Maps for "Roofing [ZIP], [STATE]"
  2. Scrolls through all results to collect comprehensive business data
  3. Extracts business names, addresses, phone numbers, ratings, and website URLs
  4. `google_filter.py` filters to keep only businesses with names but NO websites
- **Output**: `data/output/leads/raw/google_filter.json`

#### Step 2: BBB Profile Verification
- **Script**: `BBB/bbb_bus.py`
- **Function**: Verifies business legitimacy through BBB profiles
- **Input**: `google_filter.json` from Step 1
- **Process**:
  1. Searches BBB website for each business from the filtered list
  2. Extracts BBB profile URLs, ratings, and contact information
  3. Matches businesses with their BBB profiles for credibility verification
- **Output**: `data/output/leads/raw/bbb_match.json`

#### Step 3: Final Lead Qualification
- **Script**: `BBB/filtering_for_bbb.py`
- **Function**: Creates final qualified lead list
- **Input**: `bbb_match.json` from Step 2
- **Process**: Filters to keep only businesses with valid BBB profiles
- **Output**: `data/output/leads/final/final_leads.json`

### Usage
```bash
# Activate virtual environment
source public/data/generation/myenv/bin/activate

# Generate leads for Georgia ZIP codes 30002-30004
python public/data/generation/leads/run_pipeline.py GA 30002 30004
```

### Final Lead Output
Qualified leads contain:
- Business name and contact information
- Google Reviews link (for content generation)
- BBB profile link (for credibility verification)
- Location data
- Verified absence of existing website

---

## Phase 2: Website Generation (`data/generation/webgen/`)

**REMINDER**: Ensure the virtual environment is activated before running any step:
```bash
source /Users/rhettburnham/Desktop/projects/roofing-co/public/data/generation/myenv/bin/activate
```

The website generation phase takes a qualified lead and creates a complete professional website by scraping data, analyzing content, and generating all necessary website components.

### Directory Structure
```
data/generation/webgen/
├── step_1/                        # Data Scraping
│   ├── ScrapeBBB.py              # Scrapes BBB profile data
│   ├── ScrapeReviews.py          # Scrapes Google reviews
│   ├── yelp_scraper.py           # (Optional) Scrapes Yelp data
│   └── search_business.py        # Google Search API for web presence
├── step_2/                        # Data Processing & Analysis
│   ├── color_extractor.py        # Extracts colors from logo
│   ├── generate_colors_with_ai.py # AI-generated colors (fallback)
│   ├── AnalyzeReviews.py         # Sentiment analysis of reviews
│   ├── create_service_names.py   # Generates 8 service names
│   └── research_services.py      # Researches service details
└── step_3/                        # Content Generation (Future)
    └── ...
```

### Step 1: Data Scraping

#### BBB Profile Scraping
- **Script**: `ScrapeBBB.py`
- **Function**: Extracts comprehensive business information from BBB profile
- **Data Extracted**:
  - Business name and contact details
  - Years in business and accreditation status
  - Business logo (logo.png) if available
  - Employee information and roles
  - Services offered
  - Business address and location
- **Output**: `data/output/individual/step_1/raw/bbb_profile_data.json`
- **Optional Output**: `data/output/individual/step_1/raw/logo.png`

#### Google Reviews Scraping
- **Script**: `ScrapeReviews.py`
- **Function**: Collects customer reviews for content and sentiment analysis
- **Data Extracted**:
  - Customer names and ratings
  - Review text and dates
  - Overall rating distribution
- **Output**: `data/output/individual/step_1/raw/reviews.json`

#### Yelp Data Scraping (Optional)
- **Script**: `yelp_scraper.py`
- **Function**: Supplements business data with Yelp information
- **Data Extracted**:
  - Additional services information
  - Business hours
  - Additional customer reviews
  - Business photos (downloaded locally)
- **Output**: `data/output/individual/step_2/yelp_scrape.json`

#### Web Presence Search
- **Script**: `search_business.py`
- **Function**: Uses Google Search API to find business's online presence
- **Data Extracted**:
  - Social media profiles (Facebook, Instagram, LinkedIn, etc.)
  - Directory listings (Yelp, HomeAdvisor, Angi, etc.)
  - Any existing web presence
- **Output**: `data/output/individual/step_1/raw/google_api_search.json`

### Step 2: Data Processing & Analysis

#### Color Scheme Generation
Two approaches based on logo availability:

**With Logo** (`color_extractor.py`):
- Extracts 4 professional colors from business logo using color theory
- Uses ColorThief library for dominant color extraction
- Generates unique, non-overlapping color palette
- Creates interactive HTML editor for color adjustment

**Without Logo** (`generate_colors_with_ai.py`):
- Uses OpenAI API to generate colors based on business name and location
- Falls back to professional default colors if API unavailable
- Creates AI-aware HTML editor interface

**Output**: `data/output/individual/step_2/colors_output.json`
**HTML Editor**: `data/output/individual/step_2/color_editor.html`

#### Review Sentiment Analysis
- **Script**: `AnalyzeReviews.py`
- **Function**: Analyzes customer review sentiment using TextBlob
- **Process**:
  1. Processes each review for sentiment polarity
  2. Categorizes as positive, negative, or neutral
  3. Maintains original review data with sentiment scores
- **Output**: `data/output/individual/step_2/sentiment_reviews.json`

#### Service Generation
**Service Names** (`create_service_names.py`):
- Uses AI (OpenAI) to select 4 residential + 4 commercial services
- Based on business information from BBB and Yelp data
- Creates service structure for all website components
- Falls back to default services if AI unavailable
- **Output**: `data/output/individual/step_2/service_names.json`

**Service Research** (`research_services.py`):
- Researches each of the 8 services in comprehensive detail
- Generates 12 detailed sections per service:
  - Installation processes
  - Material variants and options
  - Repair and emergency procedures
  - Maintenance requirements
  - Cost and pricing information
  - Warranty and guarantee details
  - Regulatory compliance
  - Customer education
  - Environmental efficiency
  - Troubleshooting guides
  - Business processes
  - Specialized considerations
- **Output**: `data/output/individual/step_2/services_research.json`
- **Summary**: `data/output/individual/step_2/services_research_summary.json`

---

## Output Structure

### Lead Generation Outputs
```
data/output/leads/
├── raw/
│   ├── google_search.json        # All discovered businesses
│   ├── google_filter.json        # Businesses without websites
│   └── bbb_match.json            # BBB-matched businesses
└── final/
    └── final_leads.json          # Qualified leads ready for website generation
```

### Website Generation Outputs
```
data/output/individual/
├── step_1/raw/
│   ├── bbb_profile_data.json     # Business profile information
│   ├── reviews.json              # Customer reviews
│   ├── google_api_search.json    # Web presence search results
│   └── logo.png                  # Business logo (if available)
└── step_2/
    ├── colors_output.json        # Generated color scheme
    ├── color_editor.html         # Interactive color editor
    ├── sentiment_reviews.json    # Analyzed reviews with sentiment
    ├── service_names.json        # 8 generated service names
    ├── services_research.json    # Detailed service research
    ├── services_research_summary.json # Research summary
    └── yelp_scrape.json          # Yelp data (optional)
```

---

## Data Formats

All outputs are in JSON format (except logo.png and HTML editor files). This ensures:
- Consistent data structure across all scripts
- Easy integration with website generation systems
- Human-readable configuration files
- Standardized processing pipelines

### Key Data Structures

**Business Profile**:
```json
{
  "business_name": "Company Name",
  "address": "Full Address",
  "telephone": "Phone Number",
  "website": "Website URL",
  "years_in_business": "X years",
  "services": ["Service 1", "Service 2"],
  "logo_url": "Logo URL",
  "accredited": true/false
}
```

**Color Scheme**:
```json
{
  "accent": "#2B4C7E",
  "banner": "#D32F2F", 
  "faint-color": "#E0F7FA",
  "second-accent": "#FFA000"
}
```

**Service Structure**:
```json
{
  "residential": [
    {"id": "service-slug", "name": "Service Name", "title": "Display Title"}
  ],
  "commercial": [
    {"id": "service-slug", "name": "Service Name", "title": "Display Title"}
  ]
}
```

---

## Requirements

### System Requirements
- Python 3.8+
- Chrome browser (for Selenium automation)
- Virtual environment recommended

### Python Dependencies
```bash
# Lead Generation
selenium
webdriver-manager
beautifulsoup4
requests
pandas

# Website Generation
textblob
colorthief
pillow
openai
python-dotenv
```

### API Keys (Optional but Recommended)
- **OpenAI API Key**: For AI-enhanced color generation and service selection
- **Google Search API Key**: For comprehensive web presence analysis
- **Google Search Engine ID**: For custom search configuration

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv public/data/generation/myenv
source public/data/generation/myenv/bin/activate

# Install dependencies
pip install selenium webdriver-manager beautifulsoup4 requests pandas textblob colorthief pillow openai python-dotenv
```

---

## Execution Flow

### Complete Website Generation Process
1. **Generate Leads**: Identify businesses without websites
2. **Select Target**: Choose a business from the qualified leads
3. **Scrape Data**: Collect all available business information
4. **Process Data**: Analyze, enhance, and structure the data
5. **Generate Content**: Create website components and configurations
6. **Deploy Website**: Use the generated data to build the final website

### Individual Script Usage
Each script can be run independently for testing or partial generation:

```bash
# Lead generation
python public/data/generation/leads/run_pipeline.py GA 30002 30004

# BBB scraping
python public/data/generation/webgen/step_1/ScrapeBBB.py

# Color generation
python public/data/generation/webgen/step_2/color_extractor.py

# Service research
python public/data/generation/webgen/step_2/research_services.py
```

---

## Quality Assurance

### Data Validation
- All JSON outputs include validation and error handling
- Fallback data for cases where scraping fails
- Comprehensive logging for debugging and monitoring

### Output Standards
- **JSON Only**: All data outputs in JSON format for consistency
- **No CSV Files**: Eliminated CSV outputs for standardization
- **No Log Files**: Removed log file generation to data/output directories
- **Structured Paths**: Consistent directory structure across all scripts

### Error Handling
- Graceful fallbacks when APIs are unavailable
- Default data for missing information
- Comprehensive error logging to console only
- Retry mechanisms for network-dependent operations

---

## Quick Reference

### Virtual Environment Activation (ALWAYS FIRST)
```bash
cd /Users/rhettburnham/Desktop/projects/roofing-co/public/data/generation
source myenv/bin/activate
```

### Lead Generation Commands
```bash
# Activate environment first (see above)
cd leads
python run_pipeline.py [state] [start_zip] [end_zip]
```

### Website Generation Commands
```bash
# Activate environment first (see above)
cd webgen

# Step 1: Data Collection
cd step_1
python ScrapeBBB.py
python ScrapeReviews.py
python search_business.py

# Step 2: Data Processing
cd ../step_2
python color_extractor.py  # OR python generate_colors_with_ai.py
python AnalyzeReviews.py
python create_service_names.py
python research_services.py
```

---

This documentation represents the current state of the generation process. The system is designed to be modular, allowing for individual component testing and gradual enhancement of the website generation pipeline. 