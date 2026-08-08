from datetime import datetime
from random import randint
from fastapi import FastAPI, APIRouter, HTTPException, Response
from prometheus_fastapi_instrumentator import Instrumentator
from typing import Any

# 1. Initialize FastAPI WITHOUT the root_path
app = FastAPI()
Instrumentator().instrument(app).expose(app)


# 2. Set up a router to handle your /api/v1 prefix
router = APIRouter(prefix="/api/v1")

data: Any = [
    {
        "campaign_id": 1,
        "name": "Summer Launch",
        "due_date": datetime.now(),
        "created_at": datetime.now()
    },
    {
        "campaign_id": 2,
        "name": "Black Friday",
        "due_date": datetime.now(),
        "created_at": datetime.now()
    }
]

# 3. Attach all endpoints to the @router instead of @app

@router.get("/")
async def root():
    return {"message": "Hello world!"}

@router.get("/campaigns")
async def read_campaigns():
    return {"campaigns": data}

@router.get("/campaigns/{id}")
async def read_campaign(id: int):
    for campaign in data:
        if campaign.get("campaign_id") == id:
            return {"campaign": campaign}
    raise HTTPException(status_code=404)

@router.post("/campaigns", status_code=201)
async def create_campaign(body: dict[str, Any]):
    new: Any = {
        "campaign_id": randint(100, 1000),
        "name": body.get("name"),
        "due_date": body.get("due_date"),
        "created_at": datetime.now()
    }
    data.append(new)
    return {"campaign": new}

@router.put("/campaigns/{id}")
async def update_campaign(id: int, body: dict[str, Any]):
    for index, campaign in enumerate(data):
        if campaign.get("campaign_id") == id:
            updated: Any = {
                "campaign_id": id,
                "name": body.get("name"),
                "due_date": body.get("due_date"),
                "created_at": campaign.get("created_at")
            }
            data[index] = updated
            return {"campaign": updated}
    raise HTTPException(status_code=404)
    
@router.delete("/campaigns/{id}", status_code=204)
async def delete_campaign(id: int):
    for index, campaign in enumerate(data):
        if campaign.get("campaign_id") == id:
            data.pop(index)
            return Response(status_code=204)
    raise HTTPException(status_code=404)

# 4. Include the router in the main application
app.include_router(router)