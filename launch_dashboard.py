#!/usr/bin/env python3
"""
Quick launcher for the healthcare access dashboard.
Usage: python launch_dashboard.py
"""

import sys
import subprocess
from pathlib import Path

def main():
    dashboard_path = Path(__file__).parent / "dashboard" / "app_modern.py"
    
    if not dashboard_path.exists():
        print(f"❌ Dashboard not found at {dashboard_path}")
        sys.exit(1)
    
    print("🚀 Launching Healthcare Access Intelligence Dashboard...")
    print("📍 Navigate to http://localhost:8501 in your browser")
    print("\n" + "="*70)
    print("✨ Modern UI Features:")
    print("  • 🎨 Beautiful gradient interface with purple theme")
    print("  • 🗺️  Interactive maps with intuitive red-to-green color scheme")
    print("  • 📊 Lorenz curves & inequality analysis")
    print("  • 🎯 Priority zone identification")
    print("  • 📥 Export results as CSV/GeoJSON")
    print("  • ⚡ Real-time SDW-2SFCA computation")
    print("="*70 + "\n")
    
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run",
            str(dashboard_path),
            "--server.port=8501",
            "--server.headless=true"
        ], check=True)
    except KeyboardInterrupt:
        print("\n\n✅ Dashboard stopped")
    except Exception as e:
        print(f"\n❌ Error launching dashboard: {e}")
        print("\nTroubleshooting:")
        print("  1. Install dependencies: pip install -r requirements.txt")
        print("  2. Run pipeline first: python run_pipeline.py --config case_studies/dc.yaml")
        print("  3. Check data files exist in outputs/results/")
        sys.exit(1)

if __name__ == "__main__":
    main()
