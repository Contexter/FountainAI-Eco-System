import os
from collections import defaultdict

# Define the path to the services (relative to repo root)
SERVICES_DIR = os.getcwd()
REPORT_FILE = "env_dependency_report.md"

def get_env_files():
    """Finds all services with and without .env files."""
    services = [d for d in os.listdir(SERVICES_DIR) if os.path.isdir(d)]
    env_files = {s: os.path.join(SERVICES_DIR, s, ".env") for s in services}
    
    existing_env_files = {s: f for s, f in env_files.items() if os.path.exists(f)}
    return existing_env_files

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

def analyze_dependencies(existing_env_files):
    """Analyzes dependencies between services based on environment variables."""
    env_data = {}
    service_dependencies = defaultdict(set)

    for service, env_file in existing_env_files.items():
        env_data[service] = parse_env_file(env_file)

    # Identify dependencies based on variable values containing service names
    for service, vars_dict in env_data.items():
        for key, value in vars_dict.items():
            for other_service in env_data.keys():
                if other_service in value and other_service != service:
                    service_dependencies[service].add(other_service)

    return service_dependencies

def detect_circular_dependency(service_dependencies):
    """Detects and logs circular dependencies."""
    visited = set()
    stack = set()

    def visit(service, path):
        if service in stack:
            return path + [service]  # Circular dependency detected
        if service in visited:
            return None  # Already processed
        
        stack.add(service)
        visited.add(service)
        
        for dep in list(service_dependencies.get(service, [])):  # Copy keys before iterating
            cycle = visit(dep, path + [service])
            if cycle:
                return cycle
        
        stack.remove(service)
        return None

    for service in list(service_dependencies.keys()):  # Copy dictionary keys before iteration
        cycle = visit(service, [])
        if cycle:
            return cycle  # Return the detected cycle
    
    return None

def determine_deployment_order(service_dependencies):
    """Determines the correct order to deploy services based on dependencies."""
    deployment_order = []
    remaining_services = set(service_dependencies.keys())

    while remaining_services:
        independent_services = [s for s in remaining_services if not service_dependencies[s]]

        if not independent_services:
            return None  # Circular dependency detected

        deployment_order.extend(independent_services)

        # Remove deployed services from dependency lists
        for deployed in independent_services:
            remaining_services.remove(deployed)
            for deps in service_dependencies.values():
                deps.discard(deployed)

    return deployment_order

def generate_markdown_report(service_dependencies, deployment_order, circular_dependency):
    """Generates a Markdown report summarizing the dependency analysis."""
    with open(REPORT_FILE, "w") as md:
        md.write("# FountainAI Service Dependency Report\n\n")

        md.write("## 🔗 Detected Service Dependencies\n")
        for service, dependencies in service_dependencies.items():
            if dependencies:
                md.write(f"- **{service}** depends on: {', '.join(dependencies)}\n")
        
        if circular_dependency:
            md.write("\n## ❌ Circular Dependency Detected!\n")
            md.write("A cycle exists in the dependencies:\n")
            md.write(" → ".join(circular_dependency) + "\n")
            md.write("\n🚨 **This prevents correct deployment!**\n")
        else:
            md.write("\n## 🚀 Recommended Deployment Order\n")
            if deployment_order:
                for index, service in enumerate(deployment_order, start=1):
                    md.write(f"{index}. **{service}**\n")
            else:
                md.write("⚠️ **No valid deployment order found.** Possible dependency issue.\n")

        md.write("\n## 🎯 Key Takeaways\n")
        md.write("- Always deploy services **without dependencies first**.\n")
        md.write("- Ensure dependent services are available **before deploying**.\n")
        md.write("- **If a circular dependency is detected, manual intervention is needed!**\n")

if __name__ == "__main__":
    existing_env_files = get_env_files()
    service_dependencies = analyze_dependencies(existing_env_files)
    
    circular_dependency = detect_circular_dependency(service_dependencies)
    
    if circular_dependency:
        print(f"❌ Circular dependency detected! {circular_dependency}")
        deployment_order = None
    else:
        deployment_order = determine_deployment_order(service_dependencies)
    
    generate_markdown_report(service_dependencies, deployment_order, circular_dependency)

    print(f"✅ Analysis complete! Report saved to `{REPORT_FILE}`.")
