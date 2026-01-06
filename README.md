# Emily RL - Social Media Content Generation with Reinforcement Learning

An AI-powered social media content generation system that uses reinforcement learning to optimize content creation for different platforms and audiences.

## Features

- **Reinforcement Learning Agent**: Learns optimal content strategies based on engagement metrics
- **Multi-Platform Support**: Instagram, Twitter/X, LinkedIn, Facebook
- **Trend-Aware Generation**: Creates trendy content based on current social media trends
- **Business Profile Adaptation**: Tailors content to specific business types and industries
- **Automated Scheduling & Publishing**: Cron-based system for scheduling and publishing posts
- **Live Social Media Integration**: Real API integration with all major platforms
- **Production-Ready**: Rate limiting, error handling, and retry logic
- **Real-time Optimization**: Continuously improves content performance

## Architecture

### Core Components

- `main.py`: Main orchestrator for the RL learning cycle
- `rl_agent.py`: Reinforcement learning agent with preference learning
- `generate.py`: Prompt generation with trendy/standard modes
- `db.py`: Supabase database operations

### Post Lifecycle

1. **Generate Content**: RL agent selects creative parameters and generates content
2. **Schedule Posts**: Cron job runs at 5 AM IST, changes status from 'generated' to 'scheduled'
3. **Publish Content**: Posts are published at their scheduled time, status changes to 'posted'
4. **Collect Metrics**: Gather engagement data from social media platforms
5. **Calculate Reward**: Evaluate performance based on platform-specific metrics
6. **Update Agent**: RL agent learns from feedback to improve future content

### Automated Scheduling System

The system includes automated cron jobs for content scheduling and publishing:

- **Scheduling Job**: Runs at 5 AM IST daily, finds posts with status 'generated' and schedules them
- **Publishing Job**: Runs every 15 minutes, publishes scheduled posts at their designated time
- **Status Tracking**: Posts progress through states: `generated` → `scheduled` → `posted` → reward calculation

## Setup

### Prerequisites

- Python 3.8+
- Supabase account and project
- Social media API access (for production)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/24pai001-ritik/emily_rl.git
cd emily_rl
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp env.example .env
# Edit .env with your Supabase credentials
```

4. Configure your Supabase database with the required tables (see Database Schema section below).

5. Test the live posting system:
```bash
python test_live_posting.py
```

6. Set up automated scheduling:
```bash
# Linux/macOS
./setup_cron.sh

# Windows
setup_cron.bat
```

This will set up:
- **Scheduling job**: Runs at 5 AM IST daily to schedule generated posts
- **Publishing job**: Runs every 15 minutes to publish scheduled content

## 🚀 Going Live - Production Deployment

### Prerequisites
- ✅ Valid social media API credentials in `.env`
- ✅ Active platform connections in `platform_connections` table
- ✅ Generated content in `post_contents` table
- ✅ Cron jobs configured

### Test Live Posting
```bash
# Test credentials
python test_live_posting.py

# Test scheduling (safe - doesn't post)
python post_scheduler.py schedule

# Test actual posting (will post live!)
python post_scheduler.py post
```

### Production Monitoring
- **Logs**: Check `logs/scheduler.log` and `logs/publisher.log`
- **Database**: Monitor `post_contents` table for status changes
- **Rate Limits**: System includes automatic retry and rate limit handling

### Supported Platforms
- **Instagram**: Image posts via Graph API
- **Facebook**: Text and image posts via Graph API
- **LinkedIn**: Text and image posts via REST API
- **Twitter/X**: Text posts via API v2

### Security Notes
- Access tokens are stored encrypted in the database
- API calls include proper error handling and retry logic
- Rate limiting is handled automatically
- Failed posts are marked with `failed` status for manual review

## Database Schema

Create these tables in your Supabase database:

### Required Tables

#### `rl_preferences`
```sql
CREATE TABLE rl_preferences (
  id SERIAL PRIMARY KEY,
  platform TEXT NOT NULL,
  time_bucket TEXT NOT NULL,
  day_of_week INTEGER NOT NULL,
  dimension TEXT NOT NULL,
  action_value TEXT NOT NULL,
  preference_score FLOAT DEFAULT 0.0,
  num_samples INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(platform, time_bucket, day_of_week, dimension, action_value)
);
```

#### `post_contents`
```sql
CREATE TABLE post_contents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id TEXT NOT NULL,
  action_id UUID REFERENCES rl_actions(id) ON DELETE CASCADE,
  platform TEXT NOT NULL,
  business_id UUID,
  topic TEXT,
  post_type TEXT,
  business_context TEXT,
  business_aesthetic TEXT,
  image_prompt TEXT,
  caption_prompt TEXT,
  generated_caption TEXT,
  generated_image_url TEXT,
  status TEXT DEFAULT 'generated', -- generated | scheduled | posted | failed | deleted
  media_id TEXT, -- Social media platform's post/media ID when published
  post_date DATE, -- Scheduled date for posting
  post_time TIME, -- Scheduled time for posting
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### `rl_actions`
```sql
CREATE TABLE rl_actions (
  id SERIAL PRIMARY KEY,
  post_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  time_bucket TEXT,
  day_of_week INTEGER,
  action JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### `post_snapshots`
```sql
CREATE TABLE post_snapshots (
  id SERIAL PRIMARY KEY,
  post_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  saves INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  retweets INTEGER DEFAULT 0,
  reactions INTEGER DEFAULT 0,
  followers INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### `rl_rewards`
```sql
CREATE TABLE rl_rewards (
  id SERIAL PRIMARY KEY,
  post_id TEXT NOT NULL,
  reward FLOAT,
  baseline FLOAT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### `rl_baselines`
```sql
CREATE TABLE rl_baselines (
  id SERIAL PRIMARY KEY,
  platform TEXT NOT NULL UNIQUE,
  value FLOAT DEFAULT 0.0,
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### `profiles`
```sql
CREATE TABLE profiles (
  id TEXT PRIMARY KEY,
  profile_embedding JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

4. Configure your Supabase database with the required tables.

## Usage

### Content Generation

Run a single content generation cycle:

```bash
python main.py
```

### Manual Scheduling & Publishing

You can also run the scheduling and publishing jobs manually:

```bash
# Schedule generated posts (changes status from 'generated' to 'scheduled')
python post_scheduler.py schedule

# Publish scheduled posts (changes status from 'scheduled' to 'posted')
python post_scheduler.py post
```

### Automated Scheduling

The system includes automated cron jobs that run:

- **Scheduling job**: At 5 AM IST daily
- **Publishing job**: Every 15 minutes

Set up automated scheduling using the setup scripts:
- Linux/macOS: `./setup_cron.sh`
- Windows: `setup_cron.bat`

## Database Schema

Required Supabase tables:
- `rl_preferences`: Stores RL agent preferences
- `post_contents`: Content metadata and status
- `rl_actions`: RL agent action history
- `post_snapshots`: Engagement metrics snapshots
- `rl_rewards`: Reward calculation history
- `rl_baselines`: Performance baselines
- `profiles`: Business profile embeddings

## Deployment Considerations

⚠️ **Important**: This codebase currently uses simulated metrics for development. For production deployment:

1. Replace `simulate_platform_metrics()` with real API calls
2. Implement proper async metric collection (posts need time to accumulate engagement)
3. Add rate limiting and error handling for social media APIs
4. Set up proper monitoring and logging

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
