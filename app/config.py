import os

# Webhook authentication
GITLAB_WEBHOOK_TOKEN = os.getenv("GITLAB_WEBHOOK_TOKEN", "super-secret-webhook-token")

# GitLab API integration
GITLAB_PRIVATE_TOKEN = os.getenv("GITLAB_PRIVATE_TOKEN", "")
GITLAB_API_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")

# Elasticsearch connection
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

# Local testing switches
# Set this to True to bypass actual GitLab REST API calls and return mock diffs and file content
MOCK_GITLAB_API = os.getenv("MOCK_GITLAB_API", "True").lower() in ("true", "1", "yes")
