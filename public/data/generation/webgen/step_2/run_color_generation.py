#!/usr/bin/env python3
# public/data/generation/webgen/step_2/run_color_generation.py

import os
import json
import sys
import subprocess
from pathlib import Path

# --- Configuration ---
INPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_1/raw"
OUTPUT_DIR = "/Users/rhettburnham/Desktop/projects/roofing-co/public/data/output/individual/step_2"
COLORS_OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'colors_output.json')

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def check_for_business_specific_profile():
    """
    Check if there's a business-specific BBB profile file (e.g., bbb_profile_data_Luxury_Roofing_LLC.json)
    Returns the path if found, None otherwise.
    """
    print("Checking for business-specific BBB profile files...")
    
    # Look for files matching the pattern bbb_profile_data_*.json
    for file in os.listdir(INPUT_DIR):
        if file.startswith("bbb_profile_data_") and file.endswith(".json"):
            file_path = os.path.join(INPUT_DIR, file)
            print(f"Found business-specific profile: {file}")
            return file_path
    
    print("No business-specific BBB profile files found.")
    return None

def check_main_profile():
    """
    Check if the main bbb_profile_data.json exists and has valid data
    Returns True if it exists and has business data, False otherwise.
    """
    main_profile_path = os.path.join(INPUT_DIR, "bbb_profile_data.json")
    
    if not os.path.exists(main_profile_path):
        print("Main bbb_profile_data.json not found.")
        return False
    
    try:
        with open(main_profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if it has meaningful business data
        business_name = data.get('business_name', '')
        if business_name and business_name != "":
            print(f"Main profile found with business: {business_name}")
            return True
        else:
            print("Main profile exists but has no business name.")
            return False
            
    except Exception as e:
        print(f"Error reading main profile: {e}")
        return False

def run_color_extractor(profile_path):
    """
    Run the color_extractor.py script with the specified profile path
    """
    print(f"Running color extractor with profile: {profile_path}")
    
    # Path to the color_extractor.py script
    color_extractor_script = os.path.join(
        os.path.dirname(__file__), 
        "color_extractor.py"
    )
    
    try:
        # Run the color extractor script
        result = subprocess.run([
            sys.executable, 
            color_extractor_script
        ], capture_output=True, text=True, cwd=os.path.dirname(color_extractor_script))
        
        if result.returncode == 0:
            print("✅ Color extractor completed successfully!")
            print("Output:", result.stdout)
            return True
        else:
            print("❌ Color extractor failed!")
            print("Error:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error running color extractor: {e}")
        return False

def run_ai_color_generation():
    """
    Run the AI color generation script
    """
    print("Running AI color generation...")
    
    # Path to the generate_colors_with_ai.py script
    ai_script = os.path.join(
        os.path.dirname(__file__), 
        "generate_colors_with_ai.py"
    )
    
    try:
        # Run the AI color generation script
        result = subprocess.run([
            sys.executable, 
            ai_script
        ], capture_output=True, text=True, cwd=os.path.dirname(ai_script))
        
        if result.returncode == 0:
            print("✅ AI color generation completed successfully!")
            print("Output:", result.stdout)
            return True
        else:
            print("❌ AI color generation failed!")
            print("Error:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error running AI color generation: {e}")
        return False

def main():
    """
    Main function to orchestrate the color generation process
    """
    print("="*60)
    print("COLOR GENERATION PROCESS")
    print("="*60)
    
    # Step 1: Check for business-specific BBB profile
    business_profile = check_for_business_specific_profile()
    
    if business_profile:
        print(f"\n📁 Found business-specific profile: {business_profile}")
        print("🎨 Running color extractor with business-specific profile...")
        
        # Run color extractor with the business-specific profile
        success = run_color_extractor(business_profile)
        
        if success:
            print("✅ Color generation completed with business-specific profile!")
            return
        else:
            print("⚠️ Color extractor failed, falling back to AI generation...")
    
    # Step 2: Check main BBB profile
    print(f"\n📁 Checking main BBB profile...")
    main_profile_exists = check_main_profile()
    
    if main_profile_exists:
        print("🎨 Running color extractor with main profile...")
        
        # Run color extractor with the main profile
        success = run_color_extractor(None)  # color_extractor.py uses the default path
        
        if success:
            print("✅ Color generation completed with main profile!")
            return
        else:
            print("⚠️ Color extractor failed, falling back to AI generation...")
    
    # Step 3: Fall back to AI color generation
    print(f"\n🤖 No valid profiles found or color extractor failed.")
    print("🤖 Running AI color generation...")
    
    success = run_ai_color_generation()
    
    if success:
        print("✅ AI color generation completed!")
    else:
        print("❌ All color generation methods failed!")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("COLOR GENERATION PROCESS COMPLETED")
    print("="*60)

if __name__ == "__main__":
    main()

