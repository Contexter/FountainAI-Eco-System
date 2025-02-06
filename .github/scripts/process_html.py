import os
from bs4 import BeautifulSoup

INPUT_DIR = "docs"
OUTPUT_DIR = "docs/mobile"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def make_mobile_friendly(html_path, output_path):
    with open(html_path, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "html.parser")

    # Inject viewport meta tag if missing
    if not soup.find("meta", attrs={"name": "viewport"}):
        meta_tag = soup.new_tag("meta", name="viewport", content="width=device-width, initial-scale=1")
        soup.head.insert(0, meta_tag)

    # Inject custom mobile-friendly styles
    style_tag = soup.new_tag("style")
    style_tag.string = """
    body { font-size: 16px; line-height: 1.6; margin: 10px; padding: 10px; max-width: 100%; }
    pre, code { overflow-x: auto; word-wrap: break-word; white-space: pre-wrap; }
    table { display: block; width: 100%; overflow-x: auto; }
    """
    soup.head.append(style_tag)

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(str(soup))

def process_all_files():
    """Processes all HTML files in docs/"""
    for root, _, files in os.walk(INPUT_DIR):
        for filename in files:
            if filename.endswith(".html"):
                input_file = os.path.join(root, filename)
                output_file = os.path.join(OUTPUT_DIR, filename)
                print(f"Processing: {filename} -> {output_file}")
                make_mobile_friendly(input_file, output_file)

if __name__ == "__main__":
    process_all_files()

