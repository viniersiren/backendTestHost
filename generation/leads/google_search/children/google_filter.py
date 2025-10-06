import json
import os

def filter_google_search_data():
    """
    Filters the Google Search JSON data to find businesses with a name but no website.
    """
    input_file = 'public/data/output/leads/raw/google_search.json'
    output_dir = 'public/data/output/leads/raw'
    output_file = os.path.join(output_dir, 'google_filter.json')

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {input_file}")
        return

    # Filter the data
    filtered_data = [
        entry for entry in data
        if entry.get('BusinessName') != 'N/A' and entry.get('Website') == 'N/A'
    ]

    # Save the filtered data
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=4)

    print(f"Filtered {len(filtered_data)} businesses and saved to {output_file}")

if __name__ == "__main__":
    filter_google_search_data() 