# 🤖 Grams AI Analytics Agent

> **Enterprise-Grade AI Assistant for Banking Operations**  
> A secure, role-based AI agent built on Azure Functions that combines SQL analytics with RAG (Retrieval-Augmented Generation) to provide intelligent insights to banking staff.

[![Azure Functions](https://img.shields.io/badge/Azure-Functions-blue)](https://azure.microsoft.com/en-us/services/functions/)
[![Python](https://img.shields.io/badge/Python-3.11-green)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange)](https://openai.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Role-Based Security Model](#role-based-security-model)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Project Structure](#project-structure)
- [Technologies Used](#technologies-used)

---

## 🎯 Overview

The **Grams Bank AI Analytics Agent** is an intelligent, multi-functional assistant designed specifically for internal banking staff. It combines the power of natural language processing with secure database access and knowledge retrieval to provide:

- **📊 Data Analytics**: Natural language SQL queries with intelligent insights
- **📚 Knowledge Base**: RAG-powered document search for policies and procedures  
- **🔒 Security**: Hierarchical role-based access control (RBAC)
- **💬 Context Awareness**: Maintains conversation history for follow-up queries

This system was built to democratize data access while maintaining strict security boundaries based on organizational hierarchy.

---

## ✨ Key Features

### 1. **Intelligent Query Classification**
The agent automatically classifies user queries into four categories:
- **SQL**: Data and analytics queries requiring database access
- **RAG**: Support queries needing knowledge base search
- **HYBRID**: Queries requiring both data analysis and contextual explanation
- **FALLBACK**: Greetings, clarifications, and off-topic requests

### 2. **Role-Based Data Access Control**
Five-tier hierarchical access system:
- **RMO** (Relationship Management Officer): Access to own data only
- **BM** (Branch Manager): Access to all RMOs under their branch
- **ZM** (Zonal Manager): Access to all branches in their zone
- **CL** (Cluster Lead): Access to all zones in their cluster  
- **RM** (Regional Manager): Access to all clusters in their region

### 3. **Dynamic SQL Generation**
- AI-powered SQL query generation from natural language
- Automatic injection of role-based WHERE clauses
- Context-aware follow-up query support

### 4. **RAG Knowledge Retrieval**
- Azure Cognitive Search integration
- Indexed document search for policies, procedures, and guides
- Source attribution for all retrieved information

### 5. **Conversation Context Management**
- Persistent conversation history per user
- Support for follow-up questions
- Query history tracking

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT (Frontend)                        │
│                  React / HTML / Mobile App                   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS REST API
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  AZURE FUNCTION APP                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              API ENDPOINTS                            │  │
│  │  • /login     • /chat      • /health                  │  │
│  │  • /clear_context          • /test_db                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────┴───────────────────────────────┐   │
│  │           INTENT CLASSIFICATION                       │   │
│  │  (OpenAI GPT-4 + Keyword Analysis)                    │   │
│  └──────┬────────────┬─────────────┬─────────────────┬──┘   │
│         │            │             │                 │       │
│         ▼            ▼             ▼                 ▼       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐     ┌──────────┐   │
│  │   SQL    │ │   RAG    │ │  HYBRID  │     │ FALLBACK │   │
│  │ Handler  │ │ Handler  │ │ Handler  │     │ Handler  │   │
│  └─────┬────┘ └─────┬────┘ └─────┬────┘     └──────────┘   │
└────────┼────────────┼────────────┼──────────────────────────┘
         │            │            │
         ▼            ▼            ▼
┌─────────────┐ ┌──────────────┐ ┌─────────────────┐
│  AZURE SQL  │ │ AZURE SEARCH │ │ AZURE OPENAI    │
│  DATABASE   │ │ (Cognitive)  │ │ GPT-4 API       │
│             │ │              │ │                 │
│ • staff_    │ │ • Knowledge  │ │ • Query Gen     │
│   analytics │ │   Index      │ │ • Insights Gen  │
│ • Role-     │ │ • Document   │ │ • Classification│
│   based     │ │   Embeddings │ │                 │
│   filtering │ │              │ │                 │
└─────────────┘ └──────────────┘ └─────────────────┘
```

### **Data Flow**

1. **Authentication**: User logs in with email → System identifies role and accessible data scope
2. **Query Processing**: User asks question → Intent classifier routes to appropriate handler
3. **Data Retrieval**: 
   - **SQL Path**: Generate query → Apply role filters → Execute → Generate insights
   - **RAG Path**: Search indexed documents → Retrieve relevant content → Generate answer
4. **Response**: Return formatted response with data/sources

---

## 🔐 Role-Based Security Model

### **The Problem**
In banking organizations, staff at different levels need access to different scopes of data. A Branch Manager should see all their RMOs' data, but not data from other branches. This requires **dynamic query filtering** based on user identity.

### **The Solution**
I implemented a **hierarchical access control system** that:

1. **Identifies user role** during login by querying the organizational hierarchy
2. **Calculates accessible scope** by traversing the reporting structure
3. **Injects security filters** into every SQL query automatically

### **Access Hierarchy**

```
        RM (Regional Manager)
         │
         ├─── CL (Cluster Lead)
         │     │
         │     ├─── ZM (Zonal Manager)
         │     │     │
         │     │     ├─── BM (Branch Manager)
         │     │     │     │
         │     │     │     └─── RMO (Relationship Mgmt Officer)
         │     │     │
         │     │     └─── BM → RMO
         │     │
         │     └─── ZM → BM → RMO
         │
         └─── CL → ZM → BM → RMO
```

### **Implementation Details**

**Example: Branch Manager Access**
```python
def get_accessible_emails(email: str, role: str, cursor):
    if role == "BM":
        # Get all RMOs under this Branch Manager
        cursor.execute("""
            SELECT DISTINCT rmo_email 
            FROM staff_analytics 
            WHERE bm_email = ?
        """, email)
        return [row.rmo_email for row in cursor.fetchall()]
```

**Automatic SQL Filter Injection**
```python
# User asks: "Show me top performers this month"
# System generates:
SELECT rmo_name, total_revenue 
FROM staff_analytics 
WHERE rmo_email IN ('rmo1@company.com', 'rmo2@company.com', ...)  # Auto-injected
  AND period_month = 1 
  AND period_year = 2025
ORDER BY total_revenue DESC
```

### **Security Benefits**

✅ **Zero Trust**: No query executes without role-based filtering  
✅ **Transparent**: Users don't manage their own access - it's automatic  
✅ **Scalable**: Works for organizations with thousands of employees  
✅ **Audit-Ready**: All queries are logged with user context

---

## 🚀 Installation

### **Prerequisites**

- Python 3.11+
- Azure Functions Core Tools v4
- Azure CLI
- Azure subscription with:
  - Azure SQL Database
  - Azure OpenAI Service
  - Azure Cognitive Search

### **Setup Steps**

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/grams-bank-ai-agent.git
cd grams-bank-ai-agent
```

2. **Create virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp local.settings.json.example local.settings.json
# Edit local.settings.json with your Azure credentials
```

5. **Run locally**
```bash
func start
```

The API will be available at `http://localhost:7071`

---

## ⚙️ Configuration

### **local.settings.json**

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    
    "AZURE_OPENAI_API_KEY": "your-openai-api-key",
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "gpt-4",
    "OPENAI_API_VERSION": "2024-02-01",
    
    "AZURE_SEARCH_ENDPOINT": "https://your-search.search.windows.net",
    "AZURE_SEARCH_KEY": "your-search-key",
    
    "DATABASE_CONNECTION": "Driver={ODBC Driver 17 for SQL Server};Server=your-server.database.windows.net;Database=your-db;Uid=your-user;Pwd=your-password"
  }
}
```

### **host.json**

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

---

## 📡 API Endpoints

### **1. Login - User Authentication**
```http
POST /api/login
Content-Type: application/json

{
  "email": "john.doe@company.com"
}
```

**Response:**
```json
{
  "success": true,
  "user": {
    "email": "john.doe@company.com",
    "name": "John Doe",
    "role": "BM",
    "role_description": "Branch Manager",
    "accessible_emails": ["rmo1@company.com", "rmo2@company.com"],
    "subordinate_count": 5,
    "permissions": {
      "view_own_data": true,
      "view_subordinate_data": true,
      "view_aggregate_reports": false,
      "view_trends": true,
      "export_data": false
    }
  }
}
```

### **2. Chat - Query Processing**
```http
POST /api/chat
Content-Type: application/json

{
  "email": "john.doe@company.com",
  "question": "Show me top 5 performers this month"
}
```

**Response:**
```json
{
  "type": "analytics",
  "response": "**Top Performers - January 2025**\n\n1. **Jane Smith** - ₦45.2M revenue...",
  "data": [
    {
      "rmo_name": "Jane Smith",
      "total_revenue": 45200000,
      "score_card": 95
    }
  ],
  "total_records": 5,
  "user": "John Doe",
  "timestamp": "2025-01-15T10:30:00"
}
```

### **3. Health Check**
```http
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "Grams Analytics AI Agent",
  "version": "1.0.0",
  "timestamp": "2025-01-15T10:30:00",
  "dependencies": {
    "database": true,
    "openai": true,
    "search": true
  }
}
```

### **4. Clear Context**
```http
POST /api/clear_context
Content-Type: application/json

{
  "email": "john.doe@company.com"
}
```

### **5. Test Database Connection**
```http
GET /api/test_db
```

---

## 💡 Usage Examples

### **Example 1: Data Analytics Query**
```
User: "What's my total revenue for December 2024?"

Agent: 
**Revenue Summary - December 2024**

Your branch generated a total revenue of **₦125.4M** in December 2024.

**Breakdown:**
- CASA Balance: ₦85.2M (68%)
- Credit Turnover: ₦40.2M (32%)

**Performance:**
- Month-over-month growth: +12.5%
- Score card: 87/100
```

### **Example 2: RAG Query**
```
User: "How do I reset a customer's BVN verification?"

Agent:
To reset a customer's BVN verification, follow these steps:

1. Log into the admin portal
2. Navigate to Customer Management > BVN Verification
3. Search for the customer using account number
4. Click "Reset BVN Status"
5. Customer will receive SMS to re-verify

**Important:** Only Branch Managers and above can perform BVN resets.

*Source: BVN_Verification_Guide.pdf*
```

### **Example 3: Hybrid Query**
```
User: "Why is my score lower this month?"

Agent:
**Score Analysis - Your Performance**

Your score decreased from 92 to 85 (-7 points) this month.

**Key Contributing Factors:**
1. **CASA Balance** decreased by 15% (₦12M drop)
2. **BankApp adoption** is below target (45 vs 60 expected users)
3. **Credit turnover** remained stable

**Recommendations:**
- Focus on CASA mobilization campaigns
- Promote BankApp through branch visits
- Target high-value customers for account upgrades

*Source: Performance data + Scoring_Methodology.pdf*
```

---

## 📂 Project Structure

```
grams-bank-ai-agent/
│
├── function_app.py              # Main application file with all endpoints
├── requirements.txt             # Python dependencies
├── host.json                    # Azure Functions host configuration
├── local.settings.json          # Environment variables (gitignored)
├── .funcignore                  # Files to ignore during deployment
├── .gitignore                   # Git ignore rules
│
├── README.md                    # This file
├── LICENSE                      # MIT License
│
└── docs/                        # Additional documentation
    ├── architecture.md          # Detailed architecture docs
    ├── security.md              # Security model documentation
    └── deployment.md            # Deployment guide
```

---

## 🛠️ Technologies Used

| Technology | Purpose |
|------------|---------|
| **Azure Functions** | Serverless compute platform for API hosting |
| **Python 3.11** | Core programming language |
| **Azure OpenAI (GPT-4)** | Natural language understanding and generation |
| **Azure SQL Database** | Relational database for staff analytics |
| **Azure Cognitive Search** | Document indexing and semantic search |
| **PyODBC** | SQL Server database connectivity |
| **OpenAI Python SDK** | Integration with Azure OpenAI |

### **Key Python Libraries**
```
azure-functions==1.18.0
azure-search-documents==11.4.0
openai==1.12.0
pyodbc==5.0.1
```

---

## 🎓 What I Learned Building This

### **1. Hierarchical Access Control**
Implementing dynamic, role-based data filtering taught me:
- SQL optimization for complex joins across organizational hierarchies
- Caching strategies for user access scopes
- Security-first API design

### **2. Agentic AI Systems**
Building an AI that routes queries intelligently required:
- Intent classification with hybrid approaches (keywords + LLM)
- Prompt engineering for consistent SQL generation
- Handling ambiguous queries gracefully

### **3. RAG Implementation**
Integrating knowledge retrieval involved:
- Document chunking and embedding strategies
- Balancing search recall vs precision
- Source attribution and hallucination prevention

### **4. Production-Ready Azure Functions**
Deploying to Azure taught me:
- Environment variable management
- CORS configuration for cross-origin requests
- Health check and monitoring best practices

---

## 📈 Future Enhancements

- [ ] Add export functionality for reports (Excel, PDF)
- [ ] Implement data visualization generation
- [ ] Add multi-language support
- [ ] Create admin dashboard for usage analytics
- [ ] Implement rate limiting and query cost monitoring
- [ ] Add voice interface support
- [ ] Implement federated learning for privacy-preserving insights

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**Your Name**
- Portfolio: [yourwebsite.com](https://yourwebsite.com)
- LinkedIn: [linkedin.com/in/yourprofile](https://linkedin.com/in/yourprofile)
- Email: your.email@example.com

---

## 🙏 Acknowledgments

- Azure Functions documentation and community
- OpenAI for GPT-4 API
- The banking industry for inspiring this use case

---


**⭐ If you found this project interesting, please consider giving it a star!**
