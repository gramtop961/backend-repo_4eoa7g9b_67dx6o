import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from bson import ObjectId

app = FastAPI(title="BMW ELV Tracking API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------
class CreateVehiclePayload(BaseModel):
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine_condition: Optional[str] = "unknown"
    body_condition: Optional[str] = "unknown"
    damage_level: Optional[str] = "unknown"
    photos: Optional[List[str]] = None
    last_known_location: Optional[Dict[str, Any]] = None
    owner_id: Optional[str] = None
    status: Optional[str] = "unknown"


class EventPayload(BaseModel):
    vehicle_id: Optional[str] = None
    event_type: str
    actor_id: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    location: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = None


class PartPayload(BaseModel):
    vehicle_id: Optional[str] = None
    name: str
    serial_number: Optional[str] = None
    condition: Optional[str] = "unknown"
    location: Optional[str] = None
    price_etb: Optional[float] = None


class Mutation(BaseModel):
    op: str
    data: Dict[str, Any]
    client_id: str
    client_timestamp: datetime


class SyncEnvelope(BaseModel):
    mutations: List[Mutation]


def _serialize(doc: Dict[str, Any]):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert nested ObjectIds if any
    for k, v in d.items():
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


@app.get("/")
def read_root():
    return {"message": "BMW ELV Tracking Backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# ---------- Vehicles ----------
@app.post("/api/vehicles")
def create_vehicle(payload: CreateVehiclePayload):
    data = payload.model_dump(exclude_none=True)
    inserted_id = create_document("vehicle", data)
    vehicle = db["vehicle"].find_one({"_id": ObjectId(inserted_id)})
    return _serialize(vehicle)


@app.get("/api/vehicles")
def list_vehicles(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    filt: Dict[str, Any] = {}
    if status:
        filt["status"] = status
    docs = get_documents("vehicle", filt, limit)
    return [_serialize(d) for d in docs]


@app.get("/api/vehicles/{vehicle_id}/history")
def get_vehicle_history(vehicle_id: str):
    try:
        vids = ObjectId(vehicle_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid vehicle id")
    events = db["event"].find({"vehicle_id": str(vids)}).sort("occurred_at", 1)
    return [_serialize(e) for e in events]


# ---------- Events ----------
@app.post("/api/events")
def log_event(payload: EventPayload):
    data = payload.model_dump(exclude_none=True)
    # default occurred_at to now if missing
    data.setdefault("occurred_at", datetime.now(timezone.utc))
    inserted_id = create_document("event", data)
    ev = db["event"].find_one({"_id": ObjectId(inserted_id)})
    # side-effect: update vehicle status for certain events when possible
    if data.get("vehicle_id") and data.get("event_type") in {"dismantling", "scrap"}:
        db["vehicle"].update_one(
            {"_id": ObjectId(data["vehicle_id"])},
            {"$set": {"status": "dismantled" if data["event_type"] == "dismantling" else "scrapped", "updated_at": datetime.now(timezone.utc)}},
        )
    return _serialize(ev)


# ---------- Parts ----------
@app.post("/api/parts")
def register_part(payload: PartPayload):
    data = payload.model_dump(exclude_none=True)
    inserted_id = create_document("part", data)
    part = db["part"].find_one({"_id": ObjectId(inserted_id)})
    return _serialize(part)


# ---------- Sync (Offline batch) ----------
@app.post("/api/sync")
def sync(envelope: SyncEnvelope):
    results: List[Dict[str, Any]] = []
    for m in sorted(envelope.mutations, key=lambda x: x.client_timestamp):
        op = m.op
        data = m.data
        try:
            if op == "createVehicle":
                inserted_id = create_document("vehicle", data)
                results.append({"op": op, "status": "ok", "id": inserted_id})
            elif op == "logEvent":
                data.setdefault("occurred_at", datetime.now(timezone.utc))
                inserted_id = create_document("event", data)
                results.append({"op": op, "status": "ok", "id": inserted_id})
            elif op == "registerPart":
                inserted_id = create_document("part", data)
                results.append({"op": op, "status": "ok", "id": inserted_id})
            else:
                results.append({"op": op, "status": "ignored", "reason": "unknown op"})
        except Exception as e:
            results.append({"op": op, "status": "error", "error": str(e)})
    return {"results": results, "server_time": datetime.now(timezone.utc)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
