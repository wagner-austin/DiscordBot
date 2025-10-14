# Discord Club Bot - Complete Specification Document

## 1. DATABASE SCHEMAS

### 1.1 PostgreSQL Tables

#### Members Table
```sql
CREATE TABLE members (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(32) NOT NULL,
    discriminator VARCHAR(4),
    display_name VARCHAR(32),
    avatar_url TEXT,
    joined_server_at TIMESTAMPTZ NOT NULL,
    registered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    is_bot BOOLEAN DEFAULT FALSE,
    total_points INTEGER DEFAULT 0,
    CONSTRAINT unique_discord_id UNIQUE (discord_id)
);

CREATE INDEX idx_discord_id ON members(discord_id);
CREATE INDEX idx_total_points ON members(total_points DESC);
```

**Field Specifications:**
- `discord_id`: Discord's unique user ID (BIGINT to handle 18-digit snowflakes)
- `username`: Current Discord username (max 32 chars per Discord spec)
- `discriminator`: Legacy 4-digit discriminator (nullable for new username system)
- `display_name`: Server nickname or global display name
- `avatar_url`: Full URL to user's avatar image
- `joined_server_at`: Timestamp when user joined the Discord server
- `registered_at`: Timestamp when bot registered the user
- `is_bot`: Flag to exclude bot accounts from leaderboards
- `total_points`: Lifetime cumulative points

#### Quarters Table
```sql
CREATE TABLE quarters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    CONSTRAINT valid_date_range CHECK (end_date > start_date)
);

-- Enforce only one active quarter at a time via partial unique index
CREATE UNIQUE INDEX one_active_quarter ON quarters(is_active) WHERE is_active = TRUE;
```

**Pre-populated Data:**
```sql
INSERT INTO quarters (name, start_date, end_date, is_active) VALUES
('Fall 2025', '2025-09-22', '2025-12-20', TRUE),
('Winter 2026', '2026-01-05', '2026-03-20', FALSE),
('Spring 2026', '2026-03-30', '2026-06-15', FALSE);
```

**Field Specifications:**
- `name`: Human-readable quarter name (e.g., "Fall 2025")
- `start_date`: First day of quarter
- `end_date`: Last day of quarter
- `is_active`: Only ONE quarter can be active at a time (enforced by constraint)

#### Quarter Points Table
```sql
CREATE TABLE quarter_points (
    id SERIAL PRIMARY KEY,
    member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
    quarter_id INTEGER REFERENCES quarters(id) ON DELETE CASCADE,
    points INTEGER DEFAULT 0,
    CONSTRAINT unique_member_quarter UNIQUE (member_id, quarter_id)
);

CREATE INDEX idx_quarter_leaderboard ON quarter_points(quarter_id, points DESC);
```

**Field Specifications:**
- `member_id`: Foreign key to members table
- `quarter_id`: Foreign key to quarters table
- `points`: Points earned in this specific quarter
- Unique constraint ensures one record per member per quarter

#### Tasks Table
```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    point_value INTEGER NOT NULL,
    deadline TIMESTAMPTZ,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    CONSTRAINT positive_points CHECK (point_value > 0)
);

CREATE INDEX idx_active_tasks ON tasks(is_active, deadline);
```

**Field Specifications:**
- `title`: Task title (max 200 chars)
- `description`: Full task description (unlimited length)
- `point_value`: Points awarded upon completion (must be > 0)
- `deadline`: Optional deadline (NULL = no deadline)
- `created_by`: Discord ID of officer who created task
- `created_at`: Timestamp of task creation
- `is_active`: FALSE = task is archived/deleted

#### Task Submissions Table
```sql
CREATE TABLE task_submissions (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
    submission_url TEXT,
    submission_file_url TEXT,
    submission_notes TEXT,
    submitted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    reviewed_by BIGINT,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT submission_content CHECK (
        submission_url IS NOT NULL OR submission_file_url IS NOT NULL
    )
);

CREATE INDEX idx_pending_submissions ON task_submissions(status, submitted_at)
    WHERE status = 'pending';
CREATE INDEX idx_member_submissions ON task_submissions(member_id, status);
```

**Field Specifications:**
- `task_id`: Foreign key to tasks table
- `member_id`: Foreign key to members table (who submitted)
- `submission_url`: Google Drive/external URL (must have http:// or https://)
- `submission_file_url`: Discord CDN URL if file uploaded to Discord
- `submission_notes`: Optional text from submitter
- `submitted_at`: Timestamp of submission
- `status`: One of: 'pending', 'approved', 'rejected'
- `reviewed_by`: Discord ID of officer who reviewed
- `reviewed_at`: Timestamp of review
- `review_notes`: Optional feedback from reviewer
- Constraint ensures at least one URL is provided

#### Events Table
```sql
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    event_date TIMESTAMPTZ NOT NULL,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    check_in_code VARCHAR(50) UNIQUE
);

CREATE INDEX idx_event_date ON events(event_date DESC);
```

**Field Specifications:**
- `name`: Event name
- `description`: Optional event details
- `event_date`: When the event occurs
- `created_by`: Discord ID of officer who created event
- `check_in_code`: Unique code for QR-based check-ins (optional)

#### Event Attendance Table
```sql
CREATE TABLE event_attendance (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
    member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
    checked_in_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_attendance UNIQUE (event_id, member_id)
);

CREATE INDEX idx_member_attendance ON event_attendance(member_id);
```

**Field Specifications:**
- `event_id`: Foreign key to events table
- `member_id`: Foreign key to members table
- `checked_in_at`: When member checked in
- Unique constraint prevents duplicate check-ins

#### Board Members Table
```sql
CREATE TABLE board_members (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT UNIQUE NOT NULL,
    role_title VARCHAR(100) NOT NULL,
    display_order INTEGER DEFAULT 0,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_display_order ON board_members(display_order);
```

#### Points Ledger Table
```sql
CREATE TABLE points_ledger (
    id SERIAL PRIMARY KEY,
    member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
    delta INTEGER NOT NULL,
    reason TEXT,
    ref_type VARCHAR(32), -- e.g., 'submission'
    ref_id INTEGER,       -- e.g., task_submissions.id
    quarter_id INTEGER REFERENCES quarters(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ledger_member_time ON points_ledger(member_id, created_at DESC);
CREATE INDEX idx_ledger_quarter ON points_ledger(quarter_id, created_at DESC);
```

**Notes:**
- Immutable audit trail; corrections use new negative `delta` entries.
- Enables recomputation of totals and debugging without data loss.

**Field Specifications:**
- `discord_id`: Discord ID of board member
- `role_title`: Their role (e.g., "President", "VP", "Advocacy Director")
- `display_order`: Sort order for `/board` command (0 = first)
- `added_at`: When they were added to board

### 1.2 Redis (Upstash) Data Structures

#### Leaderboard (Sorted Set)
```
Key: leaderboard:lifetime
Type: SORTED SET
Members: discord_id (string)
Scores: total_points (integer)
```

**Operations:**
- Add/Update: `ZADD leaderboard:lifetime {points} {discord_id}`
- Get Top N: `ZREVRANGE leaderboard:lifetime 0 {n-1} WITHSCORES`
- Get User Rank: `ZREVRANK leaderboard:lifetime {discord_id}`
- Get User Score: `ZSCORE leaderboard:lifetime {discord_id}`

#### Quarter Leaderboard (Sorted Set per Quarter)
```
Key: leaderboard:quarter:{quarter_id}
Type: SORTED SET
Members: discord_id (string)
Scores: quarter_points (integer)
```

**Operations:**
- Same as lifetime, but with quarter-specific key

#### Cache: Member Data (Hash)
```
Key: cache:member:{discord_id}
Type: HASH
Fields: username, display_name, total_points, avatar_url
TTL: 300 seconds (5 minutes)
```

#### Rate Limiting (String)
```
Key: ratelimit:{command}:{discord_id}
Type: STRING
Value: timestamp
TTL: Command-specific (30-300 seconds)
```

---

## 2. SLASH COMMANDS SPECIFICATION

### 2.1 `/qrcode`

**Description:** Generate a QR code from a URL

**Parameters (LVP):**
| Name | Type | Required | Description | Validation |
|------|------|----------|-------------|------------|
| url | String | Yes | Target URL for QR code | Friendly handling: accepts bare hostnames (e.g., `example.com`) and normalizes to `https://...`; only http/https schemes are allowed. |

Note: Styling options (error_correction, box_size, border, fill_color, back_color) are configured via environment defaults in this LVP and are not exposed as slash parameters. They can be promoted to optional parameters in a future iteration.

**Permissions:** All members

**Response:**
- Defers with an ephemeral acknowledgement to avoid timeouts on slow renders
- Ephemeral message with QR code PNG attachment
- Includes a clickable hyperlink to the normalized destination URL for confirmation

**Error Handling:**
- Invalid URL: clear validation messages (e.g., "Please provide a valid URL", "URL scheme must be http or https", or "Please provide a valid host (e.g., example.com)")
- Invalid color (when exposed): "Invalid color format. Use hex codes (e.g., #FF0000) or color names"
- Rate limit: "Please wait {seconds} seconds before generating another QR code"

**Rate Limit:** Default 1 QR code per user per second (configurable via `QRCODE_RATE_LIMIT` and `QRCODE_RATE_WINDOW_SECONDS`).

**Implementation Notes:**
- Validate and normalize the URL before applying rate limiting to ensure clear user errors
- Use `ctx.defer(ephemeral=True)` prior to generation to guarantee a quick acknowledgement
- Use `qrcode[pil]` to generate an in-memory PNG; send as Discord file attachment
- Include destination link in response; filename pattern: `qrcode_{timestamp}.png`

---

### 2.2 `/task`

**Parent Command (Admin Only)**

#### Subcommand: `/task create`

**Description:** Create a new task for members to complete

**Parameters:**
| Name | Type | Required | Description | Validation |
|------|------|----------|-------------|------------|
| title | String | Yes | Task title | Max 200 characters |
| description | String | Yes | Task description | Max 2000 characters |
| points | Integer | Yes | Points awarded | Range: 1-1000 |
| deadline | String | No | Deadline (YYYY-MM-DD HH:MM) | Valid future datetime |

**Permissions:** Officers role only

**Response:** Embed showing created task with ID

**Error Handling:**
- Invalid date format: "Use format: YYYY-MM-DD HH:MM (e.g., 2025-12-31 23:59)"
- Past deadline: "Deadline must be in the future"
- Invalid points: "Points must be between 1 and 1000"

#### Subcommand: `/task delete`

**Description:** Deactivate a task (soft delete)

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| task_id | Integer | Yes | ID of task to delete |

**Permissions:** Officers role only

**Response:** Confirmation message

#### Subcommand: `/task edit`

**Description:** Edit an existing task

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| task_id | Integer | Yes | ID of task to edit |
| title | String | No | New title |
| description | String | No | New description |
| points | Integer | No | New point value |
| deadline | String | No | New deadline |

**Permissions:** Officers role only

**Response:** Embed showing updated task

---

### 2.3 `/task list`

**Description:** View all active tasks

**Parameters:** None

**Permissions:** All members

**Response:** Paginated embed showing:
- Task ID
- Title
- Points
- Deadline (if set)
- "No deadline" if not set

**Display Format:**
```
Task #1 | 50 points
Title: Attend General Meeting
Deadline: 2025-12-15 18:00
Description: Attend the general meeting and participate

Task #2 | 100 points
Title: Complete Python Workshop
No deadline
Description: Complete all modules in the Python workshop
```

**Pagination:** 5 tasks per page with Discord UI buttons (discord.ui.Button)

---

### 2.4 `/task submit`

**Description:** Submit a completed task for review

**Parameters:**
| Name | Type | Required | Description | Validation |
|------|------|----------|-------------|------------|
| task_id | Integer | Yes | Task ID from `/task list` | Must be active task |
| url | String | No | Google Drive or external URL | Must start with http:// or https:// |
| attachment | File | No | PNG, JPG, or PDF file | Max 8MB (Discord limit) |
| notes | String | No | Additional notes | Max 500 characters |

**Permissions:** All members

**Validation:**
- Must provide either `url` OR `attachment` (or both)
- Cannot submit same task twice while pending

**Response:** Confirmation message with submission ID

**Error Handling:**
- No submission: "Please provide either a URL or file attachment"
- Duplicate submission: "You already have a pending submission for this task"
- Invalid task: "Task not found or is no longer active"

---

### 2.5 `/task review`

**Parent Command (Admin Only)**

#### Subcommand: `/task review pending`

**Description:** View queue of pending task submissions

**Parameters:** None

**Permissions:** Officers role only

**Response:** Paginated embed showing:
- Submission ID
- Task title
- Submitter username
- Submitted at
- Submission links

**Display Format:**
```
Submission #42
Task: Attend General Meeting (50 points)
Submitted by: @username
Submitted: 2025-12-01 15:30

URL: https://drive.google.com/...
File: [Click to view]
Notes: Attended full meeting

[Approve] [Reject]
```

**Interaction:** Buttons for approve/reject with modal for feedback

#### Subcommand: `/task review approve`

**Description:** Approve a task submission

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| submission_id | Integer | Yes | Submission ID to approve |
| feedback | String | No | Optional feedback for submitter |

**Permissions:** Officers role only

**Actions Performed:**
1. Update submission status to 'approved'
2. Insert points_ledger entry (delta = task points, ref_type = 'submission', ref_id = submission_id, quarter = current active)
3. Add points to member's total_points
4. Add points to current quarter's points
5. Update Redis leaderboards
6. DM submitter with approval notification

**Response:** Confirmation message

#### Subcommand: `/task review reject`

**Description:** Reject a task submission

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| submission_id | Integer | Yes | Submission ID to reject |
| reason | String | Yes | Reason for rejection |

**Permissions:** Officers role only

**Actions Performed:**
1. Update submission status to 'rejected'
2. DM submitter with rejection notice and reason

**Response:** Confirmation message

---

### 2.6 `/leaderboard`

**Description:** View point rankings

**Parameters:**
| Name | Type | Required | Description | Validation |
|------|------|----------|-------------|------------|
| timeframe | String | No | Lifetime or quarter | Choices: "lifetime" (default), "current_quarter" |
| top_n | Integer | No | Number of users to show | Range: 5-50, default: 10 |

**Permissions:** All members

**Response:** Embed showing:
- Rank
- Username
- Points
- User's own rank (if not in top N)

**Display Format:**
```
Lifetime Leaderboard

1. @alice - 1,250 points
2. @bob - 980 points
3. @charlie - 875 points
...

Your rank: #15 (340 points)
```

**Data Source:**
- Fetched from Redis sorted sets for performance
- Falls back to PostgreSQL if Redis unavailable

---

### 2.7 `/profile`

**Description:** View your own profile statistics

**Parameters:** None

**Permissions:** All members

**Response:** Embed showing:
- Username and avatar
- Member since date
- Total lifetime points
- Current quarter points
- Lifetime rank
- Current quarter rank
- Tasks completed (count)
- Events attended (count)

**Display Format:**
```
Profile: @username

Member Since: September 22, 2025
Total Points: 340
Current Quarter (Fall 2025): 340 points

Rankings:
Lifetime: #15 of 200
Fall 2025: #12 of 200

Activity:
Tasks Completed: 7
Events Attended: 3
```

---

### 2.8 `/board`

**Description:** View club board members and their roles

**Parameters:** None

**Permissions:** All members

**Response:** Embed showing:
- Board member username
- Role title
- Ordered by display_order

**Display Format:**
```
Club Board Members

President: @alice
Vice President: @bob
Advocacy Director: @charlie
Policy Director: @diana
Member at Large: @eve
```

---

## 3. QR CODE SPECIFICATIONS

### 3.1 Library
- **Primary:** `qrcode[pil]` version 7.4+
- **Backup:** None (single dependency approach)

### 3.2 Output Format
- **File Type:** PNG
- **Color Mode:** RGB
- **Default Size:** 300x300 pixels (with default settings)
- **DPI:** 72 (standard screen resolution)

### 3.3 Error Correction Levels
| Level | Recovery % | Use Case |
|-------|-----------|----------|
| L | 7% | Clean displays, large QR codes |
| M | 15% | General use (default) |
| Q | 25% | Moderate damage expected |
| H | 30% | Heavy damage or small size |

### 3.4 Configuration Parameters
```python
qr = qrcode.QRCode(
    version=None,  # Auto-detect size
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=10,  # pixels per box
    border=4,     # boxes of border
)
```

### 3.5 Branding Support (Future Enhancement Placeholder)
- Logo embedding in center (PIL image overlay)
- Requires error correction Q or H
- Logo size: max 20% of QR code area
- Logo must have white border padding

---

## 4. MEMBER REGISTRATION WORKFLOW

### 4.1 Trigger Event
- **Event:** Discord `on_member_join` event
- **Timing:** Immediate (async handler)

### 4.2 Registration Process
```
1. User joins Discord server
2. Bot receives on_member_join event
3. Check if discord_id already exists in database
   - If exists: Update username/avatar (in case of change)
   - If not exists: Create new record
4. Extract all available Discord data:
   - discord_id (user.id)
   - username (user.name)
   - discriminator (user.discriminator)
   - display_name (user.display_name or member.nick)
   - avatar_url (user.avatar.url if user.avatar else user.default_avatar.url)
   - joined_server_at (member.joined_at)
   - is_bot (user.bot)
5. Insert into members table
6. Initialize Redis leaderboard entry (0 points)
7. Create quarter_points entry for current active quarter
8. Log registration (for audit trail)
9. NO message sent to user (silent registration)
```

### 4.3 Data Update Policy
- **On Member Update:** Update username, discriminator, display_name, avatar_url
- **Frequency:** Real-time via `on_member_update` event
- **No User Input:** Fully automated, no forms or commands required

### 4.4 Edge Cases
- **Bot Accounts:** Registered but excluded from leaderboards via `is_bot` flag
- **Rejoining Members:** Existing record updated, points preserved
- **Bulk Registration:** Process in batches if bot added to existing server

---

## 5. TASK/QUEST SYSTEM MECHANICS

### 5.1 Task Lifecycle
```
1. CREATION (Officer only)
   └→ Task created with: title, description, points, optional deadline

2. ACTIVE STATE
   └→ Visible in /task list
   └→ Members can submit completions

3. SUBMISSION (Member)
   └→ Member provides: URL and/or file, optional notes
   └→ Status: pending

4. REVIEW QUEUE (Officer only)
   └→ Submission appears in /task review pending
   └→ Officer chooses: approve or reject

5a. APPROVED
   └→ Points added to member (lifetime + current quarter)
   └→ Redis leaderboards updated
   └→ Member notified via DM

5b. REJECTED
   └→ No points awarded
   └→ Member notified via DM with reason
   └→ Member can resubmit (new submission)

6. ARCHIVED (Officer only)
   └→ Task marked inactive (is_active = FALSE)
   └→ No longer in /task list
   └→ Historical submissions preserved
```

### 5.2 Point System Rules

#### Point Allocation
- **Task Points:** Dynamic (set per task, 1-1000 range)
- **Award Timing:** Immediately upon approval
- **Retroactive Changes:** NOT allowed (no editing points after award)

#### Point Tracking
- **Lifetime Points:** Sum of all approved task submissions ever
- **Quarter Points:** Sum of approved submissions within that quarter
- **Quarter Determination:** Based on `submitted_at` timestamp
- **Quarter Boundaries:** Inclusive of start_date, exclusive of end_date

#### Point Display
- **Leaderboards:**
  - Lifetime: All-time cumulative points
  - Quarter: Points earned during specific quarter
- **Profile:** Shows both lifetime and current quarter

#### Point Persistence
- **Permanent:** Points never expire or decay
- **Immutable:** Once awarded, cannot be revoked; corrections are applied via new negative entries in `points_ledger` (no deletes)
- **Member Deletion:** Points removed when member deleted (CASCADE)

### 5.3 Submission Validation

#### File Upload Rules
- **Allowed Types:** PNG, JPG, JPEG, PDF, GIF, MP4 (Discord supported)
- **Max Size:** 8 MB (Discord standard limit)
- **Storage:** Discord CDN (file uploaded as message attachment)

#### URL Submission Rules
- **Protocol:** Must start with `http://` or `https://`
- **Validation:** Regex pattern: `^https?://`
- **Length:** Max 2000 characters
- **No Verification:** Bot does not verify URL is accessible

#### Duplicate Prevention
- **Rule:** One pending submission per member per task
- **Allowed:** Multiple approved submissions (same task)
- **Allowed:** Resubmission after rejection

### 5.4 Review Queue Management

#### Queue Order
- **Sort:** Oldest first (submitted_at ASC)
- **Filter:** Only 'pending' status shown
- **Display:** 5 submissions per page

#### Officer Actions
- **Approve:**
  - Add points to member
  - Update Redis
  - Send DM: "Your submission for [Task Title] has been approved! You earned {points} points."
- **Reject:**
  - No points awarded
  - Send DM: "Your submission for [Task Title] was not approved. Reason: {reason}"
  - Member can submit again

#### Notification System
- **Method:** Discord DM (direct message)
- **Fallback:** If DM fails (user has DMs disabled), log warning but continue
- **Content:** Task name, decision, points (if approved), reason (if rejected)

---

## 6. QUARTER SYSTEM

### 6.1 Quarter Management

#### Initial Quarters
```sql
Fall 2025: 2025-09-22 to 2025-12-20 (ACTIVE)
Winter 2026: 2026-01-05 to 2026-03-20
Spring 2026: 2026-03-30 to 2026-06-15
```

#### Active Quarter Rules
- **Only One Active:** Database constraint enforces single active quarter
- **Manual Activation:** Officer uses admin command to switch quarters
- **Point Assignment:** New points go to currently active quarter

#### Future Quarter Addition
- **Method:** Direct database INSERT (no slash command for now)
- **Validation:** Ensure no date overlaps
- **Naming:** Follow pattern: "{Season} {Year}"

### 6.2 Quarter Points Calculation

#### Point Assignment Logic
```python
def assign_points(member_id, points, submission_timestamp):
    # Add to lifetime
    member.total_points += points

    # Determine quarter based on submission_timestamp
    quarter = get_quarter_for_date(submission_timestamp)

    # Add to quarter_points
    quarter_points = get_or_create(member_id, quarter.id)
    quarter_points.points += points

    # Ledger entry (immutable audit trail)
    points_ledger.insert({
        'member_id': member_id,
        'delta': points,
        'reason': 'task_approved',
        'ref_type': 'submission',
        'ref_id': submission.id,
        'quarter_id': quarter.id,
        'created_at': now()
    })

    # Update Redis leaderboards
    redis.zadd("leaderboard:lifetime", {member.discord_id: member.total_points})
    redis.zadd(f"leaderboard:quarter:{quarter.id}", {member.discord_id: quarter_points.points})
```

#### Retroactive Scenarios
- **Submission during Q1, approved during Q2:** Points count toward Q1 (based on submitted_at)
- **Member joins mid-quarter:** Can still earn full quarter points
- **Quarter ends:** Points frozen for that quarter, new quarter starts

---

## 7. EVENT SYSTEM (Future Feature Placeholder)

### 7.1 Event Creation
- **Command:** `/event create` (future)
- **Fields:** name, description, event_date, optional check_in_code
- **Permissions:** Officers only

### 7.2 Check-In System
- **Method 1:** QR Code scan with check_in_code
- **Method 2:** Manual check-in command
- **Tracking:** Records in event_attendance table

### 7.3 Attendance Tracking
- **Display:** In `/profile` as "Events Attended" count
- **Leaderboard:** Potential future feature

---

## 8. HOSTING & DEPLOYMENT

### 8.1 Platform Selection
**Recommendation:** Railway.app

**Rationale:**
- Free tier: 500 hours/month ($5 credit)
- PostgreSQL included
- Zero-config deployments
- Automatic restarts
- GitHub integration
- Poetry support (auto-detects pyproject.toml)
- Expected usage: ~200 members = well within limits

**Alternatives:**
- Render.com (750 hours/month free)
- Fly.io (3 shared VMs free)

### 8.2 Database Hosting
- **PostgreSQL:** Railway's built-in Postgres (500 MB free)
- **Upstash Redis:** Free tier (10,000 commands/day)
- **Backup Strategy:** Railway automatic daily backups

### 8.3 Deployment Architecture
```
GitHub Repository (with pyproject.toml)
    ↓ (automatic deploy on push)
Railway Instance
    ├→ Discord Bot (Python process)
    ├→ PostgreSQL Database (Railway)
    └→ Upstash Redis (external, REST API)
```

### 8.4 Project Structure
```
DiscordBot/
├── pyproject.toml          # Poetry dependencies
├── poetry.lock             # Locked dependency versions
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore file
├── bot.py                  # Main entry point
├── config.py               # Configuration/environment variables
├── database.py             # Database setup
├── cogs/                   # Feature modules (slash commands)
│   ├── __init__.py
│   ├── qr_codes.py        # QR code generation
│   ├── members.py         # Member registration/tracking
│   ├── tasks.py           # Task management
│   └── leaderboard.py     # Leaderboards and profiles
├── models/                 # Database models (backend)
│   ├── __init__.py
│   ├── member.py
│   ├── task.py
│   ├── quarter.py
│   └── board_member.py
├── utils/                  # Helper functions
│   ├── __init__.py
│   ├── validators.py      # Input validation
│   ├── permissions.py     # Permission checks
│   └── redis_client.py    # Redis helper functions
└── migrations/             # Database migrations
    └── init_db.sql        # Initial schema setup
```

### 8.5 Environment Variables
```
DISCORD_TOKEN=<bot_token>
DISCORD_GUILD_ID=<server_id>
DATABASE_URL=<postgresql://...>  (Railway auto-provides)
REDIS_URL=<upstash_rest_url>
REDIS_TOKEN=<upstash_rest_token>
OFFICERS_ROLE_NAME=officers
```

### 8.6 Deployment Steps
1. Create Railway account
2. Create new project from GitHub repo
3. Add PostgreSQL database (Railway)
4. Configure environment variables
5. Railway auto-detects pyproject.toml, installs via Poetry
6. Railway runs: `python bot.py`
7. Monitor via Railway dashboard

### 8.7 Python Version
- **Required:** Python 3.11+
- **Reasoning:** Modern async syntax, better performance, Railway default
- **Specified in:** pyproject.toml (`python = "^3.11"`)

---

## 9. PACKAGE DEPENDENCIES

### 9.1 Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| py-cord | ^2.6.1 | Discord API library with slash command support |
| psycopg2-binary | ^2.9.9 | PostgreSQL database adapter |
| SQLAlchemy | ^2.0.23 | ORM for database models |
| redis | ^5.0.1 | Redis client for Upstash connection |
| qrcode[pil] | ^7.4.2 | QR code generation with PIL support |
| Pillow | ^10.1.0 | Image processing (required by qrcode) |
| python-dotenv | ^1.0.0 | Load environment variables from .env file |

### 9.2 Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ^7.4.3 | Testing framework |
| pytest-asyncio | ^0.21.1 | Async test support |

### 9.3 pyproject.toml Structure

```toml
[tool.poetry]
name = "discord-club-bot"
version = "1.0.0"
description = "Discord bot for club management with QR codes, tasks, and gamification"
authors = ["Your Name <you@example.com>"]
readme = "README.md"

[tool.poetry.dependencies]
python = "^3.11"
py-cord = "^2.6.1"
psycopg2-binary = "^2.9.9"
SQLAlchemy = "^2.0.23"
redis = "^5.0.1"
qrcode = {extras = ["pil"], version = "^7.4.2"}
Pillow = "^10.1.0"
python-dotenv = "^1.0.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.3"
pytest-asyncio = "^0.21.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

---

## 10. CONFIGURATION & ENVIRONMENT

### 10.1 Environment Variables (Complete List)

| Variable | Type | Required | Description | Example |
|----------|------|----------|-------------|---------|
| DISCORD_TOKEN | String | Yes | Bot token from Discord Developer Portal | MTk4N... |
| DISCORD_GUILD_ID | Integer | Yes | Server ID where bot operates | 1234567890 |
| DATABASE_URL | String | Yes | PostgreSQL connection string | postgresql://... |
| REDIS_URL | String | Yes | Upstash REST API URL | https://upstash... |
| REDIS_TOKEN | String | Yes | Upstash REST API token | AaBbCc... |
| OFFICERS_ROLE_NAME | String | Yes | Discord role name for admins | officers |
| LOG_LEVEL | String | No | Logging level | INFO (default) |
| SENTRY_DSN | String | No | Error tracking (future) | https://sentry... |

### 10.2 Bot Permissions (Discord)

**Required Permissions Integer:** `2147534848`

**Breakdown:**
- Read Messages/View Channels
- Send Messages
- Send Messages in Threads
- Embed Links
- Attach Files
- Read Message History
- Use Slash Commands
- Manage Roles (for future role rewards)

**Privileged Gateway Intents:**
- Server Members Intent (required for on_member_join)
- Message Content Intent (NOT required, we use slash commands)

### 10.3 Configuration Files

#### config.py
```python
import os
from typing import Optional

class Config:
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN")
    DISCORD_GUILD_ID: int = int(os.getenv("DISCORD_GUILD_ID"))
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    REDIS_URL: str = os.getenv("REDIS_URL")
    REDIS_TOKEN: str = os.getenv("REDIS_TOKEN")
    OFFICERS_ROLE_NAME: str = os.getenv("OFFICERS_ROLE_NAME", "officers")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Rate limits (per minute)
    QRCODE_RATE_LIMIT: int = 5
    TASK_SUBMIT_RATE_LIMIT: int = 3

    # QR Code defaults
    QR_DEFAULT_ERROR_CORRECTION: str = "M"
    QR_DEFAULT_BOX_SIZE: int = 10
    QR_DEFAULT_BORDER: int = 4
    QR_DEFAULT_FILL_COLOR: str = "black"
    QR_DEFAULT_BACK_COLOR: str = "white"

    # Pagination
    TASKS_PER_PAGE: int = 5
    LEADERBOARD_DEFAULT_SIZE: int = 10
    SUBMISSIONS_PER_PAGE: int = 5
```

---

## 11. ERROR HANDLING & EDGE CASES

### 11.1 Error Categories

#### User Errors (Friendly Messages)
- Invalid input
- Permission denied
- Rate limit exceeded
- Resource not found

**Response:** Ephemeral message with clear explanation

#### System Errors (Log + Generic Message)
- Database connection failure
- Redis connection failure
- Discord API errors
- File upload failures

**Response:** "An error occurred. Please try again later." + log to Sentry

### 11.2 Specific Edge Cases

#### Member Registration
| Scenario | Handling |
|----------|----------|
| Member joins twice (rejoin) | Update existing record, preserve points |
| Bot added to server with existing members | Batch register all members on first startup |
| Member leaves server | Keep database record (for historical data) |
| Member changes username | Auto-update via on_member_update event |

#### Task Submissions
| Scenario | Handling |
|----------|----------|
| Submit to inactive task | Error: "This task is no longer active" |
| Submit with neither URL nor file | Error: "Please provide a URL or file" |
| File exceeds 8 MB | Discord rejects, error: "File too large (max 8 MB)" |
| Invalid URL format | Error: "Please provide a valid URL starting with http:// or https://" |
| Submit while already pending | Error: "You already have a pending submission for this task" |
| Task deleted before review | Submission remains, shows "[Deleted Task]" in review queue |

#### Point Allocation
| Scenario | Handling |
|----------|----------|
| Approve submission after quarter ends | Points go to quarter when submission was created |
| No active quarter | Error: "No active quarter configured. Contact an officer." |
| Redis unavailable | Fall back to PostgreSQL for leaderboards |
| Negative points (database manipulation) | Blocked by CHECK constraint |

#### Leaderboard Display
| Scenario | Handling |
|----------|----------|
| User not on leaderboard | Show "Unranked" or "Not yet ranked" |
| Tie in points | Same rank, next rank skipped (e.g., 1, 2, 2, 4) |
| Bot accounts | Excluded via `WHERE is_bot = FALSE` |

#### QR Code Generation
| Scenario | Handling |
|----------|----------|
| Invalid URL | Error: "Please provide a valid URL" |
| URL too long (>2000 chars) | Allowed, QR code may be dense |
| Invalid color format | Error: "Invalid color. Use hex (#FF0000) or names (red, blue)" |
| Rate limit exceeded | Error: "Please wait {seconds} seconds" |

### 11.3 Fallback Strategies

#### Redis Failure
```python
def get_leaderboard():
    try:
        return get_from_redis()
    except RedisConnectionError:
        logger.warning("Redis unavailable, falling back to PostgreSQL")
        return get_from_postgres()
```

#### DM Failure
```python
def notify_member(member_id, message):
    try:
        user = await bot.fetch_user(member_id)
        await user.send(message)
    except discord.Forbidden:
        logger.info(f"Cannot DM user {member_id} (DMs disabled)")
        # Continue without error
```

#### Database Connection Loss
- Implement connection pooling with auto-reconnect
- Retry failed queries (max 3 attempts)
- If still fails, respond with generic error

---

## 12. DATA VALIDATION RULES

### 12.1 Input Validation

#### URLs
```python
import re
URL_PATTERN = re.compile(r'^https?://')

def validate_url(url: str) -> bool:
    if not URL_PATTERN.match(url):
        return False
    if len(url) > 2000:
        return False
    return True
```

#### Dates
```python
from datetime import datetime

def validate_deadline(date_str: str) -> datetime:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        if dt <= datetime.now():
            raise ValueError("Deadline must be in the future")
        return dt
    except ValueError as e:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD HH:MM")
```

#### Point Values
```python
def validate_points(points: int) -> bool:
    return 1 <= points <= 1000
```

#### Color Values
```python
def validate_color(color: str) -> bool:
    # Hex format: #RGB or #RRGGBB
    if re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color):
        return True
    # Named colors (PIL supported)
    named_colors = ['black', 'white', 'red', 'blue', 'green', 'yellow', 'purple', 'orange']
    return color.lower() in named_colors
```

### 12.2 Permission Validation

```python
def is_officer(interaction: discord.Interaction) -> bool:
    return any(role.name == Config.OFFICERS_ROLE_NAME for role in interaction.user.roles)

async def require_officer(interaction: discord.Interaction):
    if not is_officer(interaction):
        await interaction.response.send_message(
            "You must be an officer to use this command.",
            ephemeral=True
        )
        raise PermissionError("User is not an officer")
```

---

## 13. LOGGING & MONITORING

### 13.1 Log Levels

| Level | Use Case | Examples |
|-------|----------|----------|
| DEBUG | Development debugging | SQL queries, Redis commands |
| INFO | Normal operations | Member registered, task created |
| WARNING | Recoverable issues | Redis unavailable (fallback used), DM failed |
| ERROR | Application errors | Database query failed, invalid data |
| CRITICAL | System failures | Database unreachable, bot token invalid |

### 13.2 Log Format
```
[2025-12-01 15:30:45] [INFO] [members.py:42] Member registered: discord_id=123456789
[2025-12-01 15:31:10] [WARNING] [tasks.py:78] Redis unavailable, using PostgreSQL fallback
[2025-12-01 15:32:00] [ERROR] [qr_codes.py:55] QR generation failed: Invalid color format
```

### 13.3 Audit Trail

**Critical Actions to Log:**
- Member registration
- Task creation/deletion
- Submission approval/rejection
- Point awards
- Officer actions

**Log Entry Format:**
```json
{
    "timestamp": "2025-12-01T15:30:45Z",
    "action": "task_approved",
    "officer_id": 123456789,
    "member_id": 987654321,
    "task_id": 42,
    "points_awarded": 50,
    "quarter": "Fall 2025"
}
```

---

## 14. FUTURE ENHANCEMENTS (Out of Scope)

These features are NOT part of initial implementation but documented for future reference:

### 14.1 Role Rewards
- Auto-assign Discord roles based on point thresholds
- Example: "Gold Member" role at 1000 points

### 14.2 QR Code Branding
- Add club logo to center of QR codes
- Requires PIL image overlay logic

### 14.3 Event Check-In via QR
- Generate QR codes with event check-in codes
- Scan QR code to auto-check into events

### 14.4 Task Categories/Tags
- Categorize tasks (e.g., "Workshop", "Social", "Community Service")
- Filter `/task list` by category

### 14.5 Member Profiles (Public)
- `/profile @user` to view other members (officers only)
- Privacy settings

### 14.6 Analytics Dashboard
- Web dashboard showing stats, charts, graphs
- Requires separate web server (Flask/FastAPI)

---

## 15. TESTING STRATEGY

### 15.1 Unit Tests (Required Before Launch)

#### Database Models
- Test CRUD operations
- Test constraints (unique, check, foreign keys)
- Test cascading deletes

#### QR Code Generation
- Test all error correction levels
- Test color validation
- Test invalid URLs

#### Point Calculation
- Test lifetime point addition
- Test quarter point assignment
- Test leaderboard updates

### 15.2 Integration Tests

#### Task Workflow
1. Officer creates task
2. Member submits completion
3. Officer approves
4. Verify points added to both lifetime and quarter
5. Verify leaderboards updated

#### Member Registration
1. Simulate member join event
2. Verify database record created
3. Verify Redis leaderboard entry

### 15.3 Manual Testing Checklist

- [ ] All slash commands respond correctly
- [ ] Permission checks work (officer-only commands)
- [ ] Rate limiting functions
- [ ] QR codes generate and display
- [ ] Task submissions accept files and URLs
- [ ] Approval/rejection DMs send correctly
- [ ] Leaderboards display accurately
- [ ] Profile shows correct stats
- [ ] Board members display correctly

---

## 15. IMPLEMENTATION ORDER

### Phase 1: Foundation (Days 1-2)
1. Project structure setup
2. Database models (PostgreSQL)
3. Redis integration (Upstash)
4. Bot initialization and configuration
5. Permission system (officers role check)

### Phase 2: Core Features (Days 3-4)
6. Member registration (on_member_join)
7. `/qrcode` command
8. `/task create`, `/task list`, `/task delete`
9. `/leaderboard` command
10. `/profile` command

### Phase 3: Task Submission System (Days 5-6)
11. `/task submit` command
12. Task submission validation
13. `/task review pending` command
14. `/task review approve/reject` commands
15. Point allocation logic
16. DM notifications

### Phase 4: Additional Features (Days 7-8)
17. `/board` command
18. Quarter management system
19. Quarterly leaderboards
20. Error handling and fallbacks

### Phase 5: Deployment (Days 9-10)
21. Railway deployment setup
22. Environment variable configuration
23. Database migrations
24. Upstash Redis setup
25. Testing on live server
26. Documentation for officers

---

## 16. SUCCESS CRITERIA

### Minimum Viable Product (MVP)
- [ ] Bot connects to Discord and responds to slash commands
- [ ] Members auto-register on server join
- [ ] Officers can create tasks
- [ ] Members can submit task completions
- [ ] Officers can approve/reject submissions
- [ ] Points are awarded and tracked correctly
- [ ] Leaderboards display accurately
- [ ] QR codes generate from URLs
- [ ] Bot runs 24/7 on Railway without restarts needed

### Performance Targets
- [ ] Slash command response time: < 2 seconds
- [ ] QR code generation: < 3 seconds
- [ ] Leaderboard query: < 1 second (via Redis)
- [ ] Bot uptime: 99.5%+

### User Experience Goals
- [ ] Zero configuration required for members
- [ ] Clear error messages for invalid actions
- [ ] Intuitive command structure
- [ ] Responsive button interactions
- [ ] Timely DM notifications

---

## DOCUMENT VERSION
- **Version:** 1.0
- **Last Updated:** 2025-12-01
- **Status:** APPROVED FOR IMPLEMENTATION
- **No Changes Allowed Without User Approval**

---

END OF SPECIFICATION
