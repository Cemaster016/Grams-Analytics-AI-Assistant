# Add this import at the top of your file
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import azure.functions as func
import json
import logging
import os
import asyncio
from typing import Dict, Any, List
import pyodbc
from openai import AzureOpenAI
from datetime import datetime
import re

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Function App - MUST BE EARLY IN FILE
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Global conversation context storage
conversation_context = {}

# Initialize OpenAI
try:
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-01",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    openai_client = None
    
    
# Initialize Azure Cognitive Search
try:
    search_client = SearchClient(
        endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", "https://company-analytics-search-dev.search.windows.net"),
        index_name="company-knowledge-index",
        credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY"))
    )
    logger.info("Azure Search client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Azure Search client: {e}")
    search_client = None

# CORS headers for all responses
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

# System message for the AI
SYSTEM_MESSAGE = """
You are Grams Analytics AI Assistant, an intelligent agent for Grams Bank staff.

Your capabilities:
1. DATA ANALYTICS: Query and analyze performance metrics from the staff_analytics table
2. PLATFORM SUPPORT: Guide users on how to use Grams platforms and applications
3. BANKING KNOWLEDGE: Provide information about banking procedures and policies

Table Schema (staff_analytics):
- id: Record ID
- rm_email, rm_name: Regional Manager
- cl_email, cl_name: Cluster Lead
- zm_email, zm_name: Zonal Manager
- bm_email, bm_name: Branch Manager
- rmo_email, rmo_name: Relationship Management Officer
- total_accounts: Number of accounts managed
- casa_balance: Current and savings account balance
- total_revenue: Total revenue generated
- score_card: Performance score (0-100)
- bankapp_count: Number of BankApp digital banking users
- busacct_count: Number of BusAcct (Business Account) transactions
- ussd_count: Number of USSD banking users
- credit_turnover: Credit turnover amount
- period_month: Month of the record
- period_year: Year of the record
- created_date: When record was created

Role Hierarchy (lowest to highest):
RMO → BM → ZM → CL → RM

IMPORTANT FORMATTING RULES:
- Use **bold** for headings and important metrics
- When data is requested in tabular format, ONLY provide the summary text, not the raw table
- Structure responses with clear sections
- For follow-up questions, reference previous context
"""

# ============= ENDPOINTS =============

@app.function_name(name="login")
@app.route(route="login", methods=["POST", "OPTIONS"])
def login_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Authenticate user and return profile with permissions"""
    
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=CORS_HEADERS)
    
    try:
        try:
            req_body = req.get_json()
        except ValueError as e:
            logger.error(f"Invalid JSON in request body: {e}")
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON format"}),
                status_code=400,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        
        email = req_body.get('email', '').strip().lower() if req_body else ""
        
        if not email:
            return func.HttpResponse(
                json.dumps({"error": "Email required"}),
                status_code=400,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        
        logger.info(f"Login attempt for: {email}")
        
        user_info = get_user_info(email)
        
        if user_info:
            logger.info(f"Login successful: {email} ({user_info['role']}) - Access to {user_info['subordinate_count']} RMOs")
            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "user": user_info
                }),
                status_code=200,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        else:
            logger.warning(f"User not found: {email}")
            return func.HttpResponse(
                json.dumps({"error": "User not found in system"}),
                status_code=401,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )

@app.function_name(name="chat")
@app.route(route="chat", methods=["POST", "OPTIONS"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Process user queries with intelligent routing"""
    
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=CORS_HEADERS)
    
    try:
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON format"}),
                status_code=400,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        
        email = req_body.get('email', '').strip().lower() if req_body else ""
        question = req_body.get('question', '').strip() if req_body else ""
        
        if not email or not question:
            return func.HttpResponse(
                json.dumps({"error": "Email and question required"}),
                status_code=400,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        
        user_info = get_user_info(email)
        if not user_info:
            return func.HttpResponse(
                json.dumps({"error": "Unauthorized"}),
                status_code=401,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        
        logger.info(f"Query from {email}: {question[:50]}...")
        
        intent = classify_intent(question)
        logger.info(f"Intent classified as: {intent}")
        
        if intent == "FALLBACK":
            response = handle_fallback(question, user_info)
        elif intent == "RAG":
            response = process_rag(question, user_info)
        elif intent == "SQL":
            response = process_sql(question, user_info)
        else:  # HYBRID
            response = process_hybrid(question, user_info)
        
        return func.HttpResponse(
            json.dumps(response),
            status_code=200,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )

@app.function_name(name="clear_context")
@app.route(route="clear_context", methods=["POST", "OPTIONS"])
def clear_context_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Clear conversation context for a user"""
    
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=CORS_HEADERS)
    
    try:
        req_body = req.get_json()
        email = req_body.get('email', '').strip().lower()
        
        if email in conversation_context:
            del conversation_context[email]
            
        return func.HttpResponse(
            json.dumps({"success": True, "message": "Context cleared"}),
            status_code=200,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"Clear context error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )

@app.function_name(name="health")
@app.route(route="health", methods=["GET", "OPTIONS"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """System health check endpoint"""
    
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=CORS_HEADERS)
    
    health_status = {
        "status": "healthy",
        "service": "Grams Analytics AI Agent",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "dependencies": {
            "database": bool(os.getenv("DATABASE_CONNECTION")),
            "openai": openai_client is not None,
            "openai_key": bool(os.getenv("AZURE_OPENAI_API_KEY")),
            "openai_endpoint": bool(os.getenv("AZURE_OPENAI_ENDPOINT"))
        }
    }
    
    return func.HttpResponse(
        json.dumps(health_status, indent=2),
        status_code=200,
        headers={**CORS_HEADERS, "Content-Type": "application/json"}
    )

@app.function_name(name="test_db")
@app.route(route="test_db", methods=["GET", "OPTIONS"])
def test_db_connection(req: func.HttpRequest) -> func.HttpResponse:
    """Test database connection and show sample data"""
    
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=CORS_HEADERS)
    
    try:
        conn_str = os.getenv("DATABASE_CONNECTION")
        if not conn_str:
            return func.HttpResponse(
                json.dumps({"error": "Database connection string not configured"}),
                status_code=500,
                headers={**CORS_HEADERS, "Content-Type": "application/json"}
            )
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.execute("SELECT COUNT(*) FROM staff_analytics")
            count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT TOP 5 
                    rmo_email, rmo_name,
                    bm_email, bm_name,
                    zm_email, zm_name,
                    cl_email, cl_name,
                    rm_email, rm_name
                FROM staff_analytics
            """)
            
            samples = []
            for row in cursor.fetchall():
                samples.append({
                    "rmo": f"{row.rmo_name} ({row.rmo_email})" if row.rmo_email else None,
                    "bm": f"{row.bm_name} ({row.bm_email})" if row.bm_email else None,
                    "zm": f"{row.zm_name} ({row.zm_email})" if row.zm_email else None,
                    "cl": f"{row.cl_name} ({row.cl_email})" if row.cl_email else None,
                    "rm": f"{row.rm_name} ({row.rm_email})" if row.rm_email else None
                })
            
            cursor.execute("""
                SELECT 
                    (SELECT TOP 1 rmo_email FROM staff_analytics WHERE rmo_email IS NOT NULL) as sample_rmo,
                    (SELECT TOP 1 bm_email FROM staff_analytics WHERE bm_email IS NOT NULL) as sample_bm,
                    (SELECT TOP 1 zm_email FROM staff_analytics WHERE zm_email IS NOT NULL) as sample_zm,
                    (SELECT TOP 1 cl_email FROM staff_analytics WHERE cl_email IS NOT NULL) as sample_cl,
                    (SELECT TOP 1 rm_email FROM staff_analytics WHERE rm_email IS NOT NULL) as sample_rm
            """)
            
            test_emails = cursor.fetchone()
            
        return func.HttpResponse(
            json.dumps({
                "status": "connected",
                "database": "grams-analytics-db",
                "total_records": count,
                "sample_hierarchy": samples,
                "test_emails": {
                    "rmo": test_emails.sample_rmo,
                    "bm": test_emails.sample_bm,
                    "zm": test_emails.sample_zm,
                    "cl": test_emails.sample_cl,
                    "rm": test_emails.sample_rm
                },
                "message": "Use any of the test_emails to login"
            }, indent=2),
            status_code=200,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"Test DB error: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers={**CORS_HEADERS, "Content-Type": "application/json"}
        )

# ============= HELPER FUNCTIONS =============

def get_user_info(email: str) -> Dict[str, Any]:
    """Get complete user profile with data access permissions"""
    try:
        conn_str = os.getenv("DATABASE_CONNECTION")
        if not conn_str:
            logger.error("Database connection string not configured")
            return None
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT TOP 1
                    rmo_email, rmo_name,
                    bm_email, bm_name,
                    zm_email, zm_name,
                    cl_email, cl_name,
                    rm_email, rm_name
                FROM staff_analytics
                WHERE rmo_email = ? OR bm_email = ? OR zm_email = ? OR cl_email = ? OR rm_email = ?
            """, email, email, email, email, email)
            
            row = cursor.fetchone()
            if not row:
                return None
            
            if email == row.rmo_email:
                role, name = "RMO", row.rmo_name
            elif email == row.bm_email:
                role, name = "BM", row.bm_name
            elif email == row.zm_email:
                role, name = "ZM", row.zm_name
            elif email == row.cl_email:
                role, name = "CL", row.cl_name
            elif email == row.rm_email:
                role, name = "RM", row.rm_name
            else:
                return None
            
            accessible_emails = get_accessible_emails(email, role, cursor)
            
            return {
                "email": email,
                "name": name,
                "role": role,
                "role_description": get_role_description(role),
                "accessible_emails": accessible_emails,
                "subordinate_count": len(accessible_emails),
                "permissions": get_permissions(role)
            }
    except Exception as e:
        logger.error(f"Error in get_user_info: {e}", exc_info=True)
        return None

def get_accessible_emails(email: str, role: str, cursor) -> List[str]:
    """Get all RMO emails that user can access data for"""
    try:
        if role == "RMO":
            return [email]
        
        elif role == "BM":
            cursor.execute("SELECT DISTINCT rmo_email FROM staff_analytics WHERE bm_email = ?", email)
            emails = [row.rmo_email for row in cursor.fetchall() if row.rmo_email]
            return emails if emails else [email]
        
        elif role == "ZM":
            cursor.execute("""
                SELECT DISTINCT rmo_email 
                FROM staff_analytics 
                WHERE bm_email IN (
                    SELECT DISTINCT bm_email FROM staff_analytics WHERE zm_email = ?
                )
            """, email)
            emails = [row.rmo_email for row in cursor.fetchall() if row.rmo_email]
            return emails if emails else [email]
        
        elif role == "CL":
            cursor.execute("""
                SELECT DISTINCT rmo_email 
                FROM staff_analytics 
                WHERE bm_email IN (
                    SELECT DISTINCT bm_email FROM staff_analytics 
                    WHERE zm_email IN (
                        SELECT DISTINCT zm_email FROM staff_analytics WHERE cl_email = ?
                    )
                )
            """, email)
            emails = [row.rmo_email for row in cursor.fetchall() if row.rmo_email]
            return emails if emails else [email]
        
        elif role == "RM":
            cursor.execute("""
                SELECT DISTINCT rmo_email 
                FROM staff_analytics 
                WHERE bm_email IN (
                    SELECT DISTINCT bm_email FROM staff_analytics 
                    WHERE zm_email IN (
                        SELECT DISTINCT zm_email FROM staff_analytics 
                        WHERE cl_email IN (
                            SELECT DISTINCT cl_email FROM staff_analytics WHERE rm_email = ?
                        )
                    )
                )
            """, email)
            emails = [row.rmo_email for row in cursor.fetchall() if row.rmo_email]
            return emails if emails else [email]
        
        return [email]
    except Exception as e:
        logger.error(f"Error in get_accessible_emails: {e}")
        return [email]

def get_role_description(role: str) -> str:
    """Get human-readable role description"""
    descriptions = {
        "RMO": "Relationship Management Officer",
        "BM": "Branch Manager",
        "ZM": "Zonal Manager",
        "CL": "Cluster Lead",
        "RM": "Regional Manager"
    }
    return descriptions.get(role, role)

def get_permissions(role: str) -> Dict[str, bool]:
    """Define what each role can do"""
    base_permissions = {
        "view_own_data": True,
        "view_subordinate_data": False,
        "view_aggregate_reports": False,
        "view_trends": False,
        "export_data": False
    }
    
    role_permissions = {
        "RMO": base_permissions,
        "BM": {**base_permissions, "view_subordinate_data": True, "view_trends": True},
        "ZM": {**base_permissions, "view_subordinate_data": True, "view_aggregate_reports": True, "view_trends": True},
        "CL": {**base_permissions, "view_subordinate_data": True, "view_aggregate_reports": True, "view_trends": True, "export_data": True},
        "RM": {**base_permissions, "view_subordinate_data": True, "view_aggregate_reports": True, "view_trends": True, "export_data": True}
    }
    
    return role_permissions.get(role, base_permissions)

def classify_intent(question: str) -> str:
    """Classify query intent with detailed analysis"""
    
    question_lower = question.lower()
    
    # First check for obvious FALLBACK patterns
    fallback_patterns = ["hello", "hi", "hey", "good morning", "good afternoon", 
                        "good evening", "thank you", "thanks", "bye", "goodbye"]
    if any(pattern in question_lower for pattern in fallback_patterns):
        return "FALLBACK"
    
    # Keywords that strongly indicate knowledge base/support queries (RAG)
    rag_keywords = [
        "how do i", "what do i do", "how to", "what is", "what are",
        "explain", "guide", "help", "support", "procedure", "process",
        "bvn", "bankapp", "ussd", "busacct", "password", "reset", "login",
        "error", "failed", "issue", "problem", "troubleshoot", "fix",
        "policy", "rule", "regulation", "requirement", "document"
    ]
    
    # Keywords that strongly indicate data/metrics queries (SQL)
    sql_keywords = [
        "show me", "total", "sum", "average", "count", "number of",
        "performance", "revenue", "balance", "score", "metrics",
        "compare", "comparison", "versus", "top", "bottom", "best", "worst",
        "highest", "lowest", "trend", "analysis", "report", "statistics",
        "how many", "how much", "list of", "table", "tabular"
    ]
    
    # Keywords that indicate HYBRID (both data and explanation needed)
    hybrid_keywords = [
        "why is", "explain the", "what caused", "reason for",
        "how can i improve", "what should i do about",
        "analyze and explain", "insights on", "understanding"
    ]
    
    # Score each category
    rag_score = sum(2 if keyword in question_lower else 0 for keyword in rag_keywords)
    sql_score = sum(2 if keyword in question_lower else 0 for keyword in sql_keywords)
    hybrid_score = sum(3 if keyword in question_lower else 0 for keyword in hybrid_keywords)
    
    # Check for hybrid patterns
    if hybrid_score > 0 and (sql_score > 0 or "metric" in question_lower or "score" in question_lower):
        return "HYBRID"
    
    # Use keyword scores for clear cases
    if rag_score > sql_score and rag_score > 3:
        return "RAG"
    elif sql_score > rag_score and sql_score > 3:
        return "SQL"
    
    # For unclear cases, use OpenAI
    if not openai_client:
        logger.warning("OpenAI client not available, making best guess")
        if rag_score > sql_score:
            return "RAG"
        elif sql_score > rag_score:
            return "SQL"
        else:
            return "FALLBACK"
    
    # Use OpenAI for complex classification
    prompt = f"""
    Classify this banking query into ONE category:
    
    Categories:
    - SQL: Queries about numbers, metrics, performance data, statistics, comparisons
    - RAG: Questions about procedures, how-to guides, platform help, policies
    - HYBRID: Queries needing both data and explanation
    - FALLBACK: Greetings, unclear requests, off-topic questions
    
    Question: {question}
    
    Reply with only: SQL, RAG, HYBRID, or FALLBACK
    """
    
    try:
        response = openai_client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
            messages=[
                {"role": "system", "content": "You are a query classifier for a banking analytics system."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=10
        )
        
        result = response.choices[0].message.content.strip().upper()
        if result in ["SQL", "RAG", "HYBRID", "FALLBACK"]:
            logger.info(f"OpenAI classified '{question[:50]}...' as {result}")
            return result
        return "FALLBACK"
    except Exception as e:
        logger.error(f"Intent classification error: {e}")
        if rag_score > sql_score:
            return "RAG"
        elif sql_score > rag_score:
            return "SQL"
        return "FALLBACK"

def process_sql(question: str, user_info: Dict) -> Dict:
    """Generate and execute SQL queries with role-based filtering"""
    global conversation_context
    
    try:
        if not openai_client:
            return {
                "type": "error",
                "response": "AI service not available for SQL generation",
                "user": user_info['name']
            }
        
        user_email = user_info['email']
        if user_email not in conversation_context:
            conversation_context[user_email] = {
                "last_query": "",
                "last_results": [],
                "query_history": []
            }
        
        is_followup = any(word in question.lower() for word in ["those", "them", "these", "same", "above"])
        context_hint = ""
        
        if is_followup and conversation_context[user_email]["last_query"]:
            context_hint = f"\nThis is a follow-up to: {conversation_context[user_email]['last_query']}"
        
        wants_table = any(word in question.lower() for word in ["table", "tabular", "format", "list", "show me"])
        
        accessible_emails = user_info['accessible_emails']
        
        if user_info['role'] == 'RM' and len(accessible_emails) > 30:
            base_filter = f"rm_email = '{user_info['email']}'"
        else:
            escaped_emails = [email.replace("'", "''") for email in accessible_emails]
            emails_list = "', '".join(escaped_emails)
            base_filter = f"rmo_email IN ('{emails_list}')"
        
        prompt = f"""
        Generate SQL for: {question}
        {context_hint}
        
        User: {user_info['name']} ({user_info['role']})
        Base filter: WHERE {base_filter}
        
        Table: staff_analytics
        All columns: id, rm_email, rm_name, cl_email, cl_name, zm_email, zm_name, 
                    bm_email, bm_name, rmo_email, rmo_name, total_accounts, casa_balance, 
                    total_revenue, score_card, bankapp_count, busacct_count, ussd_count, 
                    credit_turnover, period_month, period_year, created_date
        
        Return ONLY the SQL query.
        """
        
        response = openai_client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=500
        )
        
        sql_query = response.choices[0].message.content.strip()
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        
        logger.info(f"Executing SQL: {sql_query[:150]}...")
        
        conn_str = os.getenv("DATABASE_CONNECTION")
        results = []
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_query)
            
            columns = [column[0] for column in cursor.description]
            for row in cursor.fetchall():
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if val is None:
                        row_dict[col] = None
                    elif hasattr(val, 'real'):
                        row_dict[col] = float(val)
                    elif isinstance(val, (int, float)):
                        row_dict[col] = val
                    else:
                        row_dict[col] = str(val)
                results.append(row_dict)
        
        conversation_context[user_email]["last_query"] = question
        conversation_context[user_email]["last_results"] = results
        conversation_context[user_email]["query_history"].append({
            "question": question,
            "timestamp": datetime.now().isoformat(),
            "record_count": len(results)
        })
        
        if results:
            format_instruction = "Format the response with **bold** headings and clear sections."
            if wants_table:
                format_instruction += " Organize key metrics clearly."
            
            insights_prompt = f"""
            User ({user_info['name']}, {user_info['role']}) asked: {question}
            
            Query returned {len(results)} records.
            Data: {json.dumps(results[:10], default=str)}
            
            {format_instruction}
            
            Provide:
            1. **Summary** section with key findings
            2. **Top Performers** (if applicable)
            3. **Areas Needing Attention** (if applicable)
            4. **Recommendations** section
            
            Use actual numbers from the data. Format currency as ₦.
            Keep response concise and professional.
            """
            
            insights = openai_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
                messages=[
                    {"role": "system", "content": SYSTEM_MESSAGE},
                    {"role": "user", "content": insights_prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            response_text = insights.choices[0].message.content
            response_text = re.sub(r'\|.*\|.*\|.*\n\|[-:\s|]+\n(?:\|.*\|.*\n)*', '', response_text)
            
            return {
                "type": "analytics",
                "response": response_text.strip(),
                "data": results[:10],
                "total_records": len(results),
                "user": user_info['name'],
                "context_available": True,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "type": "analytics",
                "response": "No data found matching your criteria. Please try a different query or check the filters.",
                "data": [],
                "total_records": 0,
                "user": user_info['name']
            }
    
    except Exception as e:
        logger.error(f"SQL processing error: {e}", exc_info=True)
        return {
            "type": "error",
            "response": "I encountered an issue processing your request. Please try rephrasing or simplifying your question.",
            "user": user_info['name']
        }

def process_rag(question: str, user_info: Dict) -> Dict:
    """Handle platform support queries using Azure Cognitive