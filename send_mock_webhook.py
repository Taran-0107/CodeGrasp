import sys
import requests

def send_mock_webhook():
    url = "http://127.0.0.1:8000/webhook/gitlab"
    headers = {
        "Content-Type": "application/json",
        "X-Gitlab-Event": "Merge Request Hook",
        "X-Gitlab-Token": "super-secret-webhook-token"
    }

    # Simulated Merge Request Hook JSON payload from GitLab
    payload = {
        "object_kind": "merge_request",
        "project": {
            "id": 4123,
            "name": "semantic-intelligence-engine",
            "path_with_namespace": "ai-ops/semantic-intelligence-engine",
            "web_url": "https://gitlab.com/ai-ops/semantic-intelligence-engine"
        },
        "object_attributes": {
            "id": 9876,
            "iid": 42,
            "source_project_id": 4123,
            "target_project_id": 4123,
            "source_branch": "feature/parser-core",
            "target_branch": "main",
            "title": "Implement tree-sitter core parsing engine",
            "state": "opened",
            "last_commit": {
                "id": "abc123commitsha"
            }
        }
    }

    print(f"Sending POST request to: {url}")
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Response Status Code: {response.status_code}")
        print("Response JSON:")
        print(response.json())
    except Exception as e:
        print(f"Failed to connect to the server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    send_mock_webhook()
