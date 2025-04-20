from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import os
import httpx
import asyncio
import logging
from bs4 import BeautifulSoup
from pyppeteer import launch
import json
import re
from datetime import datetime
from markdownify import markdownify as md
from readability import Document

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Documentation Extractor Service", description="Service for extracting documentation from websites")

# Configuration
KG_SERVICE_URL = os.getenv("KG_SERVICE_URL", "http://localhost:8000")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))

# Models
class ExtractionRequest(BaseModel):
    url: HttpUrl
    company: str
    company_type: str = "Company"
    product: Optional[str] = None
    product_type: Optional[str] = "AIProduct"
    recursive: bool = False
    max_depth: int = 1
    selectors: Optional[Dict[str, str]] = None

class ExtractionResponse(BaseModel):
    url: HttpUrl
    status: str
    company: str
    product: Optional[str] = None
    extracted_entities: List[Dict[str, Any]] = []
    extraction_id: str

class ExtractionStatus(BaseModel):
    extraction_id: str
    status: str
    progress: float
    completed_urls: List[str] = []
    pending_urls: List[str] = []
    error_urls: List[Dict[str, Any]] = []

# In-memory storage for extraction jobs
extraction_jobs = {}

# HTTP client
@app.on_event("startup")
async def startup_event():
    app.state.http_client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.http_client.aclose()

# Knowledge Graph API client
async def get_kg_client():
    return app.state.http_client

@app.get("/")
async def root():
    return {"message": "Documentation Extractor Service API"}

@app.post("/extract", response_model=ExtractionResponse)
async def extract_documentation(
    request: ExtractionRequest, 
    background_tasks: BackgroundTasks,
    kg_client: httpx.AsyncClient = Depends(get_kg_client)
):
    extraction_id = f"extraction_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(request.url)}"
    
    # Initialize extraction job
    extraction_jobs[extraction_id] = {
        "status": "initialized",
        "progress": 0,
        "completed_urls": [],
        "pending_urls": [str(request.url)],
        "error_urls": [],
        "request": request.dict(),
        "extracted_entities": []
    }
    
    # Start extraction in background
    background_tasks.add_task(
        run_extraction, 
        extraction_id=extraction_id, 
        kg_client=kg_client
    )
    
    return ExtractionResponse(
        url=request.url,
        status="initialized",
        company=request.company,
        product=request.product,
        extracted_entities=[],
        extraction_id=extraction_id
    )

@app.get("/status/{extraction_id}", response_model=ExtractionStatus)
async def get_extraction_status(extraction_id: str):
    if extraction_id not in extraction_jobs:
        raise HTTPException(status_code=404, detail="Extraction job not found")
    
    job = extraction_jobs[extraction_id]
    
    return ExtractionStatus(
        extraction_id=extraction_id,
        status=job["status"],
        progress=job["progress"],
        completed_urls=job["completed_urls"],
        pending_urls=job["pending_urls"],
        error_urls=job["error_urls"]
    )

@app.get("/results/{extraction_id}")
async def get_extraction_results(extraction_id: str):
    if extraction_id not in extraction_jobs:
        raise HTTPException(status_code=404, detail="Extraction job not found")
    
    job = extraction_jobs[extraction_id]
    
    if job["status"] != "completed":
        return {
            "extraction_id": extraction_id,
            "status": job["status"],
            "progress": job["progress"],
            "message": "Extraction is still in progress"
        }
    
    return {
        "extraction_id": extraction_id,
        "status": job["status"],
        "progress": job["progress"],
        "extracted_entities": job["extracted_entities"]
    }

async def run_extraction(extraction_id: str, kg_client: httpx.AsyncClient):
    """Run the extraction process in the background."""
    job = extraction_jobs[extraction_id]
    request_data = job["request"]
    job["status"] = "running"
    
    try:
        # Launch browser
        browser = await launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        page = await browser.newPage()
        
        # Process URLs
        while job["pending_urls"]:
            current_url = job["pending_urls"].pop(0)
            
            try:
                # Navigate to page
                await page.goto(current_url, {'waitUntil': 'networkidle0', 'timeout': 60000})
                
                # Get page content
                content = await page.content()
                
                # Extract data
                entities = await extract_entities_from_content(
                    content=content,
                    url=current_url,
                    company=request_data["company"],
                    company_type=request_data["company_type"],
                    product=request_data["product"],
                    product_type=request_data["product_type"],
                    selectors=request_data.get("selectors")
                )
                
                # Store extracted entities
                job["extracted_entities"].extend(entities)
                
                # Push to Knowledge Graph
                if entities:
                    await push_to_knowledge_graph(entities, kg_client)
                
                # If recursive, extract links and add to pending
                if request_data["recursive"] and len(job["completed_urls"]) < request_data["max_depth"]:
                    links = await extract_internal_links(page, current_url)
                    for link in links:
                        if (link not in job["completed_urls"] and 
                            link not in job["pending_urls"] and 
                            link not in [e["url"] for e in job["error_urls"]]):
                            job["pending_urls"].append(link)
                
                # Mark as completed
                job["completed_urls"].append(current_url)
                
            except Exception as e:
                logger.error(f"Error processing URL {current_url}: {str(e)}")
                job["error_urls"].append({"url": current_url, "error": str(e)})
            
            # Update progress
            total_urls = len(job["completed_urls"]) + len(job["pending_urls"]) + len(job["error_urls"])
            job["progress"] = len(job["completed_urls"]) / total_urls if total_urls > 0 else 1.0
        
        # Close browser
        await browser.close()
        
        # Mark job as completed
        job["status"] = "completed"
        job["progress"] = 1.0
        
    except Exception as e:
        logger.error(f"Error in extraction job {extraction_id}: {str(e)}")
        job["status"] = "failed"
        job["error"] = str(e)

async def extract_entities_from_content(
    content: str, 
    url: str, 
    company: str, 
    company_type: str,
    product: Optional[str] = None, 
    product_type: Optional[str] = None,
    selectors: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    """Extract entities from HTML content."""
    entities = []
    
    # Use readability to extract main content
    doc = Document(content)
    title = doc.title()
    main_content = doc.summary()
    
    # Convert to soup for better parsing
    soup = BeautifulSoup(main_content, 'lxml')
    
    # Extract text content
    text_content = soup.get_text(separator='\n\n')
    
    # Convert to markdown for better structure
    markdown_content = md(main_content)
    
    # Extract entities based on content type
    if "api" in url.lower() or "reference" in url.lower():
        # This is likely API documentation
        api_entities = extract_api_entities(soup, url, company, product)
        entities.extend(api_entities)
    
    if "guide" in url.lower() or "tutorial" in url.lower() or "docs" in url.lower():
        # This is likely a guide or tutorial
        guide_entities = extract_guide_entities(soup, url, company, product)
        entities.extend(guide_entities)
    
    # Extract best practices if present
    if "best-practices" in url.lower() or "best practices" in text_content.lower():
        best_practice_entities = extract_best_practices(soup, url, company, product)
        entities.extend(best_practice_entities)
    
    # If specific selectors provided, use them for extraction
    if selectors:
        custom_entities = extract_custom_entities(soup, url, company, product, selectors)
        entities.extend(custom_entities)
    
    # Always create a documentation entity
    doc_entity = {
        "name": f"{title} Documentation",
        "entityType": "Documentation",
        "observations": [
            f"URL: {url}",
            f"Title: {title}",
            f"Extracted on: {datetime.now().isoformat()}"
        ]
    }
    entities.append(doc_entity)
    
    # Create relation between company and documentation
    company_doc_relation = {
        "from": company,
        "relationType": "has_documentation",
        "to": doc_entity["name"]
    }
    entities.append(company_doc_relation)
    
    # If product is specified, create relation
    if product:
        product_doc_relation = {
            "from": product,
            "relationType": "has_documentation",
            "to": doc_entity["name"]
        }
        entities.append(product_doc_relation)
    
    return entities

def extract_api_entities(soup, url, company, product=None):
    """Extract API-related entities from documentation."""
    entities = []
    
    # Find API endpoints (common patterns in API docs)
    endpoints = []
    
    # Look for code blocks with HTTP methods
    code_blocks = soup.find_all('code')
    for block in code_blocks:
        text = block.get_text()
        if re.search(r'GET|POST|PUT|DELETE|PATCH', text):
            endpoints.append(text.strip())
    
    # Look for endpoint paths
    path_elements = soup.find_all(['h2', 'h3', 'dt'])
    for elem in path_elements:
        text = elem.get_text()
        if re.search(r'^/\w+(/\w+)*(\{.*\})?$', text):
            endpoints.append(text.strip())
    
    # Create API entity if endpoints found
    if endpoints:
        api_name = f"{product if product else company} API"
        api_entity = {
            "name": api_name,
            "entityType": "API",
            "observations": [
                f"Source: {url}",
                f"Endpoints: {', '.join(endpoints[:5])}",
                f"Total endpoints: {len(endpoints)}"
            ]
        }
        entities.append(api_entity)
        
        # Create relation to company/product
        if product:
            relation = {
                "from": product,
                "relationType": "provides",
                "to": api_name
            }
            entities.append(relation)
        else:
            relation = {
                "from": company,
                "relationType": "provides",
                "to": api_name
            }
            entities.append(relation)
    
    return entities

def extract_guide_entities(soup, url, company, product=None):
    """Extract guide/tutorial information from documentation."""
    entities = []
    
    # Extract headings to understand structure
    headings = soup.find_all(['h1', 'h2', 'h3'])
    heading_texts = [h.get_text().strip() for h in headings]
    
    # Try to identify guide type based on headings
    guide_type = "General Guide"
    if any("getting started" in h.lower() for h in heading_texts):
        guide_type = "Getting Started Guide"
    elif any("tutorial" in h.lower() for h in heading_texts):
        guide_type = "Tutorial"
    elif any("how to" in h.lower() for h in heading_texts):
        guide_type = "How-To Guide"
    
    # Create guide entity
    title = soup.find('title')
    title_text = title.get_text().strip() if title else "Documentation Guide"
    
    guide_entity = {
        "name": title_text,
        "entityType": guide_type,
        "observations": [
            f"Source: {url}",
            f"Topics: {', '.join(heading_texts[:5]) if heading_texts else 'Unknown'}",
            f"Related to: {product if product else company}"
        ]
    }
    entities.append(guide_entity)
    
    # Create relation
    if product:
        relation = {
            "from": product,
            "relationType": "has_guide",
            "to": title_text
        }
        entities.append(relation)
    else:
        relation = {
            "from": company,
            "relationType": "has_guide",
            "to": title_text
        }
        entities.append(relation)
    
    return entities

def extract_best_practices(soup, url, company, product=None):
    """Extract best practices from documentation."""
    entities = []
    
    # Find sections that might contain best practices
    best_practice_sections = []
    
    # Look for headings with "best practice" in them
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        if "best practice" in heading.get_text().lower() or "recommendation" in heading.get_text().lower():
            section_content = []
            
            # Get all text until next heading of same or higher level
            current = heading.next_sibling
            while current and (current.name not in ['h1', 'h2', 'h3', 'h4'] or 
                              (current.name == heading.name and 
                               "best practice" not in current.get_text().lower() and 
                               "recommendation" not in current.get_text().lower())):
                if current.get_text().strip():
                    section_content.append(current.get_text().strip())
                current = current.next_sibling
            
            best_practice_sections.append({
                "title": heading.get_text().strip(),
                "content": "\n".join(section_content)
            })
    
    # Create entities for each best practice
    for idx, practice in enumerate(best_practice_sections):
        practice_name = f"{product if product else company} Best Practice {idx+1}"
        practice_entity = {
            "name": practice_name,
            "entityType": "BestPractice",
            "observations": [
                f"Title: {practice['title']}",
                f"Source: {url}",
                f"Content: {practice['content'][:200]}..." if len(practice['content']) > 200 else f"Content: {practice['content']}"
            ]
        }
        entities.append(practice_entity)
        
        # Create relation
        if product:
            relation = {
                "from": product,
                "relationType": "recommends",
                "to": practice_name
            }
            entities.append(relation)
        else:
            relation = {
                "from": company,
                "relationType": "recommends",
                "to": practice_name
            }
            entities.append(relation)
    
    return entities

def extract_custom_entities(soup, url, company, product, selectors):
    """Extract entities based on custom selectors."""
    entities = []
    
    for entity_type, selector in selectors.items():
        elements = soup.select(selector)
        for idx, elem in enumerate(elements):
            entity_name = f"{product if product else company} {entity_type} {idx+1}"
            entity = {
                "name": entity_name,
                "entityType": entity_type,
                "observations": [
                    f"Source: {url}",
                    f"Content: {elem.get_text().strip()[:200]}..." if len(elem.get_text().strip()) > 200 else f"Content: {elem.get_text().strip()}"
                ]
            }
            entities.append(entity)
            
            # Create relation
            if product:
                relation = {
                    "from": product,
                    "relationType": "has",
                    "to": entity_name
                }
                entities.append(relation)
            else:
                relation = {
                    "from": company,
                    "relationType": "has",
                    "to": entity_name
                }
                entities.append(relation)
    
    return entities

async def extract_internal_links(page, base_url):
    """Extract internal links from the page."""
    links = await page.evaluate('''() => {
        const baseUrl = new URL(window.location.href);
        const domain = baseUrl.hostname;
        
        const links = Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href)
            .filter(href => {
                try {
                    const url = new URL(href);
                    return url.hostname === domain && url.pathname !== '/';
                } catch (e) {
                    return false;
                }
            });
        
        return [...new Set(links)]; // Return unique links
    }''')
    
    return links

async def push_to_knowledge_graph(entities, kg_client):
    """Push extracted entities to the Knowledge Graph service."""
    # Separate entities and relations
    entity_objects = []
    relation_objects = []
    
    for entity in entities:
        if "relationType" in entity:
            relation_objects.append({
                "from_entity": entity["from"],
                "relationType": entity["relationType"],
                "to_entity": entity["to"]
            })
        else:
            entity_objects.append(entity)
    
    # Push entities
    if entity_objects:
        try:
            response = await kg_client.post(
                f"{KG_SERVICE_URL}/entities",
                json={"entities": entity_objects}
            )
            response.raise_for_status()
            logger.info(f"Successfully pushed {len(entity_objects)} entities to Knowledge Graph")
        except Exception as e:
            logger.error(f"Error pushing entities to Knowledge Graph: {str(e)}")
    
    # Push relations
    if relation_objects:
        try:
            response = await kg_client.post(
                f"{KG_SERVICE_URL}/relations",
                json={"relations": relation_objects}
            )
            response.raise_for_status()
            logger.info(f"Successfully pushed {len(relation_objects)} relations to Knowledge Graph")
        except Exception as e:
            logger.error(f"Error pushing relations to Knowledge Graph: {str(e)}")
