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
# Load environment variables
from dotenv import load_dotenv
import os
import sys
import io

# Force UTF-8 encoding for stdout/stderr to handle emojis on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

# from db import fetch_or_calculate_reward

import uuid
import time
import random
from datetime import datetime
import numpy as np
import pytz

# Indian Standard Time (IST) - Asia/Kolkata
IST = pytz.timezone("Asia/Kolkata")
#from campaign import topic,date,time,platform

import db
# from rl_agent import update_rl
from generate import generate_prompts,embed_topic,generate_topic
#from job_queue import queue_reward_calculation_job
from content_generation import generate_content

# Add imports
import time
from datetime import datetime, timedelta
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

logger.info(" main.py ENTRYPOINT reached")
from datetime import datetime, timedelta
import pytz
import db

IST = pytz.timezone("Asia/Kolkata")

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
        time_bucket = time_bucket or scheduling_prefs["time_bucket"]

    print(f"\nStarting new post cycle for {platform} at {time_bucket}")
    
    date = datetime.now(IST).date().isoformat()


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
    business_id=BUSINESS_ID)
    
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
        topic_text,profile_data,
        business_context=profile_data,
    )

    # Extract values based on mode
    action = result["action"]
    context = result["context"]
    ctx_vec = result["ctx_vec"]
    mode = result["mode"]
    prompt_text = result.get("grok_prompt") or result.get("prompt", "") or result.get("image_prompt", "")

    # ---------- 3. STORE RL ACTION ----------
    post_id = f"{platform}_{uuid.uuid4().hex[:8]}"

    action_id = db.insert_action(
        post_id=post_id,
        platform=platform,
        context=context,
        action=action
    )

    # ---------- 4. STORE POST CONTENT ----------
    # Extract prompts based on mode (handle both trendy and standard modes)
    image_prompt = result.get("image_prompt",
        f"Create an image with {action['VISUAL_STYLE']} style, {action['TONE']} tone, {action['CREATIVITY']} creativity level.The topic is {topic_text}. Make it engaging for {platform}.Do not include caption in the image  directly.just learn from the caption and generate the image.")

    caption_prompt = result.get("caption_prompt",
        f"Write a {action['TONE']} caption in {action['INFORMATION_DEPTH']} length with {action['CREATIVITY']} creativity level. The topic is {topic_text}. Make it suitable for {platform}.")

    print("Generating caption and image content...")

    # Extract logo URL from business profile if available
    logo_url = profile_data.get("logo_url")
    if logo_url:
        print(f" Will overlay logo from: {logo_url}")

    content_result = generate_content(caption_prompt, image_prompt, profile_data, logo_url, business_id)

    if content_result["status"] == "success":
        generated_caption = content_result["caption"]
        generated_image_url = content_result["image_url"]


        print(" Content generated successfully and stored")
        print(f" Caption: {generated_caption[:100]}...")

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
        # business_context= profile_data["business_description"],
        # business_aesthetic=profile_data["brand_voice"],
        image_prompt=image_prompt,
        caption_prompt=caption_prompt,
        generated_caption=generated_caption,
        generated_image_url=generated_image_url
    )

    # ---------- 5. QUEUE FOR SCHEDULING ----------


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

                # ✅ THIS IS THE CORRECT PLACE
                
        
                schedule_next_content_generation(business_id)
                print(f"Next content_generation scheduled for {business_id}")

            except Exception as e:
                print(f"Business failed {business_id}: {e}")
                continue

        print("Daily post creation process completed")

    except Exception as e:
        print(f"Critical error in main process: {e}")
        raise
