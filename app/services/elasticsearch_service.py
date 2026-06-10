from elasticsearch import Elasticsearch
from app.config import ELASTICSEARCH_URL
from app.utils.logger import logger

class ElasticsearchService:
    def __init__(self):
        try:
            self.es = Elasticsearch(ELASTICSEARCH_URL, max_retries=0, request_timeout=2.0)
        except Exception as e:
            logger.error(f"Elasticsearch client initialization failed: {e}")
            self.es = None
        self.index_name = "code_entities"

    def initialize_index(self):
        """
        Creates the code_entities index with the required schema mapping if it does not already exist.
        """
        if not self.es:
            logger.warning("Elasticsearch client is offline. Skipping index initialization.")
            return

        try:
            if not self.es.indices.exists(index=self.index_name):
                mappings = {
                    "properties": {
                        "entity_id": { "type": "keyword" },
                        "repository": { "type": "keyword" },
                        "file_path": { "type": "keyword" },
                        "entity_type": { "type": "keyword" },
                        "entity_name": { "type": "keyword" },
                        "code_snippet": { "type": "text" },
                        "dependencies": { "type": "keyword" },
                        "mr_context": { "type": "keyword" }
                    }
                }
                self.es.indices.create(index=self.index_name, mappings=mappings)
                logger.info(f"Created Elasticsearch index '{self.index_name}' successfully.")
            else:
                logger.info(f"Elasticsearch index '{self.index_name}' already exists.")
        except Exception as e:
            logger.warning(f"Could not initialize index '{self.index_name}': {e}. "
                           "Is Elasticsearch running? Skipping initialization.")

    def index_entity(self, entity_id: str, doc: dict) -> bool:
        """
        Upserts a code entity document into Elasticsearch.
        """
        if not self.es:
            logger.error(f"Elasticsearch client is offline. Cannot index entity '{entity_id}'.")
            return False

        try:
            self.es.index(index=self.index_name, id=entity_id, document=doc)
            logger.info(f"Indexed entity '{entity_id}' successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to index entity '{entity_id}' in Elasticsearch: {e}")
            return False
