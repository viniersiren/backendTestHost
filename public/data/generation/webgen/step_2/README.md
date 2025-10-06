# Step 2: Business Search and Data Analysis

This directory contains scripts for analyzing data collected in Step 1 and enriching it with further web searches and AI-generated content.

## Scripts

### `search_business.py`

This script uses the Google Custom Search API to perform a location-aware search for the business profile data collected in Step 1.

### `generate_images_with_ai.py` ⭐ **NEW**

This script generates professional shingle images using OpenAI's DALL-E 3 API for use in the roofing company website.

**Functionality:**
- Generates 4 different types of professional shingle images:
  - Premium asphalt shingle (product photography)
  - Shingle texture closeup (macro photography)
  - Shingle installation view (construction photography)
  - Shingle color variety (product selection display)
- Uses DALL-E 3 with standard quality (lowest cost setting)
- Automatically saves images to `generated_images/` directory
- Tracks image metadata in `generated_images.json`
- Integrates seamlessly with the webgen pipeline

**Requirements:**
- OpenAI API key set in environment variable `OPENAI_API_KEY`
- Same API key used by the color generator

**Output:**
- Images saved to: `/public/data/output/individual/step_2/generated_images/`
- Metadata saved to: `/public/data/output/individual/step_2/generated_images.json`

### Setup and Configuration

To run the scripts successfully, you need to configure your environment with the necessary API keys.

**1. Dependencies:**

First, ensure you have the necessary Python packages installed. From your project root, you can activate your virtual environment and install them:

```bash
source public/data/generation/myenv/bin/activate
pip install requests python-dotenv openai
```

**2. Environment Variables:**

Set up your API keys as environment variables:

```bash
# For Google Search API (search_business.py)
export GOOGLE_SEARCH_API_KEY="YOUR_GOOGLE_API_KEY"
export GOOGLE_SEARCH_ENGINE_ID="YOUR_SEARCH_ENGINE_ID"

# For AI Image Generation (generate_images_with_ai.py)
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
```

**3. Getting Your Credentials:**

If you are missing your API keys, follow these steps:

*   **Google API Key & Search Engine ID:** The official documentation provides a complete guide on getting both of these.
    *   See: [Custom Search JSON API Overview](https://developers.google.com/custom-search/v1/overview#search_engine_id)

*   **Search Engine ID (cx) Quick Link:** You can create and manage your search engines here:
    *   [Programmable Search Engine Control Panel](https://programmablesearchengine.google.com/u/1/controlpanel/all)
    *   Once you create a search engine (you can configure it to "Search the entire web"), you will find the **Search engine ID** on its setup page.

*   **OpenAI API Key:** Get your API key from the OpenAI platform:
    *   [OpenAI Platform](https://platform.openai.com/api-keys)
    *   This is the same API key used by the color generator

### How to Run

Once your environment variables are set up correctly, you can run the scripts from the project root directory:

**Individual Scripts:**
```bash
# Run just the image generator
python public/data/generation/webgen/step_2/generate_images_with_ai.py

# Run just the business search
python public/data/generation/webgen/step_2/search_business.py
```

**Complete Pipeline:**
```bash
# Run the entire webgen pipeline (includes image generation)
python public/data/run_pipeline.py
```

The pipeline will:
1.  Read business information from `/public/data/output/individual/step_1/raw/bbb_profile_data.json`.
2.  Perform a location-specific Google search using the API.
3.  Generate professional shingle images using AI.
4.  Save the results to `/public/data/output/individual/step_2/`.

### Generated Images

The AI image generator creates 4 professional shingle images:

1. **premium_asphalt_shingle**: Full-on product photography view
2. **shingle_texture_closeup**: Macro photography showing texture details
3. **shingle_installation_view**: Construction photography showing installation
4. **shingle_color_variety**: Product selection display with multiple colors

All images are:
- High resolution (1024x1024 or 1792x1024)
- Professional quality suitable for marketing
- No watermarks or branding overlays
- Optimized for roofing company websites

### Common Errors

*   **`ERROR - Google Search Engine ID (cx) not found...`**: This means the `GOOGLE_SEARCH_ENGINE_ID` is missing from your environment. Follow step 3 above to get your ID.
*   **`ERROR: OpenAI API key not found`**: Set the `OPENAI_API_KEY` environment variable with your OpenAI API key.
*   **`FileNotFoundError: ... bbb_profile_data.json`**: The script could not find the input file. Make sure you have run the Step 1 scripts and the file exists at the correct path.
*   **API Errors (e.g., 403, 429)**:
    *   A `403` error often means the API key is invalid or the API is not enabled for your project.
    *   A `429` error means you have exceeded your daily quota. The free plan allows 100 queries per day for Google Search API.
    *   For OpenAI, check your usage limits in the OpenAI dashboard. 