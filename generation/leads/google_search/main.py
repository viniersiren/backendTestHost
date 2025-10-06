import sys
import os
import argparse

# Add the 'children' directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'children'))

try:
    # Import the main function from the scraper script
    from googlemaps_search import main as run_scraper
    # Import the main function from the filter script
    from google_filter import filter_google_search_data
except ImportError as e:
    print(f"Error: Could not import necessary functions from the 'children' directory.")
    print(f"Details: {e}")
    sys.exit(1)

def main():
    """
    Runs the Google Search and initial filtering part of the lead generation pipeline.
    This script is designed to be called with command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Run the Google Search and Filter pipeline.")
    parser.add_argument("state_abbr", type=str, help="The two-letter state abbreviation (e.g., GA).")
    parser.add_argument("start_zip", type=int, help="The starting zip code for the search.")
    parser.add_argument("end_zip", type=int, help="The ending zip code for the search.")
    args = parser.parse_args()

    print("===================================================")
    print(f"  STARTING GOOGLE SEARCH & FILTER for {args.state_abbr}: {args.start_zip}-{args.end_zip}")
    print("===================================================")

    print(f"\n--- Step 1: Running Google Maps Scraper for {args.state_abbr} ---")
    print(f"Searching ZIPs from {args.start_zip} to {args.end_zip}.")
    print("NOTE: This will open a browser window. You can stop it with Ctrl+C in the terminal.")
    
    run_scraper(state_abbr=args.state_abbr, start_zip=args.start_zip, end_zip=args.end_zip)
    print("--- Scraper finished ---")

    print("\n--- Step 2: Filtering Scraped Results ---")
    filter_google_search_data()
    print("--- Filter finished ---")
    
    print("\n===================================================")
    print("  GOOGLE SEARCH & FILTER PIPELINE COMPLETED")
    print("===================================================")

if __name__ == "__main__":
    main() 