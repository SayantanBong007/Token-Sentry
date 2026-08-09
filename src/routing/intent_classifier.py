"""
routing/intent_classifier.py — Evaluates user intent to route to the appropriate model.

WHY THIS EXISTS:
  If a user says "Hello" or "What's my name?", we don't need to spin up the
  massive Llama-3.3-70b-versatile model. We can answer it perfectly with
  Llama-3.1-8b-instant at a fraction of the cost.

  This classifier intercepts the request, looks at the final message, and
  decides if it's "SIMPLE" or "COMPLEX".
"""

import logging
from openai import AsyncOpenAI
from src.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    base_url=settings.primary_provider_url,
    api_key=settings.primary_api_key,
    max_retries=0,  # instant failover — let router.py handle fallback
)

INTENT_PROMPT = """You are an intent router for an AI assistant.
Your job is to look at the user's latest request and classify it as either SIMPLE or COMPLEX.

SIMPLE:
- Greetings ("Hello", "Hi", "How are you")
- Pleasantries ("Thanks", "Good night")
- Extremely basic factual questions ("What is the capital of France?")
- Short confirmations ("Yes", "No", "Ok")

COMPLEX:
- Coding tasks (writing, debugging, reviewing code)
- Complex logic or reasoning questions
- Creative writing (essays, stories, long-form content)
- Multi-step instructions
- Anything requiring deep thought or analysis

Respond with EXACTLY ONE WORD: either "SIMPLE" or "COMPLEX". Do not explain.

User's latest request:
"{user_request}"
"""

async def classify_intent(messages: list[dict]) -> str:
    """
    Evaluates the messages to determine if the intent is SIMPLE or COMPLEX.
    Uses the cheap summarizer model to make the decision quickly.
    
    Returns "SIMPLE" or "COMPLEX". Defaults to "COMPLEX" on error.
    """
    if not messages:
        return "COMPLEX"
        
    # Get the last user message
    last_user_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break
            
    if not last_user_msg:
        return "COMPLEX"
        
    # Truncate if it's extremely long (long prompts are automatically complex)
    if len(last_user_msg) > 500:
        return "COMPLEX"

    prompt = INTENT_PROMPT.replace("{user_request}", last_user_msg)

    try:
        response = await _client.chat.completions.create(
            model=settings.primary_summarizer_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        
        intent = response.choices[0].message.content.strip().upper()
        
        # Clean up in case the model ignored instructions
        if "SIMPLE" in intent:
            result = "SIMPLE"
        else:
            result = "COMPLEX"
            
        logger.debug(
            "Intent classified", 
            extra={"request": last_user_msg[:50] + "...", "intent": result}
        )
        return result
        
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}. Defaulting to COMPLEX.")
        return "COMPLEX"
