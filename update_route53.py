#!/usr/bin/env python3
import json
import time
import boto3

HOSTED_ZONE_ID = "Z0139253HUTGC7MBSZGU"  # Replace with your real ID
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
