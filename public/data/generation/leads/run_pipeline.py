import subprocess
import sys
import os
import argparse
import json

def run_script(command):
    """Runs a script using subprocess and handles errors."""
    print(f"\n{'='*20}\n[RUNNING]: {' '.join(command)}\n{'='*20}")
    process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr)
    process.wait() # Wait for the script to complete
    if process.returncode != 0:
        print(f"\n{'!'*20}\n[ERROR]: Script '{command[1]}' failed with return code {process.returncode}.\n{'!'*20}")
        sys.exit(1) # Exit the pipeline if any step fails
    print(f"\n{'*'*20}\n[SUCCESS]: Script '{command[1]}' finished.\n{'*'*20}")

def main():
    """
    Main function to orchestrate the entire lead generation pipeline.
    """
    parser = argparse.ArgumentParser(description="Run the full lead generation pipeline.")
    parser.add_argument("state_abbr", type=str, help="The two-letter state abbreviation (e.g., GA).")
    parser.add_argument("start_zip", type=int, help="The starting zip code for the search.")
    parser.add_argument("end_zip", type=int, help="The ending zip code for the search.")
    args = parser.parse_args()
    
    # Define paths to the scripts relative to this script's location
    base_dir = os.path.dirname(__file__)
    googlemaps_search_script = os.path.join(base_dir, 'google_search', 'children', 'googlemaps_search.py')
    google_filter_script = os.path.join(base_dir, 'google_search', 'children', 'google_filter.py')
    bbb_parallel_script = os.path.join(base_dir, 'BBB', 'bbb_bus_parallel.py')
    bbb_filter_script = os.path.join(base_dir, 'BBB', 'filtering_for_bbb.py')
    
    print(f"\n{'#'*50}\n# STARTING FULL LEAD GENERATION PIPELINE for {args.state_abbr}: {args.start_zip}-{args.end_zip} #\n{'#'*50}")

    # --- Step 1: Run Google Search in 5 parallel browsers and then filter ---
    raw_dir = os.path.join('public', 'data', 'output', 'leads', 'raw')
    os.makedirs(raw_dir, exist_ok=True)
    by_zip_dir = os.path.join(raw_dir, 'by_zip')
    os.makedirs(by_zip_dir, exist_ok=True)

    # Compute GA-valid ZIPs first, then partition those evenly across workers
    workers = 10
    state = (args.state_abbr or '').upper()
    def in_ga(zip_code: int) -> bool:
        return (30000 <= zip_code <= 31999) or (39800 <= zip_code <= 39999)
    if state == 'GA':
        candidate_zips = [z for z in range(args.start_zip, args.end_zip + 1) if in_ga(z)]
    else:
        candidate_zips = list(range(args.start_zip, args.end_zip + 1))

    if not candidate_zips:
        print("No valid ZIPs in the requested range. Exiting.")
        sys.exit(0)

    per_worker = max(1, (len(candidate_zips) + workers - 1) // workers)
    zip_slices = [candidate_zips[i:i + per_worker] for i in range(0, len(candidate_zips), per_worker)]

    processes = []
    for idx, zip_slice in enumerate(zip_slices[:workers]):
        env = os.environ.copy()
        env['GGL_TRACKER_BYPASS'] = '1'
        # Write each worker's results into the shared by-zip directory
        env['GGL_OUTPUT_BY_ZIP_DIR'] = by_zip_dir
        # Provide explicit ZIP list so workers only process usable ZIPs
        env['GGL_ZIP_LIST'] = json.dumps(zip_slice)
        cmd = [
            sys.executable,
            googlemaps_search_script,
            args.state_abbr,
            str(min(zip_slice)),
            str(max(zip_slice))
        ]
        print(f"\n{'='*20}\n[SPAWN WORKER {idx}]: {' '.join(cmd)} -> {len(zip_slice)} zips -> by-zip dir {by_zip_dir}\n{'='*20}")
        p = subprocess.Popen(cmd, env=env, stdout=sys.stdout, stderr=sys.stderr)
        processes.append((idx, p))

    # Wait for workers
    failed = False
    for idx, p in processes:
        rc = p.wait()
        if rc != 0:
            failed = True
            print(f"\n{'!'*20}\n[ERROR]: Google worker {idx} failed with code {rc}.\n{'!'*20}")
    if failed:
        sys.exit(1)

    # Merge central by-zip folder into single google_search.json
    merged_path = os.path.join(raw_dir, 'google_search.json')
    merged = []
    seen = set()  # dedupe on (BusinessName, Location)
    # include any existing content first
    if os.path.exists(merged_path):
        try:
            with open(merged_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                for item in existing if isinstance(existing, list) else []:
                    key = (item.get('BusinessName'), item.get('Location'))
                    if key not in seen:
                        seen.add(key)
                        merged.append(item)
        except Exception:
            pass

    # Walk by-zip dir
    try:
        for name in sorted(os.listdir(by_zip_dir)):
            if not name.endswith('.json'):
                continue
            zip_path = os.path.join(by_zip_dir, name)
            try:
                with open(zip_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        key = (item.get('BusinessName'), item.get('Location'))
                        if key not in seen:
                            seen.add(key)
                            merged.append(item)
            except Exception:
                continue
    except FileNotFoundError:
        pass

    with open(merged_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)
    print(f"Merged {len(merged)} records from {by_zip_dir} into {merged_path}")

    # Run the filter to produce google_filter.json
    run_script([
        sys.executable,
        google_filter_script
    ])

    # --- Step 2: Run BBB Search (parallel, 5 browsers) ---
    run_script([
        sys.executable,
        bbb_parallel_script
    ])

    # Ensure BBB parallel output is in expected path for the filter
    bbb_parallel_output = os.path.join(raw_dir, 'bbb_match_parallel.json')
    bbb_expected_output = os.path.join(raw_dir, 'bbb_match.json')
    merged_bbb = []
    if os.path.exists(bbb_expected_output):
        try:
            with open(bbb_expected_output, 'r', encoding='utf-8') as f:
                merged_bbb = json.load(f)
        except Exception:
            merged_bbb = []
    try:
        if os.path.exists(bbb_parallel_output):
            with open(bbb_parallel_output, 'r', encoding='utf-8') as f:
                new_bbb = json.load(f)
                if isinstance(new_bbb, list):
                    merged_bbb.extend(new_bbb)
    except Exception:
        pass
    # Write combined bbb_match.json
    with open(bbb_expected_output, 'w', encoding='utf-8') as f:
        json.dump(merged_bbb, f, ensure_ascii=False, indent=2)

    # --- Step 3: Run Final BBB Filter ---
    # This script creates the final lead list.
    run_script([
        sys.executable,
        bbb_filter_script
    ])
    
    print(f"\n{'#'*50}\n# LEAD GENERATION PIPELINE COMPLETED SUCCESSFULLY #\n{'#'*50}")

if __name__ == "__main__":
    main() 