"""
Utility to scan and identify product specification selectors on Amazon pages.

Usage:
    from spec_finder import SpecFinder
    finder = SpecFinder(page)
    specs = await finder.find_all_specs()
    print(specs)
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SpecFinder:
    """
    Scans Amazon product page for available specifications and their options.
    """
    
    # Common spec patterns on Amazon
    SPEC_PATTERNS = {
        'Color': {
            'keywords': ['color', 'colour', 'shade'],
            'selectors': [
                '[data-feature-name="color_name"]',
                '#variation_color_name',
                '[aria-label*="Color"]',
                '[aria-label*="Colour"]',
                '.variation-color',
            ]
        },
        'Storage': {
            'keywords': ['storage', 'capacity', 'memory'],
            'selectors': [
                '[data-feature-name="storage_size"]',
                '#variation_storage_size',
                '#variation_size_name',
                '[aria-label*="Storage"]',
                '[aria-label*="Memory"]',
            ]
        },
        'Size': {
            'keywords': ['size', 'dimensions', 'fit'],
            'selectors': [
                '[data-feature-name="size_name"]',
                '#variation_size_name',
                '[aria-label*="Size"]',
                '[aria-label*="Fit"]',
            ]
        },
        'Configuration': {
            'keywords': ['configuration', 'model', 'version'],
            'selectors': [
                '[data-feature-name="configuration"]',
                '#variation_configuration',
            ]
        },
        'Material': {
            'keywords': ['material', 'fabric', 'construction'],
            'selectors': [
                '[data-feature-name="material"]',
                '[aria-label*="Material"]',
            ]
        },
        'Style': {
            'keywords': ['style', 'design', 'pattern'],
            'selectors': [
                '[data-feature-name="style_name"]',
                '[aria-label*="Style"]',
            ]
        }
    }
    
    def __init__(self, page):
        """
        Initialize SpecFinder with Playwright page.
        
        Args:
            page: Playwright page object
        """
        self.page = page
    
    async def find_all_specs(self) -> Dict[str, List[str]]:
        """
        Scan page for all available specifications.
        
        Returns:
            Dict mapping spec names to list of available options
        """
        specs = {}
        
        for spec_name, pattern in self.SPEC_PATTERNS.items():
            options = await self._find_spec_options(pattern['selectors'])
            if options:
                specs[spec_name] = options
                logger.info(f"Found {spec_name}: {len(options)} options")
        
        return specs
    
    async def _find_spec_options(self, selectors: List[str]) -> Optional[List[str]]:
        """
        Try multiple selectors to find spec options.
        
        Args:
            selectors: List of CSS selectors to try
        
        Returns:
            List of option strings, or None if not found
        """
        for selector in selectors:
            try:
                locators = self.page.locator(selector)
                count = await locators.count()
                
                if count > 0:
                    options = []
                    for i in range(count):
                        text = await locators.nth(i).text_content()
                        if text and text.strip():
                            options.append(text.strip())
                    
                    if options:
                        return list(set(options))  # Deduplicate
            except Exception as e:
                logger.debug(f"Selector '{selector}' failed: {e}")
                continue
        
        return None
    
    async def find_best_match(
        self,
        spec_name: str,
        preferred_values: List[str]
    ) -> Optional[str]:
        """
        Find best match for a spec from preferred values.
        
        Args:
            spec_name: Specification name (e.g., 'Color')
            preferred_values: List of preferred options (e.g., ['Black', 'Space Gray'])
        
        Returns:
            Best matching option, or None
        """
        pattern = self.SPEC_PATTERNS.get(spec_name)
        if not pattern:
            logger.warning(f"Unknown spec: {spec_name}")
            return None
        
        available = await self._find_spec_options(pattern['selectors'])
        if not available:
            logger.warning(f"No options found for {spec_name}")
            return None
        
        # Try to find exact match (case-insensitive)
        for preferred in preferred_values:
            for option in available:
                if preferred.lower() == option.lower():
                    logger.info(f"Matched {spec_name}: {option}")
                    return option
        
        # Fallback: return first available
        logger.warning(f"No exact match for {spec_name}; using: {available[0]}")
        return available[0]
