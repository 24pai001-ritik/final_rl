# generate.py

from rl_agent import select_action
from prompt_template import TOPIC_GENERATOR,PROMPT_GENERATOR, TRENDY_TOPIC_PROMPT, classify_trend_style, REEL_SCRIPT_GENERATOR, POST_SCRIPT_GENERATOR, CAROUSEL_IMAGE_PROMPT_GENERATOR
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import json
import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
import numpy as np
from db import recent_topics


load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROK_API_URL = os.getenv("GROK_API_URL")
GROK_API_KEY = os.getenv("GROK_URL_KEY")


# ============================================================
# LLM CLIENTS (ABSTRACTION LAYER)
# ============================================================
# Note: Models are initialized only when API keys are available

def call_gpt_4o_mini(prompt: str) -> dict:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    # Initialize the model with the API key
    gpt_4o_mini = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=OPENAI_API_KEY,
        temperature=0.7
    )

    response = gpt_4o_mini.invoke([
        HumanMessage(content=prompt)
    ])

    try:
        return json.loads(response.content)
    except Exception:
        raise ValueError("GPT-4o mini did not return valid JSON")


def call_grok(prompt: str) -> str | dict:
    """
    Grok HTTP client.
    - Reads env vars at RUNTIME (no import-time freeze)
    - Works with paid API keys
    - Returns JSON if possible, else raw text
    """

    GROK_API_KEY = os.getenv("GROK_API_KEY")
    GROK_API_URL = os.getenv("GROK_API_URL")

    if not GROK_API_KEY:
        raise ValueError("GROK_API_KEY not found in environment variables")

    if not GROK_API_URL:
        raise ValueError("GROK_API_URL not found in environment variables")

    try:
        response = requests.post(
            GROK_API_URL,
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                # safest + cheapest + API-enabled
                "model": "grok-4-1-fast-non-reasoning",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            },
            timeout=30
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Grok request failed: {e}")

    if response.status_code != 200:
        raise RuntimeError(
            f"Grok API error {response.status_code}: {response.text}"
        )

    content = response.json()["choices"][0]["message"]["content"]

    # Prompt-generation -> JSON
    # Topic-generation -> plain text
    try:
        return json.loads(content)
    except Exception:
        return content



# ============================================================
# TOPIC GENERATOR
# ============================================================

def generate_topic(
    business_context: str,
    platform: str,
    date: str,
    business_id: str = None,
    profile_data: dict = None

) -> dict:
    """
    Generates a post topic using Grok.
    Returns:
    {
      "topic": str,
      "reasoning": str
    }
    """
    print(f"Business context: {business_context}")
    filled_prompt = TOPIC_GENERATOR
    
    # Get location data - prefer profile_data if provided, otherwise try to extract
    city = ""
    state = ""
    if profile_data:
        city = profile_data.get("location_city", "")
        state = profile_data.get("location_state", "Gujarat")
    elif isinstance(business_context, dict):
        city = business_context.get("location_city", business_context.get("city", ""))
        state = business_context.get("location_state", business_context.get("state", "Gujarat"))
    elif business_id:
        # Try to get from profile if business_context is a string
        try:
            profile_data = db.get_profile_business_data(business_id)
            city = profile_data.get("location_city", "")
            state = profile_data.get("location_state", "Gujarat")
        except:
            pass
    
    filled_prompt = filled_prompt.replace("{{BUSINESS_CONTEXT}}", str(business_context))
    filled_prompt = filled_prompt.replace("{{PLATFORM}}", platform)
    filled_prompt = filled_prompt.replace("{{DATE}}", date)
    filled_prompt = filled_prompt.replace("{{CITY}}", city)
    filled_prompt = filled_prompt.replace("{{STATE}}", state)
    filled_prompt = filled_prompt.replace("{{RECENT_TOPICS}}", str(recent_topics(business_id,platform)))

    try:
        response = call_grok(filled_prompt)
        return {
            "topic": response
        }

    except Exception as e:
        print(f"Error generating topic: {e}")
        return {
            "topic": "Get to know our brand and what we do, Give a brief introduction to the business and what we do "
        }

    

# ============================================================
# EMBED TOPIC
# ============================================================



client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def embed_topic(text: str) -> np.ndarray:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    
    return np.array(response.data[0].embedding, dtype=np.float32)

# ============================================================
# REEL SCRIPT GENERATOR
# ============================================================

def generate_reel_script(
    business_context: str,
    topic: str,
    platform: str,
    action: dict,
    profile_data: dict
) -> str:
    """
    Generates a human-followable reel script using Grok.
    
    Args:
        business_context: Business context string
        topic: Topic for the reel
        platform: Social media platform
        action: RL action dictionary containing HOOK_TYPE, TONE, etc.
        profile_data: Business profile data dictionary
    
    Returns:
        Reel script as plain text string
    """
    print(f"Generating reel script for topic: {topic}")
    
    filled_prompt = REEL_SCRIPT_GENERATOR
    
    # Prepare business context string
    business_context_str = str(business_context)
    
    # Extract values from profile_data
    business_name = profile_data.get("business_name", "Business")
    industries = profile_data.get("industries", [])
    if isinstance(industries, list):
        industries_str = ", ".join(industries)
    else:
        industries_str = str(industries)
    
    target_audience = profile_data.get("target_audience", [])
    if isinstance(target_audience, list):
        target_audience_str = ", ".join(target_audience)
    else:
        target_audience_str = str(target_audience)
    
    brand_voice = profile_data.get("brand_voice", "Professional")
    brand_tone = profile_data.get("brand_tone", "Friendly")
    city = profile_data.get("location_city", "")
    state = profile_data.get("location_state", "Gujarat")
    
    # Replace placeholders
    filled_prompt = filled_prompt.replace("{{BUSINESS_CONTEXT}}", business_context_str)
    filled_prompt = filled_prompt.replace("{{topic_text}}", topic)
    filled_prompt = filled_prompt.replace("{{PLATFORM}}", platform)
    filled_prompt = filled_prompt.replace("{{HOOK_TYPE}}", action.get("HOOK_TYPE", "question"))
    filled_prompt = filled_prompt.replace("{{TONE}}", action.get("TONE", "friendly"))
    filled_prompt = filled_prompt.replace("{{INFORMATION_DEPTH}}", action.get("INFORMATION_DEPTH", "balanced"))
    filled_prompt = filled_prompt.replace("{{CREATIVITY}}", action.get("CREATIVITY", "balanced"))
    filled_prompt = filled_prompt.replace("{{BUSINESS_NAME}}", business_name)
    filled_prompt = filled_prompt.replace("{{INDUSTRIES}}", industries_str)
    filled_prompt = filled_prompt.replace("{{TARGET_AUDIENCE}}", target_audience_str)
    filled_prompt = filled_prompt.replace("{{BRAND_VOICE}}", brand_voice)
    filled_prompt = filled_prompt.replace("{{BRAND_TONE}}", brand_tone)
    filled_prompt = filled_prompt.replace("{{CITY}}", city)
    filled_prompt = filled_prompt.replace("{{STATE}}", state)
    
    try:
        response = call_grok(filled_prompt)
        
        # Grok returns plain text for reel scripts (not JSON)
        if isinstance(response, str):
            return response
        elif isinstance(response, dict):
            # If it's a dict, try to extract script content
            return response.get("script", str(response))
        else:
            return str(response)
            
    except Exception as e:
        print(f"Error generating reel script: {e}")
        # Return a fallback script
        return f"""**HOOK (0-3 seconds)**
Show a close-up of your product or service. Display text overlay: "{topic}". Make it bold and attention-grabbing.

**SCENE 1: Introduction**
Film yourself or your product from a front angle. Show the key feature or benefit. Add text overlay: "Discover {topic}". Duration: 3-4 seconds.

**SCENE 2: Main Value**
Demonstrate the main value proposition. Use a clear camera angle. Display text: "Why it matters". Duration: 5-6 seconds.

**CALL TO ACTION**
End with text overlay: "Follow for more tips". Show your brand or logo. Duration: 2-3 seconds.

**ADDITIONAL NOTES**
- Use upbeat, energetic music
- Target duration: 15-30 seconds
- Keep transitions smooth and professional"""

# ============================================================
# POST SCRIPT GENERATOR
# ============================================================

def generate_post_script(
    generated_caption: str,
    generated_image_url: str,
    topic: str,
    platform: str,
    action: dict,
    profile_data: dict
) -> str:
    """
    Generates a human-readable script explaining how to use the generated post content.
    
    Args:
        generated_caption: The generated caption text
        generated_image_url: The URL of the generated image
        topic: Topic for the post
        platform: Social media platform
        action: RL action dictionary containing HOOK_TYPE, TONE, etc.
        profile_data: Business profile data dictionary
    
    Returns:
        Post usage script as plain text string
    """
    print(f"Generating post usage script...")
    
    filled_prompt = POST_SCRIPT_GENERATOR
    
    # Extract values from profile_data
    business_name = profile_data.get("business_name", "Business")
    industries = profile_data.get("industries", [])
    if isinstance(industries, list):
        industries_str = ", ".join(industries)
    else:
        industries_str = str(industries)
    
    target_audience = profile_data.get("target_audience", [])
    if isinstance(target_audience, list):
        target_audience_str = ", ".join(target_audience)
    else:
        target_audience_str = str(target_audience)
    
    brand_voice = profile_data.get("brand_voice", "Professional")
    brand_tone = profile_data.get("brand_tone", "Friendly")
    city = profile_data.get("location_city", "")
    state = profile_data.get("location_state", "Gujarat")
    
    # Replace placeholders
    filled_prompt = filled_prompt.replace("{{GENERATED_CAPTION}}", generated_caption)
    filled_prompt = filled_prompt.replace("{{GENERATED_IMAGE_URL}}", generated_image_url)
    filled_prompt = filled_prompt.replace("{{topic_text}}", topic)
    filled_prompt = filled_prompt.replace("{{PLATFORM}}", platform)
    filled_prompt = filled_prompt.replace("{{BUSINESS_NAME}}", business_name)
    filled_prompt = filled_prompt.replace("{{TONE}}", action.get("TONE", "friendly"))
    filled_prompt = filled_prompt.replace("{{CREATIVITY}}", action.get("CREATIVITY", "balanced"))
    filled_prompt = filled_prompt.replace("{{VISUAL_STYLE}}", action.get("VISUAL_STYLE", "modern_corporate_b2b"))
    filled_prompt = filled_prompt.replace("{{COMPOSITION_STYLE}}", action.get("COMPOSITION_STYLE", "center_focused"))
    filled_prompt = filled_prompt.replace("{{INDUSTRIES}}", industries_str)
    filled_prompt = filled_prompt.replace("{{BRAND_VOICE}}", brand_voice)
    filled_prompt = filled_prompt.replace("{{CITY}}", city)
    filled_prompt = filled_prompt.replace("{{STATE}}", state)
    
    # Add primary and secondary colors from profile_data
    primary_color = profile_data.get("primary_color", "#000000")
    secondary_color = profile_data.get("secondary_color", "#FFFFFF")
    filled_prompt = filled_prompt.replace("{{PRIMARY_COLOR}}", primary_color)
    filled_prompt = filled_prompt.replace("{{SECONDARY_COLOR}}", secondary_color)
    
    try:
        response = call_grok(filled_prompt)
        
        # Grok returns plain text for post scripts (not JSON)
        if isinstance(response, str):
            return response
        elif isinstance(response, dict):
            # If it's a dict, try to extract script content
            return response.get("script", str(response))
        else:
            return str(response)
            
    except Exception as e:
        print(f"Error generating post script: {e}")
        # Return a fallback image description
        primary_color = profile_data.get("primary_color", "#000000")
        secondary_color = profile_data.get("secondary_color", "#FFFFFF")
        visual_style = action.get("VISUAL_STYLE", "modern_corporate_b2b")
        composition_style = action.get("COMPOSITION_STYLE", "center_focused")
        
        return f"""Create an image that visually represents the topic: {topic}. Use {visual_style} visual style with {composition_style} composition. The image should use {primary_color} as the primary color and {secondary_color} as the secondary color. Include visual elements that align with the business context and topic. The image should be suitable for {platform} platform and reflect the {action.get('TONE', 'friendly')} tone. Provide step-by-step instructions on how to create this image using photography, design software, or other appropriate tools."""

# ============================================================
# CAROUSEL SCRIPT GENERATOR
# ============================================================

def generate_carousel_script(
    generated_caption: str,
    generated_image_urls: list,  # List of 4 image URLs
    topic: str,
    platform: str,
    action: dict,
    profile_data: dict
) -> str:
    """
    Generates a human-readable script explaining how to use the generated carousel content.
    
    Args:
        generated_caption: The generated caption text (for entire carousel)
        generated_image_urls: List of 4 image URLs (one per slide)
        topic: Topic for the carousel
        platform: Social media platform
        action: RL action dictionary containing HOOK_TYPE, TONE, etc.
        profile_data: Business profile data dictionary
    
    Returns:
        Carousel usage script as plain text string
    """
    print(f"Generating carousel usage script...")
    
    # Build image descriptions for each slide
    primary_color = profile_data.get("primary_color", "#000000")
    secondary_color = profile_data.get("secondary_color", "#FFFFFF")
    visual_style = action.get("VISUAL_STYLE", "modern_corporate_b2b")
    composition_style = action.get("COMPOSITION_STYLE", "center_focused")
    
    script = f"""**SLIDE 1 - Hook/Overview Image:**
Create an image that grabs attention and introduces the topic: {topic}. Use {visual_style} visual style with {composition_style} composition. The image should use {primary_color} as the primary color and {secondary_color} as the secondary color. Include visual elements that create a strong first impression and make viewers want to see more. The image should align with the business context and be suitable for {platform} platform.

**SLIDE 2 - Detail/Feature Image:**
Create an image that expands on specific features or details related to {topic}. Maintain {visual_style} visual style and {composition_style} composition for consistency. Use {primary_color} and {secondary_color} color scheme. Show more information or context that builds on what was introduced in Slide 1. Keep visual consistency with Slide 1.

**SLIDE 3 - Benefit/Value Image:**
Create an image that highlights benefits and value proposition related to {topic}. Continue using {visual_style} visual style and {composition_style} composition. Maintain {primary_color} and {secondary_color} color scheme. Show why this matters to the audience and connect to the business value proposition. Ensure visual consistency with previous slides.

**SLIDE 4 - Call-to-Action/Close Image:**
Create an image that encourages action and reinforces the main message about {topic}. Use {visual_style} visual style and {composition_style} composition. Maintain {primary_color} and {secondary_color} color scheme. Create a strong closing that leaves a lasting impression and encourages viewers to take action. Ensure all 4 slides work together as a cohesive visual story."""
    
    return script

# ============================================================
# CONTEXT BUILDER 
# ============================================================

def build_context(business_embedding, topic_embedding, platform, time):
    """
    Build RL context from embeddings and scheduling info.
    """
    return {
        "platform": platform,
        "time_bucket": time,
        "business_embedding": business_embedding,
        "topic_embedding": topic_embedding
    }


# ============================================================
# MAIN GENERATION FUNCTION
# ============================================================

def generate_prompts(
    inputs: dict,
    business_embedding,
    topic_embedding,
    platform: str,
    time: str,
    topic_text: str,profile_data: dict,
    business_context: str
) -> dict:
    """
    Single execution point between RL and LLMs.
    """

    print(f"RL Context: Platform={platform}, Time={time}")

    # 1. Build RL context (using your build_context)
    context = build_context(
        business_embedding=business_embedding,
        topic_embedding=topic_embedding,
        platform=platform,
        time=time
    )

    # 2. RL decides creative controls
    action, ctx_vec = select_action(context) 
    
    print(f"RL Selected Action: {action}")
    hook_type = action.get("HOOK_TYPE", "")

    # 3. Merge inputs + RL action for placeholders
    # Extract location data from profile_data
    city = profile_data.get("location_city", "")
    state = profile_data.get("location_state", "Gujarat")
    
    merged = {**inputs, **action, "CITY": city, "STATE": state}

    # =====================================================
    # TRENDY -> GROK
    # =====================================================
    if hook_type == "trendy topic hook":
        selected_style = classify_trend_style(
            inputs["BUSINESS_TYPES"],
            inputs["INDUSTRIES"]
        )

        filled_prompt = TRENDY_TOPIC_PROMPT
        merged_with_style = {
            **merged,
            "selected_style": selected_style,
            "BUSINESS_CONTEXT": business_context,
            "BUSINESS_AESTHETIC": profile_data["brand_voice"],
            "BUSINESS_TYPES": profile_data["business_types"],
            "INDUSTRIES": profile_data["industries"],
            "topic_text": topic_text,
            "CITY": city,
            "STATE": state
        }

        for k, v in merged_with_style.items():
            if isinstance(v, list):
                v = ", ".join(v)
            filled_prompt = filled_prompt.replace(f"{{{{{k}}}}}", str(v))

        print(f"Sending to Grok (Trendy Topic): {filled_prompt[:200]}...")
        llm_response = call_grok(filled_prompt)

        if not isinstance(llm_response, dict):
            print("Grok returned non-JSON output. Raw response:")
            print(llm_response)
            raise ValueError("Invalid Grok response format")

        if "caption_prompt" not in llm_response or "image_prompt" not in llm_response:
            raise ValueError(f"Incomplete Grok response: {llm_response}")

        print(f"Generated Caption Prompt: {llm_response['caption_prompt']}\n")
        print(f"Generated Image Prompt: {llm_response['image_prompt']}\n")

        return {
            "mode": "trendy",
            "caption_prompt": llm_response["caption_prompt"],
            "image_prompt": llm_response["image_prompt"],
            "style": selected_style,
            "action": action,
            "context": context,
            "ctx_vec": ctx_vec
        }


    # =====================================================
    # NON-TRENDY -> GPT-4o MINI
    # =====================================================
    filled_prompt = PROMPT_GENERATOR
    merged = {
    **inputs,
    **action,
    "BUSINESS_CONTEXT": business_context,
    "BUSINESS_AESTHETIC": profile_data["brand_voice"],
    "BUSINESS_TYPES": profile_data["business_types"],
    "INDUSTRIES": profile_data["industries"],
    "topic_text": topic_text,
    "CITY": city,
    "STATE": state
}

    for k, v in merged.items():
        if isinstance(v, list):
            v = ", ".join(v)
        filled_prompt = filled_prompt.replace(f"{{{{{k}}}}}", str(v))

    print(f"Sending to GPT-4o-mini (Standard)")
    llm_response = call_gpt_4o_mini(filled_prompt)
    print(f"Generated Caption Prompt: {llm_response['caption_prompt'][:180]}...")
    print(f"Generated Image Prompt: {llm_response['image_prompt'][:180]}...")

    return {
        "mode": "standard",
        "caption_prompt": llm_response["caption_prompt"],
        "image_prompt": llm_response["image_prompt"],
        "action": action,
        "context": context,
        "ctx_vec": ctx_vec
    }