import os
import time
from bs4 import BeautifulSoup

INPUT_DIR = "docs"
OUTPUT_DIR = "docs/mobile"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def make_mobile_friendly(html_path, output_path):
    """Converts a Dillinger-exported HTML file into a mobile-friendly version."""
    with open(html_path, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "html.parser")

    # Ensure head tag exists
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))

    # Inject viewport meta tag if missing
    if not soup.find("meta", attrs={"name": "viewport"}):
        meta_tag = soup.new_tag("meta")
        meta_tag.attrs["name"] = "viewport"
        meta_tag.attrs["content"] = "width=device-width, initial-scale=1"
        soup.head.insert(0, meta_tag)

    # Inject custom mobile-friendly styles
    style_tag = soup.new_tag("style")
    style_tag.string = """
    body { font-size: 16px; line-height: 1.6; margin: 10px; padding: 10px; max-width: 100%; }
    pre, code { overflow-x: auto; word-wrap: break-word; white-space: pre-wrap; }
    table { display: block; width: 100%; overflow-x: auto; }
    """
    soup.head.append(style_tag)

    # Save the modified HTML
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(str(soup))

def process_all_files():
    """Processes all HTML files in the docs/ directory."""
    for root, _, files in os.walk(INPUT_DIR):
        for filename in files:
            if filename.endswith(".html"):
                input_file = os.path.join(root, filename)
                output_file = os.path.join(OUTPUT_DIR, filename)
                print(f"Processing: {filename} -> {output_file}")
                make_mobile_friendly(input_file, output_file)

def watch_directory():
    """Continuously watches the input directory for new files and processes them."""
    print("Watching for new HTML files in docs/")
    processed_files = set(os.listdir(INPUT_DIR))
    while True:
        current_files = set(os.listdir(INPUT_DIR))
        new_files = current_files - processed_files
        if new_files:
            for filename in new_files:
                if filename.endswith(".html"):
                    input_file = os.path.join(INPUT_DIR, filename)
                    output_file = os.path.join(OUTPUT_DIR, filename)
                    print(f"Processing: {filename} -> {output_file}")
                    make_mobile_friendly(input_file, output_file)
            processed_files = current_files
        time.sleep(5)

if __name__ == "__main__":
    process_all_files()
