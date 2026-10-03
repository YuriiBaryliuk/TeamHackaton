"""Pydantic models: the shapes of our JSON. FastAPI uses them for validation and for /docs."""
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "low", "empty", "unknown"]
Confidence = Literal["fresh", "faded", "stale", "none"]
EventType = Literal["took", "empty", "refilled"]
EventSource = Literal["qr", "geo", "steward", "partner"]
Access = Literal["open", "ask_staff", "students_only"]


# ---------- points ----------

class Point(BaseModel):
    id: str
    name: str
    kind: str
    lat: float
    lon: float
    address: str | None
    access: Access
    entry_fee_pln: float
    opening_hours: dict
    open_now: bool
    wheelchair: bool
    has_products: bool
    has_qr: bool
    is_demo: bool
    # computed by app/status.py
    status: Status
    confidence: Confidence
    last_confirmed_at: str | None
    minutes_since_confirmed: int | None
    takes_since_refill: int


class PointList(BaseModel):
    city: str
    generated_at: str        # lets the offline map say "data from HH:MM"
    has_demo_data: bool      # the UI shows a "demo data" note when true
    points: list[Point]


# ---------- events ----------

class EventIn(BaseModel):
    type: EventType
    source: EventSource = "qr"
    # Only for source='geo'. Checked against the point, never stored.
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)

    model_config = {"json_schema_extra": {"examples": [{"type": "took", "source": "qr"}]}}


class EventOut(BaseModel):
    saved: bool
    type: EventType
    point: Point             # the point with its NEW status


class ApiError(BaseModel):
    """Error body. `code` is stable so the frontend can translate it."""
    code: str
    message: str
    retry_after_s: int | None = None


class ErrorResponse(BaseModel):
    detail: ApiError


# ---------- city dashboard ----------

class Kpis(BaseModel):
    boxes: int                              # points known to host a box
    active_boxes: int                       # boxes with at least one mark in the period
    fresh_pct: int                          # % of boxes confirmed in the last 24 h
    takes: int                              # "took" marks in the period
    median_empty_to_refill_h: float | None  # how long a box stays empty, median
    searches: int                           # Urgent searches in the period
    searches_not_found: int                 # ... with nothing within 10 min walk


class WhiteSpot(BaseModel):
    lat: float
    lon: float
    count: int                              # searches that found nothing nearby
    searches: int                           # all searches in this grid cell
    near: str | None                        # nearest known point, as a landmark


class BoxStats(BaseModel):
    id: str
    name: str
    kind: str
    lat: float
    lon: float
    status: Status
    confidence: Confidence
    is_demo: bool
    takes: int
    empties: int
    refills: int
    cycles: int                             # refill -> empty cycles in the period
    avg_refill_to_empty_h: float | None     # how fast it runs out
    avg_empty_to_refill_h: float | None     # how long people wait for a refill


class CityStats(BaseModel):
    city: str
    days: int
    generated_at: str
    has_demo_data: bool
    kpis: Kpis
    white_spots: list[WhiteSpot]
    boxes: list[BoxStats]                   # fastest-emptying first


# ---------- urgent ----------

class UrgentIn(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

    model_config = {"json_schema_extra": {"examples": [{"lat": 50.0617, "lon": 19.9373}]}}


class Routes(BaseModel):
    osm: str
    google: str
    apple: str


class UrgentPlace(BaseModel):
    id: str
    name: str
    kind: str
    address: str | None
    lat: float
    lon: float
    status: Status
    minutes_since_confirmed: int | None
    distance_m: int
    walking_min: float
    entry_fee_pln: float
    access: Access
    open_now: bool
    open_24_7: bool
    routes: Routes


class UrgentOut(BaseModel):
    found: bool                      # a fresh, in-stock, open point within 10 minutes' walk
    night: bool                      # 22:00-06:00 Warsaw: 24/7 places ranked first
    best: UrgentPlace | None         # may be further than 10 min when found is false
    alternatives: list[UrgentPlace]
    fallback: UrgentPlace | None     # nearest pharmacy/shop when found is false
    nearest_min: float | None
