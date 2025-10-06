#!/usr/bin/env python3
# public/data/generation/webgen/step_2/generate_colors_with_ai.py

import os
import json
import openai
import logging
import sys
import http.server
import socketserver
import webbrowser
import threading
import urllib.parse
from pathlib import Path
import base64
import re

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- File Paths ---
INPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw"
OUTPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2"
BBB_PROFILE_PATH = os.path.join(INPUT_DIR, 'bbb_profile_data.json')
LOGO_PATH = os.path.join(INPUT_DIR, 'logo.png')
COLORS_OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'colors_output.json')
HTML_EDITOR = os.path.join(OUTPUT_DIR, 'color_editor.html')

PORT = 8000  # Port for the web server

# Memory-only mode support
MEMORY_ONLY = os.environ.get("MEMORY_ONLY", "0") == "1"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_api_key():
    """
    Retrieves the OpenAI API key from environment variables.
    Returns None if not found (will trigger fallback colors).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return api_key

def _read_stdin_payload():
    """
    Read JSON payload from STDIN for MEMORY_ONLY mode.
    Expected keys: chosenLogoUrl (string, may be data URL), businessData (object, optional)
    """
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}

def generate_prompt(business_data):
    """
    Creates a detailed prompt for the AI based on business data.
    """
    business_name = business_data.get('business_name', 'a construction company')
    services = ", ".join(business_data.get('services', ['roofing', 'construction']))

    prompt = f"""
You are a professional brand designer creating a color palette for a website.
Your task is to generate a color scheme based on the following business profile.

Business Name: {business_name}
Services Offered: {services}
Industry: Roofing and Construction

The color palette should be professional, trustworthy, and modern. It must be suitable for a construction or roofing company website.

Generate a 4-color palette. Please provide the output as a valid JSON object with the following keys and hex color values:
- "accent": A strong, eye-catching color for buttons, links, and calls to action.
- "banner": A solid color for main headers and banners. Should complement the accent color.
- "faint-color": A very light, subtle color for page backgrounds or content sections.
- "second-accent": An alternative accent color for secondary highlights or special notices.

Return ONLY the raw JSON object and nothing else. Do not include markdown formatting like ```json.
"""
    return prompt.strip()

def generate_colors_with_ai(api_key, prompt):
    """
    Calls the OpenAI API to generate the color palette.
    """
    try:
        client = openai.OpenAI(api_key=api_key)
        logger.info("Sending prompt to OpenAI API...")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful design assistant that only responds with JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        logger.info("Received response from API.")
        
        # The response should be a JSON string, so we parse it
        color_palette = json.loads(content)
        
        # Validate the response structure
        expected_keys = ["accent", "banner", "faint-color", "second-accent"]
        if not all(key in color_palette for key in expected_keys):
            raise ValueError("The AI response did not contain the expected keys.")
            
        logger.info(f"Successfully generated color palette: {color_palette}")
        return color_palette

    except Exception as e:
        logger.error(f"An error occurred while communicating with the OpenAI API: {e}")
        raise

def analyze_logo_colors_with_image(api_key, logo_url_or_dataurl, business_name=None):
    """
    Use a vision-capable chat model to analyze the provided logo image and extract a 4-color palette.
    Returns the same palette shape as generate_colors_with_ai().
    """
    try:
        client = openai.OpenAI(api_key=api_key)
        logger.info("Sending image analysis request to OpenAI API...")

        system_msg = {
            "role": "system",
            "content": "You are a senior brand designer. Respond ONLY with a JSON object containing four hex colors under keys: accent, banner, faint-color, second-accent."
        }

        # Prefer passing the image via image_url content part. Data URLs are acceptable.
        user_parts = []
        if business_name:
            user_parts.append({"type": "text", "text": f"Analyze this logo for {business_name} and produce a 4-color palette in JSON with keys accent, banner, faint-color, second-accent. Return only JSON."})
        else:
            user_parts.append({"type": "text", "text": "Analyze this logo and produce a 4-color palette in JSON with keys accent, banner, faint-color, second-accent. Return only JSON."})
        user_parts.append({
            "type": "image_url",
            "image_url": {"url": logo_url_or_dataurl}
        })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[system_msg, {"role": "user", "content": user_parts}],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        color_palette = json.loads(content)
        expected_keys = ["accent", "banner", "faint-color", "second-accent"]
        if not all(k in color_palette for k in expected_keys):
            raise ValueError("Image analysis response missing expected keys")
        logger.info(f"Image analysis produced palette: {color_palette}")
        return color_palette
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        raise

def generate_html_editor(colors, is_ai_generated=True):
    """Generate an HTML page for viewing and editing colors"""
    title = "AI Generated Color Scheme Editor" if is_ai_generated else "Professional Color Scheme Editor"
    badge_text = "🤖 AI Generated" if is_ai_generated else "🎨 Professional"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{
            text-align: center;
            color: #333;
        }}
        .color-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .color-item {{
            flex: 1;
            min-width: 200px;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .color-preview {{
            height: 100px;
            border-radius: 4px;
            margin-bottom: 10px;
        }}
        label {{
            display: block;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        input[type="color"] {{
            width: 100%;
            height: 40px;
            cursor: pointer;
        }}
        input[type="text"] {{
            width: 100%;
            padding: 8px;
            box-sizing: border-box;
            margin-top: 5px;
        }}
        .button-container {{
            display: flex;
            gap: 10px;
            justify-content: center;
            margin: 20px 0;
        }}
        button {{
            color: white;
            border: none;
            padding: 12px 24px;
            text-align: center;
            text-decoration: none;
            font-size: 16px;
            cursor: pointer;
            border-radius: 4px;
            min-width: 120px;
        }}
        .save-button {{
            background-color: #4CAF50;
        }}
        .save-button:hover {{
            background-color: #45a049;
        }}
        .done-button {{
            background-color: #2196F3;
        }}
        .done-button:hover {{
            background-color: #1976D2;
        }}
        .color-sample {{
            margin-top: 30px;
            border: 1px solid #ddd;
            padding: 20px;
            border-radius: 8px;
        }}
        .sample-header {{
            background-color: {colors["banner"]};
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
        }}
        .sample-button {{
            background-color: {colors["accent"]};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 10px;
        }}
        .sample-content {{
            background-color: {colors["faint-color"]};
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
        }}
        .sample-highlight {{
            background-color: {colors["second-accent"]};
            padding: 5px 10px;
            border-radius: 4px;
            display: inline-block;
            margin: 5px 0;
        }}
        .ai-badge {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            margin-left: 10px;
        }}
    </style>
</head>
<body>
    <h1>{title} <span class="ai-badge">{badge_text}</span></h1>
    <p>{"These colors were generated by AI based on your business profile." if is_ai_generated else "These are professional fallback colors (no AI API key provided)."} Adjust the colors below. Click "Save Colors" to save temporarily, or "Done" to save and close the editor.</p>
    
    <form action="/save_colors" method="get">
        <div class="color-container">
            <div class="color-item">
                <div class="color-preview" id="accent-preview" style="background-color: {colors["accent"]};"></div>
                <label for="accent">Accent Color:</label>
                <input type="color" id="accent" name="accent" value="{colors["accent"]}" onchange="updatePreview('accent')">
                <input type="text" id="accent-text" value="{colors["accent"]}" oninput="updateColor('accent')">
                <p>Used for: Buttons, links, and primary interactive elements</p>
            </div>
            
            <div class="color-item">
                <div class="color-preview" id="banner-preview" style="background-color: {colors["banner"]};"></div>
                <label for="banner">Banner Color:</label>
                <input type="color" id="banner" name="banner" value="{colors["banner"]}" onchange="updatePreview('banner')">
                <input type="text" id="banner-text" value="{colors["banner"]}" oninput="updateColor('banner')">
                <p>Used for: Headers, navigation bars, and prominent UI elements</p>
            </div>
            
            <div class="color-item">
                <div class="color-preview" id="faint-color-preview" style="background-color: {colors["faint-color"]};"></div>
                <label for="faint-color">Faint Color:</label>
                <input type="color" id="faint-color" name="faint-color" value="{colors["faint-color"]}" onchange="updatePreview('faint-color')">
                <input type="text" id="faint-color-text" value="{colors["faint-color"]}" oninput="updateColor('faint-color')">
                <p>Used for: Backgrounds, subtle highlights, and secondary elements</p>
            </div>
            
            <div class="color-item">
                <div class="color-preview" id="second-accent-preview" style="background-color: {colors["second-accent"]};"></div>
                <label for="second-accent">Second Accent Color:</label>
                <input type="color" id="second-accent" name="second-accent" value="{colors["second-accent"]}" onchange="updatePreview('second-accent')">
                <input type="text" id="second-accent-text" value="{colors["second-accent"]}" oninput="updateColor('second-accent')">
                <p>Used for: Call-to-actions, highlights, and accent elements</p>
            </div>
        </div>
        
        <h2>Color Sample Preview</h2>
        <div class="color-sample">
            <div class="sample-header">This is a banner using the Banner Color</div>
            <div class="sample-content">
                <p>This is content with a Faint Color background.</p>
                <button class="sample-button">Accent Color Button</button>
                <p>Here is some text with a <span class="sample-highlight">Second Accent highlight</span> to show contrast.</p>
            </div>
        </div>
        
        <div class="button-container">
            <button type="submit" class="save-button">Save Colors</button>
            <button type="button" class="done-button" onclick="finishEditing()">Done</button>
        </div>
    </form>

    <script>
        function updatePreview(colorType) {{
            const colorInput = document.getElementById(colorType);
            const preview = document.getElementById(colorType + '-preview');
            const textInput = document.getElementById(colorType + '-text');
            
            preview.style.backgroundColor = colorInput.value;
            textInput.value = colorInput.value;
            updateSamplePreview();
        }}
        
        function updateColor(colorType) {{
            const textInput = document.getElementById(colorType + '-text');
            const colorInput = document.getElementById(colorType);
            const preview = document.getElementById(colorType + '-preview');
            
            // Validate hex color
            const isValidHex = /^#([0-9A-F]{{3}}){{1,2}}$/i.test(textInput.value);
            
            if (isValidHex) {{
                colorInput.value = textInput.value;
                preview.style.backgroundColor = textInput.value;
                updateSamplePreview();
            }}
        }}
        
        function updateSamplePreview() {{
            const accentColor = document.getElementById('accent').value;
            const bannerColor = document.getElementById('banner').value;
            const faintColor = document.getElementById('faint-color').value;
            const secondAccentColor = document.getElementById('second-accent').value;
            
            document.querySelector('.sample-header').style.backgroundColor = bannerColor;
            document.querySelector('.sample-button').style.backgroundColor = accentColor;
            document.querySelector('.sample-content').style.backgroundColor = faintColor;
            document.querySelector('.sample-highlight').style.backgroundColor = secondAccentColor;
        }}
        
        function finishEditing() {{
            // Get current color values
            const colors = {{
                accent: document.getElementById('accent').value,
                banner: document.getElementById('banner').value,
                'faint-color': document.getElementById('faint-color').value,
                'second-accent': document.getElementById('second-accent').value
            }};
            
            // Build query string
            const params = new URLSearchParams(colors);
            
            // Save colors and close
            fetch('/done?' + params.toString())
                .then(response => response.text())
                .then(data => {{
                    // Show success message
                    alert('AI-generated colors saved successfully! The editor will now close.');
                    // Try to close the window
                    window.close();
                }})
                .catch(error => {{
                    console.error('Error saving colors:', error);
                    alert('Error saving colors. Please try again.');
                }});
        }}
    </script>
</body>
</html>
"""
    with open(HTML_EDITOR, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return HTML_EDITOR

class ColorEditorHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Handle color save request
        if self.path.startswith('/save_colors'):
            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # Extract color values from query parameters
            new_colors = {
                "accent": query_params.get('accent', ['#2B4C7E'])[0],
                "banner": query_params.get('banner', ['#1976D2'])[0],
                "faint-color": query_params.get('faint-color', ['#F5F5F5'])[0],
                "second-accent": query_params.get('second-accent', ['#FF6B35'])[0]
            }
            
            # Save the new colors
            try:
                with open(COLORS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump(new_colors, f, indent=2)
                logger.info(f"Updated AI color scheme saved to {COLORS_OUTPUT_PATH}")
                
                # Send response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                # Create a success page
                success_page = f"""<!DOCTYPE html>
<html>
<head>
    <title>AI Colors Saved</title>
    <meta http-equiv="refresh" content="2;url=/" />
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }}
        .success {{ color: green; }}
        .ai-badge {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 5px 15px; border-radius: 20px; font-size: 12px; margin-left: 10px; }}
    </style>
</head>
<body>
    <h1 class="success">AI Colors Saved Successfully! <span class="ai-badge">🤖 AI</span></h1>
    <p>Redirecting back to the editor...</p>
    <div style="margin: 30px auto; display: flex; justify-content: center; gap: 10px;">
        <div style="width: 50px; height: 50px; background-color: {new_colors['accent']}"></div>
        <div style="width: 50px; height: 50px; background-color: {new_colors['banner']}"></div>
        <div style="width: 50px; height: 50px; background-color: {new_colors['faint-color']}"></div>
        <div style="width: 50px; height: 50px; background-color: {new_colors['second-accent']}"></div>
    </div>
</body>
</html>
"""
                self.wfile.write(success_page.encode())
                
            except Exception as e:
                logger.error(f"Error saving updated AI color scheme: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f"Error saving colors: {str(e)}".encode())
            
            return
            
        # Handle done request - save colors and signal server to shut down
        if self.path.startswith('/done'):
            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # Extract color values from query parameters
            new_colors = {
                "accent": query_params.get('accent', ['#2B4C7E'])[0],
                "banner": query_params.get('banner', ['#1976D2'])[0],
                "faint-color": query_params.get('faint-color', ['#F5F5F5'])[0],
                "second-accent": query_params.get('second-accent', ['#FF6B35'])[0]
            }
            
            # Save the new colors
            try:
                with open(COLORS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump(new_colors, f, indent=2)
                logger.info(f"Final AI color scheme saved to {COLORS_OUTPUT_PATH}")
                
                # Send response
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"AI-generated colors saved successfully!")
                
                # Signal server to shut down
                def shutdown_server():
                    import time
                    time.sleep(1)  # Give time for response to be sent
                    self.server.shutdown()
                    
                threading.Thread(target=shutdown_server, daemon=True).start()
                
            except Exception as e:
                logger.error(f"Error saving final AI color scheme: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error saving colors: {str(e)}".encode())
            
            return
            
        # Serve the editor HTML if requesting root
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            with open(HTML_EDITOR, 'rb') as file:
                self.wfile.write(file.read())
            return
            
        # For any other path, use the default handler
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

def start_web_server(html_path):
    """Start a web server to host the color editor"""
    # Change to the directory containing the HTML file
    os.chdir(os.path.dirname(html_path))
    
    # Create the server
    handler = ColorEditorHandler
    httpd = socketserver.TCPServer(("", PORT), handler)
    
    logger.info(f"Starting web server at port {PORT}")
    logger.info(f"Open your browser to http://localhost:{PORT}/")
    
    # Open the browser automatically
    webbrowser.open(f"http://localhost:{PORT}/")
    
    # Start the server
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    finally:
        httpd.server_close()
        logger.info("Server closed")

def main():
    """
    Main function to orchestrate the AI color generation process.
    """
    logger.info("--- Starting AI Color Generation Script ---")

    # MEMORY_ONLY fast-path: accept chosen logo and return palette to stdout
    if MEMORY_ONLY:
        payload = _read_stdin_payload() or {}
        chosen_logo = payload.get("chosenLogoUrl")
        business_data = payload.get("businessData") or {}
        business_name = business_data.get("business_name") or business_data.get("name")

        api_key = get_api_key()  # hard-require API key
        is_ai_generated = True

        if chosen_logo:
            palette = analyze_logo_colors_with_image(api_key, chosen_logo, business_name)
        else:
            prompt = generate_prompt(business_data)
            palette = generate_colors_with_ai(api_key, prompt)

        # Emit palette for backend parsing
        print("AI_COLORS_JSON_START")
        print(json.dumps({"colors": palette, "ai": is_ai_generated}))
        print("AI_COLORS_JSON_END")
        return

    # Non-memory legacy flow below

    # 1. Check if BBB profile exists (legacy flow uses it for context); do not early-exit
    if os.path.exists(BBB_PROFILE_PATH):
        try:
            with open(BBB_PROFILE_PATH, 'r', encoding='utf-8') as f:
                _ = json.load(f)
        except Exception as e:
            logger.error(f"Error reading BBB profile: {e}")
    
    logger.info("No logo URL found in BBB profile. Proceeding with AI color generation.")

    # 2. Check if the BBB profile data exists.
    if not os.path.exists(BBB_PROFILE_PATH):
        logger.error(f"Business profile data not found at {BBB_PROFILE_PATH}.")
        print(f"ERROR: Cannot find 'bbb_profile_data.json'. Please run the scraping script first.")
        sys.exit(1)

    # 3. Load business data
    try:
        with open(BBB_PROFILE_PATH, 'r', encoding='utf-8') as f:
            business_data = json.load(f)
        logger.info(f"Successfully loaded business profile data for: {business_data.get('business_name', 'Unknown')}")
    except Exception as e:
        logger.error(f"Failed to read or parse {BBB_PROFILE_PATH}: {e}")
        sys.exit(1)

    # 4. Get API key and generate colors
    is_ai_generated = True
    try:
        api_key = get_api_key()  # hard-require API key
        prompt = generate_prompt(business_data)
        color_palette = generate_colors_with_ai(api_key, prompt)
    except Exception as e:
        logger.error(f"Error in AI color generation: {e}")
        sys.exit(1)

    # 5. Save the generated colors
    try:
        with open(COLORS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(color_palette, f, indent=2)
        logger.info(f"Successfully saved AI-generated color palette to {COLORS_OUTPUT_PATH}")
        
        # Log the colors
        for key, value in color_palette.items():
            logger.info(f"  {key}: {value}")
            
    except Exception as e:
        logger.error(f"Failed to save the color palette file: {e}")
        sys.exit(1)

    # 6. Generate the HTML editor
    html_path = generate_html_editor(color_palette, is_ai_generated)
    logger.info(f"Generated HTML editor at {html_path}")
    
    print("\n========== AI COLOR GENERATION COMPLETE ==========")
    print(f"AI-generated colors saved to {COLORS_OUTPUT_PATH}")
    print(f"HTML editor generated at {html_path}")
    print("Opening color editor automatically...")
    
    # Start web server and open the editor automatically
    start_web_server(html_path)

if __name__ == "__main__":
    main() 