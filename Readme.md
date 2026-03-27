# BBS Agent - Intelligent Forum Assistant System

## 🎯 Project Overview

The BBS Agent is an intelligent forum assistant system designed to help users efficiently search, retrieve, and interact with forum content. It combines advanced AI technologies including Large Language Models (LLMs), vector databases, and web crawling to provide a comprehensive solution for forum knowledge management.

**Key Features:**
- 🧠 Intelligent query understanding and processing
- 🔍 Multi-level semantic search across forum sections
- 📊 Dynamic knowledge base with real-time updates
- 🎯 Context-aware response generation
- 🔄 Automated content crawling and indexing

## 🏗️ System Architecture

The system follows a modular, layered architecture designed for scalability and maintainability:

### Core Layers

```
┌──────────────────────────────────────────┐
│               APP Layer                  │
│  - Main application entry point         │
│  - Agent initialization and control     │
└──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────┐
│              CORE Layer (Brain)          │
│  agent.py           - Main controller    │
│  planner.py         - Query planning     │
│  router.py          - Tool routing       │
│  pipeline.py        - Workflow control   │
│  memory.py          - Conversation state │
└──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────┐
│           KNOWLEDGE Layer                │
│  Three-tier vector database system:      │
│  - Static Store    - Forum structure     │
│  - Dynamic Store   - Crawled content     │
│  - User Store      - User uploads        │
└──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────┐
│             TOOLS Layer                  │
│  - Web crawlers                         │
│  - Search tools                         │
│  - Data processing tools                │
└──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────┐
│        INFRASTRUCTURE Layer             │
│  - Vector database (Chroma)             │
│  - Browser management (Playwright)      │
│  - Embedding models                     │
│  - Configuration management             │
└──────────────────────────────────────────┘
```

## 📁 Project Structure

```
BBS_Agent/
├── agent/                           # Core orchestration & session control
│   ├── agent.py                    # Single-turn Q&A entry (orchestration center)
│   ├── agent_task.py              # run_tasks loop / expansion / replan coordination
│   ├── agent_plan.py               # Default/merged task table structures
│   ├── agent_replan.py             # Replan entry
│   ├── planner.py                  # Planning and rule-based replanning
│   ├── router.py                   # task -> tool routing
│   ├── pipeline.py                 # Tool execution (param injection / retry / unified result)
│   ├── memory.py                   # Conversation & task result persistence
│   └── tools/                      # Tools layer (thin wrappers / parameter adaptation)
│       ├── initialize/             # Initialization / vector loading
│       ├── query/                  # Query tools
│       ├── search/                 # Search / crawling tools
│       └── summarize/             # RAG summarization & final answer generation
├── infrastructure/                 # Infrastructure layer (technical capabilities)
│   ├── browser_manager/          # Playwright browser control
│   ├── browser_manager_ts/       # TS-side browser manager (adapter)
│   ├── model_factory/            # Model factory (embedding/LLM routing)
│   └── vector_store/             # Chroma vector store service
├── knowledge/                      # Knowledge & retrieval implementation details
│   ├── ingestion/                 # Data ingestion
│   ├── processing/                # Data processing / cleaning / tagging
│   ├── retrieval/                 # Retrieval & re-ranking
│   └── stores/                    # Static/dynamic/user stores & indexing
├── config/                         # JSON configuration
│   ├── data/                      # Data dimension / derived configs
│   ├── driver/                    # Browser driver configuration
│   ├── model/                     # Model configuration
│   ├── prompts/                   # Prompt template selection
│   ├── vector_store/             # Vector DB / collection configuration
│   └── websites/                # Forum sites / site list
├── data/                           # Input data & crawl outputs
│   ├── static/                    # Static forum data
│   ├── dynamic/                   # Dynamically crawled data
│   ├── store/                     # User uploaded data
│   ├── web_structure/            # Forum structure data
│   └── test/                      # Test/sample data
├── vector_db/                      # Chroma persistence directory (static/dynamic/user)
│   ├── static/
│   ├── dynamic/
│   └── store/
├── utils/                          # Shared utilities
├── logs/                           # Application logs
├── prompts/                        # LLM prompt templates
├── main.py                         # Application entry (CLI chat loop)
├── test.py                         # Local test script
└── requirements.txt                # Dependencies
```

## 🧱 Layered Refactor Roadmap (from `.cursor/plans`)

The current repository already implements the full loop: single-turn Q&A -> planning -> task loop -> replan -> answer-sufficiency check -> RAG generation.
The next step is to decouple business orchestration from `tools` and move toward a long-term layered architecture.

### P0 (first: decouple & make it maintainable)
- Add `agent/services` skeleton: `query/crawler/indexing/safety` service interfaces
- Turn `agent/tools/search` and `agent/tools/initialize` into thin wrappers (parameter adaptation + calling services)
- Remove import-time side effects (especially vector/store initialization) and use an explicit `bootstrap`
- Establish a minimal end-to-end smoke test: question -> on-demand crawl -> vectorization -> retrieve answer (freeze regression baseline)

### P1 (next: quality & stability)
- Incremental jobs (cursor, retry, idempotency keys)
- Add rerank plug-in points (keep the switch)
- Add schema validation for `config` (Pydantic)
- Add offline evaluation scripts (Recall@k, MRR, hit rate, etc.)

### P2 (later: fine-tuned model productization)
- `model_registry` + `model_router`: configurable routing from task to model
- Training & evaluation pipelines (versioning, sample extraction/cleaning)
- Canary/rollback: `base` / `ft-*` model paths controlled

### Target boundaries (acceptance criteria)
- `tools`: no direct browser/vector-store operations; only input adaptation + routing
- `services`: holds the business orchestration core (Query/Crawler/Indexing/Safety)
- `infrastructure`: only provides technical capabilities
- `knowledge`: converges to retrieval/indexing implementation details

## 🚀 Development Process

Based on git history analysis, the project evolved through several key phases:

### Phase 1: Foundation (2026-03-02)
- **Init agent**: Basic agent framework setup
- **Update framework**: Core system architecture

### Phase 2: Data Infrastructure (2026-03-03)
- **Add vector store**: Multi-tier vector database implementation
- **Init initialize tools**: Tool system foundation

### Phase 3: Core Features (2026-03-04)
- **Init search function**: Basic search capabilities

### Phase 4: Advanced Features (2026-03-05)
- **Update batch crawl**: Automated content crawling
- **Update agent framework**: Enhanced agent capabilities
- **Update plan function**: Improved planning system

### Phase 5: LLM Integration (2026-03-06)
- **Update planner**: LLM-based query planning

## 🔧 Key Components

### Vector Store System
The system implements a sophisticated three-tier vector database:

1. **Static Store** (`vector_db/static/`)
   - Forum structure summaries
   - Section introductions and metadata
   - Stable, long-term knowledge

2. **Dynamic Store** (`vector_db/dynamic/`)
   - Real-time crawled forum content
   - Time-sensitive information
   - Frequently updated data

3. **User Store** (`vector_db/store/`)
   - User-uploaded documents
   - Custom knowledge bases
   - Personalized content

### Configuration Management
- **JSON-based configuration**: Modular, easy-to-maintain configs
- **Environment-specific settings**: Development/production separation
- **Dynamic reloading**: Runtime configuration updates

### Tool System
- **Modular tool architecture**: Easy extension and maintenance
- **Tool discovery**: Automatic tool registration
- **Dependency injection**: Clean separation of concerns

## 🛠️ Technology Stack

- **Python 3.8+**: Core programming language
- **LangChain**: LLM application framework
- **Chroma**: Vector database
- **Playwright**: Web automation and crawling
- **Transformers**: NLP model integration
- **Hugging Face**: Embedding models
- **Beautiful Soup**: HTML parsing

## 🔁 Single-turn Q&A loop (current implementation)

```mermaid
flowchart LR
    U[User input] --> M[main.py: create session + write chat.jsonl]
    M --> A[agent/agent.py: create_conversation + run_tasks]
    A --> P[planner.plan / planner.replan]
    P --> T[run_tasks loop (board expansion possible)]
    T --> R[router.route: task -> tool_name]
    R --> X[pipeline.execute_task: param injection / retry]
    X --> Mem[memory: write back each task result]
    Mem --> S[answer-sufficiency check (may trigger replanning)]
    S -->|sufficient| G[rag_summarize: generate answer + collect references]
    S -->|insufficient| Re[agent_replan.run_replan: update task queue]
```

Implementation highlights (mapped to code modules):
- `main.py`: reads user input, creates `usr_history/<first-question-summary>/` on first valid input, writes `chat.jsonl`, and generates readable `chat.txt` on exit.
- `agent/agent.py`: initializes conversation/context, runs `planner.plan` to get the default to-do table, executes tasks via Router->Pipeline->tools, and triggers replan when results are insufficient.
- `agent/agent_task.py`: manages the `replan_count` limit; supports expanding board-related tasks into `3-x/4-x` style tasks.
- `agent/router.py` + `agent/pipeline.py`: perform tool routing and unified execution records (`execution_record`) with retries; then write results into Memory.
- `agent/tools/summarize/rag_summarize.py`: builds the final hierarchical, conversational answer and attaches `【参考来源】`.

## 🚀 Getting Started

### Prerequisites
```bash
pip install -r requirements.txt
playwright install
```

### Basic Usage
```python
# Run the test script
python test.py

# Start the main application
python main.py
```

### Configuration
1. Edit `config/vector_store/` JSON files for database settings
2. Configure prompts in `prompts/` directory
3. Set up data paths in configuration files

## 🔮 Optimization Suggestions

### Immediate Improvements
1. **Enhanced Error Handling**: Add comprehensive error handling and logging
2. **Performance Optimization**: Implement caching and async operations
3. **Testing Framework**: Add unit tests and integration tests
4. **Documentation**: Expand API documentation and usage examples

### Medium-term Enhancements
1. **Advanced Caching**: Implement Redis/memory caching for frequent queries
2. **Real-time Updates**: WebSocket support for live forum updates
3. **Multi-language Support**: Internationalization and localization
4. **User Authentication**: Secure access control and user management

### Long-term Vision
1. **Multi-agent Collaboration**: Distributed agent system
2. **Advanced Analytics**: User behavior analysis and insights
3. **Mobile Application**: Native mobile app integration
4. **API Gateway**: RESTful API for external integrations

## 📈 Performance Considerations

- **Vector Database Optimization**: Chunk size tuning, index optimization
- **Memory Management**: Efficient conversation state handling
- **Concurrent Processing**: Multi-threaded crawling and processing
- **Resource Monitoring**: System health and performance metrics

## 🔒 Security Considerations

- **Input Validation**: Sanitize all user inputs
- **Rate Limiting**: Prevent abuse and DoS attacks
- **Data Privacy**: Secure handling of user data
- **Authentication**: Secure access to sensitive operations

## 🤝 Contributing

1. Fork the repository
2. Create feature branches for new functionality
3. Add tests for new features
4. Update documentation
5. Submit pull requests

## 📞 Support

For questions, issues, or contributions, please use the GitHub issue tracker or contact the development team.

