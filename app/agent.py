# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from .a2ui_utils import a2ui_callback

# Load local environment variables from .env if present
load_dotenv()

MODEL = "gemini-2.5-flash"

# IMPORTANT: Hardcoded Project ID & Bucket Name strings (required on Agent Platform)
PROJECT_ID = "qwiklabs-gcp-01-cb4e8877ebdc"
GCS_BUCKET_NAME = "wandermind-media-qwiklabs-gcp-01-cb4e8877ebdc"

# Initialize Firestore, Storage, and GenAI clients
db = firestore.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)
genai_client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location="global",
)

# Load Agent Engine resource name from deployment_metadata.json if available
deployment_metadata_path = os.path.join(
    os.path.dirname(__file__), "..", "deployment_metadata.json"
)
agent_engine_resource_name = None
if os.path.exists(deployment_metadata_path):
    try:
        with open(deployment_metadata_path, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
    except Exception as e:
        print(f"Warning: Could not read deployment_metadata.json: {e}")

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)


def search_destinations(city: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search travel destinations stored in Firestore database.

    Args:
        city: Optional city name to filter by (e.g., 'Kyoto', 'Paris', 'Tokyo', 'New York', 'Barcelona').
        category: Optional category filter (e.g., 'Culture & Nature', 'Sightseeing & Romance', 'City Life & Shopping').

    Returns:
        List of destination dictionaries matching search criteria.
    """
    collection_ref = db.collection("destinations")
    docs = collection_ref.stream()
    
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        
        # Filtering logic
        if city and city.lower() not in data.get("city", "").lower() and city.lower() not in data.get("country", "").lower():
            continue
        if category and category.lower() not in data.get("category", "").lower():
            continue
            
        results.append(data)
        
    return results


def get_destination_details(destination_id: str) -> Dict[str, Any]:
    """Retrieve full details for a specific travel destination from Firestore.

    Args:
        destination_id: Document ID of the destination (e.g., 'dest_kyoto', 'dest_paris').

    Returns:
        Dictionary containing destination details or an error dictionary.
    """
    doc_ref = db.collection("destinations").document(destination_id)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return {"error": f"Destination with ID '{destination_id}' not found."}


def add_destination(
    name: str,
    city: str,
    country: str,
    category: str,
    description: str,
    price_range: str = "$$",
    rating: float = 4.8
) -> Dict[str, Any]:
    """Add a new travel destination to the Firestore catalog.

    Args:
        name: Name of the destination/attraction.
        city: City where the destination is located.
        country: Country where the destination is located.
        category: Category/theme of the destination (e.g., 'Beach', 'Culture', 'Food').
        description: A brief summary describing the destination.
        price_range: Price level indicator ('$', '$$', '$$$', '$$$$'). Defaults to '$$'.
        rating: Rating out of 5.0. Defaults to 4.8.

    Returns:
        Dictionary with status message and newly created document ID.
    """
    doc_id = f"dest_{city.lower().replace(' ', '_')}_{name.lower().replace(' ', '_')[:10]}"
    doc_data = {
        "id": doc_id,
        "name": name,
        "city": city,
        "country": country,
        "category": category,
        "description": description,
        "price_range": price_range,
        "rating": rating
    }
    
    db.collection("destinations").document(doc_id).set(doc_data)
    return {"status": "success", "message": f"Successfully saved destination '{name}' to Firestore.", "id": doc_id}


def get_live_weather(location: str) -> Dict[str, Any]:
    """Fetch real-time weather information and temperature for any city or destination worldwide.

    Args:
        location: Name of the city or destination (e.g., 'Kyoto', 'Paris', 'Tokyo', 'New York').

    Returns:
        Dictionary containing real-time weather condition, temperature in Fahrenheit and Celsius, and humidity.
    """
    try:
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            curr = data["current_condition"][0]
            condition = curr["weatherDesc"][0]["value"]
            temp_f = curr["temp_F"]
            temp_c = curr["temp_C"]
            humidity = curr["humidity"]
            return {
                "location": location,
                "condition": condition,
                "temperature_f": f"{temp_f}°F",
                "temperature_c": f"{temp_c}°C",
                "humidity": f"{humidity}%",
            }
    except Exception as e:
        return {"location": location, "error": f"Unable to fetch live weather: {str(e)}"}


def get_exchange_rates(base_currency: str = "USD", target_currencies: str = "EUR,JPY,GBP") -> Dict[str, Any]:
    """Fetch live foreign currency exchange rates for travel budget calculations using Frankfurter Open API.

    Args:
        base_currency: The base 3-letter currency code (e.g., 'USD', 'EUR', 'GBP', 'JPY'). Defaults to 'USD'.
        target_currencies: Comma-separated target currency codes (e.g., 'EUR,JPY,GBP').

    Returns:
        Dictionary containing base currency, exchange rates map, and publication date.
    """
    try:
        base = base_currency.strip().upper()
        targets = target_currencies.strip().upper()
        api_key = os.getenv("EXCHANGE_RATE_API_KEY")
        url = f"https://api.frankfurter.app/latest?from={base}&to={targets}"
        headers = {"User-Agent": "WandermindTravelApp/1.0"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "base": data.get("base", base),
                "date": data.get("date"),
                "rates": data.get("rates", {}),
            }
    except Exception as e:
        return {"error": f"Unable to fetch exchange rates for {base_currency}: {str(e)}"}


def geocode_address(address: str) -> Dict[str, Any]:
    """Convert an address or location name into latitude and longitude coordinates using Google Geocoding API.

    Args:
        address: The address or location name to geocode (e.g., 'Eiffel Tower, Paris' or 'Fushimi Inari, Kyoto').

    Returns:
        Dictionary containing formatted address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not set in .env."}

    try:
        encoded_address = urllib.parse.quote(address)
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "WandermindTravelApp/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "OK" and data.get("results"):
                res = data["results"][0]
                loc = res["geometry"]["location"]
                return {
                    "formatted_address": res.get("formatted_address"),
                    "location": {
                        "latitude": loc.get("lat"),
                        "longitude": loc.get("lng"),
                    },
                }
            return {"error": f"Geocoding failed for address '{address}': {data.get('status')}"}
    except Exception as e:
        return {"error": f"Geocoding request error: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 1000.0,
) -> Dict[str, Any]:
    """Find nearby places of a given type around a latitude/longitude using Google Places API (New).

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Type of place to search for (e.g., 'restaurant', 'tourist_attraction', 'museum', 'cafe', 'lodging').
        radius_meters: Search radius in meters (default 1000m).

    Returns:
        Dictionary containing list of nearby places with name, formatted address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not set in .env."}

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        payload = {
            "includedTypes": [place_type],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_meters),
                }
            },
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        }
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            places = []
            for place in data.get("places", []):
                name = place.get("displayName", {}).get("text", "Unknown")
                address = place.get("formattedAddress", "")
                loc = place.get("location", {})
                places.append({
                    "name": name,
                    "address": address,
                    "location": {
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                    },
                })
            return {"place_type": place_type, "count": len(places), "places": places}
    except Exception as e:
        return {"error": f"Nearby places search error: {str(e)}"}


def generate_destination_postcard(
    tool_context: ToolContext,
    destination_name: str,
    visual_description: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a scenic travel postcard image for a destination using Gemini Image Generation model.

    Saves the generated image to Playground Artifacts and uploads it to public GCS storage.

    Args:
        tool_context: ADK tool execution context for saving artifacts.
        destination_name: Name of the travel destination (e.g., 'Kyoto Bamboo Forest', 'Eiffel Tower at Sunset').
        visual_description: Optional additional visual details (e.g., 'vibrant autumn colors, sunset glow').

    Returns:
        Dictionary containing destination, public GCS image URL, and status.
    """
    try:
        prompt = f"A stunning travel postcard of {destination_name}."
        if visual_description:
            prompt += f" Details: {visual_description}."

        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": f"Failed to generate image bytes for {destination_name}."}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = destination_name.lower().replace(" ", "_")[:20]
        ext = "jpg" if "jpeg" in mime_type else "png"
        filename = f"postcard_{safe_name}_{timestamp}.{ext}"

        # 1. Save artifact to ADK tool_context (Playground Artifacts panel)
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload image bytes to public Cloud Storage bucket
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "destination": destination_name,
            "filename": filename,
            "image_url": public_url,
            "message": f"Successfully generated postcard for {destination_name}."
        }
    except Exception as e:
        return {"error": f"Image generation error for {destination_name}: {str(e)}"}


def generate_destination_video(
    tool_context: ToolContext,
    destination_name: str,
    scene_description: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a short travel video for a destination using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the generated video to Playground Artifacts and uploads it to public Cloud Storage.

    Args:
        tool_context: ADK tool execution context for saving artifacts.
        destination_name: Name of the travel destination or attraction (e.g., 'Kyoto Bamboo Forest', 'Eiffel Tower', 'Santorini').
        scene_description: Optional description of the video scene (e.g., 'gentle breeze swaying trees at sunrise').

    Returns:
        Dictionary containing destination name, public GCS video URL, and status.
    """
    try:
        prompt = f"A short 3-second travel video of {destination_name}."
        if scene_description:
            prompt += f" Scene details: {scene_description}."

        video_bytes = None
        mime_type = "video/mp4"

        # 1. Call gemini-omni-flash-preview model in global region via Interactions API
        try:
            import base64
            import google.auth
            import google.auth.transport.requests

            credentials, _ = google.auth.default()
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)
            token = credentials.token

            url = f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/global/interactions"
            payload = {
                "model": "gemini-omni-flash-preview",
                "input": [{"type": "text", "text": prompt}],
                "response_format": [{"type": "video"}]
            }
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            })
            with urllib.request.urlopen(req, timeout=120) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))

            def extract_bytes(obj):
                if isinstance(obj, dict):
                    if "bytes" in obj and isinstance(obj["bytes"], str):
                        try: return base64.b64decode(obj["bytes"])
                        except Exception: pass
                    if "data" in obj and isinstance(obj["data"], str):
                        try: return base64.b64decode(obj["data"])
                        except Exception: pass
                    if "b64_data" in obj and isinstance(obj["b64_data"], str):
                        try: return base64.b64decode(obj["b64_data"])
                        except Exception: pass
                    if "gcs_uri" in obj or "uri" in obj:
                        uri = obj.get("gcs_uri") or obj.get("uri")
                        if uri and uri.startswith("gs://"):
                            p = uri[5:].split("/", 1)
                            return storage_client.bucket(p[0]).blob(p[1]).download_as_bytes()
                    for v in obj.values():
                        res = extract_bytes(v)
                        if res: return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = extract_bytes(item)
                        if res: return res
                return None

            video_bytes = extract_bytes(res_data)
        except Exception as e:
            print(f"Interactions API video call warning: {e}")

        if not video_bytes:
            # Try SDK fallback
            try:
                res = genai_client.interactions.create(
                    model="gemini-omni-flash-preview",
                    input=prompt,
                    response_format=[{"type": "video"}]
                )
                if hasattr(res, "model_dump"):
                    video_bytes = extract_bytes(res.model_dump())
            except Exception as e:
                return {"error": f"Failed to generate video for {destination_name}: {str(e)}"}

        if not video_bytes:
            return {"error": f"Failed to retrieve generated video bytes for {destination_name}."}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = destination_name.lower().replace(" ", "_")[:20]
        filename = f"video_{safe_name}_{timestamp}.mp4"

        # (1) Save video artifact with tool_context.save_artifact (shows in Playground Artifacts)
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload video bytes to public Cloud Storage bucket
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "destination": destination_name,
            "filename": filename,
            "video_url": public_url,
            "message": f"Successfully generated video for {destination_name}."
        }
    except Exception as e:
        return {"error": f"Video generation error for {destination_name}: {str(e)}"}


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: City name.

    Returns:
        Current time string.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    elif "tokyo" in query.lower() or "kyoto" in query.lower():
        tz_identifier = "Asia/Tokyo"
    elif "paris" in query.lower():
        tz_identifier = "Europe/Paris"
    else:
        tz_identifier = "UTC"

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# Memory Bank Service configuration (for deployment)
MEMORY_BANK_ID = "2195071610761773056"
memory_service = VertexAiMemoryBankService(
    project=PROJECT_ID,
    location="us-east1",
    agent_engine_id=MEMORY_BANK_ID,
)


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback to extract durable user facts and preferences to Memory Bank after each turn."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Wandermind, an expert Travel Concierge AI assistant. "
        "You help users explore travel destinations, check real-time weather, convert foreign currency, "
        "geocode addresses, search nearby attractions/restaurants with Google Maps, "
        "generate visual destination postcards, generate short travel videos using Google's Omni model, view travel details, and manage saved recommendations in Firestore database. "
        "You can also execute Python code safely in a sandbox environment for data processing, complex calculations, and analysis. "
        "IMPORTANT: You remember user facts, health requirements, and ALLERGIES (such as dietary restrictions, food allergies, peanut, gluten, shellfish, or medical allergies) across user sessions. "
        "Always tailor dining, restaurant, activity, and travel recommendations to strictly respect and accommodate all of the user's remembered allergies and preferences. "
        "Always recommend destinations stored in Firestore when queried about travel locations."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="simple_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        add_destination,
        get_live_weather,
        get_exchange_rates,
        geocode_address,
        find_nearby_places,
        generate_destination_postcard,
        generate_destination_video,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
