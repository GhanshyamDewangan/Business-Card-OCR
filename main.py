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
async_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

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

class KeyPerson(BaseModel):
    name: str = Field(default="Not Found")
    role: str = Field(default="Not Found")
    contact: str = Field(default="Not Found")

class OCRResponse(BaseModel):
    # --- Card Data ---
    company: str = Field(default="", description="Company Name from Card")
    name: str = Field(default="", description="Person Name from Card")
    title: str = Field(default="", description="Job Title from Card")
    phone: str = Field(default="", description="Phone Number from Card")
    email: str = Field(default="", description="Email from Card")
    address: str = Field(default="", description="Address from Card")
    location: str = Field(default="", description="City/State from Card")
    
    # --- Enriched Data (Web Search) ---
    industry: str = Field(default="", description="Industry/Sector")
    website: str = Field(default="", description="Official Website URL")
    social_media: str = Field(default="", description="Comma-separated List of Raw Profile URLs (e.g. https://instagram.com/xyz, https://facebook.com/abc)")
    services: str = Field(default="", description="List of services/products")
    company_size: str = Field(default="", description="Number of employees (e.g. 1-10)")
    founded_year: str = Field(default="", description="Year established")
    registration_status: str = Field(default="", description="Registration details (GST/CIN/Active)")
    trust_score: str = Field(default="0", description="Reliability score 0-10")
    key_people: list[KeyPerson] = Field(default_factory=list, description="List of key leadership found")
    key_people_str: str = Field(default="", description="Backup string of key people")
    
    # --- Meta Data ---
    validation_source: str = Field(default="", description="Source URL for verification")
    is_validated: bool = Field(default=False)
    about_the_company: str = Field(default="", description="Short description of company")
    
    # Legacy fields (kept for compatibility)
    founder: str | None = Field(default=None)
    ceo: str | None = Field(default=None)
    owner: str | None = Field(default=None)

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
        base64_image1 = base64_image1.strip()
        logger.info(f"Image 1 Payload Size: {len(base64_image1)} chars")
        
        base64_image2_cleaned = ""
        if base64_image2:
            if "," in base64_image2:
                base64_image2_cleaned = base64_image2.split(',')[1]
            else:
                base64_image2_cleaned = base64_image2
            base64_image2_cleaned = base64_image2_cleaned.strip()
            logger.info(f"Image 2 Payload Size: {len(base64_image2_cleaned)} chars")

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

        # --- Step 2: Verification & Enrichment via OpenAI Web Search ---
        logger.info("Step 2: Using OpenAI Web Search to Verify & Enrich...")

        search_prompt = f"""
        I have extracted the following information from a business card:
        {json.dumps(ocr_data, indent=2)}

        your Goal: Verify and Enrich this data using the Internet.
        
        **SEARCH INSTRUCTIONS:**
        1.  **Search for the Company:** Find the OFFICIAL website.
        2.  **VERIFY LEGITIMACY ("Sahi hai ya nahi"):** 
            - Check if the company is REGISTERED (e.g., look for GST, CIN, Zauba Corp, Tofler, or local business registries).
            - Look for "Scam" or "Fake" reports if suspicious.
            - Check if the social media pages are active.
        3.  **Find the Owner/Leadership:** Search specifically for "Owner", "Founder", "Managing Director", "CEO".
        4.  **GET THEIR CONTACT DETAILS:** Try to find the Email or Phone Number specifically for the Founder/CEO from LinkedIn or 'About Us'.
        5.  **Enrich Details:** Find Industry, Company Size, Services, and Social Media links.
        
        **VALIDATION RULES:**
        - **Website:** Must be the official domain.
        - **Legitimacy:** If you find a registration (MCA/GST/etc), mark as "Verified" in registration_status.
        
        **OUTPUT REQUIREMENT:**
        You MUST return a valid JSON object matching the `OCRResponse` schema exactly.
        Ensure all fields are filled to the best of your ability using the search results.
        If a field is not found, use an empty string or "Not Found".
        """

        # Using Structured Outputs (beta.chat.completions.parse)
        # ERROR FIX: `parse` does not support `web_search` tool directly yet.
        # STRATEGY: 
        # 1. Use `client.responses.create` (or `chat.completions` with search) to get the raw search data.
        # 2. Use `beta.chat.completions.parse` to structured that raw text into our Pydantic model.


        try:
             logger.info("Phase 2A: Recursive Deep Investigation...")
             import asyncio
             
             # --- Step 1: Discovery (Find Legal Entity Name) ---
             # We need to know who the "Real" company is (e.g. "Grand Arsh" instead of "Grand Imperia")
             discovery_query = f"{ocr_data.get('company', '')} {ocr_data.get('location', '')} legal name GST owner"
             logger.info(f"1. Discovery Search: {discovery_query}")
             
             discovery_response = await async_client.responses.create(
                model="gpt-5",
                tools=[{"type": "web_search"}],
                input=f"Find the legal registered entity name, GSTIN, and owner for: {discovery_query}. If a parent company exists, identify it."
            )
             discovery_text = discovery_response.output_text
             logger.info(f"Discovery Complete. Length: {len(discovery_text)}")

             # --- Step 2: Parallel Deep Dive (Using BEST KNOWN NAME) ---
             # We pass the discovery text to the agents so they know what to look for
             
             async def search_leadership_deep():
                 # The prompt here is dynamic - it asks the AI to use the discovery text to refine its search
                 return await async_client.responses.create(
                    model="gpt-5",
                    tools=[{"type": "web_search"}],
                    input=f"""
                    Context from previous search: {discovery_text}
                    
                    Task: Find the Directors / Partners / Owners of the LEGAL ENTITY found above.
                    Search Query Suggestions:
                    - "[Legal Name]" Director Zauba Corp
                    - "[Legal Name]" Owner LinkedIn
                    - "{ocr_data.get('company', '')}" Owner
                    """
                )

             async def search_socials_deep():
                 # HACKER MODE: Targeted Site Search using Brand AND Legal Name
                 return await async_client.responses.create(
                    model="gpt-5",
                    tools=[{"type": "web_search"}],
                    input=f"""
                    Context: {discovery_text}
                    
                    Task: Find OFFICIAL Social Media URLs using "Hacker Mode" queries.
                    
                    INSTRUCTIONS:
                    1. Identify the Legal Entity Name from the context above.
                    2. Execute searches like:
                       - site:instagram.com ("{ocr_data.get('company', '')}" OR [Legal Name]) "{ocr_data.get('location', '')}"
                       - site:facebook.com ("{ocr_data.get('company', '')}" OR [Legal Name]) "{ocr_data.get('location', '')}"
                       - site:linkedin.com ("{ocr_data.get('company', '')}" OR [Legal Name]) "{ocr_data.get('location', '')}"
                       
                    3. EXTRACT the matching profile URLs.
                    """
                )

             logger.info("Launching Deep Dive Agents (Leadership + Socials)...")
             results = await asyncio.gather(search_leadership_deep(), search_socials_deep())
             
             combined_search_context = f"""
             --- 1. DISCOVERY & LEGAL REGISTRATION ---
             {discovery_text}
             
             --- 2. LEADERSHIP & OWNERSHIP (Deep Dive) ---
             {results[0].output_text}
             
             --- 3. SOCIAL MEDIA & CONTACTS ---
             {results[1].output_text}
             """
             
             logger.info(f"Phase 2A: Recursive Search Complete. Context Length: {len(combined_search_context)}")
             
             # 2. STRUCTURE PHASE (Force Pydantic Schema)
             logger.info("Phase 2B: Structuring Data into Pydantic Schema...")
             extraction_prompt = f"""
             Here is the deep investigation report from 3 different agents:
             
             {combined_search_context}
             
             
             Using ONLY the information above (and the original card data), fill out the required JSON structure.
             Original Card Data: {json.dumps(ocr_data)}
             
             Validation Rules:
             - Registration: If GST/CIN found -> 'Verified'.
             - Leadership: Combine findings from Agent 2.
             
             **CRITICAL INSTRUCTION FOR SOCIAL MEDIA:**
             - DO NOT SUMMARIZE (e.g. "Found Facebook Page").
             - YOU MUST EXTRACT THE FULL RAW URL (e.g. "https://www.facebook.com/companyname").
             - If multiple links are found (Insta, FB, LinkedIn), join them with commas or newlines.
             - LOOK CLOSELY at Agent 3's output. If a URL is there, IT MUST BE IN THE FINAL JSON.
             
             - Trust Score: 9-10 if Website+Reg+Socials found.
             """
             
             completion = await async_client.beta.chat.completions.parse(
                model="gpt-5", 
                messages=[
                    {"role": "system", "content": "You are a data structuring assistant. Convert the provided research text into the strict JSON schema."},
                    {"role": "user", "content": extraction_prompt}
                ],
                response_format=OCRResponse, 
            )
             
             final_data_obj = completion.choices[0].message.parsed
             final_data = final_data_obj.model_dump()
             logger.info(f"Step 2: Structured Data Received: {final_data}")

        except Exception as e:
             logger.error(f"Structured Output Parsing Failed: {e}. Fallback to manual JSON.")
             # Fallback logic
             final_data = ocr_data 
             final_data["is_validated"] = False

        # --- Step 5b: Confidence Score (Enhanced) ---
        confidence_score = 0
        if final_data.get("is_validated"): confidence_score += 30
        if final_data.get("website"): confidence_score += 20
        # Trust score from AI (0-10) converted to points (max 20)
        try:
            trust_val = int(str(final_data.get("trust_score", "0")).split('/')[0].strip())
            confidence_score += (trust_val * 2) 
        except:
            pass
            
        if final_data.get("registration_status") and "Active" in final_data.get("registration_status"): confidence_score += 10
        if final_data.get("key_people"): confidence_score += 10 # Check list existence
        if final_data.get("social_media"): confidence_score += 10
        
        logger.info(f"Confidence Score: {confidence_score}")

        # Clean up phone number
        phone_number = final_data.get("phone", "")
        if phone_number and phone_number.startswith('+'):
            final_data["phone"] = "'" + phone_number

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