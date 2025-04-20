from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import os
from neo4j import GraphDatabase

app = FastAPI(title="Knowledge Graph Service", description="Service for managing the Unified Data Architecture knowledge graph")

# Neo4j connection settings
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Database driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Models
class Entity(BaseModel):
    name: str
    entityType: str
    observations: List[str]

class Relation(BaseModel):
    from_entity: str
    relationType: str
    to_entity: str

class EntitiesRequest(BaseModel):
    entities: List[Entity]

class RelationsRequest(BaseModel):
    relations: List[Relation]

class ObservationRequest(BaseModel):
    entityName: str
    contents: List[str]

class ObservationsRequest(BaseModel):
    observations: List[ObservationRequest]

class EntityNamesRequest(BaseModel):
    entityNames: List[str]

class DeleteRelationsRequest(BaseModel):
    relations: List[Relation]

class DeleteObservationsRequest(BaseModel):
    deletions: List[ObservationRequest]

# Database session dependency
def get_db():
    with driver.session() as session:
        yield session

@app.on_event("startup")
def startup_db_client():
    # Initialize constraints
    with driver.session() as session:
        session.run("CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

@app.on_event("shutdown")
def shutdown_db_client():
    driver.close()

@app.get("/")
async def root():
    return {"message": "Knowledge Graph Service API"}

@app.post("/entities", response_model=List[Entity])
async def create_entities(request: EntitiesRequest, db=Depends(get_db)):
    created_entities = []
    
    for entity in request.entities:
        result = db.run(
            """
            MERGE (e:Entity {name: $name})
            SET e.entityType = $entityType
            WITH e
            UNWIND $observations as observation
            MERGE (o:Observation {content: observation})
            MERGE (e)-[:HAS_OBSERVATION]->(o)
            RETURN e.name as name, e.entityType as entityType, collect(o.content) as observations
            """,
            name=entity.name,
            entityType=entity.entityType,
            observations=entity.observations
        )
        
        record = result.single()
        created_entities.append(Entity(
            name=record["name"], 
            entityType=record["entityType"], 
            observations=record["observations"]
        ))
    
    return created_entities

@app.post("/relations", response_model=List[Relation])
async def create_relations(request: RelationsRequest, db=Depends(get_db)):
    created_relations = []
    
    for relation in request.relations:
        result = db.run(
            """
            MATCH (from:Entity {name: $from_entity})
            MATCH (to:Entity {name: $to_entity})
            MERGE (from)-[r:RELATES_TO {type: $relationType}]->(to)
            RETURN from.name as from_entity, r.type as relationType, to.name as to_entity
            """,
            from_entity=relation.from_entity,
            relationType=relation.relationType,
            to_entity=relation.to_entity
        )
        
        record = result.single()
        created_relations.append(Relation(
            from_entity=record["from_entity"],
            relationType=record["relationType"],
            to_entity=record["to_entity"]
        ))
    
    return created_relations

@app.post("/observations", response_model=List[ObservationRequest])
async def add_observations(request: ObservationsRequest, db=Depends(get_db)):
    added_observations = []
    
    for observation_req in request.observations:
        result = db.run(
            """
            MATCH (e:Entity {name: $entityName})
            WITH e
            UNWIND $contents as content
            MERGE (o:Observation {content: content})
            MERGE (e)-[:HAS_OBSERVATION]->(o)
            RETURN e.name as entityName, collect(o.content) as contents
            """,
            entityName=observation_req.entityName,
            contents=observation_req.contents
        )
        
        record = result.single()
        added_observations.append(ObservationRequest(
            entityName=record["entityName"],
            contents=record["contents"]
        ))
    
    return added_observations

@app.delete("/entities", response_model=List[str])
async def delete_entities(request: EntityNamesRequest, db=Depends(get_db)):
    deleted_entities = []
    
    for entity_name in request.entityNames:
        result = db.run(
            """
            MATCH (e:Entity {name: $name})
            OPTIONAL MATCH (e)-[:HAS_OBSERVATION]->(o:Observation)
            DETACH DELETE e, o
            RETURN $name as name
            """,
            name=entity_name
        )
        
        record = result.single()
        deleted_entities.append(record["name"])
    
    return deleted_entities

@app.delete("/relations", response_model=List[Relation])
async def delete_relations(request: DeleteRelationsRequest, db=Depends(get_db)):
    deleted_relations = []
    
    for relation in request.relations:
        result = db.run(
            """
            MATCH (from:Entity {name: $from_entity})-[r:RELATES_TO {type: $relationType}]->(to:Entity {name: $to_entity})
            DELETE r
            RETURN from.name as from_entity, $relationType as relationType, to.name as to_entity
            """,
            from_entity=relation.from_entity,
            relationType=relation.relationType,
            to_entity=relation.to_entity
        )
        
        record = result.single()
        deleted_relations.append(Relation(
            from_entity=record["from_entity"],
            relationType=record["relationType"],
            to_entity=record["to_entity"]
        ))
    
    return deleted_relations

@app.delete("/observations", response_model=List[ObservationRequest])
async def delete_observations(request: DeleteObservationsRequest, db=Depends(get_db)):
    deleted_observations = []
    
    for deletion in request.deletions:
        result = db.run(
            """
            MATCH (e:Entity {name: $entityName})-[r:HAS_OBSERVATION]->(o:Observation)
            WHERE o.content IN $contents
            DELETE r, o
            RETURN e.name as entityName, collect(o.content) as contents
            """,
            entityName=deletion.entityName,
            contents=deletion.contents
        )
        
        record = result.single()
        deleted_observations.append(ObservationRequest(
            entityName=record["entityName"],
            contents=record["contents"]
        ))
    
    return deleted_observations

@app.get("/graph", response_model=dict)
async def read_graph(db=Depends(get_db)):
    entities_result = db.run(
        """
        MATCH (e:Entity)
        OPTIONAL MATCH (e)-[:HAS_OBSERVATION]->(o:Observation)
        RETURN e.name as name, e.entityType as entityType, collect(o.content) as observations
        """
    )
    
    relations_result = db.run(
        """
        MATCH (from:Entity)-[r:RELATES_TO]->(to:Entity)
        RETURN from.name as from_entity, r.type as relationType, to.name as to_entity
        """
    )
    
    entities = [
        {
            "type": "entity",
            "name": record["name"],
            "entityType": record["entityType"],
            "observations": record["observations"]
        }
        for record in entities_result
    ]
    
    relations = [
        {
            "type": "relation",
            "from": record["from_entity"],
            "relationType": record["relationType"],
            "to": record["to_entity"]
        }
        for record in relations_result
    ]
    
    return {"entities": entities, "relations": relations}

@app.get("/search", response_model=dict)
async def search_nodes(query: str, db=Depends(get_db)):
    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    
    search_term = f".*{query}.*"
    
    entities_result = db.run(
        """
        MATCH (e:Entity)
        WHERE e.name =~ $search_term OR e.entityType =~ $search_term
        OPTIONAL MATCH (e)-[:HAS_OBSERVATION]->(o:Observation)
        RETURN e.name as name, e.entityType as entityType, collect(o.content) as observations
        UNION
        MATCH (e:Entity)-[:HAS_OBSERVATION]->(o:Observation)
        WHERE o.content =~ $search_term
        RETURN e.name as name, e.entityType as entityType, collect(o.content) as observations
        """,
        search_term=search_term
    )
    
    entities = [
        {
            "type": "entity",
            "name": record["name"],
            "entityType": record["entityType"],
            "observations": record["observations"]
        }
        for record in entities_result
    ]
    
    return {"entities": entities}

@app.get("/nodes", response_model=dict)
async def open_nodes(names: List[str], db=Depends(get_db)):
    if not names:
        raise HTTPException(status_code=400, detail="Entity names list cannot be empty")
    
    entities_result = db.run(
        """
        MATCH (e:Entity)
        WHERE e.name IN $names
        OPTIONAL MATCH (e)-[:HAS_OBSERVATION]->(o:Observation)
        RETURN e.name as name, e.entityType as entityType, collect(o.content) as observations
        """,
        names=names
    )
    
    entities = [
        {
            "type": "entity",
            "name": record["name"],
            "entityType": record["entityType"],
            "observations": record["observations"]
        }
        for record in entities_result
    ]
    
    return {"entities": entities}