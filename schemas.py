"""
Database Schemas for BMW ELV Tracking

Each Pydantic model represents a MongoDB collection (collection name is the lowercase class name).
The data model is designed to accept incomplete or uncertain data. Optional fields are allowed and
unknown values can be represented via enums that include "unknown".
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime

# ---------- Users ----------
class User(BaseModel):
    role: Literal["importer", "mechanic", "scrapyard_owner", "market_seller", "admin"] = Field(
        ..., description="User role"
    )
    name: str = Field(..., description="Full name")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    organization: Optional[str] = Field(None, description="Company or organization")
    is_active: bool = Field(True, description="Whether the user account is active")

# ---------- Vehicles ----------
ConditionLevel = Literal["good", "fair", "poor", "unknown"]
DamageLevel = Literal["none", "minor", "moderate", "severe", "unknown"]
VehicleStatus = Literal[
    "imported", "active", "dismantled", "scrapped", "sold", "unknown"
]

class Vehicle(BaseModel):
    vin: Optional[str] = Field(None, description="Vehicle Identification Number (may be missing)")
    make: Optional[str] = Field(None, description="Vehicle make")
    model: Optional[str] = Field(None, description="Vehicle model")
    year: Optional[int] = Field(None, description="Manufacture year")
    engine_condition: Optional[ConditionLevel] = Field(
        "unknown", description="Engine condition"
    )
    body_condition: Optional[ConditionLevel] = Field(
        "unknown", description="Body condition"
    )
    damage_level: Optional[DamageLevel] = Field(
        "unknown", description="Overall damage level"
    )
    photos: Optional[List[HttpUrl]] = Field(default=None, description="Photo URLs")
    last_known_location: Optional[Dict[str, Any]] = Field(
        default=None, description="GeoJSON-like object or simple lat/lng"
    )
    owner_id: Optional[str] = Field(None, description="Current owner user id")
    status: VehicleStatus = Field("unknown", description="Lifecycle status")

# ---------- Parts ----------
PartCondition = Literal["new", "used", "damaged", "unknown"]

class Part(BaseModel):
    vehicle_id: Optional[str] = Field(None, description="Related vehicle id")
    name: str = Field(..., description="Part name (e.g., engine, door)")
    serial_number: Optional[str] = Field(None, description="Part serial number")
    condition: PartCondition = Field("unknown", description="Part condition")
    location: Optional[str] = Field(None, description="Where the part is stored")
    price_etb: Optional[float] = Field(None, description="Price in ETB")

# ---------- Events ----------
EventType = Literal[
    "ownership_change",
    "dismantling",
    "recycling",
    "scrap",
    "inspection",
    "location_update",
    "note",
]

class Event(BaseModel):
    vehicle_id: Optional[str] = Field(None, description="Related vehicle id")
    event_type: EventType = Field(..., description="Type of event")
    actor_id: Optional[str] = Field(None, description="User who performed the action")
    notes: Optional[str] = Field(None, description="Free text notes")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Arbitrary key-values for flexible data"
    )
    location: Optional[Dict[str, Any]] = Field(
        default=None, description="Location at time of event"
    )
    occurred_at: Optional[datetime] = Field(
        None, description="Client-side timestamp for offline sync"
    )

# ---------- SyncEnvelope (for offline batch sync) ----------
class Mutation(BaseModel):
    op: Literal["createVehicle", "logEvent", "registerPart"]
    data: Dict[str, Any]
    client_id: str
    client_timestamp: datetime

class SyncEnvelope(BaseModel):
    mutations: List[Mutation]
