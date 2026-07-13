"""Install 3D dependencies for Remotion project."""
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent / "remotion_project"

def run(cmd, label):
    print(f"\n>>> {label}")
    r = subprocess.run(cmd, cwd=str(PROJECT), capture_output=True, text=True, timeout=300)
    if r.stdout:
        print(r.stdout[-3000:])
    if r.stderr:
        print("STDERR:", r.stderr[-2000:])
    print(f"Return code: {r.returncode}")
    return r.returncode

rc = 0
rc |= run(["npm", "install", "three", "@react-three/fiber", "@remotion/three", "@react-three/drei"], "npm install three + r3f + remotion/three + drei")
rc |= run(["npm", "install", "-D", "@types/three"], "npm install @types/three")

# Verify
rc |= run(["npm", "ls", "three", "@react-three/fiber", "@remotion/three"], "Verify packages installed")

print(f"\n{'SUCCESS' if rc == 0 else 'FAILED'}")
sys.exit(rc)
