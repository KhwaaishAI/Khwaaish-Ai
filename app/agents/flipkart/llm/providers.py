from typing import Dict, Any, Optional
import openai
from config import Config
import asyncio

class LLMProvider:
    def __init__(self, config: Config):
        self.config = config
        self.logger = None
        
    def set_logger(self, logger):
        self.logger = logger
        
    def _safe_log(self, level: str, message: str):
        """Safely log messages without assuming logger is set"""
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(message)
        else:
            print(f"[{level.upper()}] {message}")
        
    async def get_completion(self, prompt: str) -> Optional[str]:
        raise NotImplementedError

class OpenAIProvider(LLMProvider):
    async def get_completion(self, prompt: str) -> Optional[str]:
        if not self.config.OPENAI_API_KEY:
            self._safe_log('warning', "OpenAI API key not provided")
            return None
            
        try:
            client = openai.OpenAI(api_key=self.config.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            self._safe_log('error', f"OpenAI API error: {str(e)}")
            return None

class G4FProvider(LLMProvider):
    def __init__(self, config: Config):
        super().__init__(config)
        self.client = None
        # Don't initialize client here - wait for logger to be set
        self._client_initialized = False
        
    def _initialize_client(self):
        """Initialize g4f client - call this after logger is set"""
        if self._client_initialized:
            return
            
        try:
            from g4f.client import Client
            self.client = Client()
            self._safe_log('info', "g4f Client initialized successfully")
            self._client_initialized = True
        except Exception as e:
            self._safe_log('warning', f"Failed to initialize g4f client: {str(e)}")
            self.client = None

    async def get_completion(self, prompt: str) -> Optional[str]:
        """Get completion using latest g4f API"""
        # Initialize client on first use (after logger is set)
        if not self._client_initialized:
            self._initialize_client()
            
        try:
            # First try with the new client API
            if self.client:
                result = await self._try_client_api(prompt)
                if result:
                    return result
            
            # Fallback to traditional approach
            result = await self._try_traditional_approach(prompt)
            if result:
                return result
                
            # Last resort: try direct approach
            result = await self._try_direct_approach(prompt)
            return result
            
        except Exception as e:
            self._safe_log('error', f"g4f comprehensive error: {str(e)}")
            return None

    async def _try_client_api(self, prompt: str) -> Optional[str]:
        """Try the new client API"""
        try:
            models = ["gpt-4", "gpt-4.1", "gpt-3.5-turbo", "claude-3-opus"]
            
            for model in models:
                try:
                    self._safe_log('info', f"Trying g4f client with model: {model}")
                    
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1000
                    )
                    
                    if (response and 
                        hasattr(response, 'choices') and 
                        len(response.choices) > 0 and
                        response.choices[0].message.content):
                        
                        content = response.choices[0].message.content
                        if content and content.strip():
                            self._safe_log('info', f"✅ g4f client success with {model}")
                            return content
                            
                except Exception as e:
                    self._safe_log('debug', f"g4f client model {model} failed: {str(e)}")
                    continue
                    
        except Exception as e:
            self._safe_log('debug', f"g4f client API failed: {str(e)}")
            
        return None

    async def _try_traditional_approach(self, prompt: str) -> Optional[str]:
        """Try traditional g4f ChatCompletion with working providers"""
        try:
            import g4f
            from g4f.Provider import (
                Bing, You, DeepInfra, Aivvm, GeekGpt,
                Liaobots, HuggingChat, OpenaiChat, FreeGpt
            )
            
            # List of currently working providers
            providers = [
                Bing, You, DeepInfra, Aivvm, GeekGpt, 
                Liaobots, HuggingChat, FreeGpt
            ]
            
            models = ["gpt-4", "gpt-4.1", "gpt-3.5-turbo"]
            
            for provider in providers:
                for model in models:
                    try:
                        self._safe_log('info', f"Trying {provider.__name__} with {model}")
                        
                        response = g4f.ChatCompletion.create(
                            model=model,
                            messages=[{"role": "user", "content": prompt}],
                            provider=provider,
                            timeout=30
                        )
                        
                        if response and response.strip():
                            self._safe_log('info', f"✅ {provider.__name__} success with {model}")
                            return response
                            
                    except Exception as e:
                        self._safe_log('debug', f"{provider.__name__} with {model} failed: {str(e)}")
                        continue
                        
        except Exception as e:
            self._safe_log('debug', f"Traditional g4f approach failed: {str(e)}")
            
        return None

    async def _try_direct_approach(self, prompt: str) -> Optional[str]:
        """Try direct g4f approach as last resort"""
        try:
            import g4f
            
            # Simple direct approach
            response = g4f.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                timeout=30
            )
            
            if response and response.strip():
                self._safe_log('info', "✅ Direct g4f approach success")
                return response
                
        except Exception as e:
            self._safe_log('debug', f"Direct g4f approach failed: {str(e)}")
            
        return None

class GeminiProvider(LLMProvider):
    async def get_completion(self, prompt: str) -> Optional[str]:
        try:
            import google.generativeai as genai
            
            if not self.config.GEMINI_API_KEY:
                self._safe_log('warning', "Gemini API key not provided")
                return None
                
            # Configure Gemini
            genai.configure(api_key=self.config.GEMINI_API_KEY)
            
            # Use Gemini Pro model
            model = genai.GenerativeModel('gemini-pro')
            
            response = model.generate_content(prompt)
            return response.text
            
        except ImportError:
            self._safe_log('error', "Google Generative AI not installed. Install with: pip install google-generativeai")
            return None
        except Exception as e:
            self._safe_log('error', f"Gemini API error: {str(e)}")
            return None

class AWSBedrockProvider(LLMProvider):
    def __init__(self, config: Config):
        super().__init__(config)
        self.client = None
        self.initialized = False
        
    async def _initialize_client(self):
        """Initialize Bedrock client asynchronously"""
        if self.initialized:
            return True
            
        try:
            import boto3
            
            # Check for AWS credentials
            if not all([self.config.AWS_ACCESS_KEY_ID, self.config.AWS_SECRET_ACCESS_KEY, self.config.AWS_REGION]):
                self._safe_log('warning', "AWS credentials not fully configured")
                return False
                
            # Create Bedrock client
            self.client = boto3.client(
                'bedrock-runtime',
                aws_access_key_id=self.config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.config.AWS_SECRET_ACCESS_KEY,
                region_name=self.config.AWS_REGION
            )
            
            self.initialized = True
            return True
            
        except ImportError:
            self._safe_log('error', "boto3 not installed. Install with: pip install boto3")
            return False
        except Exception as e:
            self._safe_log('error', f"AWS Bedrock initialization error: {str(e)}")
            return False

    async def get_completion(self, prompt: str) -> Optional[str]:
        """Get completion from AWS Bedrock"""
        if not await self._initialize_client():
            return None
            
        try:
            # Try Claude first (most reliable)
            models_to_try = [
                {
                    "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                    "body": {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    }
                },
                {
                    "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
                    "body": {
                        "anthropic_version": "bedrock-2023-05-31", 
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    }
                },
                {
                    "model_id": "amazon.titan-text-premier-v1:0",
                    "body": {
                        "inputText": prompt,
                        "textGenerationConfig": {
                            "maxTokenCount": 1000,
                            "temperature": 0.1
                        }
                    }
                }
            ]
            
            for model_config in models_to_try:
                try:
                    self._safe_log('info', f"Trying Bedrock model: {model_config['model_id']}")
                    
                    if 'anthropic' in model_config['model_id']:
                        import json
                        response = self.client.invoke_model(
                            modelId=model_config['model_id'],
                            body=json.dumps(model_config['body'])
                        )
                        response_body = json.loads(response['body'].read())
                        return response_body['content'][0]['text']
                        
                    elif 'amazon' in model_config['model_id']:
                        import json
                        response = self.client.invoke_model(
                            modelId=model_config['model_id'],
                            body=json.dumps(model_config['body'])
                        )
                        response_body = json.loads(response['body'].read())
                        return response_body['results'][0]['outputText']
                        
                except Exception as e:
                    self._safe_log('debug', f"Bedrock model {model_config['model_id']} failed: {str(e)}")
                    continue
            
            self._safe_log('error', "All Bedrock models failed")
            return None
            
        except Exception as e:
            self._safe_log('error', f"AWS Bedrock API error: {str(e)}")
            return None

class AnthropicProvider(LLMProvider):
    async def get_completion(self, prompt: str) -> Optional[str]:
        try:
            import anthropic
            
            if not self.config.ANTHROPIC_API_KEY:
                self._safe_log('warning', "Anthropic API key not provided")
                return None
                
            client = anthropic.Anthropic(api_key=self.config.ANTHROPIC_API_KEY)
            
            response = client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
            
        except ImportError:
            self._safe_log('error', "anthropic not installed. Install with: pip install anthropic")
            return None
        except Exception as e:
            self._safe_log('error', f"Anthropic API error: {str(e)}")
            return None

class LLMProviderManager:
    """Manager to handle multiple LLM providers with fallback"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = None
        self.providers = []
        # Don't initialize providers here - wait for logger to be set
        
    def set_logger(self, logger):
        self.logger = logger
        # Initialize providers only after logger is set
        self._initialize_providers()
        for provider in self.providers:
            provider.set_logger(logger)
            
    def _initialize_providers(self):
        """Initialize all available providers based on configuration"""
        providers = []
        providers.append(G4FProvider(self.config))
        # Add providers based on configuration and availability
        # if self.config.OPENAI_API_KEY:
        #     providers.append(OpenAIProvider(self.config))
            
        # if self.config.ANTHROPIC_API_KEY:
        #     providers.append(AnthropicProvider(self.config))
            
        # if self.config.GEMINI_API_KEY:
        #     providers.append(GeminiProvider(self.config))
            
        # if all([self.config.AWS_ACCESS_KEY_ID, self.config.AWS_SECRET_ACCESS_KEY, self.config.AWS_REGION]):
        #     providers.append(AWSBedrockProvider(self.config))
            
        # Always add G4F as fallback (free)
        # providers.append(G4FProvider(self.config))
        
        self.providers = providers
        
    def _safe_log(self, level: str, message: str):
        """Safely log messages without assuming logger is set"""
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(message)
        else:
            print(f"[{level.upper()}] {message}")
            
    async def get_completion(self, prompt: str, preferred_provider: str = None) -> Optional[str]:
        """Get completion from providers with fallback"""
        if preferred_provider:
            # Try preferred provider first
            for provider in self.providers:
                if provider.__class__.__name__.lower().replace('provider', '') == preferred_provider.lower():
                    self._safe_log('info', f"Trying preferred provider: {provider.__class__.__name__}")
                    result = await provider.get_completion(prompt)
                    if result:
                        return result
                    break
        
        # Try all providers in order
        for provider in self.providers:
            self._safe_log('info', f"Trying LLM provider: {provider.__class__.__name__}")
            result = await provider.get_completion(prompt)
            if result:
                self._safe_log('info', f"✅ Success with {provider.__class__.__name__}")
                return result
                
        self._safe_log('error', "All LLM providers failed")
        return None
        
    def get_available_providers(self) -> list:
        """Get list of available provider names"""
        return [provider.__class__.__name__.replace('Provider', '') for provider in self.providers]