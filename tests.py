import os
import sys
import subprocess
import json
import logging
from logging.handlers import RotatingFileHandler
import tempfile
import re
import requests

# Load configuration
def load_config():
    try:
        with open("config.json") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

# Setup logging
def setup_logging(log_path):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File handler
    file_handler = RotatingFileHandler(log_path, maxBytes=3 * 1024 * 1024, backupCount=2)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Run shell commands
def run_command(command, cwd=None):
    logging.info(f"Running command: {command}")
    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True, cwd=cwd)
        if result.returncode != 0:
            logging.warning(f"Command failed: {result.stderr.strip()}")
        return result
    except Exception as e:
        logging.error(f"Error running command: {e}")
        sys.exit(1)

# Clone or pull repo and checkout branch
def setup_repository(repo_url, branch, local_path):
    if not os.path.exists(local_path):
        logging.info("Cloning repository...")
        run_command(f"git clone {repo_url} {local_path}")
    else:
        logging.info("Repository already cloned. Pulling latest changes...")
        run_command("git fetch", cwd=local_path)

    run_command(f"git checkout {branch}", cwd=local_path)
    run_command("git pull", cwd=local_path)

# Parse pytest results for failed test cases
def parse_pytest_output(output):
    failures = []
    pattern = re.compile(r"________+ ([^\s]+) ________+.*?FAILED\s+(.*)", re.DOTALL)
    matches = pattern.findall(output)
    for match in matches:
        test_name, reason = match
        failures.append((test_name.strip(), reason.strip()))
    return failures

# Create GitHub issue
def create_github_issue(repo_owner, repo_name, title, body):
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        logging.error("GITHUB_TOKEN not set in environment variables.")
        return

    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"title": title, "body": body}
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 201:
        logging.info(f"Issue created: {title}")
    else:
        logging.error(f"Failed to create issue: {response.text}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_tests.py <branch-name>")
        sys.exit(1)

    branch = sys.argv[1]
    config = load_config()
    setup_logging(config["log_file"])

    logging.info("=== Script Started ===")
    try:
        setup_repository(config["repository"], branch, config["local_repo_path"])

        logging.info("Running pytest...")
        result = run_command("pytest -v", cwd=config["local_repo_path"])
        if result.returncode != 0:
            failures = parse_pytest_output(result.stdout + result.stderr)
            repo_owner = config["repository"].split("/")[-2]
            repo_name = config["repository"].split("/")[-1].replace(".git", "")

            for test_name, reason in failures:
                title = f"Test failure: {test_name}"
                body = f"Branch: `{branch}`\n\nFailure Reason:\n```\n{reason}\n```"
                create_github_issue(repo_owner, repo_name, title, body)
        else:
            logging.info("All tests passed successfully.")

    except Exception as e:
        logging.exception("Unexpected error occurred.")
    finally:
        logging.info("=== Script Ended ===")

if __name__ == "__main__":
    main()
