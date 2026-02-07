import base64
print("--- LOADING main_openai_search.py ---")
import logging
import json
import os
import requests
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import openai

# --- CONFIGURATION ---
load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
LINKUP_API_KEY = os.getenv("LINKUP_API_KEY") # Restore LinkUp Key
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")

if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found.")
if not APPS_SCRIPT_URL:
    raise ValueError("No APPS_SCRIPT_URL found in .env file.")
if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
    print("WARNING: Google API Keys not found. Google Search will fail.")
if not LINKUP_API_KEY:
    print("WARNING: LINKUP_API_KEY not found. Fallback will fail.")

# Initialize Client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# --- Basic Setup ---
app = FastAPI()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Request/Response Models ---
class OCRRequest(BaseModel):
    base64Image1: str # From Card Front
    base64Image2: str | None = None # From Card Back

class OCRResponse(BaseModel):
    company: str | None = Field(default="")
    name: str | None = Field(default="")
    title: str | None = Field(default="")
    phone: str | None = Field(default="")
    email: str | None = Field(default="")
    address: str | None = Field(default="")
    website: str | None = Field(default="")
    validation_source: str | None = Field(default="")
    is_validated: bool = Field(default=False)
    about_the_company: str | None = Field(default="")
    location: str | None = Field(default="")
    founder: str | None = Field(default="")
    ceo: str | None = Field(default="")
    owner: str | None = Field(default="")

# --- Search Function (LinkUp) ---
def search_linkup(query, depth="standard"):
    """
    Performs a search using LinkUp API.
    Used as fallback.
    """
    if not LINKUP_API_KEY:
        logger.warning("Skipping LinkUp fallback: No API Key.")
        return None

    endpoint = "https://api.linkup.so/v1/search"
    headers = {
        "Authorization": f"Bearer {LINKUP_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "q": query,
        "depth": depth,
        "include_raw_content": False,
        "outputType": "searchResults"
    }

    try:
        logger.info(f"Fallback: Searching LinkUp for: {query}")
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if not response.ok:
            logger.error(f"LinkUp API Error: {response.status_code} - {response.text}")
            return None
            
        data = response.json()
        results = data.get("results", [])
        if results:
            logger.info(f"LinkUp (Fallback) found {len(results)} results.")
            normalized_results = []
            for r in results:
                normalized_results.append({
                    "title": r.get("title") or r.get("name"),
                    "link": r.get("url"),
                    "snippet": r.get("content") or r.get("snippet")
                })
            return normalized_results
        else:
            logger.info("LinkUp found no matching results.")
            return None

    except Exception as e:
        logger.error(f"Error during LinkUp fallback search: {e}", exc_info=True)
        return None

# --- Search Function (Google Custom Search with LinkUp Fallback) ---
def search_google(query, num_results=3):
    """
    Performs a Google Custom Search.
    Falls back to LinkUp if Google API fails.
    """
    # 1. Try Google API
    if GOOGLE_API_KEY and GOOGLE_CSE_ID:
        try:
            logger.info(f"Searching Google for: {query}")
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': GOOGLE_API_KEY,
                'cx': GOOGLE_CSE_ID,
                'q': query,
                'num': num_results
            }
            response = requests.get(url, params=params)
            
            if response.ok:
                results = response.json()
                if "items" in results and len(results["items"]) > 0:
                    logger.info(f"Google found {len(results['items'])} results.")
                    normalized_results = []
                    for r in results["items"]:
                        normalized_results.append({
                            "title": r.get("title"),
                            "link": r.get("link"),
                            "snippet": r.get("snippet")
                        })
                    return normalized_results
                else:
                    logger.info("Google found no matching results.")
                    return None
            else:
                 logger.warning(f"Google API Error ({response.status_code}): {response.text}")
                 # Fall through to specific fallback call
        except Exception as e:
             logger.error(f"Error during Google search: {e}", exc_info=True)
             # Fall through to specific fallback call
    
    # 2. Fallback: LinkUp
    logger.info("Initiating Fallback to LinkUp...")
    return search_linkup(query)

# --- Helper to parse JSON (Unchanged) ---
def parse_openai_json(response_content):
    if "```json" in response_content:
        response_content = response_content.split("```json")[1].split("```")[0].strip()
    return json.loads(response_content)

# --- OpenAI Web Search Cleanup ---
# We removed search_google, search_linkup, and generate_multi_queries
# because we are delegating search to the OpenAI Model.

# --- Middleware (Unchanged) ---
@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Request to {request.url} completed with status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {e}", exc_info=True)
        raise

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "OCR Backend is running"}

@app.post("/ocr", response_model=OCRResponse)
async def perform_ocr(request_data: OCRRequest):
    logger.info("Incoming request to /ocr")
    
    try:
        base64_image1 = request_data.base64Image1
        base64_image2 = request_data.base64Image2

        if "," in base64_image1:
            base64_image1 = base64_image1.split(',')[1]
        
        base64_image2_cleaned = ""
        if base64_image2:
            if "," in base64_image2:
                base64_image2_cleaned = base64_image2.split(',')[1]
            else:
                base64_image2_cleaned = base64_image2

        # --- Step 1: Initial Extraction (Unchanged) ---
        logger.info("Step 1: Sending image(s) to OpenAI for initial extraction...")
        
        system_prompt_extract = """
        You are an expert OCR assistant. Extract business card details into JSON:
        {company, name, title, phone, email, address, slogan, location, website}
        If a field is missing, use empty string.
        """
        
        user_content = [{"type": "text", "text": "Extract details from this business card."}]
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image1}"}})
        if base64_image2_cleaned:
             user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image2_cleaned}"}})
             
        initial_response = client.chat.completions.create(
            model="gpt-5", # Use standard vision model for extraction
            messages=[
                {"role": "system", "content": system_prompt_extract},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            # temperature=0.0 # Not supported by this model
        )
        ocr_data = parse_openai_json(initial_response.choices[0].message.content)
        logger.info(f"Step 1: Extracted Raw Data: {ocr_data}")

        # --- Step 2: Verification & Enrichment via OpenAI Web Search ---
        logger.info("Step 2: Using OpenAI Web Search to Verify & Enrich...")

        # Construct a prompt that forces the model to SEARCH
        search_prompt = f"""
        I have extracted the following information from a business card:
        {json.dumps(ocr_data, indent=2)}

        your Goal: Verify and Enrich this data using the Internet.
        
        **SEARCH INSTRUCTIONS:**
        1.  **Search for the Company:** Find the OFFICIAL website.
        2.  **Find the Owner/Leadership:** Search specifically for "Owner", "Founder", "Managing Director", "Directors" of this company (especially on Zauba Corp/Tofler if Indian).
        3.  **Find Contact Details:** Look for official email addresses (info@, contact@) and phone numbers if missing.
        4.  **Write Description:** Write a detailed 'about_the_company'.
        
        **VALIDATION RULES:**
        - **Website:** Must be the official domain (e.g. .com, .in). Avoid JustDial/LinkedIn/Facebook unless no official site exists.
        - **Person:** If the card has a name, verify their role. If no name, FIND the owner/director.
        - **Address:** Verify the address matches the location.

        Return the FINAL MERGED JSON in this format:
        {{
            "company": "...",
            "name": "...", 
            "title": "...",
            "phone": "...",
            "email": "...",
            "address": "...",
            "slogan": "...",
            "location": "...",
            "website": "...",
            "validation_source": "URL of the best source found",
            "is_validated": true/false,
            "about_the_company": "...",
            "founder": "...",
            "ceo": "...",
            "owner": "..."
        }}
        """

        # Using the Responses API (Beta Web Search)
        logger.info("Calling OpenAI Responses API (Web Search)...")
        try:
             # User explicit request: use client.responses.create
             # Ensure openai package is up to date for this feature.
             search_response = client.responses.create(
                model="gpt-5",
                tools=[{"type": "web_search"}],
                input=search_prompt
            )
             
             raw_output = search_response.output_text
             logger.info(f"Raw Response Output: {raw_output[:200]}...") 
             
             final_data = parse_openai_json(raw_output)
             logger.info(f"Step 2: OpenAI Search Result (via Responses API): {final_data}")

        except Exception as e:
             logger.warning(f"client.responses failed: {e}. Fallback to Manual Search + Chat Completions.")
             
             # 1. Manual Search Fallback
             query_parts = [ocr_data.get("company", ""), ocr_data.get("name", ""), "official website contact info"]
             query = " ".join([p for p in query_parts if p]).strip()
             
             search_results = None
             if query:
                 logger.info(f"Fallback Search Query: {query}")
                 search_results = search_google(query)
             
             search_context = ""
             if search_results:
                 logger.info(f"Fallback search found {len(search_results)} results.")
                 search_context = f"Here are the search results from the internet:\n{json.dumps(search_results, indent=2)}"
             else:
                 logger.info("Fallback search returned no results.")
                 search_context = "No external search results found. Do your best with the OCR data."

             # 2. Update Prompt with Context
             augmented_prompt = f"""
             {search_context}
             
             {search_prompt}
             """
             
             # 3. Call Chat Completion
             fallback_response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Use the provided search results to verify and enrich the data. Output JSON."},
                    {"role": "user", "content": augmented_prompt}
                ],
                response_format={"type": "json_object"}
             )
             final_data = parse_openai_json(fallback_response.choices[0].message.content)

        except Exception as e:
             logger.error(f"Search failed: {e}")
             final_data = ocr_data # Fallback to original data
             final_data["is_validated"] = False

        # --- Step 5b: Confidence Score (Simplified) ---
        confidence_score = 0
        if final_data.get("is_validated"): confidence_score += 40
        if final_data.get("founder") or final_data.get("owner"): confidence_score += 20
        if final_data.get("about_the_company"): confidence_score += 10
        if final_data.get("website"): confidence_score += 10
        
        logger.info(f"Confidence Score: {confidence_score}")

        # Clean up phone number and slogan if present
        phone_number = final_data.get("phone", "")
        if phone_number and phone_number.startswith('+'):
            final_data["phone"] = "'" + phone_number
        if 'slogan' in final_data:
            del final_data['slogan']

        # --- Step 6: Submit to Google Apps Script ---
        logger.info("Step 6: Submitting final data to Google Apps Script...")
        try:
            # Prepare payload
            apps_script_payload = {
                "action": "save",
                "extractedData": final_data,
                "confidence_score": confidence_score,
                "photo1Base64": base64_image1, # Use cleaned variable
                "photo2Base64": base64_image2_cleaned or "" # Use cleaned variable
            }
            
            # Simple POST with JSON payload
            # json=payload handles content-type and serialization automatically
            response = requests.post(APPS_SCRIPT_URL, json=apps_script_payload)
            
            if response.ok:
                logger.info(f"Google Apps Script Response: {response.status_code} - {response.text}")
            else:
                logger.error(f"Google Apps Script Error: {response.status_code} - {response.text}")
                
        except Exception as e:
             logger.error(f"Google Apps Script failed to save (non-fatal): {e}")

        return OCRResponse(**final_data)

    except Exception as e:
        logger.error(f"An error occurred during processing: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.head("/")
def status_check():
    return Response(status_code=200)

if __name__ == "__main__":
    print("Starting FastAPI server. Run with: uvicorn main:app --host 0.0.0.0 --port 8000")