# Step 4: Website Data Integration and AI Enhancement

This folder contains Python scripts that integrate all previously collected and generated data into a comprehensive JSON structure that powers the roofing company website. The scripts combine data from multiple sources and use AI to enhance content where needed.

## Files Overview

### 1. `generate_combined_data.py`

The main script that orchestrates the creation of the complete website data structure.

**Functionality:**
- Combines data from multiple sources:
  - BBB profile data (Step 1)
  - Reviews and sentiment analysis (Step 2)
  - Service descriptions (Step 3)
  - About page content (Step 3)
- Uses AI to enhance and generate missing content
- Creates a unified data structure following `template_data.json`
- Handles data validation and fallbacks
- Generates SEO-friendly content

**Input Sources:**
- `raw_data/step_1/bbb_profile_data.json`
- `raw_data/step_2/sentiment_reviews.json`
- `raw_data/step_3/about_page.json`
- `raw_data/step_3/services/*.json`

**Output:** `raw_data/combined_data.json`

### 2. `deepseek_utils.py`

A utility module that handles AI-powered content generation using the DeepSeek API.

**Functionality:**
- Manages API communication with DeepSeek
- Provides fallback content when API is unavailable
- Handles various content generation tasks:
  - Business name formatting
  - Rich text content
  - Service categorization
  - Geographic coordinate estimation
- Includes robust error handling and logging

**Dependencies:**
- DeepSeek API key (in `.env.deepseek` file)
- `requests` library for API calls
- `python-dotenv` for environment management

### 3. `template_data.json`

The template file that defines the structure of the final website data.

**Structure:**
- Navigation configuration
- Hero section layout
- Booking section
- Rich text content
- Service descriptions
- Map and contact information
- Team member profiles
- Gallery and before/after images
- Reviews section

**Template Variables:**
- `{{BUSINESS_NAME_MAIN}}` - Primary business name
- `{{BUSINESS_NAME_SUB}}` - Business subtitle
- `{{BOOKING_HEADER_TEXT}}` - Booking section header
- `{{PHONE_NUMBER}}` - Business phone number
- `{{RICH_TEXT_*}}` - Various rich text content
- `{{MAP_LAT}}`, `{{MAP_LNG}}` - Map coordinates
- And more...

### 4. `test.py`

A comprehensive test suite for the data generation process.

**Functionality:**
- Unit tests for data integration
- Validation of JSON structure
- API response testing
- Fallback behavior verification
- Template variable replacement testing

### 5. `sharpen_logo.py` ⭐ **NEW**

A specialized script for enhancing silhouette design logos by sharpening edges and reducing noise.

**Functionality:**
- **Noise Reduction**: Uses bilateral filtering to reduce noise while preserving edges
- **Edge Enhancement**: Applies multiple sharpening techniques using both OpenCV and PIL
- **Morphological Operations**: Cleans up silhouette designs by filling gaps and removing artifacts
- **Multi-method Processing**: Combines OpenCV and PIL techniques for optimal results
- **Batch Processing**: Can process single files or all logo files in the project
- **Comparison Images**: Creates before/after comparison images to visualize improvements

**Key Features:**
- Specifically designed for silhouette and logo images
- Preserves transparency in PNG files
- Multiple enhancement algorithms combined for best results
- Automatic file discovery across the project
- High-quality output with optimization

**Usage Examples:**
```bash
# Process a specific logo file
python sharpen_logo.py --input /path/to/logo.png

# Process all logo files in the project with comparison images
python sharpen_logo.py --all --comparison

# Process with custom output path
python sharpen_logo.py --input logo.png --output sharpened_logo.png --comparison
```

**Dependencies:**
Install required packages:
```bash
pip install -r requirements_sharpen.txt
```

**Processing Steps:**
1. **Noise Reduction**: Bilateral filtering to smooth noise while keeping edges sharp
2. **OpenCV Enhancement**: Gaussian blur + sharpening kernel + contrast enhancement
3. **PIL Enhancement**: Unsharp mask + edge enhancement + contrast/sharpness boost
4. **Morphological Cleanup**: Closing and opening operations to clean silhouette edges
5. **Method Blending**: Combines both enhancement approaches (70% PIL, 30% OpenCV)
6. **Final Sharpening**: Final unsharp mask pass for crisp edges

### 6. `requirements_sharpen.txt` ⭐ **NEW**

Dependencies required for the logo sharpening script.

**Packages:**
- `opencv-python`: Advanced image processing and computer vision
- `Pillow`: Python Imaging Library for basic image operations
- `numpy`: Numerical operations for image arrays
- `pathlib2`: Path handling for older Python versions

## Data Flow

1. **Input Collection:**
   - Load BBB profile data
   - Load processed reviews
   - Load service descriptions
   - Load about page content

2. **Content Enhancement:**
   - AI-powered content generation
   - Business name formatting
   - Geographic data processing
   - Review selection and formatting

3. **Template Integration:**
   - Variable replacement
   - Structure validation
   - Content organization
   - Image path verification

4. **Output Generation:**
   - Combined JSON file creation
   - Logging and verification
   - Fallback handling

5. **Logo Enhancement:** ⭐ **NEW**
   - Logo file discovery
   - Multi-algorithm sharpening
   - Noise reduction and edge enhancement
   - Quality comparison generation

## Dependencies

The scripts require these Python packages:
```
requests
python-dotenv
logging
json
```

For logo sharpening (additional):
```
opencv-python
Pillow
numpy
```

Install dependencies with:
```bash
pip install requests python-dotenv
pip install -r requirements_sharpen.txt  # For logo sharpening
```

## Environment Setup

1. Create a `.env.deepseek` file in the `public/data` directory:
```
DEEPSEEK_API_KEY=your_api_key_here
```

2. Ensure all input data from previous steps is available in the correct locations.

## Usage

1. **Generate Combined Data:**
```bash
python generate_combined_data.py
```

2. **Run Tests:**
```bash
python test.py
```

3. **Sharpen Logo Images:** ⭐ **NEW**
```bash
# Auto-detect and process common logo locations
python sharpen_logo.py

# Process all logos in project
python sharpen_logo.py --all --comparison

# Process specific file
python sharpen_logo.py --input ../raw_data/step_1/logo.png --comparison
```

## Error Handling

The scripts include comprehensive error handling:
- Graceful fallbacks when API is unavailable
- Logging of all operations
- Validation of input/output data
- Automatic creation of missing directories

## Output Validation

The generated `combined_data.json` should be validated against these criteria:
- All required fields are present
- Image paths are valid
- URLs are properly formatted
- Content is properly escaped
- Template variables are all replaced

**Logo Enhancement Output:**
- Sharpened logos saved with `_sharpened` suffix
- Comparison images show before/after results
- Maintains original file format and transparency
- Optimized for web usage with high quality

Note: The scripts will automatically create necessary directories and handle missing data gracefully. However, for optimal results, ensure all input data from previous steps is available. 