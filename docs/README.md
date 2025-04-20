# Unified Data Architecture Documentation

## Table of Contents

1. [Installation](#installation)
2. [Architecture Overview](#architecture-overview)
3. [Component Documentation](#component-documentation)
4. [Development Guide](#development-guide)
5. [API Reference](#api-reference)
6. [Usage Examples](#usage-examples)

## Installation

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Node.js 18+

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/unified-data-architecture.git
cd unified-data-architecture

# Build and start services using Docker Compose
docker-compose up -d

# Install Python client library
pip install -e ./client/python
```

## Architecture Overview

The Unified Data Architecture is built around a microservices architecture with the following components:

- **Knowledge Graph Service**: Neo4j database with API endpoints for storing and querying relationships
- **Documentation Extractor Service**: Scrapes and processes documentation from the web
- **Prompt Library Service**: Manages and serves optimized prompts
- **Prompt Optimizer Service**: Analyzes and improves prompts
- **Project Manager Service**: Handles project setup and management
- **MCP Client**: Implementation of the Model Context Protocol client
- **MCP Servers**: Collection of MCP servers for various data sources

See [Architecture Diagram](./architecture/overview.md) for a visual representation.

## Component Documentation

- [Knowledge Graph](./components/knowledge-graph.md)
- [Documentation Extractor](./components/documentation-extractor.md)
- [Prompt Library](./components/prompt-library.md)
- [Prompt Optimizer](./components/prompt-optimizer.md)
- [Project Manager](./components/project-manager.md)
- [MCP Implementation](./components/mcp-implementation.md)

## Development Guide

- [Setup Development Environment](./development/setup.md)
- [Contributing Guidelines](./development/contributing.md)
- [Testing Strategy](./development/testing.md)
- [CI/CD Pipeline](./development/cicd.md)

## API Reference

- [Knowledge Graph API](./api/knowledge-graph.md)
- [Documentation Extractor API](./api/documentation-extractor.md)
- [Prompt Library API](./api/prompt-library.md)
- [Prompt Optimizer API](./api/prompt-optimizer.md)
- [Project Manager API](./api/project-manager.md)
- [MCP Client API](./api/mcp-client.md)
- [MCP Server API](./api/mcp-server.md)

## Usage Examples

- [Building a Company Knowledge Graph](./examples/company-knowledge-graph.md)
- [Optimizing Prompts for Claude](./examples/prompt-optimization.md)
- [Setting Up a New Project](./examples/project-setup.md)
- [Implementing MCP Servers](./examples/mcp-server-implementation.md)