# **FountainAI Ecosystem: Admin Onboarding Guide**

*Version: 1.1*  
*Date: February 6, 2025*

---

## **1. Introduction**

Welcome to the FountainAI Ecosystem! This guide is designed to assist administrators in effectively managing and navigating the FountainAI-Eco-System repository. It provides an overview of the repository structure, details on existing Python scripts, and instructions on how to utilize these scripts within a Dockerized environment for consistent and efficient operations.

---

## **2. Running Scripts Within a Docker Container**

To ensure consistency and avoid dependency issues, we utilize Docker to manage the execution environment for our scripts. Docker allows us to package applications and their dependencies into a standardized unit, ensuring that they run seamlessly across different environments.

### 2.1. Building a Docker Image

A Docker image is a lightweight, standalone, and executable software package that includes everything needed to run a piece of software, including the code, runtime, libraries, and system tools.

**Steps to Build a Docker Image:**

1. **Create a Dockerfile:** This file contains a series of instructions on how to build the Docker image. For example:

    ```dockerfile
    # Use an official Python runtime as a parent image
    FROM python:3.9-slim

    # Set the working directory in the container
    WORKDIR /app

    # Copy the current directory contents into the container at /app
    COPY . /app

    # Install any needed packages specified in requirements.txt
    RUN pip install --no-cache-dir -r requirements.txt

    # Make port 80 available to the world outside this container
    EXPOSE 80

    # Define environment variable
    ENV NAME World

    # Run app.py when the container launches
    CMD ["python", "app.py"]
    ```

2. **Build the Image:** Navigate to the directory containing the Dockerfile and run:

    ```bash
    docker build -t your-image-name .
    ```

    This command builds the image using the instructions in the Dockerfile and tags it as `your-image-name`.

### 2.2. Running a Container from the Image

Once the image is built, you can run a container based on that image.

**Command:**

```bash
docker run -it --rm --name your-container-name your-image-name
```

- `-it`: Runs the container in interactive mode with a terminal.
- `--rm`: Automatically removes the container when it exits.
- `--name`: Assigns a name to the container.
- `your-image-name`: The name of the image to use.

### 2.3. Executing Scripts Inside the Container

There are multiple ways to execute scripts within a Docker container:

1. **During Container Startup:** You can specify the script to run when the container starts by setting the `CMD` or `ENTRYPOINT` in the Dockerfile.

2. **Using `docker exec`:** If the container is already running, you can execute a script inside it using:

    ```bash
    docker exec -it your-container-name /bin/bash -c "your-script.sh"
    ```

    Replace `your-container-name` with the name of your running container and `your-script.sh` with the path to your script inside the container.

3. **Piping a Script into the Container:** You can also pipe a script from your host machine into the container:

    ```bash
    cat your-script.sh | docker exec -i your-container-name /bin/bash
    ```

    This command sends the contents of `your-script.sh` into the container's bash shell.

**Note:** Ensure that the script has the necessary execute permissions and that any required dependencies are installed within the container.

---

## **3. Repository Overview**

The FountainAI-Eco-System repository is structured to facilitate the development and deployment of various services within the FountainAI ecosystem. Below is a snapshot of the repository structure as of February 6, 2025:

```
FountainAI-Eco-System/
├── Dockerfile
├── README.md
├── caddyfile2BatchManageRoute53.py
├── update_route53.py
└── ...
```

**Note:** This structure is subject to change as the project evolves. Always refer to the latest version of the repository for the most up-to-date information.

---

## **4. Python Scripts Index**

At the root of the repository, you will find several Python scripts designed to assist with various administrative tasks. Below is an index of the current scripts:

1. **`caddyfile2BatchManageRoute53.py`**
   - **Purpose:** Parses a Caddyfile to extract subdomains and generates a JSON batch file for updating DNS records in AWS Route 53.
   - **Usage:** Helps automate the synchronization between your Caddy server configurations and Route 53 DNS records.

2. **`update_route53.py`**
   - **Purpose:** Reads a JSON batch file and applies the changes to AWS Route 53, facilitating bulk updates to DNS records.
   - **Usage:** Streamlines the process of updating DNS records by applying predefined changes in a controlled manner.

---

## **5. Setting Up the Environment**

To ensure consistency and avoid dependency issues, we utilize Docker to manage the execution environment for our Python scripts.

### 5.1. Prerequisites

- **Docker:** Ensure Docker is installed on your system. You can download it from [Docker's official website](https://www.docker.com/get-started).

### 5.2. Docker Configuration

A `Dockerfile` is present at the root of the repository to set up the necessary environment:

```dockerfile
# Use an official minimal Python base image
FROM python:3.9-slim

# Install required Python packages
RUN pip install --no-cache-dir boto3 awscli

# Set the working directory inside the container
WORKDIR /app

# Copy all files from the current directory into /app inside the container
COPY . /app

# Set the default command to bash
CMD ["bash"]
```

This Dockerfile performs the following actions:

- **Base Image:** Utilizes a slim version of Python 3.9.
- **Dependencies:** Installs `boto3` and `awscli` Python packages.
- **Working Directory:** Sets `/app` as the working directory within the container.
- **File Copy:** Copies all files from the current directory into the container's `/app` directory.
- **Default Command:** Sets the default command to `bash` for interactive use.

### 5.3. Building the Docker Image

To build the Docker image, navigate to the root of the repository and execute:

```bash
docker build -t fountainai/dns-scripts:latest .
```

This command creates a Docker image named `fountainai/dns-scripts` with the `latest` tag.



## **6. Running Python Scripts Using Docker**

With the Docker environment set up, you can run the Python scripts as needed.

### 6.1. Running `caddyfile2BatchManageRoute53.py`

This script parses the `Caddyfile` and generates a JSON batch file for Route 53.

**Command:**

```bash
docker run --rm \
    -v $(pwd):/app \
    fountainai/dns-scripts:latest \
    python caddyfile2BatchManageRoute53.py
```

**Explanation:**

- `docker run`: Runs a new container.
- `--rm`: Automatically removes the container once it exits.
- `-v $(pwd):/app`: Mounts the current directory (`$(pwd)`) to `/app` inside the container.
- `fountainai/dns-scripts:latest`: Specifies the Docker image to use.
- `python caddyfile2BatchManageRoute53.py`: Executes the script inside the container.

**Note:** Ensure that the `Caddyfile` is present in the current directory when running this command.

### 6.2. Running `update_route53.py`

This script reads a JSON batch file and applies the changes to AWS Route 53.

**Command:**

```bash
docker run --rm \
    -v $(pwd):/app \
    -e AWS_ACCESS_KEY_ID=your_access_key_id \
    -e AWS_SECRET_ACCESS_KEY=your_secret_access_key \
    fountainai/dns-scripts:latest \
    python update_route53.py
```

**Explanation:**

- `-e AWS_ACCESS_KEY_ID=your_access_key_id`: Sets the AWS access key ID as an environment variable.
- `-e AWS_SECRET_ACCESS_KEY=your_secret_access_key`: Sets the AWS secret access key as an environment variable.

**Note:** Replace `your_access_key_id` and `your_secret_access_key` with your actual AWS credentials. Ensure that the JSON batch file (`change-batch.json`) is present in the current directory.

---

## **7. Best Practices**

To maintain a consistent and secure environment:

- **Version Control:** Keep all scripts under version control using Git. This practice allows for tracking changes and collaborative development.
- **Environment Variables:** Avoid hardcoding sensitive information, such as AWS credentials, in your scripts. Instead, use environment variables or AWS IAM roles for authentication.
- **Testing:** Before applying any changes to production systems, thoroughly test your scripts in a controlled environment to prevent unintended consequences.
- **Documentation:** Maintain up-to-date documentation for each script, detailing its purpose, usage, and any prerequisites. This practice ensures that team members can effectively utilize and maintain the scripts.

---

## **8. Troubleshooting**

If you encounter issues:

- **Docker Issues:** Ensure Docker is running correctly on your system. Verify that the Docker image builds without errors and that containers start as expected.
- **Script Errors:** Check for syntax errors or missing dependencies in your Python scripts. Ensure that all required modules are installed and that the scripts are compatible with the Python version specified in the Docker image.
- **AWS Authentication:** Verify that your AWS credentials are correct and have the necessary permissions to perform the desired actions in Route 53.

---

## **9. Conclusion**

This onboarding guide provides a comprehensive overview of administering the FountainAI Ecosystem repository and effectively utilizing its Python scripts within a Dockerized environment. By following the practices outlined herein, you can ensure a consistent, secure, and efficient workflow for managing the repository's resources.
