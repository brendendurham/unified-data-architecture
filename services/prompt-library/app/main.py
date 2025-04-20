from fastapi import FastAPI, HTTPException, Depends, Query, Body, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
import os
import json
import yaml
import re
import aiofiles
import logging
from datetime import datetime
import uuid
import semver
import jinja2
from pathlib import Path
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from jinja2 import Template

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Prompt Library Service", description="Service for managing the Unified Data Architecture prompt library")

# Configuration
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DB_URL = os.getenv("DB_URL", f"sqlite:///{DATA_DIR}/prompts.db")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(f"{DATA_DIR}/prompts", exist_ok=True)
os.makedirs(f"{DATA_DIR}/templates", exist_ok=True)
os.makedirs(f"{DATA_DIR}/versions", exist_ok=True)

# Database setup
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database models
class PromptModel(Base):
    __tablename__ = "prompts"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text)
    category = Column(String, index=True)
    model = Column(String, index=True)
    tags = Column(String)  # Stored as JSON
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    current_version = Column(String)
    versions = relationship("PromptVersionModel", back_populates="prompt")

class PromptVersionModel(Base):
    __tablename__ = "prompt_versions"
    
    id = Column(String, primary_key=True, index=True)
    prompt_id = Column(String, ForeignKey("prompts.id"))
    version = Column(String, index=True)
    content = Column(Text)
    template = Column(Boolean, default=False)
    template_schema = Column(String)  # Stored as JSON
    parameters = Column(String)  # Stored as JSON
    created_at = Column(DateTime)
    performance_metrics = Column(String)  # Stored as JSON
    prompt = relationship("PromptModel", back_populates="versions")

# Create tables
Base.metadata.create_all(bind=engine)

# Dependency for database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models
class PromptParameter(BaseModel):
    name: str
    description: str
    type: str
    required: bool = True
    default: Optional[Any] = None

class PromptTemplate(BaseModel):
    content: str
    is_template: bool = False
    parameters: Optional[List[PromptParameter]] = None

class PerformanceMetric(BaseModel):
    metric: str
    value: float
    timestamp: datetime
    model: str
    notes: Optional[str] = None

class PromptVersion(BaseModel):
    version: str
    content: str
    template: bool = False
    template_schema: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    created_at: datetime
    performance_metrics: Optional[List[PerformanceMetric]] = None

class Prompt(BaseModel):
    id: str
    name: str
    description: str
    category: str
    model: str
    tags: List[str] = []
    created_at: datetime
    updated_at: datetime
    current_version: str
    versions: List[PromptVersion] = []

class PromptCreate(BaseModel):
    name: str
    description: str
    category: str
    model: str
    tags: List[str] = []
    content: str
    is_template: bool = False
    template_schema: Optional[Dict[str, Any]] = None

class PromptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    model: Optional[str] = None
    tags: Optional[List[str]] = None

class PromptVersionCreate(BaseModel):
    content: str
    template: bool = False
    template_schema: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None

class PromptMetricsUpdate(BaseModel):
    metric: str
    value: float
    model: str
    notes: Optional[str] = None

class PromptRender(BaseModel):
    version: Optional[str] = None
    parameters: Dict[str, Any]

# Helper functions
def prompt_model_to_pydantic(db_prompt, include_versions=True):
    """Convert database model to Pydantic model"""
    versions = []
    if include_versions and db_prompt.versions:
        for v in db_prompt.versions:
            performance_metrics = json.loads(v.performance_metrics) if v.performance_metrics else []
            template_schema = json.loads(v.template_schema) if v.template_schema else None
            parameters = json.loads(v.parameters) if v.parameters else None
            
            versions.append(PromptVersion(
                version=v.version,
                content=v.content,
                template=v.template,
                template_schema=template_schema,
                parameters=parameters,
                created_at=v.created_at,
                performance_metrics=performance_metrics
            ))
    
    return Prompt(
        id=db_prompt.id,
        name=db_prompt.name,
        description=db_prompt.description,
        category=db_prompt.category,
        model=db_prompt.model,
        tags=json.loads(db_prompt.tags) if db_prompt.tags else [],
        created_at=db_prompt.created_at,
        updated_at=db_prompt.updated_at,
        current_version=db_prompt.current_version,
        versions=versions
    )

def render_template(template_content, parameters):
    """Render a Jinja2 template with provided parameters"""
    try:
        template = Template(template_content)
        return template.render(**parameters)
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error rendering template: {str(e)}")

def generate_new_version(current_version):
    """Generate a new semantic version based on the current version"""
    if not current_version:
        return "1.0.0"
    
    try:
        ver = semver.VersionInfo.parse(current_version)
        return str(ver.bump_patch())
    except Exception as e:
        logger.error(f"Error parsing version {current_version}: {str(e)}")
        # If we can't parse the current version, start from 1.0.0
        return "1.0.0"

@app.get("/")
async def root():
    return {"message": "Prompt Library Service API"}

@app.post("/prompts", response_model=Prompt, status_code=status.HTTP_201_CREATED)
async def create_prompt(prompt: PromptCreate, db: Session = Depends(get_db)):
    # Check if prompt with given name already exists
    existing_prompt = db.query(PromptModel).filter(PromptModel.name == prompt.name).first()
    if existing_prompt:
        raise HTTPException(status_code=400, detail=f"Prompt with name '{prompt.name}' already exists")
    
    prompt_id = str(uuid.uuid4())
    version = "1.0.0"
    now = datetime.utcnow()
    
    # Create new prompt in database
    db_prompt = PromptModel(
        id=prompt_id,
        name=prompt.name,
        description=prompt.description,
        category=prompt.category,
        model=prompt.model,
        tags=json.dumps(prompt.tags),
        created_at=now,
        updated_at=now,
        current_version=version
    )
    db.add(db_prompt)
    
    # Create first version
    version_id = str(uuid.uuid4())
    template_schema = json.dumps(prompt.template_schema) if prompt.template_schema else None
    
    db_version = PromptVersionModel(
        id=version_id,
        prompt_id=prompt_id,
        version=version,
        content=prompt.content,
        template=prompt.is_template,
        template_schema=template_schema,
        parameters=None,
        created_at=now,
        performance_metrics=json.dumps([])
    )
    db.add(db_version)
    db.commit()
    
    # Save prompt content to file
    prompt_dir = Path(f"{DATA_DIR}/prompts/{prompt_id}")
    prompt_dir.mkdir(exist_ok=True)
    
    version_file = prompt_dir / f"{version}.txt"
    async with aiofiles.open(version_file, "w") as f:
        await f.write(prompt.content)
    
    # Save metadata
    metadata = {
        "id": prompt_id,
        "name": prompt.name,
        "description": prompt.description,
        "category": prompt.category,
        "model": prompt.model,
        "tags": prompt.tags,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "current_version": version,
        "versions": [{
            "version": version,
            "created_at": now.isoformat(),
            "template": prompt.is_template,
            "template_schema": prompt.template_schema
        }]
    }
    
    metadata_file = prompt_dir / "metadata.json"
    async with aiofiles.open(metadata_file, "w") as f:
        await f.write(json.dumps(metadata, indent=2))
    
    return prompt_model_to_pydantic(db_prompt)

@app.get("/prompts", response_model=List[Prompt])
async def list_prompts(
    skip: int = 0, 
    limit: int = 100, 
    category: Optional[str] = None,
    model: Optional[str] = None,
    tag: Optional[str] = None,
    include_versions: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(PromptModel)
    
    if category:
        query = query.filter(PromptModel.category == category)
    
    if model:
        query = query.filter(PromptModel.model == model)
    
    if tag:
        # Filter prompts that have the specified tag
        query = query.filter(PromptModel.tags.like(f'%"{tag}"%'))
    
    prompts = query.offset(skip).limit(limit).all()
    return [prompt_model_to_pydantic(p, include_versions) for p in prompts]

@app.get("/prompts/{prompt_id}", response_model=Prompt)
async def get_prompt(prompt_id: str, include_versions: bool = True, db: Session = Depends(get_db)):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        prompt = db.query(PromptModel).filter(PromptModel.name == prompt_id).first()
        
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID or name '{prompt_id}' not found")
    
    return prompt_model_to_pydantic(prompt, include_versions)

@app.put("/prompts/{prompt_id}", response_model=Prompt)
async def update_prompt(prompt_id: str, prompt_update: PromptUpdate, db: Session = Depends(get_db)):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID '{prompt_id}' not found")
    
    # Update fields if provided
    if prompt_update.name is not None:
        # Check if the new name already exists
        existing = db.query(PromptModel).filter(PromptModel.name == prompt_update.name).first()
        if existing and existing.id != prompt_id:
            raise HTTPException(status_code=400, detail=f"Prompt with name '{prompt_update.name}' already exists")
        prompt.name = prompt_update.name
        
    if prompt_update.description is not None:
        prompt.description = prompt_update.description
        
    if prompt_update.category is not None:
        prompt.category = prompt_update.category
        
    if prompt_update.model is not None:
        prompt.model = prompt_update.model
        
    if prompt_update.tags is not None:
        prompt.tags = json.dumps(prompt_update.tags)
    
    prompt.updated_at = datetime.utcnow()
    db.commit()
    
    # Update metadata file
    metadata_file = Path(f"{DATA_DIR}/prompts/{prompt_id}/metadata.json")
    if metadata_file.exists():
        async with aiofiles.open(metadata_file, "r") as f:
            metadata = json.loads(await f.read())
            
        if prompt_update.name is not None:
            metadata["name"] = prompt_update.name
        if prompt_update.description is not None:
            metadata["description"] = prompt_update.description
        if prompt_update.category is not None:
            metadata["category"] = prompt_update.category
        if prompt_update.model is not None:
            metadata["model"] = prompt_update.model
        if prompt_update.tags is not None:
            metadata["tags"] = prompt_update.tags
            
        metadata["updated_at"] = datetime.utcnow().isoformat()
        
        async with aiofiles.open(metadata_file, "w") as f:
            await f.write(json.dumps(metadata, indent=2))
    
    return prompt_model_to_pydantic(prompt)

@app.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(prompt_id: str, db: Session = Depends(get_db)):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID '{prompt_id}' not found")
    
    # Delete all versions
    db.query(PromptVersionModel).filter(PromptVersionModel.prompt_id == prompt_id).delete()
    
    # Delete the prompt
    db.delete(prompt)
    db.commit()
    
    # Delete files
    prompt_dir = Path(f"{DATA_DIR}/prompts/{prompt_id}")
    if prompt_dir.exists():
        for file in prompt_dir.glob("*"):
            file.unlink()
        prompt_dir.rmdir()
    
    return None

@app.post("/prompts/{prompt_id}/versions", response_model=PromptVersion)
async def create_prompt_version(
    prompt_id: str, 
    version_create: PromptVersionCreate, 
    db: Session = Depends(get_db)
):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID '{prompt_id}' not found")
    
    # Generate new version number
    new_version = generate_new_version(prompt.current_version)
    now = datetime.utcnow()
    
    # Convert template schema and parameters to JSON
    template_schema = json.dumps(version_create.template_schema) if version_create.template_schema else None
    parameters = json.dumps(version_create.parameters) if version_create.parameters else None
    
    # Create new version in database
    version_id = str(uuid.uuid4())
    db_version = PromptVersionModel(
        id=version_id,
        prompt_id=prompt_id,
        version=new_version,
        content=version_create.content,
        template=version_create.template,
        template_schema=template_schema,
        parameters=parameters,
        created_at=now,
        performance_metrics=json.dumps([])
    )
    db.add(db_version)
    
    # Update prompt with new current version
    prompt.current_version = new_version
    prompt.updated_at = now
    db.commit()
    
    # Save version to file
    prompt_dir = Path(f"{DATA_DIR}/prompts/{prompt_id}")
    prompt_dir.mkdir(exist_ok=True)
    
    version_file = prompt_dir / f"{new_version}.txt"
    async with aiofiles.open(version_file, "w") as f:
        await f.write(version_create.content)
    
    # Update metadata
    metadata_file = prompt_dir / "metadata.json"
    if metadata_file.exists():
        async with aiofiles.open(metadata_file, "r") as f:
            metadata = json.loads(await f.read())
            
        metadata["current_version"] = new_version
        metadata["updated_at"] = now.isoformat()
        metadata["versions"].append({
            "version": new_version,
            "created_at": now.isoformat(),
            "template": version_create.template,
            "template_schema": version_create.template_schema
        })
        
        async with aiofiles.open(metadata_file, "w") as f:
            await f.write(json.dumps(metadata, indent=2))
    
    return PromptVersion(
        version=new_version,
        content=version_create.content,
        template=version_create.template,
        template_schema=version_create.template_schema,
        parameters=version_create.parameters,
        created_at=now,
        performance_metrics=[]
    )

@app.get("/prompts/{prompt_id}/versions/{version}", response_model=PromptVersion)
async def get_prompt_version(prompt_id: str, version: str, db: Session = Depends(get_db)):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID '{prompt_id}' not found")
    
    db_version = db.query(PromptVersionModel).filter(
        PromptVersionModel.prompt_id == prompt_id,
        PromptVersionModel.version == version
    ).first()
    
    if not db_version:
        raise HTTPException(status_code=404, detail=f"Version '{version}' not found for prompt '{prompt_id}'")
    
    performance_metrics = json.loads(db_version.performance_metrics) if db_version.performance_metrics else []
    template_schema = json.loads(db_version.template_schema) if db_version.template_schema else None
    parameters = json.loads(db_version.parameters) if db_version.parameters else None
    
    return PromptVersion(
        version=db_version.version,
        content=db_version.content,
        template=db_version.template,
        template_schema=template_schema,
        parameters=parameters,
        created_at=db_version.created_at,
        performance_metrics=performance_metrics
    )

@app.post("/prompts/{prompt_id}/versions/{version}/metrics", response_model=List[PerformanceMetric])
async def add_metrics(
    prompt_id: str, 
    version: str, 
    metrics: PromptMetricsUpdate, 
    db: Session = Depends(get_db)
):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID '{prompt_id}' not found")
    
    db_version = db.query(PromptVersionModel).filter(
        PromptVersionModel.prompt_id == prompt_id,
        PromptVersionModel.version == version
    ).first()
    
    if not db_version:
        raise HTTPException(status_code=404, detail=f"Version '{version}' not found for prompt '{prompt_id}'")
    
    # Add new metric
    new_metric = {
        "metric": metrics.metric,
        "value": metrics.value,
        "timestamp": datetime.utcnow().isoformat(),
        "model": metrics.model,
        "notes": metrics.notes
    }
    
    performance_metrics = json.loads(db_version.performance_metrics) if db_version.performance_metrics else []
    performance_metrics.append(new_metric)
    
    db_version.performance_metrics = json.dumps(performance_metrics)
    db.commit()
    
    return performance_metrics

@app.post("/prompts/{prompt_id}/render", response_model=dict)
async def render_prompt(prompt_id: str, render_params: PromptRender, db: Session = Depends(get_db)):
    prompt = db.query(PromptModel).filter(PromptModel.id == prompt_id).first()
    if not prompt:
        prompt = db.query(PromptModel).filter(PromptModel.name == prompt_id).first()
        
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt with ID or name '{prompt_id}' not found")
    
    # Get requested version or use current version
    version = render_params.version or prompt.current_version
    
    db_version = db.query(PromptVersionModel).filter(
        PromptVersionModel.prompt_id == prompt.id,
        PromptVersionModel.version == version
    ).first()
    
    if not db_version:
        raise HTTPException(status_code=404, detail=f"Version '{version}' not found for prompt '{prompt_id}'")
    
    # Check if this is a template
    if db_version.template:
        # Render template with provided parameters
        rendered_content = render_template(db_version.content, render_params.parameters)
        
        return {
            "prompt_id": prompt.id,
            "name": prompt.name,
            "version": version,
            "rendered_content": rendered_content,
            "parameters": render_params.parameters
        }
    else:
        # Return the content as is
        return {
            "prompt_id": prompt.id,
            "name": prompt.name,
            "version": version,
            "rendered_content": db_version.content,
            "parameters": {}
        }

@app.get("/categories", response_model=List[str])
async def list_categories(db: Session = Depends(get_db)):
    categories = db.query(PromptModel.category).distinct().all()
    return [c[0] for c in categories if c[0] is not None]

@app.get("/models", response_model=List[str])
async def list_models(db: Session = Depends(get_db)):
    models = db.query(PromptModel.model).distinct().all()
    return [m[0] for m in models if m[0] is not None]

@app.get("/tags", response_model=List[str])
async def list_tags(db: Session = Depends(get_db)):
    prompts = db.query(PromptModel).all()
    tags = set()
    
    for prompt in prompts:
        if prompt.tags:
            prompt_tags = json.loads(prompt.tags)
            tags.update(prompt_tags)
    
    return sorted(list(tags))

@app.post("/import", response_model=List[Prompt])
async def import_prompts(file_path: str = Body(..., embed=True), db: Session = Depends(get_db)):
    import_path = Path(file_path)
    if not import_path.exists():
        raise HTTPException(status_code=400, detail=f"File or directory '{file_path}' does not exist")
    
    imported_prompts = []
    
    if import_path.is_file():
        # Import single file
        if import_path.suffix in ['.json', '.yaml', '.yml']:
            try:
                # Read file content
                async with aiofiles.open(import_path, "r") as f:
                    content = await f.read()
                
                if import_path.suffix == '.json':
                    data = json.loads(content)
                else:
                    data = yaml.safe_load(content)
                
                # Handle both single prompt and list of prompts
                prompts_data = data if isinstance(data, list) else [data]
                
                for prompt_data in prompts_data:
                    # Create prompt using the API endpoint
                    create_data = PromptCreate(
                        name=prompt_data['name'],
                        description=prompt_data.get('description', ''),
                        category=prompt_data.get('category', 'General'),
                        model=prompt_data.get('model', 'Any'),
                        tags=prompt_data.get('tags', []),
                        content=prompt_data['content'],
                        is_template=prompt_data.get('is_template', False),
                        template_schema=prompt_data.get('template_schema')
                    )
                    
                    prompt = await create_prompt(create_data, db)
                    imported_prompts.append(prompt)
            
            except Exception as e:
                logger.error(f"Error importing file {import_path}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Error importing file: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Only JSON and YAML are supported.")
    
    elif import_path.is_dir():
        # Import all files in directory
        for file in import_path.glob("**/*"):
            if file.is_file() and file.suffix in ['.json', '.yaml', '.yml']:
                try:
                    # Read file content
                    async with aiofiles.open(file, "r") as f:
                        content = await f.read()
                    
                    if file.suffix == '.json':
                        data = json.loads(content)
                    else:
                        data = yaml.safe_load(content)
                    
                    # Handle both single prompt and list of prompts
                    prompts_data = data if isinstance(data, list) else [data]
                    
                    for prompt_data in prompts_data:
                        # Create prompt using the API endpoint
                        create_data = PromptCreate(
                            name=prompt_data['name'],
                            description=prompt_data.get('description', ''),
                            category=prompt_data.get('category', 'General'),
                            model=prompt_data.get('model', 'Any'),
                            tags=prompt_data.get('tags', []),
                            content=prompt_data['content'],
                            is_template=prompt_data.get('is_template', False),
                            template_schema=prompt_data.get('template_schema')
                        )
                        
                        try:
                            prompt = await create_prompt(create_data, db)
                            imported_prompts.append(prompt)
                        except HTTPException as he:
                            # Skip prompts that already exist
                            if he.status_code == 400 and "already exists" in he.detail:
                                logger.warning(f"Skipping import of '{prompt_data['name']}': {he.detail}")
                            else:
                                raise
                
                except Exception as e:
                    logger.error(f"Error importing file {file}: {str(e)}")
                    # Continue with other files
    
    return imported_prompts

@app.post("/export", response_model=dict)
async def export_prompts(
    export_path: str = Body(..., embed=True),
    category: Optional[str] = None,
    model: Optional[str] = None,
    tag: Optional[str] = None,
    format: str = "json",
    db: Session = Depends(get_db)
):
    # Get prompts based on filters
    query = db.query(PromptModel)
    
    if category:
        query = query.filter(PromptModel.category == category)
    
    if model:
        query = query.filter(PromptModel.model == model)
    
    if tag:
        # Filter prompts that have the specified tag
        query = query.filter(PromptModel.tags.like(f'%"{tag}"%'))
    
    prompts = query.all()
    
    if not prompts:
        raise HTTPException(status_code=404, detail="No prompts found matching the criteria")
    
    # Convert to export format
    export_data = []
    for prompt in prompts:
        # Get current version
        current_version = db.query(PromptVersionModel).filter(
            PromptVersionModel.prompt_id == prompt.id,
            PromptVersionModel.version == prompt.current_version
        ).first()
        
        if current_version:
            export_item = {
                "name": prompt.name,
                "description": prompt.description,
                "category": prompt.category,
                "model": prompt.model,
                "tags": json.loads(prompt.tags) if prompt.tags else [],
                "content": current_version.content,
                "is_template": current_version.template,
                "template_schema": json.loads(current_version.template_schema) if current_version.template_schema else None
            }
            export_data.append(export_item)
    
    # Ensure export directory exists
    export_dir = Path(export_path).parent
    export_dir.mkdir(exist_ok=True, parents=True)
    
    # Write export file
    if format.lower() == "json":
        async with aiofiles.open(export_path, "w") as f:
            await f.write(json.dumps(export_data, indent=2))
    elif format.lower() in ["yaml", "yml"]:
        async with aiofiles.open(export_path, "w") as f:
            await f.write(yaml.dump(export_data, sort_keys=False))
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Only JSON and YAML are supported.")
    
    return {
        "message": f"Successfully exported {len(export_data)} prompts to {export_path}",
        "prompts_exported": len(export_data),
        "export_path": export_path
    }