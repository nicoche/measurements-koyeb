import time
import sys
import os
import requests
import koyeb
# --- CORRECTED IMPORTS ---
from koyeb.api.apps_api import AppsApi
from koyeb.api.services_api import ServicesApi
from koyeb.api.instances_api import InstancesApi
from koyeb.model.create_app import CreateApp
from koyeb.model.create_service import CreateService
from koyeb.model.deployment_definition import DeploymentDefinition
from koyeb.model.docker_source import DockerSource
from koyeb.model.deployment_port import DeploymentPort
from koyeb.model.deployment_route import DeploymentRoute
from prometheus_client import start_http_server, Gauge

# 1. Define the Prometheus Metric
# We use a Gauge to track the duration of the last successful run.
# This allows you to visualize "current performance" easily in Grafana.
TIME_TO_READY = Gauge(
    'time_to_publicly_ready', 
    'Time in seconds for a Koyeb Sandbox to become publicly accessible (HTTP 200)'
)

# --- Configuration ---
API_TOKEN = os.environ.get("KOYEB_API_TOKEN")
APP_NAME = "nginx-benchmark-app"
SERVICE_NAME = "nginx-service"
REGION = "fra"
PORT = 80

if not API_TOKEN:
    print("Error: Please set the KOYEB_TOKEN environment variable.")
    sys.exit(1)

def setup_client():
    configuration = koyeb.Configuration(
        host = "https://app.koyeb.com",
        api_key = {"Bearer": API_TOKEN}
    )
    return koyeb.ApiClient(configuration)

def measure_deployment(api_client):
    # Initialize API wrappers using the client
    app_api = AppsApi(api_client)
    service_api = ServicesApi(api_client)
    instance_api = InstancesApi(api_client)

    print(f"\n🚀 Starting Benchmark for Nginx on Region {REGION}...")

    # 1. Create App (Container for the service)
    try:
        print(f"   Creating App '{APP_NAME}'...")
        app_req = CreateApp(name=APP_NAME)
        app_resp = app_api.create_app(app=app_req)
        app_id = app_resp.app.id
    except koyeb.ApiException as e:
        # If app exists, we try to find it to reuse it
        if e.status == 400 or "already exists" in str(e).lower():
            print(f"   ℹ️  App '{APP_NAME}' likely already exists. Fetching ID...")
            # Ideally you would list apps to find the ID, but for simplicity:
            print("   ⚠️  Please delete the existing app manually or use a new name.")
            return
        else:
            print(f"❌ Error creating app: {e}")
            return

    # 2. Define and Create Service
    print(f"   Creating Service '{SERVICE_NAME}' (Nginx)...")

    definition = DeploymentDefinition(
        name=SERVICE_NAME,
        type="WEB",
        regions=[REGION],
        docker=DockerSource(image="nginx:latest"),
        ports=[DeploymentPort(port=PORT, protocol="http")],
        routes=[DeploymentRoute(path="/", port=PORT)]
    )

    create_service_req = CreateService(
        app_id=app_id,
        definition=definition
    )

    # --- MEASUREMENT START: Creation ---
    t_start_creation = time.time()

    try:
        service_resp = service_api.create_service(service=create_service_req)
        service_id = service_resp.service.id
    except koyeb.ApiException as e:
        print(f"❌ Error creating service: {e}")
        return

    t_end_creation = time.time()
    creation_duration = t_end_creation - t_start_creation
    print(f"   ✅ Service Object Created. ID: {service_id}")
    print(f"   ⏱️  API Call Duration: {creation_duration:.2f}s")

    # 3. Measure time to 'Allocating' state
    print("   Waiting for instance to reach 'ALLOCATING' state...")
    t_allocating_start = time.time()
    instance_allocating_time = None

    # Construct Public URL
    # App domain is usually: <app_name>-<org_name>.koyeb.app
    # We retrieve it from the App creation response
    public_domain = app_resp.app.domains[0].name
    public_url = f"https://{public_domain}"
    print(f"   🌍 Target URL: {public_url}")

    # Polling Loop
    while True:
        current_time = time.time()

        # Check Instances Status
        if instance_allocating_time is None:
            # List instances for this service
            inst_resp = instance_api.list_instances(service_id=service_id, limit=1)
            if inst_resp.instances:
                instance = inst_resp.instances[0]
                status = instance.status
                # We want to catch the first sign of activity (ALLOCATING, STARTING, etc)
                if status in ["ALLOCATING", "STARTING", "HEALTHY"]:
                    instance_allocating_time = current_time - t_end_creation
                    print(f"   ✅ Instance found in state: {status}")
                    print(f"   ⏱️  Time to 'Allocating': {instance_allocating_time:.2f}s")

        # Check Public URL Responsiveness
        if instance_allocating_time is not None:
            try:
                r = requests.get(public_url, timeout=2)
                if r.status_code == 200:
                    t_responsive_end = time.time()
                    total_responsive_time = t_responsive_end - t_end_creation
                    print(f"   ✅ App is responsive: {r.status_code} OK")
                    print(f"   ⏱️  Total Time to Live: {total_responsive_time:.2f}s")
                    break
            except requests.RequestException:
                # Still starting up, ignore connection errors
                pass

        time.sleep(1) # Poll every second

    print("\n--- 📊 Final Benchmark Results ---")
    print(f"1. API Creation Call:      {creation_duration:.4f} s")
    print(f"2. Instance Allocating:    {instance_allocating_time:.4f} s")
    print(f"3. App Responsive (200 OK): {total_responsive_time:.4f} s")

    # Cleanup Prompt
    delete = input("\nWould you like to delete the App and Service now? (y/n): ")
    if delete.lower() == 'y':
        print("Cleaning up...")
        service_api.delete_service(service_id)
        # We generally need to wait for service deletion before deleting the app,
        # or just delete the app (which cascades).
        print("Service deleting. Attempting to delete App (this might fail if service is not gone yet)...")
        time.sleep(2)
        try:
            app_api.delete_app(app_id)
            print("App deleted.")
        except Exception as e:
            print(f"Could not delete app immediately (standard behavior): {e}")
            print("Please delete 'nginx-benchmark-app' manually in the dashboard.")

if __name__ == "__main__":
    # Start the Prometheus endpoint on port 7777
    start_http_server(7777)
    print("Prometheus metrics server running on port 7777")

    client = setup_client()

    while True:
        measure_deployment(client)
        print("sleep 300s")
        time.sleep(300)
