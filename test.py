import g4f

prompt = """System:
        You are an expert data extraction model specialized in parsing Flipkart product pages.

        Task:
        - Analyze the provided Flipkart product page HTML.
        - Extract all relevant product information accurately.
        - Return a clean, valid JSON object strictly following the structure below.
        - Do NOT include explanations, markdown, or any extra text.

        Output JSON structure:
        {
            ""name"": "" "",
            ""rating"": 0.0,
            ""ratings_count"": 0,
            ""reviews_count"": 0,
            ""current_price"": 0,
            ""original_price"": 0,
            ""discount_percentage"": 0,
            ""availability"": "" "",
            ""exchange_offer"": "" "",
            "specifications": {
                "ram_rom": "" "",
                "display": " "",
                "camera": " ",
                "battery"": "" "",
                "processor"": "" "",
                "warranty"": "" ""
            },
            ""product_url"": "" "",
            ""image_url"": "" ""
        }

        Rules:
        1. Extract numbers as integers or floats without symbols (no ₹, %, commas).
        2. Keep all text fields exactly as shown on the site.
        3. Use empty string ("") for missing text fields and 0 for missing numeric fields.
        4. If a field is not present on the page, do NOT guess — use empty or zero values.
        5. Output valid JSON only — no explanations, markdown, or extra words.
        6. Include the product URL and main image URL if available.
        7. Always keep the JSON structure intact, even if some specification fields are empty.
         """


response = g4f.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}],
    timeout=300
)
print(response)
