import os
from collections import defaultdict

# Define the path to the services (relative to repo root)
SERVICES_DIR = os.getcwd()
REPORT_FILE = "env_report.md"

def get_env_files():
    """Finds all services with and without .env files."""
    services = [d for d in os.listdir(SERVICES_DIR) if os.path.isdir(d)]
    env_files = {s: os.path.join(SERVICES_DIR, s, ".env") for s in services}
    
    existing_env_files = {s: f for s, f in env_files.items() if os.path.exists(f)}
    missing_env_files = {s: f for s, f in env_files.items() if not os.path.exists(f)}
    
    return existing_env_files, missing_env_files

def parse_env_file(env_file):
    """Parses an .env file and returns a dictionary of key-value pairs."""
    variables = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # Ignore comments and empty lines
            key, _, value = line.partition("=")
            variables[key.strip()] = value.strip()
    return variables

def analyze_env_files(existing_env_files):
    """Analyzes all found .env files and collects insights."""
    env_data = {}
    all_keys = set()
    duplicate_keys = defaultdict(list)
    
    for service, env_file in existing_env_files.items():
        env_data[service] = parse_env_file(env_file)
        all_keys.update(env_data[service].keys())

    # Check for missing keys across services
    missing_keys = {key: [] for key in all_keys}
    for service, vars_dict in env_data.items():
        for key in all_keys:
            if key not in vars_dict:
                missing_keys[key].append(service)

    # Check for duplicate keys within each service
    for service, vars_dict in env_data.items():
        seen_keys = set()
        for key in vars_dict:
            if key in seen_keys:
                duplicate_keys[service].append(key)
            else:
                seen_keys.add(key)

    return env_data, missing_keys, duplicate_keys

def generate_markdown_report(existing_env_files, missing_env_files, env_data, missing_keys, duplicate_keys):
    """Generates a Markdown report summarizing the .env analysis."""
    with open(REPORT_FILE, "w") as md:
        md.write("# FountainAI `.env` Analysis Report\n\n")

        md.write("## ✅ Services with `.env` Files\n")
        for service in existing_env_files.keys():
            md.write(f"- **{service}** ({len(env_data[service])} variables)\n")

        md.write("\n## ❌ Services Missing `.env` Files\n")
        for service in missing_env_files.keys():
            md.write(f"- **{service}**\n")

        md.write("\n## 📌 Variables Per Service\n")
        md.write("| Service | Variable | Value |\n|---------|----------|-------|\n")
        for service, vars_dict in env_data.items():
            for key, value in vars_dict.items():
                md.write(f"| {service} | {key} | {value} |\n")

        md.write("\n## 🔍 Missing Variables Across Services\n")
        md.write("| Variable | Missing in Services |\n|----------|----------------------|\n")
        for key, services in missing_keys.items():
            if services:
                md.write(f"| {key} | {', '.join(services)} |\n")

        md.write("\n## ⚠️ Duplicate Variables Within Services\n")
        md.write("| Service | Duplicate Variables |\n|---------|----------------------|\n")
        for service, keys in duplicate_keys.items():
            if keys:
                md.write(f"| {service} | {', '.join(keys)} |\n")

        md.write("\n## 🎯 Improvement Recommendations\n")
        md.write("- Ensure all services have an `.env` file.\n")
        md.write("- Standardize missing keys across services.\n")
        md.write("- Remove duplicate keys within `.env` files.\n")
        md.write("- Review variable consistency across services.\n")

if __name__ == "__main__":
    existing_env_files, missing_env_files = get_env_files()
    env_data, missing_keys, duplicate_keys = analyze_env_files(existing_env_files)
    generate_markdown_report(existing_env_files, missing_env_files, env_data, missing_keys, duplicate_keys)

    print(f"✅ Analysis complete! Report saved to `{REPORT_FILE}`.")
