#!/usr/bin/env python3
"""
caddyfile2BatchManageRoute53.py

Reads a Caddyfile for *.fountain.coach or subdomain.fountain.coach site blocks
and generates a Route 53 JSON batch file (change-batch.json) to UPSERT A records.

Usage:
  ./caddyfile2BatchManageRoute53.py <path_to_caddyfile> [optional IP or LB endpoint]
If no endpoint is provided, you'll be prompted for one.
"""

import sys
import re
import json

def main():
    if len(sys.argv) < 2:
        print("Usage: caddyfile2BatchManageRoute53.py <path_to_caddyfile> [IP_or_LB_endpoint]")
        sys.exit(1)

    caddyfile_path = sys.argv[1]

    if len(sys.argv) >= 3:
        default_ip = sys.argv[2]
    else:
        default_ip = input("Enter the IP or load balancer endpoint for these subdomains: ").strip()
        if not default_ip:
            print("No IP/endpoint provided. Exiting.")
            sys.exit(1)

    # Read lines from the Caddyfile
    try:
        with open(caddyfile_path, 'r') as f:
            caddy_lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Caddyfile not found at {caddyfile_path}")
        sys.exit(1)

    # Regex: match something like:
    #   subdomain.fountain.coach {
    #   *.fountain.coach {
    domain_pattern = re.compile(r'^([\S]+\.fountain\.coach)\s*\{')

    subdomains = []
    for line in caddy_lines:
        line = line.strip()
        match = domain_pattern.match(line)
        if match:
            domain = match.group(1)
            if not domain.endswith('.'):
                domain += '.'
            subdomains.append(domain)

    # Deduplicate
    subdomains = list(dict.fromkeys(subdomains))

    if not subdomains:
        print("No fountain.coach subdomains found in the provided Caddyfile.")
        sys.exit(0)

    # Build the JSON change batch
    change_batch = {
        "Comment": "Batch creation/update of subdomains from Caddyfile for fountain.coach",
        "Changes": []
    }

    for sd in subdomains:
        record_change = {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": sd,
                "Type": "A",
                "TTL": 300,
                "ResourceRecords": [
                    { "Value": default_ip }
                ]
            }
        }
        change_batch["Changes"].append(record_change)

    # Write to "change-batch.json"
    output_file = "change-batch.json"
    with open(output_file, 'w') as f:
        json.dump(change_batch, f, indent=2)

    print(f"Found {len(subdomains)} subdomain(s).")
    print("Generated change-batch.json with the following records:")
    for c in change_batch["Changes"]:
        print(f'  - {c["ResourceRecordSet"]["Name"]} -> {default_ip}')
    print(f"\nUse 'aws route53 change-resource-record-sets --hosted-zone-id <ID> "
          f"--change-batch file://{output_file}' to apply changes.")

if __name__ == "__main__":
    main()
