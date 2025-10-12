import re
import json
from typing import Dict, Any, Optional
from config import Config
from llm.provider import LLMProviderManager

class LLMAssistant:
    def __init__(self, config: Config):
        self.config = config
        self.logger = None
        self.provider_manager = LLMProviderManager(self.config)

    def set_logger(self, logger):
        self.logger = logger
        self.provider_manager.set_logger(logger)

    async def analyze_dom_and_suggest_action(self, dom_snapshot: Dict, goal: str) -> Dict[str, Any]:
        """
        Use LLM to analyze DOM and suggest next action (with fallback to rule-based).
        Updated as per new workflow: mainly used for fallback or fine-grained actions, as main steps are now generated in main.py and steps.py.
        """
        prompt = self._build_action_prompt(dom_snapshot, goal)

        response = await self.provider_manager.get_completion(
            prompt,
            preferred_provider=self.config.PREFERRED_PROVIDER
        )

        if response:
            parsed_response = self._parse_llm_response(response)
            if parsed_response:
                return parsed_response

        # Fallback to rule-based system (logic aligned with steps and new workflow)
        self.logger.warning("All LLM providers failed, using rule-based fallback")
        return self._get_rule_based_action(goal)


    async def analyze_failure(self, step_name: str, error: str, dom_snapshot: Dict) -> Dict[str, Any]:
        """
        Use LLM to analyze step failure and suggest a recovery plan (fallback if LLM fails).
        """
        prompt = self._build_failure_prompt(step_name, error, dom_snapshot)

        response = await self.provider_manager.get_completion(prompt)
        if response:
            parsed_response = self._parse_llm_response(response)
            if parsed_response:
                return parsed_response

        # Fallback: very basic self-healing aligned to new workflow steps
        return self._get_fallback_recovery_plan()

    def _build_action_prompt(self, dom_snapshot: Dict, goal: str) -> str:
        # More focused prompt for updated workflow (works for both search and in-page actions)
        return f"""
Analyze the following web page snapshot and suggest the most reliable CSS selector & action to accomplish the goal: "{goal}"

Page Info:
- Title: {dom_snapshot.get('title', 'N/A')}
- URL: {dom_snapshot.get('url', 'N/A')}

Relevant Interactive HTML (first 10 of each type):
{self._extract_interactive_elements(dom_snapshot.get('body', ''))}

Please answer ONLY in this JSON format:
{{
    "action": "click/type/select/wait/navigate",
    "selector": "css_selector_here",
    "value": "optional_value_for_typing",
    "confidence": 0.0-1.0,
    "reason": "short_explanation"
}}

Selector preference order:
1. data-testid attribute
2. aria-label attribute
3. Button text
4. Input name
5. Key semantic class

Return nothing except the JSON.
"""

    def _build_failure_prompt(self, step_name: str, error: str, dom_snapshot: Dict) -> str:
        return f"""
Web automation failed at step: {step_name}
Error encountered: {error}

Current page info:
- Title: {dom_snapshot.get('title', 'N/A')}
- URL: {dom_snapshot.get('url', 'N/A')}

Suggest a concise fallback recovery plan in JSON as shown. If a simple reload or close-modal would help, include it in 'actions':

{{
    "analysis": "what_may_have_gone_wrong",
    "actions": [
        {{"type": "click/wait/navigate/reload", "selector": "css_selector", "reason": "why_this_helps"}}
    ]
}}
"""

    def _extract_interactive_elements(self, html: str) -> str:
        """Extract first N interactive elements for LLM prompt (for efficiency with big DOMs)."""
        elements = []
        buttons = re.findall(r'<button[^>]*>.*?</button>', html, re.IGNORECASE | re.DOTALL)
        elements.extend(buttons[:10])
        inputs = re.findall(r'<input[^>]*>', html, re.IGNORECASE)
        elements.extend(inputs[:10])
        links = re.findall(r'<a[^>]*href[^>]*>.*?</a>', html, re.IGNORECASE | re.DOTALL)
        elements.extend(links[:10])
        return '\n'.join(elements)

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        # Extract any JSON in response, for robustness
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return None

    def _get_rule_based_action(self, goal: str) -> Dict[str, Any]:
        """
        Rule-based fallback, adapted to the new workflow and steps.
        """
        goal_lower = goal.lower()
        # Map new workflow phrases to selectors; you can tweak as workflow/steps evolve!

        if "generate search url" in goal_lower or "search" in goal_lower:
            return {
                "action": "type",
                "selector": self.config.SELECTORS["search_input"][0],
                "reason": "Fallback: search box detected",
                "confidence": 0.7
            }
        elif "launch search url" in goal_lower:
            return {
                "action": "navigate",
                "selector": None,
                "reason": "Fallback: navigating to search URL",
                "confidence": 0.8
            }
        elif "select exact product" in goal_lower or "exact product" in goal_lower or "choose product" in goal_lower:
            return {
                "action": "click",
                "selector": self.config.SELECTORS["product_card"][0],
                "reason": "Fallback: Select product card",
                "confidence": 0.7
            }
        elif "add to cart" in goal_lower:
            return {
                "action": "click",
                "selector": self.config.SELECTORS["add_to_cart"][0],
                "reason": "Fallback: Add to cart button",
                "confidence": 0.8
            }
        elif "place order" in goal_lower:
            return {
                "action": "click",
                "selector": self.config.SELECTORS.get("place_order", ["button:has-text('Place Order')"])[0],
                "reason": "Fallback: Place order button",
                "confidence": 0.7
            }
        elif "increase quantity" in goal_lower or "quantity" in goal_lower:
            return {
                "action": "click",
                "selector": self.config.SELECTORS.get("quantity_increase", ["button:has-text('+')"])[0],
                "reason": "Fallback: Quantity increase button",
                "confidence": 0.7
            }
        elif "continue" in goal_lower:
            return {
                "action": "click",
                "selector": self.config.SELECTORS.get("continue_button", ["button:has-text('Continue')"])[0],
                "reason": "Fallback: Continue button",
                "confidence": 0.65
            }
        else:
            # Generic minimal fallback for unknown goals
            return {
                "action": "wait",
                "selector": "body",
                "reason": "Fallback: Safe wait",
                "confidence": 0.5
            }

    def _get_fallback_recovery_plan(self) -> Dict[str, Any]:
        # Robust recovery plan, aligned with steps.py/common Flipkart modal annoyance
        return {
            "analysis": "LLM providers unavailable or failed. Using basic recovery plan.",
            "actions": [
                {"type": "click", "selector": s, "reason": "Try close initial modal"}
                for s in self.config.SELECTORS.get("login_close", [])[:2]
            ] + [
                {"type": "wait", "selector": "body", "reason": "Wait for page stability"},
                {"type": "reload", "reason": "Reload page to clear glitches"}
            ]
        }

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