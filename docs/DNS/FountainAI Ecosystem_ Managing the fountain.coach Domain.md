

# **FountainAI Ecosystem: Managing the `fountain.coach` Domain**

## **1. Introduction**

Welcome to the FountainAI DNS Management guide! This document will show you how to:

- Create and manage DNS records for `fountain.coach` in Amazon Route 53.  
- Use an IAM user with minimal privileges to keep things secure.  
- Perform bulk (batch) updates via the AWS CLI or Python scripts.  
- Consider automation (e.g., building a microservice or using a helper script) to reduce manual overhead.

### **Why This Matters**

- Proper DNS configuration ensures your subdomains (like `action.fountain.coach`, `2fa.fountain.coach`) route to the correct servers or load balancers.  
- Maintaining the domain in a consistent, automated manner prevents downtime or misconfiguration.

---

## **2. Prerequisites & IAM User Setup**

1. **AWS Account & Route 53**  
   - We have a public hosted zone for `fountain.coach` in AWS Route 53.  
   - The domain’s Hosted Zone ID is typically found by running:
     ```bash
     aws route53 list-hosted-zones
     ```
     You’ll see an entry for `fountain.coach`, something like `/hostedzone/Z012345EXAMPLE`.

2. **IAM User**  
   - Create (or use) an IAM user with the minimum privileges needed to manage that specific hosted zone.  
   - Example policy snippet for a single hosted zone (replace `<HOSTED_ZONE_ID>` with your actual ID):
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": [
             "route53:ChangeResourceRecordSets",
             "route53:ListResourceRecordSets",
             "route53:GetHostedZone"
           ],
           "Resource": [
             "arn:aws:route53:::hostedzone/<HOSTED_ZONE_ID>"
           ]
         },
         {
           "Effect": "Allow",
           "Action": "route53:ListHostedZones",
           "Resource": "*"
         }
       ]
     }
     ```
   - During user creation, store the **Access Key ID** and **Secret Access Key** securely.

3. **Credential Storage**  
   - Add a named profile (e.g., `[route53-batch-user]`) to your `~/.aws/credentials` file. Example:
     ```ini
     [route53-batch-user]
     aws_access_key_id = YOUR_ACCESS_KEY_ID
     aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
     region = us-east-1
     ```
   - This ensures we can run commands as that user.

---

## **3. AWS CLI & Checking Access**

1. **Install/Update AWS CLI**  
   - Make sure you have AWS CLI v2 (or at least a recent version) installed.

2. **Validate Access**  
   - Run:
     ```bash
     aws route53 list-hosted-zones --profile route53-batch-user
     ```
   - You should see the hosted zone for `fountain.coach`. If not, verify the IAM policy and credentials.

---

## **4. Creating or Updating DNS in Batches**

### **4.1. The Batch File (JSON)**

- For each subdomain (e.g. `2fa.fountain.coach`), you can create a record set:
  ```json
  {
    "Comment": "Batch creation of subdomains for fountain.coach",
    "Changes": [
      {
        "Action": "UPSERT",
        "ResourceRecordSet": {
          "Name": "2fa.fountain.coach.",
          "Type": "A",
          "TTL": 300,
          "ResourceRecords": [
            { "Value": "1.2.3.4" }
          ]
        }
      },
      {
        "Action": "UPSERT",
        "ResourceRecordSet": {
          "Name": "action.fountain.coach.",
          "Type": "A",
          "TTL": 300,
          "ResourceRecords": [
            { "Value": "1.2.3.4" }
          ]
        }
      }
      // ... more records ...
    ]
  }
  ```

- **Tips**:
  - **`Action`**: Use `UPSERT` to create if absent or update if present.  
  - **`TTL`**: 300 seconds is typical (5 minutes).  
  - If you need a wildcard, do `"Name": "*.fountain.coach."`.  
  - If you need an alias to an AWS load balancer or CloudFront distribution, you’ll use `"AliasTarget"` instead of `ResourceRecords`.

### **4.2. Applying the Batch**

1. **Run the AWS CLI command**:
   ```bash
   aws route53 change-resource-record-sets \
       --hosted-zone-id Z012345EXAMPLE \
       --change-batch file://change-batch.json \
       --profile route53-batch-user
   ```
2. **Check the response** for a `ChangeInfo` object with a `Change ID`.
3. **Monitor** the status with:
   ```bash
   aws route53 get-change --id CHANGE_ID --profile route53-batch-user
   ```
   When status = `INSYNC`, Route 53 has applied your changes.

### **4.3. Verifying Records**

- **List** the record sets:
  ```bash
  aws route53 list-resource-record-sets \
      --hosted-zone-id Z012345EXAMPLE \
      --profile route53-batch-user
  ```
- **DNS Lookup** (e.g. `dig` or `nslookup`):
  ```bash
  dig action.fountain.coach +short
  ```
  Should show the IP or alias you set.

### **4.4. Changing Records Later**

- If you decide to switch to a new IP or load balancer, just create **another** batch JSON with the same `Names` but updated `Value`s.  
- Run the **same** CLI command with `UPSERT` to overwrite.  

---

## **5. Automation Options**

### **5.1. Using a Helper Script to Parse a Caddyfile**

If you manage your subdomains in a **Caddyfile** (where each subdomain or wildcard is declared in a block), you can automate DNS record generation with a script that:

1. **Parses** your Caddyfile for lines like `subdomain.fountain.coach {` or `*.fountain.coach {`.  
2. **Generates** a JSON batch file using those subdomains.  
3. **Outputs** `change-batch.json`, ready for Route 53.

Below is a sample Python script (`caddyfile2BatchManageRoute53.py`) that does exactly this. It assumes each relevant line in your Caddyfile ends with a `{` and includes `.fountain.coach`.

```python
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
```

#### **How to Use**

1. **Make executable** (on Linux/Mac):  
   ```bash
   chmod +x caddyfile2BatchManageRoute53.py
   ```
2. **Run** it, passing the path to your Caddyfile and optionally an IP or LB endpoint:
   ```bash
   ./caddyfile2BatchManageRoute53.py /path/to/Caddyfile 1.2.3.4
   ```
   - If you don’t provide an endpoint, it will prompt you interactively.

3. **Check** the generated `change-batch.json` file.  
4. **Apply** it to Route 53:
   ```bash
   aws route53 change-resource-record-sets \
       --hosted-zone-id <YOUR_HOSTED_ZONE_ID> \
       --change-batch file://change-batch.json \
       --profile route53-batch-user
   ```

**Pros**:  
- Automatically stays in sync with subdomains specified in your Caddyfile.  
- Minimizes manual editing.  

**Cons**:  
- Relies on your Caddyfile being consistently structured.  
- For more advanced Caddy configs (multiple lines per block, etc.), you may need a more robust parser.

### **5.2. Building a Dedicated Microservice**

If you anticipate **frequent** DNS changes, or want to integrate with other internal tools, you can:

1. **Build a Python or Node.js microservice** that:  
   - Receives REST calls (e.g. “Create record `foo.fountain.coach` → IP `1.2.3.4`”).  
   - Calls the Route 53 API under the hood (using the same approach as above).  
   - Tracks changes, logs them for auditing, and possibly sends Slack/email notifications.  

2. **Integrate** with CI/CD or other automation pipelines for a more robust DevOps flow.

**Pros**:  
- Central authority for DNS changes.  
- Reduces manual steps.  
- Potential for auditing and logging each DNS update.

**Cons**:  
- Requires building & maintaining additional service infrastructure.  
- Must ensure tight security so only authorized requests can update DNS.

For smaller or infrequent updates, the **AWS CLI** or a simple **Python script** is often sufficient.

---

## **6. Troubleshooting & Maintenance**

1. **Common Issues**:
   - **Permission Errors**: Check your IAM policy.  
   - **Record Already Exists**: Use `UPSERT` instead of `CREATE` if you’re not sure.  
   - **DNS Propagation Delays**: Even after Route 53 is `INSYNC`, global DNS caches may take up to the TTL to update.

2. **Logging & Auditing**:
   - Each `change-resource-record-sets` call is recorded in **CloudTrail** if enabled.  
   - Keep track of your `change-batch.json` files, scripts, or microservice logs in version control (Git) for historical reference.

3. **Housekeeping**:
   - Periodically use `aws route53 list-resource-record-sets` to see if there are stale or unused records you can remove.  
   - If you have a wildcard record (`*.fountain.coach`), be mindful of conflicts with explicit subdomains.

---

# **Appendix: Example Python Automation for Manual JSON**

Here’s a **Python script** (`update_route53.py`) for interactive updates if you’re **not** auto‐generating from a Caddyfile but already have your `change-batch.json`:

```python
#!/usr/bin/env python3
import json
import time
import boto3

HOSTED_ZONE_ID = "Z012345EXAMPLE"  # Replace with your real ID
PROFILE_NAME = "route53-batch-user"

def main():
    # 1. Initialize session & client
    session = boto3.Session(profile_name=PROFILE_NAME)
    route53 = session.client('route53')

    # 2. Load the JSON change batch
    with open('change-batch.json') as f:
        change_batch_content = json.load(f)

    # 3. Preview
    print("Proposed Route53 changes:")
    for change in change_batch_content["Changes"]:
        record_name = change["ResourceRecordSet"]["Name"]
        record_type = change["ResourceRecordSet"]["Type"]
        records = [
            rr["Value"]
            for rr in change["ResourceRecordSet"].get("ResourceRecords", [])
        ]
        print(f"{change['Action']} - {record_name} [{record_type}]: {records}")

    # 4. Confirm
    confirm = input("Are you sure you want to proceed? (y/n) ")
    if confirm.lower() != 'y':
        print("Aborting.")
        return

    # 5. Submit changes
    response = route53.change_resource_record_sets(
        HostedZoneId=HOSTED_ZONE_ID,
        ChangeBatch=change_batch_content
    )
    change_id = response['ChangeInfo']['Id']
    print(f"Change submitted, ID: {change_id}")

    # 6. Wait for INSYNC
    while True:
        status_resp = route53.get_change(Id=change_id)
        status = status_resp['ChangeInfo']['Status']
        if status == 'INSYNC':
            print("Record changes are INSYNC.")
            break
        else:
            print(f"Current status = {status}, waiting 10s...")
            time.sleep(10)

    # 7. Optional: List updated records
    print("Listing final records...")
    paginator = route53.get_paginator('list_resource_record_sets')
    for page in paginator.paginate(HostedZoneId=HOSTED_ZONE_ID):
        for record_set in page['ResourceRecordSets']:
            print(record_set)

if __name__ == "__main__":
    main()
```

**Usage**:
```bash
python3 update_route53.py
```
It will show a preview, prompt for confirmation, apply changes, wait for propagation, and then list records for final verification.

---

## **Conclusion**

- You now have a **unified onboarding doc** that walks through everything an admin or team member needs to safely manage DNS for `fountain.coach`.  
- Options include:
  - Direct **JSON batch** usage with the AWS CLI.  
  - Automated **Python scripts** (either referencing a static JSON file or **parsing a Caddyfile**).  
  - Building a **microservice** for frequent DNS updates.  
- For more detail on Route 53, consult the official [AWS Route 53 documentation](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Welcome.html).

**Happy DNSing!** If you have further questions, reach out on your internal Slack or reference this doc for next steps.