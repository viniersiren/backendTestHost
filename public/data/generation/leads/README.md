# Lead Generation Pipeline

This document outlines the step-by-step process for generating a filtered list of business leads using a single, unified command.

### Prerequisite: Activate Virtual Environment

Before running any scripts, you must activate the Python virtual environment, which contains all necessary dependencies. From the project root, run:

```bash
source public/data/generation/myenv/bin/activate
```
---

### The All-in-One Lead Generation Command

This single command orchestrates the entire lead generation pipeline, from initial search to final filtering.

**To start the full process, run:**

```bash
python public/data/generation/leads/run_pipeline.py [STATE] [START_ZIP] [END_ZIP]
```

**Example:**
To search for leads in Georgia from ZIP code 30002 to 30004, you would run:
```bash
python public/data/generation/leads/run_pipeline.py GA 30002 30004
```

---

### How It Works

The `run_pipeline.py` script executes the following steps in sequence:

1.  **Google Maps Scraping & Filtering:**
    *   A Chrome browser window will open and automatically search for "Roofing" businesses within the specified state and ZIP code range.
    *   It scrolls through all results to gather a comprehensive list.
    *   Once scraping is complete, it automatically filters this list to keep only businesses that **do not** have a website listed.
    *   **Intermediate Output:** `public/data/output/leads/raw/google_filter.json`

2.  **BBB Profile Matching:**
    *   The script then takes the filtered list of businesses (those without websites) and searches for each one on the Better Business Bureau website.
    *   It attempts to find a matching business profile to verify its legitimacy.
    *   **Intermediate Output:** `public/data/output/leads/raw/bbb_match.json`

3.  **Final Filtering:**
    *   Finally, the script processes the list of BBB-matched businesses and removes any that could not be successfully matched with a BBB profile.
    *   This ensures the final list contains only high-quality leads.

---

### Final Output

Your final, high-quality lead list—containing businesses with no website but with a verified BBB profile—will be saved to: 

**`public/data/output/leads/final/final_leads.json`** 