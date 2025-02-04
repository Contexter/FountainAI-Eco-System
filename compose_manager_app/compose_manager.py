#!/usr/bin/env python3
"""
FountainAI Compose Manager Utility
-----------------------------------

This command‑line application scans through a specified root directory (representing your 
FountainAI Eco System) for immediate subdirectories that contain a Dockerfile.
It extracts configuration details (such as SERVICE_PORT from a .env file, if present)
and generates a docker‑compose.yml file in that same root directory.

Usage Examples:
  # Generate docker-compose.yml using services found under /path/to/FountainAI-Eco-System:
  python compose_manager.py --root /path/to/FountainAI-Eco-System

  # Generate with a custom output filename:
  python compose_manager.py --root /path/to/FountainAI-Eco-System --output my-compose.yml

Options:
  --root      The root directory to scan for service folders (required).
  --output    The output filename for the docker-compose file (default: docker-compose.yml).
"""

import os
import re
import argparse
import yaml  # PyYAML must be installed

# Default values
DEFAULT_INTERNAL_PORT = 8000  # If a service’s .env does not define SERVICE_PORT
HOST_PORT_START = 9000          # Starting host port for mapping

def get_service_directories(root_dir):
    """
    Scan the given root directory for immediate subdirectories that contain a Dockerfile.
    Returns a sorted list of such subdirectory names.
    """
    service_dirs = []
    try:
        for entry in os.listdir(root_dir):
            full_path = os.path.join(root_dir, entry)
            # Only consider immediate subdirectories
            if os.path.isdir(full_path):
                dockerfile_path = os.path.join(full_path, "Dockerfile")
                if os.path.exists(dockerfile_path):
                    service_dirs.append(entry)
    except Exception as e:
        print(f"Error scanning directory {root_dir}: {e}")
    print(f"Found service directories: {service_dirs}")
    return sorted(service_dirs)

def extract_service_port(service_dir):
    """
    Reads the .env file in the given service directory (if it exists) and extracts the SERVICE_PORT.
    Returns the port as an integer if found; otherwise returns DEFAULT_INTERNAL_PORT.
    """
    env_path = os.path.join(service_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                match = re.match(r"^\s*SERVICE_PORT\s*=\s*(\d+)", line)
                if match:
                    port = int(match.group(1))
                    print(f"In {service_dir}, found SERVICE_PORT: {port}")
                    return port
    print(f"In {service_dir}, SERVICE_PORT not found; using default {DEFAULT_INTERNAL_PORT}")
    return DEFAULT_INTERNAL_PORT

def generate_docker_compose_config(root_dir):
    """
    Scans the specified root directory for service folders and generates a docker-compose configuration dictionary.
    Each service is assigned a unique host port starting from HOST_PORT_START.
    """
    services = {}
    service_dirs = get_service_directories(root_dir)
    host_port = HOST_PORT_START

    for service in service_dirs:
        service_path = os.path.join(root_dir, service)
        internal_port = extract_service_port(service_path)
        services[service] = {
            "build": f"./{service}",
            "container_name": service,
            "ports": [f"{host_port}:{internal_port}"],
            "environment": [
                f"SERVICE_PORT={internal_port}"
            ],
            "networks": ["fountainai-net"]
        }
        print(f"Service {service}: host port {host_port} -> container port {internal_port}")
        host_port += 1

    compose_config = {
        "version": "3.9",
        "services": services,
        "networks": {
            "fountainai-net": {
                "driver": "bridge"
            }
        }
    }
    return compose_config

def write_compose_file(compose_config, output_file, root_dir):
    """
    Writes the docker-compose configuration dictionary to a YAML file in the specified root directory.
    """
    output_path = os.path.join(root_dir, output_file)
    with open(output_path, "w") as f:
        yaml.dump(compose_config, f, sort_keys=False)
    print(f"Generated docker-compose file at: {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Generate a docker-compose.yml for FountainAI services by scanning a specified root directory."
    )
    parser.add_argument(
        "--root",
        "-r",
        type=str,
        required=True,
        help="The root directory to scan for FountainAI service folders."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="docker-compose.yml",
        help="Output filename for the generated docker-compose configuration (default: docker-compose.yml)."
    )
    args = parser.parse_args()

    root_dir = os.path.abspath(args.root)
    if not os.path.exists(root_dir):
        print(f"Error: The directory '{root_dir}' does not exist.")
        return

    compose_config = generate_docker_compose_config(root_dir)
    write_compose_file(compose_config, args.output, root_dir)

if __name__ == "__main__":
    main()
