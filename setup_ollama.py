"""
Setup script to configure Ollama environment for custom model directory.
Run this once to set environment variables and configure the system.
"""

import os
import sys
import subprocess
from pathlib import Path

# Ollama installation and models directory
OLLAMA_BIN = r"C:\Users\tirth\AppData\Local\Programs\Ollama\ollama.exe"
OLLAMA_MODELS_DIR = r"D:\OllamaModels"


def setup_ollama_environment():
    """Configure environment variables for Ollama with custom models directory."""

    print("Setting up Ollama environment...")
    print(f"Ollama binary: {OLLAMA_BIN}")
    print(f"Models directory: {OLLAMA_MODELS_DIR}")

    # Set environment variables for this session
    os.environ['OLLAMA_HOME'] = OLLAMA_MODELS_DIR
    os.environ['OLLAMA_MODELS'] = OLLAMA_MODELS_DIR

    # Add Ollama to PATH
    ollama_dir = str(Path(OLLAMA_BIN).parent)
    if ollama_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] = ollama_dir + \
            os.pathsep + os.environ.get('PATH', '')

    print(f"✅ Environment variables set:")
    print(f"   OLLAMA_HOME={os.environ['OLLAMA_HOME']}")
    print(f"   OLLAMA_MODELS={os.environ['OLLAMA_MODELS']}")
    print(f"   PATH includes: {ollama_dir}")

    # Verify Ollama is accessible
    try:
        result = subprocess.run([OLLAMA_BIN, "list"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print("\n✅ Ollama is accessible!")
            print("Available models:")
            print(result.stdout)
            return True
        else:
            print(f"⚠️  Ollama error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error accessing Ollama: {e}")
        return False


def set_permanent_environment_variables():
    """Set environment variables permanently (Windows)."""
    import subprocess

    print("\nSetting permanent environment variables (requires admin)...")

    # Set for current user (no admin required)
    try:
        subprocess.run([
            "powershell", "-Command",
            f'[Environment]::SetEnvironmentVariable("OLLAMA_HOME", "{OLLAMA_MODELS_DIR}", "User")'
        ], check=True)

        subprocess.run([
            "powershell", "-Command",
            f'[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "{OLLAMA_MODELS_DIR}", "User")'
        ], check=True)

        print("✅ Permanent environment variables set for current user")
        print(
            "   Note: You may need to restart your terminal/IDE for changes to take effect")
        return True
    except Exception as e:
        print(f"⚠️  Could not set permanent variables: {e}")
        return False


if __name__ == "__main__":
    success = setup_ollama_environment()

    if success:
        print("\n" + "="*70)
        print("Setup successful! You can now run main.py")
        print("="*70)

        if len(sys.argv) > 1 and sys.argv[1] == "--permanent":
            set_permanent_environment_variables()
    else:
        print("\n" + "="*70)
        print("Setup failed. Please check Ollama installation.")
        print("="*70)
        sys.exit(1)
