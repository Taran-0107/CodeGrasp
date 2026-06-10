import sys
import os

# Dynamic path resolution to allow direct script execution (e.g. `python app/main.py`)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import GITLAB_WEBHOOK_TOKEN
from app.services.gitlab_service import GitLabService
from app.services.parser_service import ParserService
from app.services.elasticsearch_service import ElasticsearchService
from app.utils.logger import logger

# Initialize services
gitlab_service = GitLabService()
es_service = ElasticsearchService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Elasticsearch index on startup
    logger.info("Initializing services on startup...")
    es_service.initialize_index()
    yield
    logger.info("Shutting down application...")

app = FastAPI(
    title="Semantic Engineering Intelligence Ingestion Service",
    description="Phase 1 - Code Parsing & Ingestion Service",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/webhook/gitlab", status_code=status.HTTP_200_OK)
async def gitlab_webhook(
    request: Request,
    x_gitlab_event: str = Header(None, alias="X-Gitlab-Event"),
    x_gitlab_token: str = Header(None, alias="X-Gitlab-Token")
):
    # 1. Webhook Validation
    if not x_gitlab_event:
        logger.warning("Missing X-Gitlab-Event header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Gitlab-Event header"
        )
    
    if x_gitlab_event != "Merge Request Hook":
        logger.warning(f"Unsupported event type: {x_gitlab_event}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported event type. Only 'Merge Request Hook' is supported."
        )

    if GITLAB_WEBHOOK_TOKEN and x_gitlab_token != GITLAB_WEBHOOK_TOKEN:
        logger.warning("Unauthorized GitLab webhook token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token"
        )

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON"
        )

    object_kind = payload.get("object_kind")
    if object_kind != "merge_request":
        logger.warning(f"Unexpected object_kind in payload: {object_kind}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event payload. Object kind must be 'merge_request'."
        )

    # Extract project and MR metadata
    project = payload.get("project", {})
    project_id = project.get("id")
    repo_name = project.get("path_with_namespace") or project.get("name")
    
    object_attributes = payload.get("object_attributes", {})
    mr_iid = object_attributes.get("iid")
    last_commit = object_attributes.get("last_commit", {})
    commit_sha = last_commit.get("id")

    if not project_id or not mr_iid or not commit_sha:
        logger.error("Missing critical MR identifiers in webhook payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook payload is missing project_id, merge_request iid, or commit sha."
        )

    logger.info(f"Processing Merge Request event for project {project_id} (Repo: {repo_name}), MR IID: {mr_iid}")

    try:
        _mock_data = payload.get("_mock_data")
        
        processed_entities_count = 0
        indexed_entities_count = 0
        debug_entities = []
        changed_lines_list = []

        if _mock_data:
            logger.info("Using frontend custom mock data payload.")
            changes = [{
                "new_path": _mock_data.get("file_path", "example_math.py"),
                "diff": _mock_data.get("diff", ""),
                "deleted_file": False
            }]
        else:
            changes = gitlab_service.get_mr_changes(project_id, mr_iid)

        for change in changes:
            if change.get("deleted_file", False):
                logger.info(f"Skipping deleted file: {change.get('old_path')}")
                continue

            file_path = change.get("new_path")
            diff_content = change.get("diff")

            # Only process files for supported languages (initially python/ts)
            if not file_path or not file_path.endswith((".py", ".js", ".ts")):
                logger.info(f"Skipping unsupported file extension: {file_path}")
                continue

            logger.info(f"Parsing changed file: {file_path}")

            # Retrieve raw source code
            if _mock_data:
                raw_code = _mock_data.get("raw_code", "").encode("utf-8")
            else:
                raw_code = gitlab_service.get_file_content(project_id, file_path, commit_sha)

            # Determine changed lines in this file version
            changed_lines = gitlab_service.parse_changed_lines(diff_content)
            changed_lines_list = list(changed_lines)
            logger.info(f"Detected modified line numbers in new version of {file_path}: {changed_lines_list}")

            # 3 & 4. AST Generation and Entity Extraction
            lang_name = "python"
            if file_path.endswith((".js", ".ts")):
                logger.warning(f"File {file_path} is Javascript/Typescript. Skipping parsing in this iteration.")
                continue

            entities = ParserService.extract_entities(raw_code, file_path, lang_name)
            debug_entities.extend(entities)
            
            # Log all extracted AST entities to console
            logger.info(f"--- Extracted {len(entities)} AST Entities from {file_path} ---")
            for ent in entities:
                logger.info(
                    f"Entity: [{ent['entity_type']}] Name: '{ent['entity_name']}' "
                    f"Lines: {ent['start_line']}-{ent['end_line']} "
                    f"Deps: {ent['dependencies']}"
                )

            # 5 & 6. Data Transformation and Indexing
            for ent in entities:
                processed_entities_count += 1
                
                # Check if this entity's line range overlaps with the changed lines in the diff
                entity_range = set(range(ent["start_line"], ent["end_line"] + 1))
                is_modified = bool(entity_range.intersection(changed_lines))

                if is_modified:
                    # Flat Elasticsearch JSON Schema
                    entity_name = ent["entity_name"]
                    entity_id = f"{repo_name}:{file_path}:{entity_name}"
                    
                    doc = {
                        "entity_id": entity_id,
                        "repository": repo_name,
                        "file_path": file_path,
                        "entity_type": ent["entity_type"],
                        "entity_name": entity_name,
                        "code_snippet": ent["code_snippet"],
                        "dependencies": ent["dependencies"],
                        "mr_context": str(mr_iid)
                    }

                    # Index document into Elasticsearch
                    success = es_service.index_entity(entity_id, doc)
                    if success:
                        indexed_entities_count += 1
                else:
                    logger.info(f"Entity '{ent['entity_name']}' was not modified in this MR. Skipping indexing.")

        return {
            "status": "success",
            "message": "GitLab webhook processed successfully",
            "processed_entities": processed_entities_count,
            "indexed_entities": indexed_entities_count,
            "debug_entities": debug_entities,
            "changed_lines": changed_lines_list
        }

    except Exception as e:
        logger.error(f"Error handling webhook logic: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
