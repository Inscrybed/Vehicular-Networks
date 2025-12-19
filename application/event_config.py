# event_config.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import time
import uuid

class EventType(Enum):
    ROAD_SURFACE_HAZARD = "road_surface_hazard"
    VEHICLE_BREAKDOWN = "vehicle_breakdown"
    WEATHER_HAZARD = "weather_hazard"
    TRAFFIC_CONDITION = "traffic_condition"
    ROADWORKS = "roadworks"

class HazardSubType(Enum):
    POTHOLES = "potholes"
    FLOODING = "flooding"
    ICE = "ice"
    DEBRIS = "debris"
    OIL_SPILL = "oil_spill"
    FOG = "fog"
    HAIL = "hail"
    ACCIDENT = "accident"

class EventStatus(Enum):
    START = "start"
    UPDATE = "update"
    STOP = "stop"

@dataclass
class EventConfig:
    """Dynamic event configuration"""
    event_id: str  # Unique identifier for this specific event instance
    event_type: EventType
    hazard_subtype: Optional[HazardSubType] = None
    status: EventStatus = EventStatus.START
    repetition_interval: int = 3  # 0 for single event
    max_hops: int = 8
    roi_x: int = 0
    roi_y: int = 0
    max_latency: int = 10000
    # Extended hazard-specific fields
    severity: int = 1  # 1-5 scale
    confidence: float = 0.0  # 0.0-1.0
    dimensions: Optional[Dict[str, float]] = None  # width, length, depth
    location: Optional[Dict[str, float]] = None  # GPS coordinates
    timestamp: float = 0.0
    source_vehicle: Optional[str] = None
    
    @classmethod
    def create_hazard_event(cls, 
                           event_type: EventType,
                           hazard_subtype: HazardSubType,
                           severity: int,
                           confidence: float,
                           location: Dict[str, float],
                           dimensions: Dict[str, float] = None,
                           source_vehicle: str = None):
        """Factory method for creating hazard events"""
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            hazard_subtype=hazard_subtype,
            severity=severity,
            confidence=confidence,
            location=location,
            dimensions=dimensions or {},
            source_vehicle=source_vehicle,
            timestamp=time.time()
        )
    
