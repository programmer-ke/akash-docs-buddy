# High-level Structure

The overall design was inspired by common principles used in
hexagonal/onion/clean architectures, DDD and CQRS, with a message bus
being used for command/event dispatch.

A Mermaid representation of the dependency graph:

```mermaid
graph TB
    subgraph entrypoints["Entrypoints"]
        ENTRYPOINT["CLI / WEB"]
        Bootstrap["Bootstrap (composition root)"]
    end

    subgraph services["Services Layer"]
        direction TB
        Handlers["Handlers"]
        UseCases["Use Cases"]
        Commands["Commands"]
        Events["Events"]
        Protocols["Protocols (interfaces)"]
    end

    subgraph domain["Domain Layer"]
        Entities["Entities (Query, DocumentChunk, etc.)"]
        Logic["Domain Logic (sliding_window, overlapping_chunks)"]
    end

    subgraph adapters["Adapters Layer"]
        direction LR
        FSStorage["FileSystem Storage Adapters"]
        Whoosh["Whoosh Index Adapter"]
        Agent["OpenAI Agent Adapter"]
        InMemBus["InMemory MessageBus"]
    end

    ENTRYPOINT --> Bootstrap
    Bootstrap -->|wires| Handlers
    Bootstrap -->|wires| adapters
    Handlers -->|calls| UseCases
    Handlers -->|emits| Commands
    Handlers -->|publishes| Events
    UseCases -->|uses| Entities
    UseCases -->|depends on| Protocols
    adapters -->|implements| Protocols
    adapters -->|uses| Entities

    classDef entrypoint fill:#e1f5fe,stroke:#0288d1
    classDef service fill:#fff3e0,stroke:#f57c00
    classDef domain fill:#e8f5e9,stroke:#388e3c
    classDef adapter fill:#fce4ec,stroke:#d81b60
    class ENTRYPOINT,Bootstrap entrypoint
    class Handlers,UseCases,Commands,Events,Protocols service
    class Entities,Logic domain
    class FSStorage,Whoosh,Agent,InMemBus adapter
```

## Repository Structure

### Main package

The package root is `src/docs_buddy`

The structure underneath is as follows:

- **domain** - core entities and domain logic
- **services** - use cases, handlers, adapter protocols, commands & events
- **adapters** - concrete implementation of the adapter protocols
- **entrypoints** - CLI, web, composition root

### Tests

Tests are structured as follows:

- **unit** - domain & service functionality, isolated components
- **integration** - functionality cutting across architectural layers
- **e2e** - functionality exposed at the endpoints


## Key flows

### Fetching documentation

```mermaid
sequenceDiagram
    actor User
    participant CLI as CLI (__main__.py)
    participant Bus as Message Bus
    participant Handler as Handler (handlers.py)
    participant UseCase as Use Case (use_cases.py)
    participant Storage as Repository Storage
    participant Logger as Logging Adapter

    User->>CLI: Run with --repo-id --update-sources
    CLI->>Bus: send(SyncRepo(url))
    activate Bus
    Bus->>Handler: execute sync_repository handler
    activate Handler
    Handler->>UseCase: sync_repository(url, storage)
    activate UseCase
    UseCase->>Storage: pull_repo() or clone_repo(url)
    UseCase-->>Handler: (completes)
    deactivate UseCase
    Handler->>Bus: publish(RepositorySynced(url))
    Handler->>Bus: send(UpdateDocumentArtifacts)
    deactivate Handler
    deactivate Bus

    Bus->>Handler: execute update_document_artifacts handler
    activate Handler
    Handler->>UseCase: update_document_artifacts(storage, processor)
    Handler->>Bus: publish(DocumentArtifactsUpdated)
    Handler->>Bus: send(UpdateDocumentIndex)
    deactivate Handler

    Bus->>Handler: execute index_document_chunks handler
    activate Handler
    Handler->>UseCase: index_document_chunks(pipeline, index)
    Handler->>Bus: publish(DocumentIndexUpdated)
    deactivate Handler

    Bus->>Logger: notify_index_updated()
    Logger-->>CLI: log update message
    CLI-->>User: Sync complete
```

### Answering user queries

```mermaid
sequenceDiagram
    actor User
    participant CLI as CLI (__main__.py)
    participant Bus as Message Bus
    participant Handler as Handler (handlers.py)
    participant UseCase as Use Case (use_cases.py)
    participant Agent as OpenAI Agent
    participant Tool as Search Tool
    participant Index as Index Searcher

    User->>CLI: Run with --query "your question"
    CLI->>Bus: send(AnswerQuery(query))
    activate Bus
    Bus->>Handler: execute answer_query handler
    activate Handler
    Handler->>UseCase: find_answer(query, agent, tools)
    activate UseCase
    UseCase->>UseCase: Create Query domain object
    UseCase->>Agent: run_agent(query, hooks, config)
    activate Agent
    Agent->>Tool: search(query, max_results)
    activate Tool
    Tool->>Index: search(query, max_results)
    activate Index
    Index-->>Tool: list[QueryResult]
    deactivate Index
    Tool-->>Agent: search results
    deactivate Tool
    Agent-->>UseCase: QueryResponse(answer, sources)
    deactivate Agent
    UseCase-->>Handler: QueryResponse
    deactivate UseCase
    Handler-->>Bus: (completes)
    deactivate Handler
    deactivate Bus
    Bus-->>CLI: QueryResponse
    CLI-->>User: Display answer with sources
```
