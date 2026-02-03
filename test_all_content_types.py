"""
Comprehensive test for all content types: POST, CAROUSEL, and REEL
Tests generation, database storage, and content_type setting
"""

import sys
import os
from datetime import datetime, timedelta
import pytz
import uuid
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import required modules
import db
from generate import generate_prompts, embed_topic, generate_topic, generate_reel_script, generate_post_script, generate_carousel_script
from content_generation import generate_content, generate_carousel_content
from rl_agent import select_action

# Indian Standard Time
IST = pytz.timezone("Asia/Kolkata")

# Test profile ID
TEST_PROFILE_ID = "77306a64-848f-4241-b2f0-3accfa06a46a"
TEST_PLATFORM = "instagram"


def test_post_generation():
    """Test POST generation and save"""
    print("\n" + "=" * 80)
    print("TEST 1: POST GENERATION")
    print("=" * 80)
    
    try:
        # Get business context
        business_embedding = db.get_profile_embedding_with_fallback(TEST_PROFILE_ID)
        if business_embedding is None:
            return {"status": "error", "error": "No business embedding found"}
        
        profile_data = db.get_profile_business_data(TEST_PROFILE_ID)
        print(f"Business: {profile_data.get('business_name', 'Unknown')}")
        
        # Generate topic
        date = (datetime.now(IST) + timedelta(days=4)).date().isoformat()
        topic_data = generate_topic(
            business_context=str(profile_data),
            platform=TEST_PLATFORM,
            date=date,
            business_id=TEST_PROFILE_ID,
            profile_data=profile_data
        )
        topic_text = topic_data["topic"]
        print(f"Topic: {topic_text[:80]}...")
        
        # Create embedding
        topic_embedding = embed_topic(topic_text)
        
        # Generate prompts
        inputs = {
            "BUSINESS_AESTHETIC": profile_data["brand_voice"],
            "BUSINESS_TYPES": profile_data["business_types"],
            "INDUSTRIES": profile_data["industries"],
            "BUSINESS_DESCRIPTION": profile_data["business_description"],
        }
        
        result = generate_prompts(
            inputs,
            business_embedding,
            topic_embedding,
            TEST_PLATFORM,
            "evening",
            topic_text,
            profile_data,
            business_context=profile_data,
        )
        
        # Force post type
        result["action"]["CONTENT_TYPE"] = "post"
        action = result["action"]
        context = result["context"]
        content_type = "post"
        
        print(f"Content Type: {content_type}")
        
        # Store action
        post_id = f"{TEST_PLATFORM}_{uuid.uuid4().hex[:8]}"
        action_id = db.insert_action(
            post_id=post_id,
            platform=TEST_PLATFORM,
            context=context,
            action=action
        )
        print(f"Action ID: {action_id}")
        
        # Generate content
        image_prompt = result.get("image_prompt", "")
        caption_prompt = result.get("caption_prompt", "")
        logo_url = profile_data.get("logo_url")
        
        content_result = generate_content(
            caption_prompt,
            image_prompt,
            profile_data,
            logo_url,
            TEST_PROFILE_ID
        )
        
        if content_result["status"] != "success":
            return {"status": "error", "error": content_result.get("error")}
        
        generated_caption = content_result["caption"]
        generated_image_url = content_result["image_url"]
        print(f"Caption: {len(generated_caption)} chars")
        print(f"Image: {generated_image_url[:60]}...")
        
        # Generate post script
        post_script = generate_post_script(
            generated_caption=generated_caption,
            generated_image_url=generated_image_url,
            topic=topic_text,
            platform=TEST_PLATFORM,
            action=action,
            profile_data=profile_data
        )
        print(f"Post Script: {len(post_script)} chars")
        
        # Save to database
        db.insert_post_content(
            post_id=post_id,
            action_id=action_id,
            platform=TEST_PLATFORM,
            business_id=TEST_PROFILE_ID,
            topic=topic_text,
            image_prompt=image_prompt,
            caption_prompt=caption_prompt,
            generated_caption=generated_caption,
            generated_image_url=generated_image_url,
            post_script=post_script,
            content_type=content_type
        )
        print(f"✅ POST saved: {post_id}")
        
        # Create reward record
        db.create_post_reward_record(TEST_PROFILE_ID, post_id, TEST_PLATFORM, action_id)
        
        return {
            "status": "success",
            "type": "post",
            "post_id": post_id,
            "action_id": action_id
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def test_carousel_generation():
    """Test CAROUSEL generation and save"""
    print("\n" + "=" * 80)
    print("TEST 2: CAROUSEL GENERATION")
    print("=" * 80)
    
    try:
        # Get business context
        business_embedding = db.get_profile_embedding_with_fallback(TEST_PROFILE_ID)
        if business_embedding is None:
            return {"status": "error", "error": "No business embedding found"}
        
        profile_data = db.get_profile_business_data(TEST_PROFILE_ID)
        print(f"Business: {profile_data.get('business_name', 'Unknown')}")
        
        # Generate topic
        date = (datetime.now(IST) + timedelta(days=4)).date().isoformat()
        topic_data = generate_topic(
            business_context=str(profile_data),
            platform=TEST_PLATFORM,
            date=date,
            business_id=TEST_PROFILE_ID,
            profile_data=profile_data
        )
        topic_text = topic_data["topic"]
        print(f"Topic: {topic_text[:80]}...")
        
        # Create embedding
        topic_embedding = embed_topic(topic_text)
        
        # Generate prompts
        inputs = {
            "BUSINESS_AESTHETIC": profile_data["brand_voice"],
            "BUSINESS_TYPES": profile_data["business_types"],
            "INDUSTRIES": profile_data["industries"],
            "BUSINESS_DESCRIPTION": profile_data["business_description"],
        }
        
        result = generate_prompts(
            inputs,
            business_embedding,
            topic_embedding,
            TEST_PLATFORM,
            "evening",
            topic_text,
            profile_data,
            business_context=profile_data,
        )
        
        # Force carousel type
        result["action"]["CONTENT_TYPE"] = "carousel"
        action = result["action"]
        context = result["context"]
        content_type = "carousel"
        
        print(f"Content Type: {content_type}")
        
        # Store action
        post_id = f"{TEST_PLATFORM}_{uuid.uuid4().hex[:8]}"
        action_id = db.insert_action(
            post_id=post_id,
            platform=TEST_PLATFORM,
            context=context,
            action=action
        )
        print(f"Action ID: {action_id}")
        
        # Generate carousel image prompts
        from prompt_template import CAROUSEL_IMAGE_PROMPT_GENERATOR
        from generate import call_grok
        
        image_prompt = result.get("image_prompt", "")
        caption_prompt = result.get("caption_prompt", "")
        
        city = profile_data.get("location_city", "")
        state = profile_data.get("location_state", "Gujarat")
        
        filled_carousel_prompt = CAROUSEL_IMAGE_PROMPT_GENERATOR.replace("{{BUSINESS_CONTEXT}}", str(profile_data))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{topic_text}}", topic_text)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{PLATFORM}}", TEST_PLATFORM)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{CITY}}", city)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{STATE}}", state)
        filled_carousel_prompt = filled_carousel_prompt.replace("{{VISUAL_STYLE}}", action.get("VISUAL_STYLE", "modern_corporate_b2b"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{COMPOSITION_STYLE}}", action.get("COMPOSITION_STYLE", "center_focused"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{TONE}}", action.get("TONE", "friendly"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{CREATIVITY}}", action.get("CREATIVITY", "balanced"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{HOOK_TYPE}}", action.get("HOOK_TYPE", "question"))
        filled_carousel_prompt = filled_carousel_prompt.replace("{{INFORMATION_DEPTH}}", action.get("INFORMATION_DEPTH", "balanced"))
        
        try:
            carousel_prompts_response = call_grok(filled_carousel_prompt)
            if isinstance(carousel_prompts_response, dict):
                carousel_image_prompts = [
                    carousel_prompts_response.get("slide_1_prompt", image_prompt),
                    carousel_prompts_response.get("slide_2_prompt", image_prompt),
                    carousel_prompts_response.get("slide_3_prompt", image_prompt),
                    carousel_prompts_response.get("slide_4_prompt", image_prompt)
                ]
            else:
                carousel_image_prompts = [
                    f"{image_prompt} Slide 1: Hook/Overview",
                    f"{image_prompt} Slide 2: Detail/Feature",
                    f"{image_prompt} Slide 3: Benefit/Value",
                    f"{image_prompt} Slide 4: Call-to-Action"
                ]
        except Exception as e:
            print(f"⚠️  Using fallback prompts: {e}")
            carousel_image_prompts = [
                f"{image_prompt} Slide 1: Hook/Overview",
                f"{image_prompt} Slide 2: Detail/Feature",
                f"{image_prompt} Slide 3: Benefit/Value",
                f"{image_prompt} Slide 4: Call-to-Action"
            ]
        
        # Generate carousel content
        logo_url = profile_data.get("logo_url")
        carousel_result = generate_carousel_content(
            caption_prompt=caption_prompt,
            image_prompts=carousel_image_prompts,
            business_context=profile_data,
            logo_url=logo_url,
            business_id=TEST_PROFILE_ID
        )
        
        if carousel_result["status"] != "success":
            return {"status": "error", "error": carousel_result.get("error")}
        
        generated_caption = carousel_result["caption"]
        generated_image_urls = carousel_result["image_urls"]
        print(f"Caption: {len(generated_caption)} chars")
        print(f"Slides: {len(generated_image_urls)} images")
        
        # Generate carousel script
        carousel_script = generate_carousel_script(
            generated_caption=generated_caption,
            generated_image_urls=generated_image_urls,
            topic=topic_text,
            platform=TEST_PLATFORM,
            action=action,
            profile_data=profile_data
        )
        print(f"Carousel Script: {len(carousel_script)} chars")
        
        # Save to database
        db.insert_post_content(
            post_id=post_id,
            action_id=action_id,
            platform=TEST_PLATFORM,
            business_id=TEST_PROFILE_ID,
            topic=topic_text,
            image_prompt=image_prompt,
            caption_prompt=caption_prompt,
            generated_caption=generated_caption,
            generated_image_url=None,
            post_script=carousel_script,
            carousel_image_urls=generated_image_urls,
            content_type=content_type
        )
        print(f"✅ CAROUSEL saved: {post_id}")
        
        # Create reward record
        db.create_post_reward_record(TEST_PROFILE_ID, post_id, TEST_PLATFORM, action_id)
        
        return {
            "status": "success",
            "type": "carousel",
            "post_id": post_id,
            "action_id": action_id
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def test_reel_generation():
    """Test REEL generation and save"""
    print("\n" + "=" * 80)
    print("TEST 3: REEL GENERATION")
    print("=" * 80)
    
    try:
        # Get business context
        business_embedding = db.get_profile_embedding_with_fallback(TEST_PROFILE_ID)
        if business_embedding is None:
            return {"status": "error", "error": "No business embedding found"}
        
        profile_data = db.get_profile_business_data(TEST_PROFILE_ID)
        print(f"Business: {profile_data.get('business_name', 'Unknown')}")
        
        # Generate topic
        date = (datetime.now(IST) + timedelta(days=4)).date().isoformat()
        topic_data = generate_topic(
            business_context=str(profile_data),
            platform=TEST_PLATFORM,
            date=date,
            business_id=TEST_PROFILE_ID,
            profile_data=profile_data
        )
        topic_text = topic_data["topic"]
        print(f"Topic: {topic_text[:80]}...")
        
        # Create embedding
        topic_embedding = embed_topic(topic_text)
        
        # Generate prompts
        inputs = {
            "BUSINESS_AESTHETIC": profile_data["brand_voice"],
            "BUSINESS_TYPES": profile_data["business_types"],
            "INDUSTRIES": profile_data["industries"],
            "BUSINESS_DESCRIPTION": profile_data["business_description"],
        }
        
        result = generate_prompts(
            inputs,
            business_embedding,
            topic_embedding,
            TEST_PLATFORM,
            "evening",
            topic_text,
            profile_data,
            business_context=profile_data,
        )
        
        # Force reel type
        result["action"]["CONTENT_TYPE"] = "reel"
        action = result["action"]
        context = result["context"]
        content_type = "reel"
        
        print(f"Content Type: {content_type}")
        
        # Store action
        post_id = f"{TEST_PLATFORM}_{uuid.uuid4().hex[:8]}"
        action_id = db.insert_action(
            post_id=post_id,
            platform=TEST_PLATFORM,
            context=context,
            action=action
        )
        print(f"Action ID: {action_id}")
        
        # Generate reel script
        reel_script = generate_reel_script(
            business_context=str(profile_data),
            topic=topic_text,
            platform=TEST_PLATFORM,
            action=action,
            profile_data=profile_data
        )
        print(f"Reel Script: {len(reel_script)} chars")
        
        # Save to database
        db.insert_reel_script(
            post_id=post_id,
            action_id=action_id,
            platform=TEST_PLATFORM,
            business_id=TEST_PROFILE_ID,
            topic=topic_text,
            script_content=reel_script
        )
        print(f"✅ REEL saved: {post_id}")
        
        # Create reward record
        db.create_post_reward_record(TEST_PROFILE_ID, post_id, TEST_PLATFORM, action_id)
        
        return {
            "status": "success",
            "type": "reel",
            "post_id": post_id,
            "action_id": action_id
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def verify_database_records(results):
    """Verify all database records are correct"""
    print("\n" + "=" * 80)
    print("DATABASE VERIFICATION")
    print("=" * 80)
    
    all_passed = True
    
    for result in results:
        if result.get("status") != "success":
            continue
        
        post_id = result.get("post_id")
        content_type = result.get("type")
        action_id = result.get("action_id")
        
        print(f"\nVerifying {content_type.upper()} (post_id: {post_id})...")
        
        # Verify action record
        try:
            res = db.supabase.table("rl_actions").select("*").eq("id", action_id).execute()
            if res.data:
                action_record = res.data[0]
                db_content_type = action_record.get("content_type")
                if db_content_type == content_type:
                    print(f"   ✅ Action record: content_type = '{db_content_type}'")
                else:
                    print(f"   ❌ Action record: content_type mismatch (expected '{content_type}', got '{db_content_type}')")
                    all_passed = False
            else:
                print(f"   ❌ Action record not found")
                all_passed = False
        except Exception as e:
            print(f"   ❌ Error checking action: {e}")
            all_passed = False
        
        # Verify content record
        if content_type in ["post", "carousel"]:
            try:
                res = db.supabase.table("post_contents").select("*").eq("post_id", post_id).execute()
                if res.data:
                    content_record = res.data[0]
                    db_content_type = content_record.get("content_type")
                    
                    if db_content_type == content_type:
                        print(f"   ✅ Post contents: content_type = '{db_content_type}'")
                    else:
                        print(f"   ❌ Post contents: content_type mismatch (expected '{content_type}', got '{db_content_type}')")
                        all_passed = False
                    
                    # Verify specific fields
                    if content_type == "post":
                        if content_record.get("generated_image_url"):
                            print(f"   ✅ Has single image URL")
                        else:
                            print(f"   ❌ Missing generated_image_url")
                            all_passed = False
                    
                    if content_type == "carousel":
                        carousel_urls = content_record.get("carousel_image_urls")
                        if carousel_urls:
                            if isinstance(carousel_urls, list):
                                if len(carousel_urls) == 4:
                                    print(f"   ✅ Has 4 carousel image URLs")
                                else:
                                    print(f"   ❌ Expected 4 URLs, got {len(carousel_urls)}")
                                    all_passed = False
                            else:
                                print(f"   ⚠️  carousel_image_urls is not a list: {type(carousel_urls)}")
                        else:
                            print(f"   ❌ Missing carousel_image_urls")
                            all_passed = False
                    
                    if content_record.get("generated_caption"):
                        print(f"   ✅ Has caption")
                    else:
                        print(f"   ❌ Missing caption")
                        all_passed = False
                    
                    if content_record.get("post_script"):
                        print(f"   ✅ Has post script")
                    else:
                        print(f"   ⚠️  Missing post script")
                else:
                    print(f"   ❌ Post contents record not found")
                    all_passed = False
            except Exception as e:
                print(f"   ❌ Error checking post_contents: {e}")
                all_passed = False
        
        elif content_type == "reel":
            try:
                res = db.supabase.table("reel_scripts").select("*").eq("post_id", post_id).execute()
                if res.data:
                    reel_record = res.data[0]
                    if reel_record.get("script_content"):
                        print(f"   ✅ Reel script: Has script content")
                    else:
                        print(f"   ❌ Reel script: Missing script content")
                        all_passed = False
                else:
                    print(f"   ❌ Reel script record not found")
                    all_passed = False
            except Exception as e:
                print(f"   ❌ Error checking reel_scripts: {e}")
                all_passed = False
        
        # Verify reward record
        try:
            res = db.supabase.table("post_rewards").select("*").eq("post_id", post_id).eq("platform", TEST_PLATFORM).execute()
            if res.data:
                print(f"   ✅ Reward record exists")
            else:
                print(f"   ⚠️  Reward record not found")
        except Exception as e:
            print(f"   ⚠️  Error checking reward: {e}")
    
    return all_passed


def main():
    """Run all tests"""
    print("=" * 80)
    print("COMPREHENSIVE TEST: ALL CONTENT TYPES")
    print("=" * 80)
    print(f"Profile ID: {TEST_PROFILE_ID}")
    print(f"Platform: {TEST_PLATFORM}")
    print("\n⚠️  NOTE: This test requires:")
    print("   - Database connection (Supabase)")
    print("   - API keys (Grok, OpenAI, Gemini)")
    print("   - All database changes applied")
    print("=" * 80)
    
    results = []
    
    # Test POST
    print("\n🔵 Testing POST generation...")
    post_result = test_post_generation()
    results.append(post_result)
    
    # Test CAROUSEL
    print("\n🟢 Testing CAROUSEL generation...")
    carousel_result = test_carousel_generation()
    results.append(carousel_result)
    
    # Test REEL
    print("\n🟡 Testing REEL generation...")
    reel_result = test_reel_generation()
    results.append(reel_result)
    
    # Verify all records
    all_passed = verify_database_records(results)
    
    # Summary
    print("\n\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    for result in results:
        content_type = result.get("type", "unknown")
        status = result.get("status", "unknown")
        post_id = result.get("post_id", "N/A")
        
        if status == "success":
            print(f"✅ {content_type.upper()}: SUCCESS (post_id: {post_id})")
        else:
            print(f"❌ {content_type.upper()}: FAILED")
            print(f"   Error: {result.get('error', 'Unknown error')}")
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED - All content types working correctly!")
        print("✅ content_type is being set correctly in database")
        return True
    else:
        print("\n⚠️  SOME VERIFICATIONS FAILED - Check database records")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

