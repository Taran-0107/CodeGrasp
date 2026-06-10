import urllib.parse
import requests
from app.config import GITLAB_API_URL, GITLAB_PRIVATE_TOKEN, MOCK_GITLAB_API
from app.utils.logger import logger

class GitLabService:
    def __init__(self):
        self.headers = {}
        if GITLAB_PRIVATE_TOKEN:
            self.headers["PRIVATE-TOKEN"] = GITLAB_PRIVATE_TOKEN
        self.api_url = GITLAB_API_URL

    def get_mr_changes(self, project_id: int, mr_iid: int) -> list[dict]:
        """
        Fetches the files changed in the merge request.
        If MOCK_GITLAB_API is True, returns simulated changed files.
        """
        if MOCK_GITLAB_API:
            logger.info("[Mock Mode] Simulating GitLab Merge Request changes API response.")
            return [
                {
                    "old_path": "example_math.py",
                    "new_path": "example_math.py",
                    "new_file": False,
                    "renamed_file": False,
                    "deleted_file": False,
                    "diff": (
                        "--- a/example_math.py\n"
                        "+++ b/example_math.py\n"
                        "@@ -10,6 +10,8 @@\n"
                        "     def multiply(self, a, b):\n"
                        "-        result = a * b\n"
                        "-        return result\n"
                        "+        result = a * b\n"
                        "+        self.history.append(f\"Multiply: {a} * {b} = {result}\")\n"
                        "+        return result\n"
                    )
                }
            ]

        url = f"{self.api_url}/projects/{project_id}/merge_requests/{mr_iid}/changes"
        logger.info(f"Fetching MR changes from: {url}")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("changes", [])
        except Exception as e:
            logger.error(f"Error fetching MR changes from GitLab: {e}")
            raise

    def get_file_content(self, project_id: int, file_path: str, ref: str) -> bytes:
        """
        Retrieves the raw content of a specific file from the repository at a given ref/commit SHA.
        If MOCK_GITLAB_API is True, returns simulated Python source code content.
        """
        if MOCK_GITLAB_API:
            logger.info(f"[Mock Mode] Simulating GitLab file content API response for: {file_path}")
            # Mock python code containing Calculator class and some functions
            mock_code = (
                "import math\n"
                "\n"
                "class Calculator:\n"
                "    def __init__(self):\n"
                "        self.history = []\n"
                "\n"
                "    def add(self, a, b):\n"
                "        result = a + b\n"
                "        self.history.append(f\"Add: {a} + {b} = {result}\")\n"
                "        return result\n"
                "\n"
                "    def multiply(self, a, b):\n"
                "        result = a * b\n"
                "        self.history.append(f\"Multiply: {a} * {b} = {result}\")\n"
                "        return result\n"
                "\n"
                "def calculate_average(numbers):\n"
                "    total = sum(numbers)\n"
                "    count = len(numbers)\n"
                "    return total / count\n"
            )
            return mock_code.encode("utf-8")

        encoded_path = urllib.parse.quote(file_path, safe="")
        url = f"{self.api_url}/projects/{project_id}/repository/files/{encoded_path}/raw?ref={ref}"
        logger.info(f"Fetching file content from: {url}")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Error fetching file content from GitLab: {e}")
            raise

    @staticmethod
    def parse_changed_lines(diff_content: str) -> set[int]:
        """
        Parses a unified diff and returns a set of 1-indexed line numbers in the new file 
        that were added or modified in the MR.
        """
        changed_lines = set()
        if not diff_content:
            return changed_lines

        current_line = 0
        for line in diff_content.splitlines():
            if line.startswith("@@"):
                # Header example: @@ -10,4 +12,6 @@
                parts = line.split()
                if len(parts) >= 3:
                    new_file_range = parts[2]  # "+12,6" or "+12"
                    if new_file_range.startswith("+"):
                        new_file_range = new_file_range[1:]
                    if "," in new_file_range:
                        start_str, _ = new_file_range.split(",")
                    else:
                        start_str = new_file_range
                    try:
                        current_line = int(start_str)
                    except ValueError:
                        pass
            elif line.startswith("+") and not line.startswith("+++"):
                changed_lines.add(current_line)
                current_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                # Removed lines don't exist in the new file version
                pass
            else:
                # Unchanged context lines
                current_line += 1

        return changed_lines
