# Neo4j Introduction

### 🎯 What is Neo4j?

**Neo4j** is a graph database: a special type of database designed to store and query data as a graph of connected nodes and relationships. Unlike traditional databases that use tables, Neo4j stores data as a network of interconnected entities.

### 🤔 Why Graph Databases?

Traditional databases (like MySQL or PostgreSQL) store data in tables with rows and columns. This works great for many things, but struggles when relationships between data are important.

**Graph databases excel when:**
- You need to find connections between entities
- Relationships are as important as the data itself
- You want to traverse connections quickly
- You need to find paths between entities

### 🧩 Core Concepts

#### 🔵 1. Nodes (Vertices)

**Nodes** represent entities—the "things" in your data. Think of them as circles or boxes in a diagram.

**Examples:**
- A person
- A product
- A model
- A dataset
- A paper

**Properties:**
- Nodes can have properties (like name, age, description)
- Nodes can have labels (like `Person`, `Model`, `Dataset`)
- Labels help categorize nodes

#### 🔗 2. Relationships (Edges)

**Relationships** connect nodes together. They represent how entities are related.

**Examples:**
- Person → KNOWS → Person
- Model → USES → Dataset
- Model → CITES → Paper

**Properties:**
- Relationships have types (like `KNOWS`, `USES`, `CITES`)
- Relationships can have properties (like date, strength)
- Relationships have direction (A → B is different from B → A)

#### 📝 3. Properties

**Properties** are key-value pairs attached to nodes and relationships. They store the actual data.

**Node Properties:**
```
Node: Model
Properties:
  - name: "BERT"
  - downloads: 5000000
  - task: "text-classification"
```

**Relationship Properties:**
```
Relationship: USES_DATASET
Properties:
  - date: "2023-01-15"
  - purpose: "training"
```

#### 🏷️ 4. Labels

**Labels** categorize nodes. A node can have multiple labels.

**Example:**
- A node might have labels: `Model`, `Transformer`, `NLP`
- Labels help organize and query the graph
- You can find all nodes with a specific label

### 🔍 Cypher Query Language

**Cypher** is Neo4j's query language. It's designed to be visual and intuitive—queries look like the graph structure.

#### 📐 Basic Patterns

**Find all models:**
```cypher
MATCH (m:Model)
RETURN m
```

**Find models using a specific dataset:**
```cypher
MATCH (m:Model)-[:USES_DATASET]->(d:Dataset {name: "SQuAD"})
RETURN m
```

**Find related models:**
```cypher
MATCH (m1:Model)-[:USES_DATASET]->(d:Dataset)<-[:USES_DATASET]-(m2:Model)
WHERE m1.name <> m2.name
RETURN m1.name, m2.name
```

#### 📖 Reading Cypher

Cypher reads like English:
- `MATCH` = find
- `(m:Model)` = a node labeled Model, call it 'm'
- `-[:USES_DATASET]->` = connected by USES_DATASET relationship
- `RETURN` = give me back

### 🌐 Neo4j Browser

The **Neo4j Browser** (accessible at http://localhost:7474) is a web interface for interacting with your graph database.

#### ⭐ Key Features

**1. Query Editor**
- Write and run Cypher queries
- See results in a visual graph
- Save queries for later

**2. Graph Visualization**
- Results appear as an interactive graph
- Click nodes to see properties
- Drag to rearrange the view
- Zoom in/out to explore

**3. Data Browser**
- Browse nodes and relationships
- Filter by labels
- See property values
- Explore connections

#### 🖥️ Using Neo4j Browser

**1. Connect:**
- Open http://localhost:7474
- Enter username and password
- Click "Connect"

**2. Run a Query:**
- Type a Cypher query in the editor
- Press Enter or click "Run"
- Results appear below

**3. Explore Results:**
- Results show as a graph visualization
- Click nodes to see properties
- Click relationships to see details
- Use the sidebar to filter

**4. Save Queries:**
- Click the star icon to save queries
- Access saved queries from the sidebar
- Share queries with others

### 💼 Common Use Cases

#### 🔍 Finding Connections

**Question:** "What datasets does BERT use?"
```cypher
MATCH (m:Model {name: "BERT"})-[:USES_DATASET]->(d:Dataset)
RETURN d.name
```

#### 🔗 Finding Related Entities

**Question:** "What other models use the same datasets as BERT?"
```cypher
MATCH (bert:Model {name: "BERT"})-[:USES_DATASET]->(d:Dataset)
      <-[:USES_DATASET]-(other:Model)
WHERE other.name <> "BERT"
RETURN DISTINCT other.name
```

#### 🗺️ Path Finding

**Question:** "How is Model A connected to Model B?"
```cypher
MATCH path = shortestPath(
  (a:Model {name: "Model A"})-[*]-(b:Model {name: "Model B"})
)
RETURN path
```

### ✅ Key Takeaways

- **Neo4j** is a graph database for storing connected data
- **Nodes** represent entities (models, datasets, papers)
- **Relationships** connect nodes (USES, CITES, BASED_ON)
- **Cypher** is the query language (visual and intuitive)
- **Neo4j Browser** provides a web interface for exploration
- Graph databases excel at finding connections and relationships

### 📋 Quick Reference

| Concept | Description |
|---------|-------------|
| Node | An entity in the graph (like a model or dataset) |
| Relationship | A connection between nodes |
| Label | A category for nodes (like `Model` or `Dataset`) |
| Property | Data attached to nodes or relationships |
| Cypher | Neo4j's query language |
| Traversal | Following relationships from one node to another |

---

**Next:** [Elasticsearch Basics](elasticsearch.md) | [Previous: Dagster Basics](dagster.md) | [Back to Tutorial Overview](../concepts-tutorial.md)

