#!/usr/bin/env python3
"""Create and manage a sandbox with detailed timing information for debugging"""

import argparse
import os
import time
from collections import defaultdict
from datetime import datetime

from prometheus_client import start_http_server, Histogram

from koyeb import Sandbox
from koyeb.sandbox.utils import get_api_client

prom_metric = Histogram(
    'sandbox_operation_duration_seconds',
    'Duration of sandbox operations in seconds',
    ['operation', 'category', 'region'],
    buckets=[
    0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
    1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0,
    2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0,
    3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0,
    4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 5.0,
    5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.0,
    6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.0,
    7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 8.0,
    8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 9.0,
    9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 10.0,
    10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11.0,
    11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 12.0,
    12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 13.0,
    13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 14.0,
    14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 15.0,
    16.0, 17.0, 18.0, 19.0, 20.0, 30.0, 45.0, 60.0, float("inf")
]
)

class TimingTracker:
    """Track timing information for operations"""
    def __init__(self):
        self.operations = []
        self.categories = defaultdict(list)


    def record(self, name, duration, category="general", region=""):
        """Record an operation's timing"""
        self.operations.append({
            'name': name,
            'duration': duration,
            'category': category,
            'timestamp': datetime.now()
        })
        self.categories[category].append(duration)

        prom_metric.labels(operation=name, category=category, region=region).observe(duration)

    def record_total_time(self, region=""):
        total_time = self.get_total_time()
        prom_metric.labels(operation="total", category="total", region=region).observe(total_time)

    def get_total_time(self):
        """Get total time for all operations"""
        return sum(op['duration'] for op in self.operations)

    def get_category_total(self, category):
        """Get total time for a specific category"""
        return sum(self.categories[category])

    def print_recap(self):
        """Print a detailed recap of all timings"""
        print("\n" + "="*70)
        print(" TIMING SUMMARY")
        print("="*70)

        if not self.operations:
            print("No operations recorded")
            return

        total_time = self.get_total_time()

        # Print individual operations
        print()

        for op in self.operations:
            percentage = (op['duration'] / total_time * 100) if total_time > 0 else 0
            bar_length = int(percentage / 2)  # 50 chars = 100%
            bar = "█" * bar_length

            print(f"  {op['name']:<30} {op['duration']:6.2f}s  {percentage:5.1f}%  {bar}")

        print()
        print("-" * 70)
        print(f"  {'TOTAL':<30} {total_time:6.2f}s  100.0%")
        print("="*70)

def get_instance_status(instances_api, sandbox_id):
    rep = instances_api.list_instances(service_id=sandbox_id)
    if len(rep.instances) == 0:
        return ""
    return str(rep.instances[0].status)

def main(region="fra"):

    
    print("Starting sandbox operations...")
    
    api_token = os.getenv("KOYEB_API_TOKEN")
    if not api_token:
        print("Error: KOYEB_API_TOKEN not set")
        return

    instances_api = get_api_client(api_token=api_token)[2]

    script_start = time.time()
    tracker = TimingTracker()

    sandbox = None
    try:
        # Create sandbox with timing
        print("  → Creating sandbox...")
        sandbox_create_start = time.time()
        sandbox = Sandbox.create(
            image="koyeb/sandbox",
            name="example-sandbox-timed",
            wait_ready=False,
            api_token=api_token,
            delete_after_delay=60,
            region=region,
        )
        sandbox_create_duration = time.time() - sandbox_create_start
        tracker.record("Sandbox creation", sandbox_create_duration, "setup", region=region)
        print(f"    ✓ took {sandbox_create_duration:.1f}s")

        instance_status = ""
        print("  → Waiting for instance creation...")
        instance_create_start = time.time()
        while instance_status == "":
            instance_status = get_instance_status(instances_api, sandbox.id)
            if instance_status == "":
                time.sleep(0.2)
        instance_create_duration = time.time() - instance_create_start
        tracker.record("instance creation", instance_create_duration, "setup", region=region)
        print(f"    ✓ took {instance_create_duration:.1f}s")

        print("  → Waiting for instance allocation...")
        instance_allocation_start = time.time()
        while instance_status not in ('InstanceStatus.STARTING', 'InstanceStatus.ALLOCATING', 'InstanceStatus.HEALTHY'):
            instance_status = get_instance_status(instances_api, sandbox.id)
            if instance_status == "":
                time.sleep(0.2)
        instance_allocation_duration = time.time() - instance_allocation_start
        tracker.record("instance allocation", instance_allocation_duration, "setup", region=region)
        print(f"    ✓ took {instance_allocation_duration:.1f}s")

        print("  → Waiting for instance to be started...")
        instance_starting_start = time.time()
        while instance_status not in ('InstanceStatus.STARTING', 'InstanceStatus.HEALTHY'):
            instance_status = get_instance_status(instances_api, sandbox.id)
            if instance_status == "":
                time.sleep(0.2)
        instance_starting_duration = time.time() - instance_starting_start
        tracker.record("instance starting", instance_starting_duration, "setup", region=region)
        print(f"    ✓ took {instance_starting_duration:.1f}s")

        # Check health with timing
        print("  → Checking sandbox health...")
        health_start = time.time()
        is_healthy = False
        while not is_healthy:
            is_healthy = sandbox.is_healthy()
            time.sleep(0.05)
        health_duration = time.time() - health_start
        tracker.record("Health check", health_duration, "monitoring", region=region)
        print(f"    ✓ took {health_duration:.1f}s")

        tracker.record_total_time(region=region)

    except Exception as e:
        print(f"\n✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if sandbox:
            print("  → Deleting sandbox...")
            delete_start = time.time()
            sandbox.delete()
            delete_duration = time.time() - delete_start
            tracker.record("Sandbox deletion", delete_duration, "cleanup", region=region)
            print(f"    ✓ took {delete_duration:.1f}s")
        
        print("\n✓ All operations completed")
        
        # Print detailed recap
        tracker.print_recap()


if __name__ == "__main__":
    # 4. Start the Prometheus endpoint on port 7777
    print("Starting Prometheus metrics server on port 7777...")
    start_http_server(7777)
    while True:
        for region in ("fra", "was", "sin"):
            print("measuring time in", region)
            main(region=region)
            time.sleep(60)
        print("sleeping 3 minutes")
        time.sleep(180)
