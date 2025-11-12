from pydandic import BaseModel, Field                   #library that gives you data validation and type-safe models.
from typing import Literal, Optional, Dict, Any         #

JobType = Literal["shell", "python"]

class JobCreate(BaseModel):
    type: JobType
    payload: Dict[str, Any] = Field(default_factory=dict)

class Job(BaseModel):
    id: str
    type: JobType
    payload: Dict[str, Any]
    status: Literal["queued", "running", "succeeded", "failed"] = "queued"
    result: Optional[Dict[str, Any]] = None