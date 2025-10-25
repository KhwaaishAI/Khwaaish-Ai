"""
Basic smoke tests for Amazon Automator.

Run with: pytest tests/
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# Mock the import path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_automator_initialization():
    """Test AmazonAutomator can be initialized."""
    from amazon_automator.automator import AmazonAutomator
    
    automator = AmazonAutomator(
        headful=False,
        dry_run=True,
        throttle=0.5
    )
    
    assert automator.headful == False
    assert automator.dry_run == True
    assert automator.throttle == 0.5


@pytest.mark.asyncio
async def test_product_selection_dataclass():
    """Test ProductSelection dataclass."""
    from amazon_automator.automator import ProductSelection
    
    product = ProductSelection(
        asin='B08XY5YML4',
        title='Test Product',
        url='https://amazon.in/dp/B08XY5YML4',
        specifications={'Color': 'Black'}
    )
    
    assert product.asin == 'B08XY5YML4'
    assert product.title == 'Test Product'
    assert product.specifications['Color'] == 'Black'


def test_config_defaults():
    """Test Config class has sensible defaults."""
    from amazon_automator.config import Config
    
    config_dict = Config.to_dict()
    
    assert 'headful' in config_dict
    assert 'throttle' in config_dict
    assert config_dict['throttle'] > 0
    assert isinstance(config_dict['session_store_path'], str)


@pytest.mark.asyncio
async def test_parse_price():
    """Test price parsing utility."""
    from amazon_automator.automator import AmazonAutomator
    
    automator = AmazonAutomator(dry_run=True)
    
    # Test various price formats
    assert automator._parse_price('₹299') == 299.0
    assert automator._parse_price('₹1,299') == 1299.0
    assert automator._parse_price('₹1,299.99') == 1299.99
    assert automator._parse_price(None) is None
    assert automator._parse_price('') is None


@pytest.mark.asyncio
async def test_extract_asin_from_url():
    """Test ASIN extraction from URL."""
    from amazon_automator.automator import AmazonAutomator
    
    automator = AmazonAutomator(dry_run=True)
    
    url = 'https://www.amazon.in/dp/B08XY5YML4'
    asin = automator._extract_asin_from_url(url)
    
    assert asin == 'B08XY5YML4'


@pytest.mark.asyncio
async def test_display_products():
    """Test product display formatting."""
    from amazon_automator.automator import AmazonAutomator
    
    automator = AmazonAutomator(dry_run=True)
    
    products = [
        {
            'asin': 'B08XY5YML4',
            'title': 'USB-C Cable 3-Pack',
            'price': 299,
            'rating_value': 4.5,
            'available': True
        },
        {
            'asin': 'B09KQXSYGH',
            'title': 'Premium USB-C Cable',
            'price': 599,
            'rating_value': 4.7,
            'available': True
        }
    ]
    
    # Should not raise error
    automator.display_products(products)
    assert len(automator.displayed_products) == 2


@pytest.mark.asyncio
async def test_select_product():
    """Test product selection."""
    from amazon_automator.automator import AmazonAutomator
    
    automator = AmazonAutomator(dry_run=True)
    
    products = [
        {'asin': 'B08XY5YML4', 'title': 'Product 1'},
        {'asin': 'B09KQXSYGH', 'title': 'Product 2'}
    ]
    
    automator.displayed_products = products
    
    # Select first product
    selected = automator.select_product(1)
    assert selected['asin'] == 'B08XY5YML4'
    
    # Select second product
    selected = automator.select_product(2)
    assert selected['asin'] == 'B09KQXSYGH'
    
    # Invalid index should raise error
    with pytest.raises(ValueError):
        automator.select_product(99)


def test_automation_flow_initialization():
    """Test AmazonAutomationFlow can be created."""
    from amazon_automator.automator import AmazonAutomator, AmazonAutomationFlow
    
    automator = AmazonAutomator(dry_run=True)
    flow = AmazonAutomationFlow(automator)
    
    assert flow.automator == automator
