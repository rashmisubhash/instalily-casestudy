"""
Part Tools - Core functions for part lookup, compatibility, and search

Updated to use AWS Bedrock Titan Embeddings (matching ingestion)

Functions:
- lookup_part: Get part details by part_id
- check_compatibility: Check if part works with model
- vector_search: Semantic search in ChromaDB using Bedrock Titan
"""

import logging
import json
import boto3
from typing import Dict, List, Optional
import chromadb
from app.core import config
from app.core.state import state

logger = logging.getLogger(__name__)


# ============================================================================
# BEDROCK CLIENT FOR EMBEDDINGS
# ============================================================================

try:
    bedrock_runtime = boto3.client(
        service_name='bedrock-runtime',
        region_name='us-east-1'  # Change to your region
    )
    logger.info("✓ Bedrock runtime client initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize Bedrock client: {e}")
    bedrock_runtime = None


# ============================================================================
# CHROMADB CLIENT (Initialize once)
# ============================================================================

try:
    CHROMA_DIR = config.CHROMA_DIR
    COLLECTION_NAME = "partselect_parts"
    
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    chroma_collection = chroma_client.get_collection(name=COLLECTION_NAME)
    
    logger.info("✓ ChromaDB initialized successfully")
    
except Exception as e:
    logger.error(f"✗ Failed to initialize ChromaDB: {e}")
    chroma_collection = None


# ============================================================================
# EMBEDDING GENERATION (BEDROCK TITAN)
# ============================================================================

def get_embedding(text: str, model_id: str = "amazon.titan-embed-text-v1") -> Optional[List[float]]:
    """
    Generate embedding using AWS Bedrock Titan
    
    Args:
        text: Text to embed
        model_id: Bedrock embedding model
                  - "amazon.titan-embed-text-v1" (1536 dimensions)
                  - "amazon.titan-embed-text-v2:0" (1024 dimensions)
    
    Returns:
        List of floats (embedding vector) or None on error
    """
    
    if not bedrock_runtime:
        logger.error("[EMBEDDING] Bedrock client not initialized")
        return None
    
    try:
        # Prepare request body
        body = json.dumps({
            "inputText": text
        })
        
        # Call Bedrock Titan Embeddings
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        embedding = response_body.get('embedding')
        
        if not embedding:
            logger.error("[EMBEDDING] No embedding in response")
            return None
        
        return embedding
        
    except Exception as e:
        logger.error(f"[EMBEDDING ERROR] {str(e)}", exc_info=True)
        return None


# ============================================================================
# PART LOOKUP
# ============================================================================

def lookup_part(part_id: str) -> Optional[Dict]:
    """
    Look up part details by part_id
    
    Args:
        part_id: Part ID (e.g., PS11752778)
        
    Returns:
        Dict with part details or None if not found
    """
    
    part_id = part_id.upper().strip()
    
    part_data = state["part_id_map"].get(part_id)
    
    if part_data:
        logger.info(f"[LOOKUP] Found part {part_id}")
        return part_data
    else:
        logger.warning(f"[LOOKUP] Part {part_id} not found")
        return None


# ============================================================================
# COMPATIBILITY CHECK
# ============================================================================

def check_compatibility(model_id: str, part_id: str) -> bool:
    """
    Check if part is compatible with model
    
    Args:
        model_id: Model number (e.g., WDT780SAEM1)
        part_id: Part ID (e.g., PS11752778)
        
    Returns:
        True if compatible, False otherwise
    """
    
    model_id = model_id.upper().strip()
    part_id = part_id.upper().strip()
    
    # Get list of compatible parts for this model
    compatible_parts = state["model_id_to_parts_map"].get(model_id, [])
    
    is_compatible = part_id in compatible_parts
    
    if is_compatible:
        logger.info(f"[COMPATIBILITY] ✓ {part_id} compatible with {model_id}")
    else:
        logger.info(f"[COMPATIBILITY] ✗ {part_id} NOT compatible with {model_id}")
    
    return is_compatible


# ============================================================================
# VECTOR SEARCH (USING BEDROCK TITAN EMBEDDINGS)
# ============================================================================

def vector_search(
    query: str, 
    top_k: int = 10,
    embedding_model: str = "amazon.titan-embed-text-v1"
) -> List[Dict]:
    """
    Semantic search using ChromaDB with Bedrock Titan embeddings
    
    IMPORTANT: Use the SAME embedding model that was used during ingestion!
    
    Args:
        query: Search query (e.g., "ice maker not working")
        top_k: Number of results to return
        embedding_model: Bedrock model ID
                        - "amazon.titan-embed-text-v1" (1536 dims) - DEFAULT
                        - "amazon.titan-embed-text-v2:0" (1024 dims)
    
    Returns:
        List of part dictionaries with similarity scores
    """
    
    if not chroma_collection:
        logger.error("[VECTOR_SEARCH] ChromaDB not initialized")
        return []
    
    if not bedrock_runtime:
        logger.error("[VECTOR_SEARCH] Bedrock client not initialized")
        return []
    
    try:
        # Step 1: Generate query embedding using Bedrock Titan
        logger.info(f"[VECTOR_SEARCH] Generating embedding for query: '{query}'")
        query_embedding = get_embedding(query, model_id=embedding_model)
        
        if not query_embedding:
            logger.error("[VECTOR_SEARCH] Failed to generate embedding")
            return []
        
        # Step 2: Query ChromaDB with the embedding vector
        results = chroma_collection.query(
            query_embeddings=[query_embedding],  # Use embedding, not text
            n_results=top_k
        )
        
        # Step 3: Parse results
        parts = []
        
        if results and results.get("documents"):
            documents = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            for i, doc in enumerate(documents):
                metadata = metadatas[i] if i < len(metadatas) else {}
                distance = distances[i] if i < len(distances) else 1.0
                
                # Parse document text to extract fields
                part_data = _parse_document(doc, metadata)
                
                # Add similarity score (convert distance to similarity)
                # Cosine distance: 0 = identical, 2 = opposite
                # Convert to similarity: 1 - (distance/2)
                part_data["similarity_score"] = max(0.0, 1.0 - (distance / 2.0))
                part_data["distance"] = distance  # Keep raw distance too
                
                parts.append(part_data)
        
        logger.info(f"[VECTOR_SEARCH] Query: '{query}' → {len(parts)} results")
        
        return parts
        
    except Exception as e:
        logger.error(f"[VECTOR_SEARCH ERROR] {str(e)}", exc_info=True)
        return []


def _parse_document(doc_text: str, metadata: Dict) -> Dict:
    """
    Parse ChromaDB document text into structured dict
    
    Document format from ingestion:
        Title: ...
        Description: ...
        Symptoms: ...
        Part ID: ...
        Brand: ...
        Installation: ...
        Related Parts: ...
        Replacement Parts: ...
        URL: ...
    """
    
    part_data = {}
    
    # Extract from metadata (more reliable)
    part_data["part_id"] = metadata.get("part_id", "")
    part_data["brand"] = metadata.get("brand", "")
    part_data["product_types"] = metadata.get("product_types", "")
    part_data["symptoms"] = metadata.get("symptoms", "")
    
    # Parse document text for remaining fields
    lines = doc_text.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        
        if ":" not in line:
            continue
        
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()
        
        if value and value != "N/A":
            part_data[key] = value
    
    # Enrich with data from part_id_map if available
    part_id = part_data.get("part_id")
    if part_id and part_id in state["part_id_map"]:
        full_data = state["part_id_map"][part_id]
        # Merge, but don't overwrite parsed data
        for k, v in full_data.items():
            if k not in part_data or not part_data[k]:
                part_data[k] = v
    
    return part_data


# ============================================================================
# ALTERNATIVE PARTS SEARCH
# ============================================================================

def find_similar_parts(
    part_id: str, 
    limit: int = 5,
    embedding_model: str = "amazon.titan-embed-text-v1"
) -> List[Dict]:
    """
    Find similar parts using vector similarity
    
    Args:
        part_id: Original part ID
        limit: Max number of similar parts
        embedding_model: Bedrock model ID (must match ingestion)
        
    Returns:
        List of similar parts
    """
    
    # Get original part
    original = state["part_id_map"].get(part_id)
    
    if not original:
        logger.warning(f"[SIMILAR_PARTS] Part {part_id} not found")
        return []
    
    # Build search query from original part
    query = f"{original.get('title', '')} {original.get('symptoms', '')}"
    
    # Search
    results = vector_search(query, top_k=limit + 1, embedding_model=embedding_model)
    
    # Filter out the original part
    similar = [p for p in results if p.get("part_id") != part_id]
    
    return similar[:limit]


# ============================================================================
# SYMPTOM-BASED SEARCH
# ============================================================================

def search_by_symptom(
    symptom: str,
    appliance: Optional[str] = None,
    brand: Optional[str] = None,
    top_k: int = 10,
    embedding_model: str = "amazon.titan-embed-text-v1"
) -> List[Dict]:
    """
    Search parts by symptom with optional filters
    
    Args:
        symptom: Problem description
        appliance: Appliance type (refrigerator, dishwasher)
        brand: Brand name (Whirlpool, GE, etc.)
        top_k: Max results
        embedding_model: Bedrock model ID (must match ingestion)
        
    Returns:
        List of relevant parts
    """
    
    # Build enhanced query
    query_parts = [symptom]
    
    if appliance:
        query_parts.append(appliance)
    
    if brand:
        query_parts.append(brand)
    
    query = " ".join(query_parts)
    
    # Search using vector similarity
    results = vector_search(query, top_k=top_k, embedding_model=embedding_model)
    
    # Post-filter by appliance/brand if specified
    # (Vector search already considers these, but we can be more strict)
    if appliance or brand:
        filtered = []
        for part in results:
            product_types = part.get("product_types", "").lower()
            part_brand = part.get("brand", "").lower()
            
            # Check appliance match
            appliance_match = True
            if appliance:
                appliance_match = appliance.lower() in product_types
            
            # Check brand match
            brand_match = True
            if brand:
                brand_match = brand.lower() in part_brand
            
            if appliance_match and brand_match:
                filtered.append(part)
        
        return filtered
    
    return results


# ============================================================================
# BATCH OPERATIONS
# ============================================================================

def lookup_parts_batch(part_ids: List[str]) -> List[Dict]:
    """
    Look up multiple parts at once
    
    Args:
        part_ids: List of part IDs
        
    Returns:
        List of part data dicts
    """
    
    parts = []
    
    for part_id in part_ids:
        part = lookup_part(part_id)
        if part:
            parts.append(part)
    
    return parts


def check_compatibility_batch(
    model_id: str, 
    part_ids: List[str]
) -> Dict[str, bool]:
    """
    Check compatibility for multiple parts at once
    
    Args:
        model_id: Model number
        part_ids: List of part IDs
        
    Returns:
        Dict mapping part_id → compatible (bool)
    """
    
    results = {}
    
    for part_id in part_ids:
        results[part_id] = check_compatibility(model_id, part_id)
    
    return results


# ============================================================================
# UTILITY: TEST EMBEDDING CONNECTION
# ============================================================================

def test_embedding_connection() -> bool:
    """
    Test if Bedrock embeddings are working
    
    Returns:
        True if working, False otherwise
    """
    
    try:
        test_text = "test refrigerator ice maker"
        embedding = get_embedding(test_text)
        
        if embedding and len(embedding) > 0:
            logger.info(f"✓ Embedding test successful (dimension: {len(embedding)})")
            return True
        else:
            logger.error("✗ Embedding test failed - no embedding returned")
            return False
            
    except Exception as e:
        logger.error(f"✗ Embedding test failed: {e}")
        return False


# ============================================================================
# UTILITY: GET EMBEDDING MODEL INFO
# ============================================================================

def get_embedding_model_info(model_id: str = "amazon.titan-embed-text-v1") -> Dict:
    """
    Get information about the embedding model
    
    Returns:
        Dict with model info
    """
    
    model_specs = {
        "amazon.titan-embed-text-v1": {
            "dimensions": 1536,
            "max_tokens": 8192,
            "description": "Titan Embeddings V1"
        },
        "amazon.titan-embed-text-v2:0": {
            "dimensions": 1024,
            "max_tokens": 8192,
            "description": "Titan Embeddings V2"
        }
    }
    
    info = model_specs.get(model_id, {
        "dimensions": "unknown",
        "max_tokens": "unknown",
        "description": model_id
    })
    
    info["model_id"] = model_id
    info["available"] = bedrock_runtime is not None
    
    return info


# ============================================================================
# AUTO-TEST ON IMPORT
# ============================================================================

# Test embedding connection when module loads
if bedrock_runtime and chroma_collection:
    logger.info("Testing Bedrock Titan embeddings...")
    if test_embedding_connection():
        logger.info("✓ part_tools ready with Bedrock Titan embeddings")
    else:
        logger.warning("⚠ Embedding test failed - vector search may not work")
else:
    logger.warning("⚠ Bedrock or ChromaDB not initialized - some features disabled")