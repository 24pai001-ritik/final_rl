"""
job_queue.py
-------------
Cron-safe job poller for reward calculation + RL updates.
Runs once, processes all due jobs, then exits.
"""

import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pytz
import subprocess
import sys

import db
import rl_agent

# ---------------- CONFIG ----------------

IST = pytz.timezone("Asia/Kolkata")
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("job_queue")

# ---------------- JOB FETCHING ----------------

def fetch_due_jobs():
    """
    Fetch jobs that are ready to run.
    """
    result = (
        db.supabase
        .table("jobs")
        .select("*")
        .eq("status", "queued")
        .lte("run_at", datetime.now(IST).isoformat())
        .limit(20)
        .execute()
    )
    return result.data or []

def mark_job_running(job_id: str):
    db.supabase.table("jobs").update({
        "status": "running",
        "started_at": datetime.now(IST).isoformat()
    }).eq("job_id", job_id).execute()

def mark_job_completed(job_id: str, result: Dict[str, Any]):
    db.supabase.table("jobs").update({
        "status": "completed",
        "completed_at": datetime.now(IST).isoformat(),
        "result": result
    }).eq("job_id", job_id).execute()

def mark_job_failed(job_id: str, error: str, retry_count: int):
    new_status = "failed" if retry_count + 1 >= MAX_RETRIES else "queued"

    db.supabase.table("jobs").update({
        "status": new_status,
        "retry_count": retry_count + 1,
        "last_error": error
    }).eq("job_id", job_id).execute()

# ---------------- JOB PROCESSORS ----------------

async def process_reward_calculation(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job["payload"]
    profile_id = payload["profile_id"]
    post_id = payload["post_id"]
    platform = payload["platform"]

    logger.info(f"Reward calc → {post_id} ({platform})")

    result = db.fetch_or_calculate_reward(profile_id, post_id, platform)

    if result.get("status") == "calculated":
        # Queue RL update job
        db.supabase.table("jobs").insert({
            "job_id": f"rl_{post_id}_{int(time.time())}",
            "job_type": "rl_update",
            "payload": {
                "profile_id": profile_id,
                "post_id": post_id,
                "platform": platform,
                "reward_value": result["reward"]
            },
            "status": "queued",
            "run_at": datetime.now(IST).isoformat(),
            "retry_count": 0,
            "created_at": datetime.now(IST).isoformat()
        }).execute()

    return result

async def process_rl_update(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job["payload"]

    profile_id = payload["profile_id"]
    post_id = payload["post_id"]
    platform = payload["platform"]
    reward_value = payload["reward_value"]

    logger.info(f"RL update → {post_id} (reward={reward_value:.4f})")

    action_data = get_action_and_context_from_db(post_id, platform, profile_id)
    if not action_data:
        return {"status": "skipped", "reason": "missing_action_context"}

    baseline = db.update_baseline_mathematical(
        platform,
        reward_value,
        beta=0.1
    )

    rl_agent.update_rl(
        context=action_data["context"],
        action=action_data["action"],
        ctx_vec=action_data["ctx_vec"],
        reward=reward_value,
        baseline=baseline
    )

    return {"status": "completed", "baseline": baseline}

# ---------------- CONTEXT FETCH ----------------

def get_action_and_context_from_db(
    post_id: str,
    platform: str,
    profile_id: str
) -> Optional[Dict[str, Any]]:

    action_res = (
        db.supabase
        .table("rl_actions")
        .select("*")
        .eq("post_id", post_id)
        .eq("platform", platform)
        .execute()
    )

    if not action_res.data:
        return None

    row = action_res.data[0]

    action = {
        "HOOK_TYPE": row.get("hook_type"),
        "LENGTH": row.get("hook_length"),
        "TONE": row.get("tone"),
        "CREATIVITY": row.get("creativity"),
        "TEXT_IN_IMAGE": row.get("text_in_image"),
        "VISUAL_STYLE": row.get("visual_style"),
        "CONTENT_TYPE": row.get("content_type"),  # New: post or reel
        "INFORMATION_DEPTH": row.get("information_depth"),
        "COMPOSITION_STYLE": row.get("composition_style")
    }

    business_embedding = db.get_profile_embedding_with_fallback(profile_id)
    topic = row.get("topic", "")
    topic_embedding = db.embed_topic(topic) if topic else None

    context = {
        "platform": platform,
        "time_bucket": row.get("time_bucket"),
        "day_of_week": row.get("day_of_week"),
        "business_embedding": business_embedding,
        "topic_embedding": topic_embedding or business_embedding
    }

    from rl_agent import build_context_vector
    ctx_vec = build_context_vector(context)

    return {
        "action": action,
        "context": context,
        "ctx_vec": ctx_vec
    }

# ---------------- MAIN CRON ENTRY ----------------

def run_once():
    jobs = fetch_due_jobs()

    if not jobs:
        logger.info("No due jobs found")
        return

    logger.info(f"Processing {len(jobs)} jobs")

    for job in jobs:
        job_id = job["job_id"]
        job_type = job["job_type"]
        retry_count = job.get("retry_count", 0)

        try:
            mark_job_running(job_id)

            if job_type == "reward_calculation":
                result = asyncio.run(process_reward_calculation(job))

            elif job_type == "rl_update":
                result = asyncio.run(process_rl_update(job))

            elif job_type == "content_generation":
                logger.info("Triggering main.py for content generation")

                proc = subprocess.run(
                    [sys.executable, "main.py"],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )

                logger.info("main.py stdout:\n" + (proc.stdout or ""))

                if proc.returncode != 0:
                    raise RuntimeError(
                        f"main.py failed:\n{proc.stderr}"
                    )

                result = {"status": "completed"}

            else:
                raise ValueError(f"Unknown job type: {job_type}")


            mark_job_completed(job_id, result)

        except Exception as e:
            logger.exception(f"Job failed: {job_id}")
            mark_job_failed(job_id, str(e), retry_count)

# ---------------- ENTRYPOINT ----------------

if __name__ == "__main__":
    logger.info("Cron job_queue started")
    run_once()
    logger.info("Cron job_queue finished")
