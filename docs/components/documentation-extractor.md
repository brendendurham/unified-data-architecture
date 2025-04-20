# Documentation Extractor

The Documentation Extractor component automatically scrapes documentation websites, extracts structured information, and populates the Knowledge Graph with entities and relationships.

## Overview

Documentation is a rich source of information about companies, products, APIs, and best practices. The Documentation Extractor automates the process of:

1. Fetching web content from documentation sites
2. Extracting structured information using selectors and heuristics
3. Identifying entities such as companies, products, APIs, and best practices
4. Determining relationships between these entities
5. Populating the Knowledge Graph with this information

## Architecture

The Documentation Extractor is implemented as a microservice with the following components:

```
┌─────────────────────────────────────────────────┐
│         Documentation Extractor Service         │
│                                                 │
│  ┌─────────────┐       ┌─────────────────────┐  │
│  │             │       │                     │  │
│  │  FastAPI    │◄──────┤ Extraction Engine   │  │
│  │  Endpoints  │       │                     │  │
│  │             │       └──────────┬──────────┘  │
│  └─────────────┘                  │             │
│                                   │             │
│                      ┌────────────▼─────────┐   │
│                      │                      │   │
│                      │  Web Scraper         │   │
│                      │                      │   │
│                      └────────────┬─────────┘   │
│                                   │             │
│  ┌─────────────┐      ┌───────────▼────────┐    │
│  │             │      │                    │    │
│  │  Entity     │◄─────┤  Content Parser    │    │
│  │  Extractor  │      │                    │    │
│  │             │      └────────────────────┘    │
│  └──────┬──────┘                                │
│         │                                       │
│         │                                       │
│  ┌──────▼──────┐                                │
│  │             │                                │
│  │  KG Client  │                                │
│  │             │                                │
│  └─────────────┘                                │
└─────────────────────────────────────────────────┘
```

## Features

- **Headless Browser Integration**: Uses Pyppeteer (Python port of Puppeteer) to render JavaScript-heavy documentation sites
- **Recursive Crawling**: Can recursively crawl documentation sites up to a specified depth
- **Entity Extraction**: Automatically identifies and extracts entities like:
  - API references
  - Best practices
  - Guides and tutorials
  - Code examples
- **Custom Selectors**: Supports custom CSS selectors for targeted extraction
- **Background Processing**: Handles extraction tasks asynchronously
- **Status Tracking**: Provides endpoints to monitor extraction progress
- **Knowledge Graph Integration**: Automatically pushes extracted entities to the Knowledge Graph service

## API Reference

### POST /extract

Starts a new extraction job.

**Request:**
```json
{
  "url": "https://docs.example.com/",
  "company": "ExampleCorp",
  "company_type": "Company",
  "product": "ExampleProduct",
  "product_type": "AIProduct",
  "recursive": true,
  "max_depth": 2,
  "selectors": {
    "APIEndpoint": ".endpoint",
    "CodeExample": "pre.code"
  }
}
```

**Response:**
```json
{
  "url": "https://docs.example.com/",
  "status": "initialized",
  "company": "ExampleCorp",
  "product": "ExampleProduct",
  "extracted_entities": [],
  "extraction_id": "extraction_20230401120000_12345"
}
```

### GET /status/{extraction_id}

Retrieves the status of an extraction job.

**Response:**
```json
{
  "extraction_id": "extraction_20230401120000_12345",
  "status": "running",
  "progress": 0.5,
  "completed_urls": ["https://docs.example.com/"],
  "pending_urls": ["https://docs.example.com/api", "https://docs.example.com/guides"],
  "error_urls": []
}
```

### GET /results/{extraction_id}

Retrieves the results of a completed extraction job.

**Response:**
```json
{
  "extraction_id": "extraction_20230401120000_12345",
  "status": "completed",
  "progress": 1.0,
  "extracted_entities": [
    {
      "name": "ExampleAPI",
      "entityType": "API",
      "observations": [
        "Source: https://docs.example.com/api",
        "Endpoints: /users, /items, /auth",
        "Total endpoints: 3"
      ]
    },
    // More entities...
  ]
}
```

## Extraction Process

1. The service receives an extraction request with a URL and metadata
2. A headless browser is launched to render the page with JavaScript
3. Content is parsed using BeautifulSoup and readability algorithms
4. Entity extraction is performed based on page content and structure
5. Entities and relationships are formatted for the Knowledge Graph
6. Data is pushed to the Knowledge Graph service via API calls
7. If recursive mode is enabled, links are extracted and added to the queue
8. The process continues until all URLs are processed or max_depth is reached

## Entity Types

The Documentation Extractor identifies and extracts the following entity types:

- **API**: Application Programming Interfaces
- **BestPractice**: Recommended implementation approaches
- **Guide**: Documentation guides and tutorials
- **CodeExample**: Code snippets and examples
- **Documentation**: General documentation pages
- Custom entity types specified via selectors

## Configuration

The Documentation Extractor service is configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| KG_SERVICE_URL | URL of the Knowledge Graph service | http://localhost:8000 |
| SERVICE_PORT | Port on which the service listens | 8001 |

## Usage Examples

### Extract API Documentation

```bash
curl -X POST http://localhost:8001/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.anthropic.com/en/docs/api-reference",
    "company": "Anthropic",
    "product": "Claude",
    "recursive": false
  }'
```

### Extract Best Practices

```bash
curl -X POST http://localhost:8001/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.anthropic.com/en/docs/prompt-engineering",
    "company": "Anthropic",
    "product": "Claude",
    "recursive": false
  }'
```

## Deployment

The Documentation Extractor service is containerized using Docker and can be deployed as part of the Unified Data Architecture stack using Docker Compose or Kubernetes.

### Docker Compose

```yaml
documentation-extractor:
  build:
    context: ./services/documentation-extractor
    dockerfile: Dockerfile
  container_name: doc-extractor
  ports:
    - "8001:8001"
  environment:
    - KG_SERVICE_URL=http://knowledge-graph-service:8000
    - SERVICE_PORT=8001
  networks:
    - uda-network
```

### Kubernetes

See the Kubernetes deployment manifests in `kubernetes/services/documentation-extractor.yaml`.