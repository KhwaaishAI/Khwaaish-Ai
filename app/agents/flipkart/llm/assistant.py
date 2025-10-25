import re
import json
from typing import Dict, Any, Optional
from app.agents.flipkart.config import Config
from app.agents.flipkart.llm.providers import LLMProviderManager

class LLMAssistant:
    def __init__(self, config: Config):
        self.config = config
        self.logger = None
        self.provider_manager = LLMProviderManager(self.config)

    def set_logger(self, logger):
        self.logger = logger
        self.provider_manager.set_logger(logger)

    async def invoke(self, prompt: str, preferred_provider: Optional[str] = None) -> Dict[str, str]:
        """
        Directly invoke the LLM with a given prompt and always return a standardized query response.
        Returns:
            {"query": "<final_search_query_string>"}
        """

        try:
            response = await self.provider_manager.get_completion(
                prompt,
                preferred_provider=preferred_provider or self.config.PREFERRED_PROVIDER
            )

            if not response:
                if self.logger:
                    self.logger.warning("No response received from LLM provider.")
                return {"query": ""}

            # Attempt to extract query from JSON if LLM returns structured data
            parsed_response = self._parse_llm_response(response)
            if parsed_response and isinstance(parsed_response, dict):
                if "query" in parsed_response:
                    return {"query": parsed_response["query"].strip()}
                # If JSON contains a single key-value, use its value as query
                if len(parsed_response) == 1:
                    return {"query": list(parsed_response.values())[0].strip()}

            # Otherwise, treat raw text output as the query
            clean_query = response.strip().strip('"').strip("'")
            return {"query": clean_query}

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error during LLM invocation: {e}")
            return {"query": ""}


