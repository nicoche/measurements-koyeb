#!/usr/bin/env python3
"""Create and manage a sandbox with detailed timing information for debugging"""

import argparse
import os
import time
from collections import defaultdict
from datetime import datetime

from prometheus_client import start_http_server, Gauge

from koyeb import Sandbox
from koyeb.sandbox.utils import get_api_client

class TimingTracker:
    """Track timing information for operations"""
    def __init__(self):
        self.operations = []
        self.categories = defaultdict(list)

        self.prom_metric = Gauge(
            'sandbox_operation_duration_seconds',
            'Duration of sandbox operations in seconds',
            ['operation', 'category']
        )

    def record(self, name, duration, category="general"):
        """Record an operation's timing"""
        self.operations.append({
            'name': name,
            'duration': duration,
            'category': category,
            'timestamp': datetime.now()
        })
        self.categories[category].append(duration)

        self.prom_metric.labels(operation=name, category=category).set(duration)

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

def main():

    
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
        )
        sandbox_create_duration = time.time() - sandbox_create_start
        tracker.record("Sandbox creation", sandbox_create_duration, "setup")
        print(f"    ✓ took {sandbox_create_duration:.1f}s")

        instance_status = ""
        print("  → Waiting for instance creation...")
        instance_create_start = time.time()
        while instance_status == "":
            instance_status = get_instance_status(instances_api, sandbox.id)
            if instance_status == "":
                time.sleep(0.1)
        instance_create_duration = time.time() - instance_create_start
        tracker.record("instance creation", instance_create_duration, "setup")
        print(f"    ✓ took {instance_create_duration:.1f}s")

        print("  → Waiting for instance allocation...")
        instance_allocation_start = time.time()
        while instance_status not in ('InstanceStatus.STARTING', 'InstanceStatus.ALLOCATING', 'InstanceStatus.HEALTHY'):
            instance_status = get_instance_status(instances_api, sandbox.id)
            if instance_status == "":
                time.sleep(0.1)
        instance_allocation_duration = time.time() - instance_allocation_start
        tracker.record("instance allocation", instance_allocation_duration, "setup")
        print(f"    ✓ took {instance_allocation_duration:.1f}s")

        print("  → Waiting for instance to be started...")
        instance_starting_start = time.time()
        while instance_status not in ('InstanceStatus.STARTING', 'InstanceStatus.HEALTHY'):
            instance_status = get_instance_status(instances_api, sandbox.id)
            if instance_status == "":
                time.sleep(0.1)
        instance_starting_duration = time.time() - instance_starting_start
        tracker.record("instance starting", instance_starting_duration, "setup")
        print(f"    ✓ took {instance_starting_duration:.1f}s")

        # Check health with timing
        print("  → Checking sandbox health...")
        health_start = time.time()
        is_healthy = False
        while not is_healthy:
            is_healthy = sandbox.is_healthy()
            time.sleep(0.05)
        health_duration = time.time() - health_start
        tracker.record("Health check", health_duration, "monitoring")
        print(f"    ✓ took {health_duration:.1f}s")

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
            tracker.record("Sandbox deletion", delete_duration, "cleanup")
            print(f"    ✓ took {delete_duration:.1f}s")
        
        print("\n✓ All operations completed")
        
        # Print detailed recap
        tracker.print_recap()


if __name__ == "__main__":
    # 4. Start the Prometheus endpoint on port 7777
    print("Starting Prometheus metrics server on port 7777...")
    start_http_server(7777)
    while True:
        main()
        print("sleeping 5 minutes")
        time.sleep(300)
