# Prompt Library

The Prompt Library component provides a centralized repository for storing, managing, versioning, and optimizing prompts for various large language models.

## Overview

Effective prompting is crucial for getting the best results from large language models. The Prompt Library component aims to:

1. Provide a centralized location for storing and retrieving prompts
2. Support versioning and tracking of prompt evolution
3. Enable parameterized templates for dynamic prompt generation
4. Track performance metrics for different prompt versions
5. Organize prompts by category, model, and tags
6. Support importing and exporting prompts for sharing and backup

## Architecture

The Prompt Library is implemented as a microservice with a RESTful API and persistent storage:

```
┌───────────────────────────────────────────────────────┐
│              Prompt Library Service                    │
│                                                        │
│  ┌─────────────┐       ┌─────────────────────────┐    │
│  │             │       │                         │    │
│  │   FastAPI   │◄──────┤  Prompt Management      │    │
│  │  Endpoints  │       │      Logic              │    │
│  │             │       └───────────┬─────────────┘    │
│  └─────────────┘                   │                  │
│                                    │                  │
│                       ┌────────────▼─────────────┐    │
│                       │                          │    │
│                       │   Template Rendering     │    │
│                       │       Engine             │    │
│                       └────────────┬─────────────┘    │
│                                    │                  │
│  ┌─────────────┐      ┌────────────▼─────────────┐    │
│  │             │      │                          │    │
│  │ File-based  │◄─────┤    Database Layer        │    │
│  │  Storage    │      │                          │    │
│  │             │      └──────────────────────────┘    │
│  └─────────────┘                                      │
│                                                        │
└───────────────────────────────────────────────────────┘
```

## Data Model

### Prompt

The core entity in the Prompt Library is the Prompt:

- `id`: Unique identifier for the prompt
- `name`: Human-readable name for the prompt
- `description`: Detailed description of the prompt's purpose and usage
- `category`: Classification category (e.g., "Content Generation", "Question Answering")
- `model`: Target LLM model (e.g., "Claude", "GPT-4")
- `tags`: List of tags for filtering and organization
- `created_at`: Timestamp when the prompt was created
- `updated_at`: Timestamp when the prompt was last updated
- `current_version`: The latest version identifier
- `versions`: List of all versions of this prompt

### PromptVersion

Each prompt can have multiple versions, enabling tracking of improvements:

- `version`: Semantic version identifier (e.g., "1.2.0")
- `content`: The actual prompt text
- `template`: Boolean indicating if this is a template
- `template_schema`: Schema for parameterized templates
- `parameters`: Default parameters for the template
- `created_at`: Timestamp when the version was created
- `performance_metrics`: List of performance measurements

### PerformanceMetric

Metrics track how well a prompt version performs:

- `metric`: Name of the metric (e.g., "accuracy", "relevance")
- `value`: Numeric value of the metric
- `timestamp`: When the metric was recorded
- `model`: The model used for evaluation
- `notes`: Additional context or information

## Features

### Prompt Management

- **CRUD Operations**: Create, read, update, and delete prompts
- **Versioning**: Track changes to prompts with semantic versioning
- **Metadata**: Store and retrieve rich metadata about prompts
- **Filtering**: Find prompts by name, category, model, or tags

### Template Support

- **Jinja2 Templates**: Use Jinja2 syntax for dynamic prompt templates
- **Parameter Validation**: Validate template parameters against schema
- **Default Values**: Provide sensible defaults for optional parameters
- **Rendering**: Generate filled-in prompts from templates and parameters

### Performance Tracking

- **Custom Metrics**: Define and track any performance metrics
- **Historical Data**: Maintain performance history across versions
- **Comparison**: Compare different versions to identify improvements
- **Model-specific Metrics**: Track performance across different LLMs

### Import/Export

- **JSON/YAML Support**: Import and export prompts in common formats
- **Bulk Operations**: Import/export multiple prompts at once
- **Category/Model/Tag Filtering**: Export only specific subsets of prompts
- **Version Control Integration**: Work with Git-based version control

## API Reference

### Prompt Endpoints

#### GET /prompts

List all prompts with optional filtering.

**Query Parameters:**
- `skip`: Number of prompts to skip (pagination)
- `limit`: Maximum number of prompts to return
- `category`: Filter by category
- `model`: Filter by target model
- `tag`: Filter by tag
- `include_versions`: Whether to include version details

#### POST /prompts

Create a new prompt.

**Request Body:**
```json
{
  "name": "Claude Content Generation",
  "description": "Generates creative content based on a topic",
  "category": "Content Generation",
  "model": "Claude",
  "tags": ["creative", "writing"],
  "content": "Generate a creative piece about {{topic}} in the style of {{style}}.",
  "is_template": true,
  "template_schema": {
    "topic": {
      "type": "string",
      "description": "The topic to write about"
    },
    "style": {
      "type": "string",
      "description": "The writing style",
      "default": "modern"
    }
  }
}
```

#### GET /prompts/{prompt_id}

Retrieve a prompt by ID or name.

#### PUT /prompts/{prompt_id}

Update a prompt's metadata.

#### DELETE /prompts/{prompt_id}

Delete a prompt and all its versions.

### Version Endpoints

#### POST /prompts/{prompt_id}/versions

Create a new version of a prompt.

#### GET /prompts/{prompt_id}/versions/{version}

Retrieve a specific version of a prompt.

#### POST /prompts/{prompt_id}/versions/{version}/metrics

Add performance metrics for a prompt version.

### Rendering Endpoint

#### POST /prompts/{prompt_id}/render

Render a prompt template with provided parameters.

**Request Body:**
```json
{
  "version": "1.0.0",
  "parameters": {
    "topic": "artificial intelligence",
    "style": "academic"
  }
}
```

### Utility Endpoints

#### GET /categories

List all available prompt categories.

#### GET /models

List all target models used in prompts.

#### GET /tags

List all tags used across prompts.

#### POST /import

Import prompts from a file or directory.

#### POST /export

Export prompts to a file in JSON or YAML format.

## Usage Examples

### Creating a Template Prompt

```bash
curl -X POST http://localhost:8002/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Knowledge Graph Query",
    "description": "Prompt for querying entities in a knowledge graph",
    "category": "Query",
    "model": "Claude",
    "tags": ["knowledge-graph", "query"],
    "content": "Given the following knowledge graph entities:\n\n{{entities}}\n\nFind all relationships between {{entity_type}} and answer: {{question}}",
    "is_template": true,
    "template_schema": {
      "entities": {
        "type": "string",
        "description": "Knowledge graph entity dump"
      },
      "entity_type": {
        "type": "string",
        "description": "The type of entity to focus on"
      },
      "question": {
        "type": "string",
        "description": "The question to answer about the entities"
      }
    }
  }'
```

### Rendering a Template

```bash
curl -X POST http://localhost:8002/prompts/Knowledge%20Graph%20Query/render \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "entities": "Entity: Anthropic (Company)\nEntity: Claude (AIModel)\nEntity: MCP (Protocol)",
      "entity_type": "Company",
      "question": "What protocols are implemented by AI models from this company?"
    }
  }'
```

### Adding Performance Metrics

```bash
curl -X POST http://localhost:8002/prompts/Knowledge%20Graph%20Query/versions/1.0.0/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "metric": "accuracy",
    "value": 0.92,
    "model": "Claude-3-Opus",
    "notes": "Improved accuracy with more specific entities list"
  }'
```

## Deployment

The Prompt Library service is containerized using Docker and can be deployed as part of the Unified Data Architecture stack using Docker Compose or Kubernetes.

### Docker Compose

```yaml
prompt-library:
  build:
    context: ./services/prompt-library
    dockerfile: Dockerfile
  container_name: prompt-library
  ports:
    - "8002:8002"
  environment:
    - SERVICE_PORT=8002
    - DATA_DIR=/app/data
  volumes:
    - prompt-data:/app/data
  networks:
    - uda-network
```

### Kubernetes

See the Kubernetes deployment manifests in `kubernetes/services/prompt-library.yaml`

## Integration Points

The Prompt Library integrates with other components of the Unified Data Architecture:

- **Knowledge Graph Service**: Retrieves entity information for context-aware prompts
- **Documentation Extractor**: Uses prompts to extract specific entities from documentation
- **Prompt Optimizer**: Analyzes and improves prompts based on performance metrics
- **MCP Servers**: Exposes prompt library functionality through the Model Context Protocol