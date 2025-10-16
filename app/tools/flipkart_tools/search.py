import json
import re
import g4f
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time
import os
from dotenv import load_dotenv
from tavily import TavilyClient
from app.prompts.flipkart_prompts.flipkart_prompt import PROMPT

# Load environment variables
load_dotenv()

class FlipkartExtractor:
    def __init__(self):
        self.max_concurrent_requests = 8
        self.chunk_size = 10000
        self.prompt = PROMPT
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        if self.tavily_api_key:
            self.tavily_client = TavilyClient(self.tavily_api_key)
        else:
            self.tavily_client = None

    def extract_products_batch(self, chunks: List[str]) -> List[Dict[str, Any]]:
        """Process chunks in parallel batches for maximum speed."""
        all_products = []
        completed = 0
        
        with ThreadPoolExecutor(max_workers=self.max_concurrent_requests) as executor:
            # Submit all chunks at once
            future_to_chunk = {
                executor.submit(self.process_single_chunk, chunk): i 
                for i, chunk in enumerate(chunks)
            }
            
            # Process completed futures
            for future in as_completed(future_to_chunk):
                try:
                    result = future.result(timeout=30)
                    if result:
                        all_products.extend(result)
                    completed += 1
                    print(f"✅ Chunk {completed}/{len(chunks)} processed")
                except Exception:
                    completed += 1
                    print(f"❌ Chunk {completed}/{len(chunks)} failed")
        
        return all_products

    def process_single_chunk(self, chunk: str) -> List[Dict[str, Any]]:
        """Process single chunk with g4f."""
        if len(chunk.strip()) < 100:
            return []
        
        try:
            response = g4f.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": self.prompt},
                    {"role": "user", "content": chunk[:8000]}  # Limit input size
                ],
                timeout=30
            )
            
            text = str(response)
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return []
            
        except Exception:
            return []

    def extract_from_html_file(self, html_file: str = "flipkart_page.html", output_file: str = "flipkart_products.json"):
        """Extract products from HTML file."""
        print("🔥 ULTRA-FAST BATCH PROCESSING")
        start = time.time()
        
        # Read and prepare data
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Quick extraction
        match = re.search(r'(\[!\[Image \d+\].*?)(Page \d+ of)', content, re.DOTALL)
        product_section = match.group(1) if match else content
        
        # Fast chunking
        chunks = re.split(r'(?=\[!\[Image \d+\])', product_section)
        chunks = [chunk for chunk in chunks if len(chunk) > 500]
        
        print(f"🎯 Processing {len(chunks)} chunks with {self.max_concurrent_requests} parallel workers...")
        
        # Batch process all chunks
        products = self.extract_products_batch(chunks)
        
        # Save
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(products, f, separators=(',', ':'), ensure_ascii=False)
        
        total = time.time() - start
        print(f"🚀 COMPLETE: {len(products)} products in {total:.1f}s ({len(products)/total:.1f} products/sec)")
        
        return products

    def extract_from_tavily(self, search_query: str, output_file: str = "flipkart_products.json"):
        """Extract products from Flipkart using Tavily API."""
        if not self.tavily_client:
            print("❌ Tavily API key not found. Please set TAVILY_API_KEY in .env file")
            return []
        
        print(f"🔍 Fetching data from Flipkart for: {search_query}")
        start = time.time()
        
        try:
            response = self.tavily_client.extract(
                urls=[search_query],
                extract_depth="advanced",
                format="text"
            )
            # Extract HTML content from Tavily response
            # Tavily response is a JSON dict; extract 'raw_content' as html string
            if isinstance(response, dict) and "results" in response and response["results"]:
                html_content = response["results"][0].get("raw_content", "")
            else:
                html_content = ""
            
            # Quick extraction
            match = re.search(r'(\[!\[Image \d+\].*?)(Page \d+ of)', html_content, re.DOTALL)
            product_section = match.group(1) if match else html_content
            
            # Fast chunking
            chunks = re.split(r'(?=\[!\[Image \d+\])', product_section)
            chunks = [chunk for chunk in chunks if len(chunk) > 500]
            
            print(f"🎯 Processing {len(chunks)} chunks with {self.max_concurrent_requests} parallel workers...")
            
            # Batch process all chunks
            products = self.extract_products_batch(chunks)
            
            # Save
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(products, f, separators=(',', ':'), ensure_ascii=False)
            
            total = time.time() - start
            print(f"🚀 COMPLETE: {len(products)} products in {total:.1f}s ({len(products)/total:.1f} products/sec)")
            
            return products
            
        except Exception as e:
            print(f"❌ Error fetching data from Tavily: {e}")
            return []


# def main():
#     # Example usage
#     extractor = FlipkartExtractor()
    
#     # Option 1: Extract from HTML file
#     # products = extractor.extract_from_html_file("flipkart_page.html", "products.json")
    
#     # Option 2: Extract directly from Flipkart using Tavily
#     products = extractor.extract_from_tavily("HP Printer", "flipkart_products.json")


# if __name__ == "__main__":
#     main()