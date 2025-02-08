Below is a comprehensive admin onboarding guide tailored to the FountainAI Eco System (repository: [Contexter/FountainAI-Eco-System](https://github.com/Contexter/FountainAI-Eco-System)) that explains how to set up and use Docker in a scenario where you build, test, and deploy your containers directly on a dedicated AWS Lightsail instance. This guide assumes you have basic Linux, Docker, and SSH knowledge.

---

# FountainAI Eco System Admin Onboarding Guide  
## Deploying and Managing Docker on an AWS Lightsail Instance

This guide walks you through configuring your AWS Lightsail instance to run Docker, setting up your local Docker environment to work remotely (using Docker contexts), and using the FountainAI Eco System repository for building and deploying containers directly on your production host.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Preparing Your Lightsail Instance](#preparing-your-lightsail-instance)
   - [1.1. Install Docker on Lightsail](#install-docker-on-lightsail)
   - [1.2. Configure Docker Permissions](#configure-docker-permissions)
4. [Setting Up SSH Access](#setting-up-ssh-access)
5. [Configuring Your Local Docker Environment](#configuring-your-local-docker-environment)
   - [3.1. Creating a Docker Context](#creating-a-docker-context)
   - [3.2. Switching Between Contexts](#switching-between-contexts)
6. [Working with the FountainAI Eco System Repository](#working-with-the-fountainai-eco-system-repository)
   - [4.1. Cloning the Repository](#cloning-the-repository)
   - [4.2. Building Docker Images Remotely](#building-docker-images-remotely)
   - [4.3. Running and Testing Containers](#running-and-testing-containers)
7. [Deployment Workflow & Best Practices](#deployment-workflow--best-practices)
8. [Troubleshooting & Security Considerations](#troubleshooting--security-considerations)
9. [Additional Resources](#additional-resources)

---

## Overview

In this setup, your local Docker Desktop controls a Docker Engine running on your dedicated AWS Lightsail instance. This means that every Docker command—whether building images, running containers, or managing deployments—executes directly on the remote host. By doing so, you build and deploy the FountainAI Eco System (found in [Contexter/FountainAI-Eco-System](https://github.com/Contexter/FountainAI-Eco-System)) without an intermediary image registry.

**Key benefits include:**

- **Direct Deployment:** Build, test, and run containers on the same Lightsail machine.
- **Streamlined Workflow:** Eliminate extra steps (e.g., pushing to/pulling from a registry) if you only deploy to one host.
- **Consistency:** Ensure that both testing and production occur in the same environment.

---

## Prerequisites

- **Local Machine Requirements:**
  - Docker Desktop installed and running.
  - An SSH client.
  - Familiarity with command-line operations.

- **Lightsail Instance Requirements:**
  - A dedicated AWS Lightsail instance (running Ubuntu or another supported Linux distribution).
  - SSH access configured (preferably with key-based authentication).
  - Administrative privileges for installing software and configuring Docker.

---

## Preparing Your Lightsail Instance

### 1.1. Install Docker on Lightsail

1. **SSH into your Lightsail instance:**

   ```bash
   ssh ubuntu@<YOUR_LIGHTSAIL_IP>
   ```

   Replace `<YOUR_LIGHTSAIL_IP>` with the public IP of your Lightsail instance. (Change the username if needed.)

2. **Update your package index:**

   ```bash
   sudo apt-get update
   ```

3. **Install prerequisites:**

   ```bash
   sudo apt-get install ca-certificates curl gnupg lsb-release
   ```

4. **Add Docker’s official GPG key and set up the repository:**

   ```bash
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

   echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   ```

5. **Install Docker Engine:**

   ```bash
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io
   ```

### 1.2. Configure Docker Permissions

To run Docker commands without `sudo`:

1. **Add your user to the Docker group:**

   ```bash
   sudo usermod -aG docker $USER
   ```

2. **Restart your SSH session:**  
   Log out and log back in (or reboot the instance) so that the group membership is updated.

---

## Setting Up SSH Access

Ensure you can SSH into your Lightsail instance from your local machine:

```bash
ssh ubuntu@<YOUR_LIGHTSAIL_IP>
```

**Tips:**

- Use key-based authentication to avoid repeated password prompts.
- Confirm that your SSH keys are properly configured on both your local machine and the Lightsail instance (i.e., your public key is in `~/.ssh/authorized_keys` on the Lightsail instance).

---

## Configuring Your Local Docker Environment

Docker contexts let you switch between your local Docker engine and a remote Docker engine seamlessly.

### 3.1. Creating a Docker Context

1. **Open your local terminal and create a context for Lightsail:**

   ```bash
   docker context create lightsail \
     --description "Docker on AWS Lightsail for FountainAI Eco System" \
     --docker "host=ssh://ubuntu@<YOUR_LIGHTSAIL_IP>"
   ```

   Replace `<YOUR_LIGHTSAIL_IP>` with your Lightsail instance’s IP address and adjust the username if needed.

2. **Verify the context:**

   ```bash
   docker context ls
   ```

   You should see an entry named `lightsail` along with your default (local) context.

### 3.2. Switching Between Contexts

- **Switch to the Lightsail context:**

  ```bash
  docker context use lightsail
  ```

  Now every Docker command you run will execute on your remote Lightsail instance.

- **Return to your local Docker engine when needed:**

  ```bash
  docker context use default
  ```

---

## Working with the FountainAI Eco System Repository

This section outlines how to clone the FountainAI Eco System repository, build its Docker image remotely, and run the container for testing and deployment.

### 4.1. Cloning the Repository

On your local machine, clone the repository:

```bash
git clone https://github.com/Contexter/FountainAI-Eco-System.git
cd FountainAI-Eco-System
```

This repository contains all the necessary configuration (e.g., Dockerfile, source code, deployment scripts) for the FountainAI Eco System.

### 4.2. Building Docker Images Remotely

With your Docker context set to `lightsail`, navigate to the repository’s root directory (where the `Dockerfile` is located) and run:

```bash
docker build -t fountainai-app:latest .
```

This command will execute on your Lightsail instance, building the Docker image directly on the production host.

### 4.3. Running and Testing Containers

To test the deployment, run the container on your Lightsail instance. For example, if your application serves on port 80:

```bash
docker run --rm -p 80:80 fountainai-app:latest
```

- **Testing:**  
  Access your application via your Lightsail instance’s public IP (e.g., [http://<YOUR_LIGHTSAIL_IP>](http://<YOUR_LIGHTSAIL_IP>)).

- **Managing Containers:**  
  Use `docker ps` to list running containers and `docker logs <container_id>` to view logs.

---

## Deployment Workflow & Best Practices

- **Local Development & Remote Builds:**  
  With Docker contexts, you can develop locally and then switch to the Lightsail context to build and deploy, ensuring that the build environment is identical to your production environment.

- **Version Control:**  
  Use Git and tags in your Docker images (e.g., `fountainai-app:v1.0.0`) so that you can roll back if needed.

- **Automation:**  
  Consider integrating scripts or CI/CD pipelines that use Docker contexts to automate the build and deployment process directly on your Lightsail instance.

- **Monitoring & Logging:**  
  Implement logging and monitoring solutions on your Lightsail instance to keep track of container health and performance.

---

## Troubleshooting & Security Considerations

- **SSH & Docker Context Issues:**  
  Ensure that your SSH keys and network configurations are correct. Use verbose SSH mode (e.g., `ssh -v`) for debugging connection issues.

- **Security:**  
  - Use strong SSH keys and change default credentials.  
  - Secure your Lightsail instance with firewall rules and restrict access to the Docker API.
  - Regularly update Docker and your system to patch vulnerabilities.

- **Resource Management:**  
  Monitor your Lightsail instance’s resources (CPU, memory, disk) to ensure that container builds and runs do not exhaust available resources.

---

## Additional Resources

- [Docker Context Documentation](https://docs.docker.com/engine/context/working-with-contexts/)
- [Docker Remote API over SSH](https://docs.docker.com/engine/security/https/)
- [AWS Lightsail Documentation](https://lightsail.aws.amazon.com/)
- [FountainAI Eco System Repository](https://github.com/Contexter/FountainAI-Eco-System)

---

By following this guide, administrators for the FountainAI Eco System can set up a robust and streamlined workflow that leverages Docker’s remote capabilities. This approach builds and deploys containerized applications directly on your dedicated AWS Lightsail instance, ensuring consistency between testing and production environments.

If you have any questions or need further assistance, please refer to the additional resources or contact your system administrator. Enjoy your streamlined deployment process!