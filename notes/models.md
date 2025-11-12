# `models.py` architecture walkthrough
```
   ┌─────────────┐
   │  Client     │  ← user or another system
   └────┬────────┘
        │  POST /jobs
        ▼
   ┌─────────────┐
   │  API Layer  │
   │ (Flask)     │
   └────┬────────┘
        │ validates request → JobCreate
        ▼
   ┌─────────────┐
   │ Job Object  │  ←  becomes part of the system's "queue"
   └────┬────────┘
        │ stored & tracked
        ▼
   ┌─────────────┐
   │ Runner/Exec │  ←  later pieces pick it up, execute it
   └─────────────┘
```
At a high level, our system needs to:
1. Accept work – something that performs a defined task.
2. Track progress – know what’s currently happening.
3. Model real-world state – queued → running → succeeded/failed.
4. Provide feedback – return results, logs, and exit codes.

| Concept            | Example                             | Why it matters                     |
| ------------------ | ----------------------------------- | ---------------------------------- |
| **Job definition** | “Run this Python or shell command”  | The *thing* you want done          |
| **Job instance**   | Job #123 running “echo hi”          | Tracks one run of that definition  |
| **Job lifecycle**  | queued → running → succeeded/failed | Models real-world progress         |
| **Job result**     | exit code, logs, output             | Gives feedback about what happened |

We use two Pydantic classes to represent these ideas:

- `JobCreate` – the contract clients use to submit work. It defines what the outside world is allowed to ask for.
- `Job` – the complete representation of a job inside and outside the system. It’s what we persist, monitor, and return from the API once metadata like id and status have been added.

## Why this structure matters
Separating input (`JobCreate`) from state (`Job`) makes the system safe and predictable:
- We validate and reject invalid requests immediately.
- The system controls state transitions (queued → running → succeeded/failed).
- A single schema defines what a job means across the entire platform.

These models are the source of truth for what a “job” is, what states it can have, and how the API and internal services understand that meaning.

## Looking ahead
Because jobs follow a well-defined schema:
- We can swap storage backends (memory → Redis → database) without changing APIs.
- We can add new job types (python, http, ml) without breaking clients.
- We can serialize/deserialize jobs consistently across boundaries (API ↔ worker ↔ database ↔ dashboard).
- We can enforce contracts: if it’s not a valid Job, the system will reject it before it ever reaches execution.

---
# Conceptually
Can be thought of like input validation vs domain model.
| Model       | Role                                             | Owner      |
| ----------- | ------------------------------------------------ | ---------- |
| `JobCreate` | Input schema – what clients send                 | The client |
| `Job`       | Full job state – what the API stores and returns | The system |
# Codebase Breakdown
## Import
```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
```
`pydantic` - gives us data validation and type-safe models
- `BaseModel` allows us to inherit automatic type checking; default values and validators; `.dict()`/`.model_dump()` methods let us easily serialize to JSON; helpful error messaging if data doesn't match the expected shape.

`typing` - Python module that gives type hints that Pydantic can also understand
- `Literal["shell","python"]`: restricts values to one of these exact strings
- `Optional[Dict[str, Any]]`: means it can be `None` or any dictionary
- `Dict[str, Any]`: means it can be only a dictionary with string keys and any type values.
- `Any`: means "any Python object"  

## JobType
```python
JobType = Literal["shell", "python"]
```
This defines the limited set of acceptable job types.
- `"shell"` means "run a shell command"
- `"python"` means "run a Python snippet" (we will have future support)

If you try to pass in `"go"` or `"node"` or `"rust"` for instance, Pydantic will reject it.

## JobCreate
```python
class JobCreate(BaseModel):
    type: JobType
    payload: Dict[str, Any] = Field(default_factory=dict)
```
When a client tries to create a job via `POST /jobs` this model defines what they **must send**.
  
| Field     | Type             | Purpose                                        |
| --------- | ---------------- | ---------------------------------------------- |
| `type`    | `JobType`        | What kind of job it is. At the time it can only be python |
| `payload` | `Dict[str, Any]` | extra data the job needs (command, code, etc.) the payload must be a dictionary with string-keys and any types for the values. |

**Default Factory**
`Field(default_factory=dict)`
- Safety implementation in Python where we ensure if a client doesn't provide a payload, it defaults to an empty {} dict instead of sharing a mutable object across instances. 

**Example**
```python
job = JobCreate(type="shell")
print(job.payload)      # {}
```

If someone sends below, Pydantic parses and validates that it fits the schema:
```python
 {"type": "shell", "payload": { "cmd": "echo hello" } }     #{ "cmd": "echo hello" } [ANY]
```

## Job
This represents a **full job object stored or returned by the API**.
```python
class Job(BaseModel):
    id: str
    type: JobType
    payload: Dict[str, Any]
    status: Literal["queued", "running", "succeeded", "failed"] = "queued"      # if it has not ran yet, meaning there is no status yet, we will make the default "queued"
    result: Optional[Dict[str, Any]] = None                                     # default: None
```
It includes more metadata that we (the backend) generate or update over time
| Field     | Type                                                      | Description                                            |
| --------- | --------------------------------------------------------- | ------------------------------------------------------ |
| `id`      | `str`                                                     | unique job ID (UUID4 string generated by backend)      |
| `type`    | `JobType`                                                 | same as above                                          |
| `payload` | `Dict[str, Any]`                                          | the data for the job (e.g., `{"cmd": "echo hi"}`)      |
| `status`  | one of `"queued"`, `"running"`, `"succeeded"`, `"failed"` | lifecycle phase of this job                            |
| `result`  | `Optional[Dict[str, Any]]`                                | outcome or error details (only filled after execution) |

**Defaults**
- `status` defaults to `"queued"` → when you first create the job, it hasn’t run yet.
- `result` defaults to `None` → will later hold something like:
    ```json
    {"exit_code": 0, "output": "hi\n"}
    ```

# Example Flow
1. Client sends:
    ```json
    { "type": "shell", "payload": {"cmd": "echo hi"} }
    ```
2. Flask route parses it:
    ```python
    job_in = JobCreate(**request.json)
    ```
3. Create a `Job` from it
    ```python
    job = Job(id="123", type=job_in.type, payload=job_in.payload)
    ```
4. The API stores it and returns
    ```json
    { "id": "123", "status": "queued" }
    ```