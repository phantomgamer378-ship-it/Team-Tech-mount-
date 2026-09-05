import os
from faster_whisper import WhisperModel

def download_models():
    print("Downloading faster-whisper small model (CPU/int8)...")
    try:
        # Initializing the model downloads it to the huggingface cache
        model = WhisperModel("small", device="cpu", compute_type="int8")
        print("faster-whisper model downloaded successfully.")
    except Exception as e:
        print(f"Failed to download faster-whisper model: {e}")

if __name__ == "__main__":
    download_models()
