# main.py
"""
MAIN ORCHESTRATOR

Flow:
1. Decide topic + post type
2. Generate prompts (via generate.py + RL)
3. Store content (post_contents)
4. Queue for scheduled posting
5. Collect metrics (via cron job)
6. Compute reward
7. Update RL
"""

# Load environment variables
from dotenv import load_dotenv
import sys
import io
from datetime import datetime, timedelta
import uuid
import time
import logging
import pytz

# Force UTF-8 encoding for stdout/stderr to handle emojis on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

# Indian Standard Time (IST) - Asia/Kolkata
IST = pytz.timezone("Asia/Kolkata")

import db
from generate import generate_prompts, embed_topic, generate_topic, generate_reel_script, generate_post_script, generate_carousel_script, call_grok
from content_generation import generate_content, generate_carousel_content
from prompt_template import CAROUSEL_IMAGE_PROMPT_GENERATOR

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

logger.info(" main.py ENTRYPOINT reached")

def schedule_next_content_generation(business_id):
    # Fetch preferred posting time
    prefs = db.get_profile_scheduling_prefs(business_id)

    hour = 10
    minute = 10

    tomorrow = datetime.now(IST) + timedelta(days=1)

    run_at = tomorrow.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0
    )

    job_id = f"content_gen_{business_id}_{run_at.date()}"

    # Idempotency: avoid duplicates
    existing = (
        db.supabase
        .table("jobs")
        .select("job_id")
        .eq("job_id", job_id)
        .execute()
    )

    if existing.data:
        return  # already scheduled

    db.supabase.table("jobs").insert({
        "job_id": job_id,
        "job_type": "content_generation",
        "payload": {"business_id": business_id},
        "status": "queued",
        "run_at": run_at.isoformat(),
        "retry_count": 0,
        "created_at": datetime.now(IST).isoformat()
    }).execute()


# MAIN LOOP
# -------------------------------------------------

def run_one_post(BUSINESS_ID, platform, time_bucket=None):
    # Get user's scheduling preferences if not provided
    if time_bucket is None:
        scheduling_prefs = db.get_profile_scheduling_prefs(BUSINESS_ID)
        time_bucket = scheduling_prefs["time_bucket"]

    print(f"\nStarting new post cycle for {platform} at {time_bucket}")
    
    date = (datetime.now(IST) + timedelta(days=4)).date().isoformat()

    # ---------- 1. BUSINESS CONTEXT ----------
    # Get business embedding and profile data from profiles table
    business_embedding = db.get_profile_embedding_with_fallback(BUSINESS_ID)
    if business_embedding is None:
        raise RuntimeError(f"No business embedding found for business {BUSINESS_ID}. Business profile must be created first.")

    profile_data = db.get_profile_business_data(BUSINESS_ID)

    #generate topic
    topic_data = generate_topic(
    business_context=str(profile_data),
    platform=platform,
    date=date,
    business_id=BUSINESS_ID,
    profile_data=profile_data)
    
    topic_text = topic_data["topic"]

    #create embedding for topic
    topic_embedding = embed_topic(topic_text)

    print(" Topic:", topic_text)
    print(" Topic embedding dim:", len(topic_embedding))

    # ---------- 2. GENERATE PROMPTS (RL INSIDE) ----------
    inputs = {
        "BUSINESS_AESTHETIC": profile_data["brand_voice"],  # Use brand voice as aesthetic
        "BUSINESS_TYPES": profile_data["business_types"],
        "INDUSTRIES": profile_data["industries"],
        "BUSINESS_DESCRIPTION": profile_data["business_description"],
    }

    result = generate_prompts(
        inputs,
        business_embedding,
        topic_embedding,
        platform,
        time_bucket,
        topic_text, profile_data,
        business_context=profile_data,
    )

    # Extract values based on mode
    action = result["action"]
    context = result["context"]

    # ---------- 3. STORE RL ACTION ----------
    post_id = f"{platform}_{uuid.uuid4().hex[:8]}"

    action_id = db.insert_action(
        post_id=post_id,
        platform=platform,
        context=context,
        action=action
    )

    # ---------- 4. CHECK CONTENT TYPE AND BRANCH ----------
    content_type = action.get("CONTENT_TYPE", "post")
    print(f"Content type selected: {content_type}")

    if content_type == "reel":
        # ---------- REEL FLOW: Generate reel script ----------
        print("Generating reel script...")
        
        reel_script = generate_reel_script(
            business_context=str(profile_data),
            topic=topic_text,
            platform=platform,
            action=action,
            profile_data=profile_data
        )
        
        print("Reel script generated successfully")
        print(f"Script preview: {reel_script[:200]}...")
        
        # Store reel script in database
        db.insert_reel_script(
            post_id=post_id,
            action_id=action_id,
            platform=platform,
            business_id=BUSINESS_ID,
            topic=topic_text,
            script_content=reel_script
        )
        
        print("Reel script stored in database")
        
    elif content_type == "carousel":
        # ---------- CAROUSEL FLOW: Generate 4 images + 1 caption ----------
        print("Generating carousel content (4 slides + caption)...")
        
        # Extract prompts
        image_prompt = result.get("image_prompt",
            f"Create an image with {action['VISUAL_STYLE']} style, {action['TONE']} tone, {action['CREATIVITY']} creativity level. The topic is {topic_text}. Make it engaging for {platform}.")
        
        caption_prompt = result.get("caption_prompt",
            f"Write a {action['TONE']} caption in {action['INFORMATION_DEPTH']} length with {action['CREATIVITY']} creativity level. The topic is {topic_text}. Make it suitable for {platform} carousel post.")
        
        # Generate 4 distinct image prompts for carousel slides
        print("Generating carousel image prompts...")
        carousel_prompt_template = CAROUSEL_IMAGE_PROMPT_GENERATOR
        
        # Fill template with values
        city = profile_data.get("location_city", "")
        state = profile_data.get("location_state", "Gujarat")
        
        filled_carousel_prompt = carousel_prompt_template.replace("{{BUSINESS_CONTEXT}}", str(profile_data))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{topic_text}}", topic_text)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{PLATFORM}}", platform)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{CITY}}", city)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{STATE}}", state)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{VISUAL_STYLE}}", action.get("VISUAL_STYLE", "modern_corporate_b2b"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{COMPOSITION_STYLE}}", action.get("COMPOSITION_STYLE", "center_focused"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{TONE}}", action.get("TONE", "friendly"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{CREATIVITY}}", action.get("CREATIVITY", "balanced"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{HOOK_TYPE}}", action.get("HOOK_TYPE", "question"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{INFORMATION_DEPTH}}", action.get("INFORMATION_DEPTH", "balanced"))
        
        # Call Grok to generate 4 image prompts
        try:
            carousel_prompts_response = call_grok(filled_carousel_prompt)
            
            # Parse JSON response
            if isinstance(carousel_prompts_response, dict):
                carousel_image_prompts = [
                    carousel_prompts_response.get("slide_1_prompt", image_prompt),
                    carousel_prompts_response.get("slide_2_prompt", image_prompt),
                    carousel_prompts_response.get("slide_3_prompt", image_prompt),
                    carousel_prompts_response.get("slide_4_prompt", image_prompt)
                ]
            else:
                # Fallback: use base prompt with variations
                print("⚠️  Could not parse carousel prompts, using base prompt with variations")
                carousel_image_prompts = [
                    f"{image_prompt} This is slide 1 of 4: Hook/Overview. Create an attention-grabbing first image.",
                    f"{image_prompt} This is slide 2 of 4: Detail/Feature. Expand on specific details.",
                    f"{image_prompt} This is slide 3 of 4: Benefit/Value. Highlight benefits and value.",
                    f"{image_prompt} This is slide 4 of 4: Call-to-Action/Close. Create a strong closing image."
                ]
        except Exception as e:
            print(f"⚠️  Error generating carousel prompts: {e}, using fallback")
            carousel_image_prompts = [
                f"{image_prompt} Slide 1: Hook/Overview",
                f"{image_prompt} Slide 2: Detail/Feature",
                f"{image_prompt} Slide 3: Benefit/Value",
                f"{image_prompt} Slide 4: Call-to-Action"
            ]
        
        print(f"Generated {len(carousel_image_prompts)} carousel image prompts")
        
        # Extract logo URL
        logo_url = profile_data.get("logo_url")
        if logo_url:
            print(f" Will overlay logo on all slides from: {logo_url}")
        
        # Generate carousel content (4 images + 1 caption)
        carousel_result = generate_carousel_content(
            caption_prompt=caption_prompt,
            image_prompts=carousel_image_prompts,
            business_context=profile_data,
            logo_url=logo_url,
            business_id=BUSINESS_ID
        )
        
        if carousel_result["status"] == "success":
            generated_caption = carousel_result["caption"]
            generated_image_urls = carousel_result["image_urls"]
            
            print(" Carousel content generated successfully")
            print(f" Caption: {generated_caption[:100]}...")
            print(f" Generated {len(generated_image_urls)} slides")
            
            # Generate carousel usage script
            print(" Generating carousel usage script...")
            carousel_script = generate_carousel_script(
                generated_caption=generated_caption,
                generated_image_urls=generated_image_urls,
                topic=topic_text,
                platform=platform,
                action=action,
                profile_data=profile_data
            )
            print(" Carousel script generated successfully")
            print(f" Script preview: {carousel_script[:200]}...")
            
            # Store in post_contents table
            db.insert_post_content(
                post_id=post_id,
                action_id=action_id,
                platform=platform,
                business_id=BUSINESS_ID,
                topic=topic_text,
                image_prompt=image_prompt,  # Base prompt
                caption_prompt=caption_prompt,
                generated_caption=generated_caption,
                generated_image_url=None,  # Not used for carousel
                post_script=carousel_script,
                carousel_image_urls=generated_image_urls,  # 4 image URLs
                content_type=content_type
            )
            print(" Carousel content stored in database")
        else:
            error_msg = f"Carousel generation failed: {carousel_result.get('error', 'Unknown error')}"
            print(f" {error_msg}")
            raise RuntimeError(error_msg)
        
    else:
        # ---------- POST FLOW: Generate image and caption (existing flow) ----------
        # Extract prompts based on mode (handle both trendy and standard modes)
        image_prompt = result.get("image_prompt",
            f"Create an image with {action['VISUAL_STYLE']} style, {action['TONE']} tone, {action['CREATIVITY']} creativity level. The topic is {topic_text}. Make it engaging for {platform}. Do not include caption in the image directly. Just learn from the caption and generate the image.")

        caption_prompt = result.get("caption_prompt",
            f"Write a {action['TONE']} caption in {action['INFORMATION_DEPTH']} length with {action['CREATIVITY']} creativity level. The topic is {topic_text}. Make it suitable for {platform}.")

        print("Generating caption and image content...")

        # Extract logo URL from business profile if available
        logo_url = profile_data.get("logo_url")
        if logo_url:
            print(f" Will overlay logo from: {logo_url}")

        content_result = generate_content(caption_prompt, image_prompt, profile_data, logo_url, BUSINESS_ID)

        if content_result["status"] == "success":
            generated_caption = content_result["caption"]
            generated_image_url = content_result["image_url"]

            print(" Content generated successfully")
            print(f" Caption: {generated_caption[:100]}...")
            
            # Generate human-readable post script
            print(" Generating post usage script...")
            post_script = generate_post_script(
                generated_caption=generated_caption,
                generated_image_url=generated_image_url,
                topic=topic_text,
                platform=platform,
                action=action,
                profile_data=profile_data
            )
            print(" Post script generated successfully")
            print(f" Script preview: {post_script[:200]}...")

        else:
            error_msg = f"Content generation failed: {content_result['error']}"
            print(f" {error_msg}")
            raise RuntimeError(error_msg)

        db.insert_post_content(
            post_id=post_id,
            action_id=action_id,
            platform=platform,
            business_id=BUSINESS_ID,
            topic=topic_text,
            image_prompt=image_prompt,
            caption_prompt=caption_prompt,
            generated_caption=generated_caption,
            generated_image_url=generated_image_url,
            post_script=post_script,
            content_type=content_type
        )

    # Create initial reward record for future calculation
    db.create_post_reward_record(BUSINESS_ID, post_id, platform, action_id)

    # ---------- 6. QUEUE REWARD CALCULATION FOR WORKER ----------
    # Queue reward calculation job (will automatically trigger RL update when ready)
    reward_job_id = f"reward_{post_id}_{int(time.time())}"

    db.supabase.table("jobs").insert({
        "job_id": reward_job_id,
        "job_type": "reward_calculation",
        "payload": {
            "profile_id": BUSINESS_ID,
            "post_id": post_id,
            "platform": platform
        },
        "status": "queued",
        "run_at": datetime.now(IST).isoformat(),
        "retry_count": 0,
        "created_at": datetime.now(IST).isoformat()
    }).execute()

    print(f" Reward calculation job queued: {reward_job_id}")


# -------------------------------------------------
# ENTRY POINT
# -------------------------------------------------
ALLOWED_PLATFORMS = {"instagram","facebook"}

if __name__ == "__main__":
    try:
        all_business_ids =db.get_all_profile_ids()
        print(f"Found {len(all_business_ids)} business profiles to check")

        for business_id in all_business_ids:
            try:
                print(f"\nProcessing business: {business_id}")

                # Check daily eligibility
                if not db.should_create_post_today(business_id):
                    print(f"Skipping business {business_id} - not scheduled for today")
                    continue

                user_connected_platforms = list(set(db.get_connected_platforms(business_id)))
                print(f"Business {business_id} platforms: {user_connected_platforms}")

                any_platform_succeeded = False

                for platform in user_connected_platforms:
                    try:
                        platform = platform.lower().strip()

                        if platform not in ALLOWED_PLATFORMS:
                            print(f"Skipping unsupported platform: {platform}")
                            continue

                        print(f"Creating post for {business_id} on {platform}")

                        run_one_post(
                            BUSINESS_ID=business_id,
                            platform=platform,
                        )

                        any_platform_succeeded = True
                        print(f"Post created for {platform}")

                    except Exception as e:
                        print(f"Platform failed {platform}: {e}")
                        continue

                schedule_next_content_generation(business_id)
                print(f"Next content_generation scheduled for {business_id}")

            except Exception as e:
                print(f"Business failed {business_id}: {e}")
                continue

        print("Daily post creation process completed")

    except Exception as e:
        print(f"Critical error in main process: {e}")
        raise
