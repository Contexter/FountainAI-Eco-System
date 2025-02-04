#!/usr/bin/env python3
import os
import re
import yaml

def get_exposed_port(dockerfile_path):
    """
    Reads the Dockerfile at dockerfile_path and returns the port declared in the EXPOSE directive.
    """
    with open(dockerfile_path, "r") as f:
        content = f.read()
    match = re.search(r'EXPOSE\s+(\d+)', content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def scan_services(root_dir):
    """
    Scans each subdirectory in root_dir for a Dockerfile and returns a mapping:
      { service_directory: exposed_port, ... }
    """
    services_ports = {}
    for item in os.listdir(root_dir):
        service_path = os.path.join(root_dir, item)
        dockerfile_path = os.path.join(service_path, "Dockerfile")
        if os.path.isdir(service_path) and os.path.isfile(dockerfile_path):
            exposed_port = get_exposed_port(dockerfile_path)
            if exposed_port:
                services_ports[item] = exposed_port
    return services_ports

def update_docker_compose(compose_file, services_ports):
    """
    Loads the docker-compose.yml, updates the ports mapping for each service based on the
    exposed port from its Dockerfile, and writes out the updated file.
    """
    with open(compose_file, "r") as f:
        compose_data = yaml.safe_load(f)

    services = compose_data.get("services", {})
    updated = False

    for service_name, service_config in services.items():
        build_path = service_config.get("build")
        if build_path and build_path.startswith("./"):
            # Extract the service directory name from the build path.
            service_dir = build_path[2:]
            expected_port = services_ports.get(service_dir)
            if expected_port:
                ports = service_config.get("ports")
                if ports and isinstance(ports, list) and len(ports) > 0:
                    # Assume the first mapping is in the form "host_port:container_port"
                    mapping = ports[0]
                    if isinstance(mapping, str):
                        parts = mapping.split(":")
                        if len(parts) == 2:
                            host_port, container_port = parts
                            if container_port != expected_port:
                                print(f"Updating service '{service_name}' (dir: {service_dir}): container port {container_port} -> {expected_port}")
                                ports[0] = f"{host_port}:{expected_port}"
                                updated = True
                    else:
                        print(f"Unexpected ports mapping format for service '{service_name}': {mapping}")
                else:
                    # No ports mapping exists – add one mapping host port = container port.
                    print(f"Service '{service_name}' (dir: {service_dir}) has no ports mapping. Adding mapping {expected_port}:{expected_port}.")
                    service_config["ports"] = [f"{expected_port}:{expected_port}"]
                    updated = True

    if updated:
        with open(compose_file, "w") as f:
            yaml.dump(compose_data, f, default_flow_style=False)
        print(f"Docker Compose file '{compose_file}' updated.")
    else:
        print("No updates required in Docker Compose file.")

if __name__ == "__main__":
    root_dir = "."
    compose_file = "docker-compose.yml"
    print("Scanning services for Dockerfile EXPOSE ports...")
    services_ports = scan_services(root_dir)
    for service, port in services_ports.items():
        print(f"  {service}: {port}")
    
    print("\nUpdating docker-compose.yml with correct port mappings...")
    update_docker_compose(compose_file, services_ports)

