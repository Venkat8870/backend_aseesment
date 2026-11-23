# Scheduled Equipment Event Monitoring API

A backend service that monitors machine events through scheduled file downloads.

Machines produce event files (CSV) with new rows of events. Operators register the event
codes they care about (for example `TEMP_HIGH`, `MOTOR_FAILURE`) and create scheduled tasks
per machine. Celery jobs periodically download new event files, match the rows against the
registered codes, and store the matching events, which can then be queried through an API.

**Stack:** FastAPI, Celery, Redis, SQLAlchemy, Postgres (Docker) / SQLite (local tests), Pytest, Docker Compose.

---

## 1. Architecture

```
                    +-------------------+
   operator ------> |  FastAPI (api)    | <---- simulator endpoints (fake machine)
   (Swagger /docs)  |  event codes      |
                    |  tasks, events    |
                    +---------+---------+
                              |
                              v
                       +-------------+
                       |  Postgres   |  event_codes, tasks, processed_files,
                       |             |  processed_events, task_executions
                       +------^------+
                              |
   +-------------+     +------+------+      HTTP       +----------------------+
   | Celery Beat | --> |   Redis     | --> | Celery worker | ------------------> | simulator (in API)  |
   | every 10s   |     |  (broker)   |     | run_task_once |   download files    +----------------------+
   +-------------+     +-------------+     +---------------+
```

| Component | Role |
|---|---|
| **FastAPI** | Exposes the Event Codes, Tasks, Events and Simulator APIs. It never does the heavy work itself. |
| **Celery Beat** | The clock. Every 10 seconds it triggers `dispatch_due_tasks`. |
| **Redis** | Message broker. Holds queued jobs until a worker picks them up. |
| **Celery worker** | Does the real work: download, match, store, update cursor, write history. |
| **Postgres** | Stores rules, tasks, processed files, matched events and execution history. |
| **Simulator** | A fake machine that lives inside the API and is called over HTTP, like a real machine would be. |

### How one run works

1. Operator registers event codes to monitor.
2. Operator creates a scheduled task for a machine (`start_at`, `stop_at`, `interval_seconds`).
3. The simulator continuously "produces" events. Each event has an increasing number called a **cursor**.
4. Celery Beat fires every 10 seconds. `dispatch_due_tasks` finds ACTIVE tasks whose `next_attempt` is due,
   pushes their `next_attempt` forward (so they are not queued twice) and queues `run_task(task_id)`.
5. The worker asks the machine: "I have processed up to cursor X, what is new?" and receives file metadata
   (`start_cursor`, `end_cursor`, `download_url`), or HTTP 204 if there is nothing new.
6. The worker downloads the CSV and reads the active event codes from the database.
7. Rows are matched against the registered codes and severity is attached.
8. Matching events are stored (duplicates skipped), the file is recorded as processed, and the
   task cursor moves forward.
9. An execution history row is written for the run.
10. Steps 8 and 9 are committed together in **one transaction**.
11. The user queries the stored events through `GET /v1/events`.

---

## 2. Setup

### Run everything with Docker (recommended)

```bash
docker compose up --build
```

This starts 5 containers: `db` (Postgres), `redis`, `api`, `worker`, `beat`.
Interactive API docs: http://localhost:8000/docs



### Run tests locally

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
pytest -v
```

Tests use an in-memory SQLite database and do not need Redis or Docker.

### Try it end to end

1. `POST /v1/event-codes` with `{"code": "TEMP_HIGH", "severity": "HIGH"}` and
   `{"code": "MOTOR_FAILURE", "severity": "CRITICAL"}`
2. `POST /v1/tasks`
   ```json
   {
     "machine_id": "ETCH-001",
     "start_at": "2026-11-21T00:00:00Z",
     "stop_at": "2026-11-30T00:00:00Z",
     "interval_seconds": 30
   }
   ```
3. Wait about a minute, then:
   - `GET /v1/tasks/1` shows `last_processed_cursor` moving forward
   - `GET /v1/tasks/1/executions` shows the run history
   - `GET /v1/events?machine_id=ETCH-001` shows the stored events

---

## 3. API overview

| Method and path | Purpose |
|---|---|
| `POST /v1/simulator/download` | Machine simulator: returns metadata of the next file after `last_processed_cursor` (204 if nothing new) |
| `GET /v1/simulator/files/{file_name}` | Machine simulator: download a CSV event file |
| `POST /v1/event-codes` | Register an event code (code is uppercased, duplicates return 409) |
| `GET /v1/event-codes` | List registered codes |
| `DELETE /v1/event-codes/{code}` | Remove a code |
| `POST /v1/tasks` | Create a scheduled task |
| `GET /v1/tasks` | List tasks (filters: `machine_id`, `status`) |
| `GET /v1/tasks/{id}` | Get one task |
| `POST /v1/tasks/{id}/pause` | Pause a task |
| `POST /v1/tasks/{id}/resume` | Resume a task (cursor is kept) |
| `DELETE /v1/tasks/{id}` | Delete a task (soft delete) |
| `GET /v1/tasks/{id}/executions` | Execution history of every run |
| `GET /v1/events` | Query stored events (filters: `machine_id`, `event_code`, `severity`, `start_time`, `end_time`, `page`, `page_size`) |
| `GET /health` | Health check |

---

## 4. Data model

| Table | Purpose | Notable constraints |
|---|---|---|
| `event_codes` | The watchlist: code, severity, description, `is_active` | `code` is unique |
| `tasks` | One scheduled job per machine: interval, window, status, `last_attempt`, `next_attempt`, `last_processed_cursor` | status: ACTIVE, PAUSED, COMPLETED, DELETED |
| `processed_files` | Files already handled | unique on (`machine_id`, `file_name`) |
| `processed_events` | Matched events that were stored | unique on (`machine_id`, `cursor`) |
| `task_executions` | One row per task run: status, file, cursor range, `events_found`, `events_stored`, error | status: RUNNING, SUCCESS, FAILED, SKIPPED |

---

## 5. How I approached it

I built it in small steps, finishing and testing each piece before starting the next one, so
that problems show up in the piece that caused them.

1. **Simulator first.** Without a machine producing events there is nothing to monitor, so I built the
   data source first: cursor-based events, CSV file generation, a metadata endpoint and a download endpoint.
2. **Database design.** I designed all five tables up front (instead of adding them gradually) because
   the relationships between them, especially cursor, processed files and processed events, are what
   make the system correct.
3. **Event Codes API.** The watchlist the worker reads at match time.
4. **Tasks API.** Create, pause, resume, delete, and execution history. The API only manages schedule
   rows. It never runs anything itself.
5. **Core processing as small single-purpose modules.** Download, match, store, cursor, idempotency
   and history are separate files, each tested on its own. A single orchestrator (`runner.py`) calls
   them in order. This keeps changes isolated: changing the matching rule only touches `matcher.py`.
6. **Celery + Redis.** Thin Celery wrappers around the orchestrator, plus Beat to find due tasks.
   The orchestrator is plain Python with no Celery inside, so it can be tested without Redis.
7. **Events API.** Filters and pagination over the stored events.
8. **Docker Compose and tests.** Tests were written alongside each step. Docker Compose ties the five
   services together.

---

## 6. Design decisions

- **Cursor-based incremental download.** The task stores `last_processed_cursor` and sends it to the
  machine, so only new events are fetched. The cursor is the bookmark of the whole system.
- **Idempotency in two layers.** (1) `processed_files` skips a file that was already handled. (2) A unique
  constraint on `processed_events (machine_id, cursor)` guarantees the same event can never be inserted
  twice, even if the first layer fails (crash, race, retry).
- **Cursor advances only after a successful commit.** Events, processed file, cursor and execution history
  are committed in one transaction. If anything fails, the run is rolled back, the cursor does not move,
  and the next run safely retries the same range.
- **Beat only dispatches; the worker does the work.** Beat finds due tasks from the database, so pause,
  resume and delete are just status changes with no need to touch the scheduler.
- **`claim_due_tasks` pushes `next_attempt` forward before queueing.** This stops the same task from being
  queued again on the next Beat tick while it is still running.
- **Watchlist is read at run time.** Adding or removing a code takes effect on the next run without a restart.
- **Severity is stored on the event code and copied onto each event.** Old events keep the severity they
  had when matched, and queries need no join.
- **Soft delete for tasks.** Deleting sets status to DELETED so execution history is preserved.
- **Nothing new from the machine returns HTTP 204 and the run is recorded as SKIPPED.** The assignment
  did not specify this case, so this was my decision.
- **Deterministic simulator.** The event for a given cursor is seeded by `machine_id:cursor`, so the same
  cursor always gives the same event. This makes retries and tests predictable.
- **Batch cap of 500 events per file.** A task that is far behind catches up over several runs.
- **All datetimes are normalised to UTC.** SQLite returns naive datetimes, so a helper (`as_utc`) is used
  everywhere to avoid naive/aware comparison errors.
- **Postgres in Docker, SQLite for tests.** Several processes write at once in Docker, which SQLite handles
  poorly. The database URL comes from an environment variable, so the code is the same for both.
- **Inside Docker the worker reaches the simulator at `http://api:8000`.** `localhost` inside a container
  means that container itself.

---

## 7. Testing

```bash
pytest -v
```

41 tests covering:

- **Simulator:** cursor ranges, batch cap, same request gives same file, CSV content, machines are independent
- **Event codes API:** create, list, uppercase normalisation, duplicates, invalid severity, delete
- **Tasks API:** create, validation, pause/resume, invalid transitions, soft delete, filters, execution history
- **Matcher:** drops unwatched codes, adds severity, keeps order, ignores case and spaces, empty input
- **Runner (processing):** successful run, nothing new is skipped, same file twice creates no duplicates,
  unique constraint as second safety net, failure keeps cursor and logs the error, inactive codes ignored,
  paused task does nothing, task completes after `stop_at`, due tasks are claimed only once
- **Events API:** listing, filters, time range, pagination, invalid range

Tests use an in-memory database per test (`tests/conftest.py`) and replace the machine with a fake, so
they run without Redis, Docker or network access.

---

## 8. Project structure

```
app/
  main.py                  FastAPI app, routers, table creation on startup
  config.py                Settings from environment variables
  db.py                    Database engine and sessions
  models.py                The 5 tables
  schemas.py               Request and response models and validation
  timeutil.py              UTC helper
  api/
    simulator.py           Machine simulator endpoints
    event_codes.py         Event Rules API
    tasks.py               Task Scheduling API
    events.py              Processed Events API
  services/
    simulator_engine.py    Event and CSV generation
    downloader.py          HTTP calls to the machine, CSV parsing
    matcher.py             Match rows against active codes
    idempotency.py         "Already processed?" checks
    storage.py             Store events, skipping duplicates
    cursor.py              Move the cursor forward
    history.py             Execution history rows
  worker/
    celery_app.py          Celery config and Beat schedule
    tasks.py               Thin Celery task wrappers
    runner.py              One task run, step by step (the core logic)
tests/
Dockerfile
docker-compose.yml
requirements.txt
```

---

## 9. Known limitations

- A newly registered code only catches events from that point on. The cursor has already moved past
  older events, so they are not rescanned.
- Simulator state (each machine's start time) is in memory, so the API must run as a single process and
  the simulated clock resets if the API restarts.
- Two tasks for the same machine are allowed. Events are still deduplicated by the unique constraint,
  but the work is duplicated.
- Tables are created with `create_all` on startup, not migrations.
- No authentication.

## 10. Future improvements

- Alembic migrations instead of `create_all`.
- Retries with exponential backoff and a dead-letter strategy for repeatedly failing runs.
- Row-level locking (`SELECT ... FOR UPDATE SKIP LOCKED`) so two workers never run the same task.
- A backfill job to rescan history when a new event code is registered.
- A partial unique index (or 409 check) to allow only one active task per machine.
- A PATCH endpoint to mute or unmute an event code using the existing `is_active` column.
- Move simulator state to Redis or the database, or run it as a separate service.
- Authentication, rate limiting, metrics and structured logging.
