import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+pg8000://appuser:apppass@localhost:5432/telemetry")
engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

SessionDp = Annotated[Session, Depends(get_session)]

class Campaign(SQLModel, table=True):
    campaign_id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    due_date: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

class CampaignCreate(SQLModel):
    name: str
    due_date: datetime | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: migrate + seed
    create_db_and_tables()
    with Session(engine) as session:
        if not session.exec(select(Campaign)).first():
            session.add_all([
                   Campaign(name="Summer Launch", due_date=datetime.now(timezone.utc)),
                Campaign(name="Black Friday", due_date=datetime.now(timezone.utc)),
            ])
            session.commit()
    yield


app = FastAPI(root_path="/api/v1", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


T = TypeVar("T")
class Response(BaseModel, Generic[T]):
    data: T

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/campaigns", response_model=Response[list[Campaign]])
async def read_campaigns(session: SessionDp):
    campaigns = session.exec(select(Campaign)).all()
    return {"data": campaigns}

@app.get("/campaigns/{id}", response_model=Response[Campaign])
async def read_campaign(id: int, session: SessionDp):
    campaign = session.get(Campaign, id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"data": campaign}

@app.post("/campaigns", response_model=Response[Campaign], status_code=201)
async def create_campaign(campaign: CampaignCreate, session: SessionDp):
    db_campaign = Campaign.model_validate(campaign)
    session.add(db_campaign)
    session.commit()
    session.refresh(db_campaign)
    return {"data": db_campaign}

@app.put("/campaigns/{id}", response_model=Response[Campaign])
async def update_campaign(id: int, campaign: CampaignCreate, session: SessionDp):
    data = session.get(Campaign, id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data.name = campaign.name
    data.due_date = campaign.due_date
    session.add(data)
    session.commit()
    session.refresh(data)
    return {"data": data}

@app.delete("/campaigns/{id}", status_code=204)
async def delete_campaign(id: int, session: SessionDp):
    data = session.get(Campaign, id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    session.delete(data)
    session.commit()
