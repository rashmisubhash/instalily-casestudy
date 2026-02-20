"""
State Management - Load and manage global state

Loads:
- part_id_map.json: part_id → part details
- model_id_to_parts_map.json: model_id → [part_ids]
"""

import json
import logging
from pathlib import Path
from typing import Dict, List
from app.core import config

logger = logging.getLogger(__name__)


# ============================================================================
# GLOBAL STATE
# ============================================================================

state: Dict = {
    "part_id_map": {},
    "model_id_to_parts_map": {},
    "loaded": False
}


# ============================================================================
# LOAD STATE
# ============================================================================

def load_state(
    part_id_map_path: str = config.PART_ID_MAP_PATH,
    model_to_parts_map_path: str = config.MODEL_ID_TO_PARTS_MAP_PATH
):

    """Load JSON maps into global state"""
    
    global state
    
    logger.info("Loading state...")
    
    try:
        # Get absolute paths
        import os
        base_dir = os.getcwd()
        
        part_path = os.path.join(base_dir, part_id_map_path)
        model_path = os.path.join(base_dir, model_to_parts_map_path)
        
        logger.info(f"Looking for part_id_map at: {part_path}")
        logger.info(f"Looking for model_to_parts_map at: {model_path}")
        
        # Load part_id_map
        with open(part_path, "r") as f:
            part_id_map = json.load(f)
            state["part_id_map"] = part_id_map
            logger.info(f"✓ Loaded {len(part_id_map)} parts from {part_id_map_path}")
        
        # Load model_to_parts_map
        with open(model_path, "r") as f:
            model_to_parts_map = json.load(f)
            state["model_id_to_parts_map"] = model_to_parts_map
            logger.info(f"✓ Loaded {len(model_to_parts_map)} models from {model_to_parts_map_path}")
        
        state["loaded"] = True
        logger.info("✓ State loaded successfully")
        
    except FileNotFoundError as e:
        logger.error(f"✗ File not found: {e}")
        logger.error(f"Current directory: {os.getcwd()}")
        logger.error(f"Files in current directory: {os.listdir('.')}")
        raise
def reload_state():
    """Reload state (useful for development)"""
    
    load_state()


def get_state() -> Dict:
    """Get current state"""
    
    if not state["loaded"]:
        logger.warning("State not loaded! Call load_state() first")
    
    return state


# ============================================================================
# STATE QUERIES
# ============================================================================

def get_part(part_id: str) -> Dict:
    """Get part by ID"""
    
    return state["part_id_map"].get(part_id.upper())


def get_model_parts(model_id: str) -> List[str]:
    """Get all compatible part IDs for a model"""
    
    return state["model_id_to_parts_map"].get(model_id.upper(), [])


def part_exists(part_id: str) -> bool:
    """Check if part exists"""
    
    return part_id.upper() in state["part_id_map"]


def model_exists(model_id: str) -> bool:
    """Check if model exists"""
    
    return model_id.upper() in state["model_id_to_parts_map"]


# ============================================================================
# STATISTICS
# ============================================================================

def get_stats() -> Dict:
    """Get state statistics"""
    
    return {
        "total_parts": len(state["part_id_map"]),
        "total_models": len(state["model_id_to_parts_map"]),
        "loaded": state["loaded"]
    }


# ============================================================================
# AUTO-LOAD ON IMPORT
# ============================================================================

# Automatically load state when module is imported
try:
    load_state()
except Exception as e:
    logger.error(f"Failed to auto-load state: {e}")
    logger.error("You can manually load with: from app.core.state import load_state; load_state()")