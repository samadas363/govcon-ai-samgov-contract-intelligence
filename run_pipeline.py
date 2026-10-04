import subprocess
import sys
from datetime import datetime


def run_script(script_name):
    print("\n" + "=" * 70)
    print(f"RUNNING: {script_name}")
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, script_name],
        text=True
    )

    if result.returncode != 0:
        print(f"\nERROR: {script_name} failed.")
        sys.exit(result.returncode)

    print(f"\nSUCCESS: {script_name} completed.")


def main():
    start_time = datetime.now()

    print("=" * 70)
    print("GOVCON AI PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time}")

    run_script("stage1_sam_ingest.py")
    run_script("run_scoring.py")
    run_script("sync_google_sheets.py")

    end_time = datetime.now()

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETED")
    print("=" * 70)
    print(f"Started : {start_time}")
    print(f"Finished: {end_time}")
    print(f"Duration: {end_time - start_time}")


if __name__ == "__main__":
    main()