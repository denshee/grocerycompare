"""
trigger_full_sync.py
--------------------
Orchestrates a full catalog sync for all active retailers.
"""

import subprocess
import time

def run_scraper(script_name, args=[]):
    print(f"\n🚀 Running {script_name}...")
    cmd = ["python", script_name] + args
    try:
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=False, text=True)
        duration = time.time() - start_time
        print(f"✅ {script_name} completed in {duration:.1f}s")
        return True
    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")
        return False

def main():
    print("=" * 60)
    print("FULL CATALOGUE REPLENISHMENT SYNC")
    print("=" * 60)
    
    scrapers = [
        "woolworths_full_catalog.py",
        "coles_full_catalog.py",
        "aldi_full_catalog.py"
    ]
    
    success_count = 0
    for s in scrapers:
        if run_scraper(s):
            success_count += 1
            
    print("\n" + "=" * 60)
    print(f"SYNC SUMMARY: {success_count}/{len(scrapers)} scrapers finished.")
    print("=" * 60)

if __name__ == "__main__":
    main()
