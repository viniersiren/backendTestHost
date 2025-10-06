import json
import os

def filter_for_final_leads():
    """
    Filters the results from the BBB scraper to keep only the leads that
    were successfully matched with a BBB profile.
    """
    input_file = 'public/data/output/leads/raw/bbb_match.json'
    output_dir = 'public/data/output/leads/final'
    output_file = os.path.join(output_dir, 'final_leads.json')

    # Ensure the final output directory exists
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}")
        print("Please run the 'bbb_bus.py' script first.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {input_file}. The file might be empty or corrupt.")
        return

    # Filter the data to keep only entries with a valid BBB_url
    filtered_new = [
        entry for entry in data if entry.get('BBB_url') and entry['BBB_url'] != 'N/A'
    ]

    # Load existing final leads (if any) to support append-and-dedupe behavior
    existing_final = []
    try:
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_final = json.load(f)
    except json.JSONDecodeError:
        # If existing file is corrupt, fall back to empty
        existing_final = []

    # Dedupe by BBB_url (primary key). If missing BBB_url, the entry would not be in filtered_new.
    # Keep the first occurrence encountered (existing entries take precedence).
    seen_urls = set()
    merged = []

    # Seed with existing entries first
    for entry in existing_final:
        bbb_url = entry.get('BBB_url')
        if bbb_url and bbb_url not in seen_urls:
            seen_urls.add(bbb_url)
            merged.append(entry)

    # Add new filtered entries
    for entry in filtered_new:
        bbb_url = entry.get('BBB_url')
        if bbb_url and bbb_url not in seen_urls:
            seen_urls.add(bbb_url)
            merged.append(entry)

    # Save the merged, deduped data to the final output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)

    print(f"Successfully added {len(merged) - len(existing_final)} new unique leads with BBB profiles.")
    print(f"Final lead list saved to: {output_file} (total {len(merged)} leads)")

if __name__ == "__main__":
    filter_for_final_leads() 