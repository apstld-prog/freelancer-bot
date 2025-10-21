import requests
from pathlib import Path

# === STEP 1: ===
# Change this line to the full path of your ZIP file:
ZIP_PATH = Path(r"C:\Users\<YOUR_NAME>\Downloads\FREELANCER - PPH semi work final.zip")

# === Do not change anything below ===
if not ZIP_PATH.exists():
    print(f"❌ File not found: {ZIP_PATH}")
    exit(1)

print(f"⏳ Uploading {ZIP_PATH.name} ...")

with open(ZIP_PATH, "rb") as f:
    response = requests.post("https://file.io", files={"file": f})

if response.status_code == 200:
    data = response.json()
    print("\n✅ Upload complete!")
    print("🔗 Download link (send this to ChatGPT):")
    print(data["link"])
else:
    print(f"❌ Upload failed: {response.status_code}")
    print(response.text)
