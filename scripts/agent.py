import os
from typing import Annotated, TypedDict
import psycopg2
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# LangChain & LangGraph imports
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage,SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
if __package__:
  from .connection import get_readonly_connection , get_admin_connection
else:
  from connection import get_readonly_connection , get_admin_connection

load_dotenv()

# ==========================================
# 1. DEFINE TOOLS FOR YOUR DELIVERY DATABASE
# ==========================================

# The previous NVIDIA free endpoint is presently degraded for function calls.
# This router selects an available free model that supports the tools supplied
# via ``bind_tools``. Override it in .env when you want to pin a model.

# OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
# llm = ChatOpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=os.environ.get("OPENROUTER_API_KEY"),
#     model=OPENROUTER_MODEL,
# )

llm = ChatOpenAI(
    base_url="https://api.groq.com/openai/v1", # Changed to Groq's base URL
    api_key=os.environ.get("GROQ_API_KEY"), # Fixed typo
    model="openai/gpt-oss-120b", # Groq's specific model ID for 3.3 70B
    temperature=0
)

# Function to update the title in PostgreSQL
def update_session_title(session_id: str, new_title: str):
    """Updates the title of an existing chat session in Postgres."""
    conn = get_admin_connection()  # Uses write connection
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_sessions SET title = %s WHERE session_id = %s;",
                (new_title, session_id)
            )
            conn.commit()
    finally:
        conn.close()

# Function to generate a title using your LLM
def generate_chat_title(first_prompt: str) -> str:
    """Uses the LLM to summarize the initial prompt into a 3 to 5 word title."""
    try:
        prompt = (
            "Summarize the following user query into a concise 3 to 5 word chat title. "
            "Do NOT use quotes or punctuation. Return ONLY the title text:\n\n"
            f"Query: {first_prompt}"
        )
        response = llm.invoke(prompt)
        title = response.content.strip().strip('"').strip("'")
        return title[:50]  # Cap at 50 chars for database safety
    except Exception:
        # Fallback: Use the first 30 characters if the LLM call fails
        return first_prompt[:30] + "..." if len(first_prompt) > 30 else first_prompt

@tool
def run_sql_query(query: str) -> str:
  """Executes a read-only SQL SELECT query on the delivery database for data analysis.

  Use this to query tables like staging_orders, orders, restaurants, customers,
  and drivers.
  """
  if not query.strip().lower().startswith("select"):
    return (
        "Error: Only read-only SELECT queries are allowed for security reasons."
    )

  conn = get_readonly_connection()
  try:
    with conn.cursor() as cursor:
      cursor.execute(query)
      results = cursor.fetchall()
      col_names = [desc[0] for desc in cursor.description]

      # Format results as text rows
      output = [", ".join(col_names)]
      for row in results[:30]:  # Limit output rows for safety
        output.append(", ".join(str(val) for val in row))
      return "\n".join(output)
  except Exception as e:
    return f"Database error: {str(e)}"
  finally:
    conn.close()


@tool
def list_database_tables() -> str:
  """Lists all available tables in the delivery database."""
  conn = get_readonly_connection()
  try:
    with conn.cursor() as cursor:
      cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """)
      tables = [row[0] for row in cursor.fetchall()]
      return f"Available tables: {', '.join(tables)}"
  finally:
    conn.close()


tools = [run_sql_query, list_database_tables]



# ==========================================
# 2. DEFINE THE LANGGRAPH STATE & MODEL
# ==========================================

class State(TypedDict):
    messages: Annotated[list, add_messages]
    is_sufficient: bool  # New state variable to track the reviewer's decision

# Initialize LLM
model = llm.bind_tools(tools)

# Define the structure for the Reviewer's output
class ReviewResult(BaseModel):
    is_sufficient: bool = Field(description="True if the assistant's answer fully and accurately answers the user's question without errors. False if it needs improvement.")
    feedback: str = Field(description="If not sufficient, provide specific instructions on what the assistant needs to fix or query.")

# ==========================================
# 3. DEFINE GRAPH NODES & EDGES
# ==========================================

def call_model(state: State):
    messages = state["messages"]
    response = model.invoke(messages)
    return {"messages": [response]}

def execute_tools(state: State):
    messages = state["messages"]
    last_message = messages[-1]

    tool_map = {tool.name: tool for tool in tools}
    outputs = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if tool_name in tool_map:
            tool_result = tool_map[tool_name].invoke(tool_args)
        else:
            tool_result = f"Error: Tool {tool_name} not found."

        outputs.append(ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]))

    return {"messages": outputs}

def reviewer_node(state: State):
    """Evaluates the agent's draft answer and provides feedback if it fails."""
    messages = state["messages"]
    
    # Bind the structured output schema to the LLM
    reviewer_llm = llm.with_structured_output(ReviewResult)
    
    system_prompt = SystemMessage(content=(
        "You are a strict Data QA Reviewer. Evaluate the latest assistant response. "
        "Does it accurately answer the user's initial question based on the SQL data provided? "
        "If yes, set is_sufficient to true. If no, set it to false and provide feedback."
    ))
    
    # Invoke reviewer with the full conversation context
    review = reviewer_llm.invoke([system_prompt] + messages)
    
    if review.is_sufficient:
        # If passed, just update the flag. No new messages needed.
        return {"is_sufficient": True}
    else:
        # If failed, append the feedback as a HumanMessage so the agent acts on it
        feedback_msg = HumanMessage(content=f"QA Reviewer Feedback: {review.feedback} Please fix this response.")
        return {"messages": [feedback_msg], "is_sufficient": False}

def should_continue(state: State):
    """Routes from the Agent to either Tools or the Reviewer."""
    messages = state["messages"]
    last_message = messages[-1]
    
    if last_message.tool_calls:
        return "tools"
    # Instead of going to END, we now send the draft to the reviewer
    return "reviewer"

def route_after_review(state: State):
    """Routes from the Reviewer to END or back to the Agent."""
    if state.get("is_sufficient"):
        return END
    return "agent"  # Send back to agent for rework

# Build the workflow graph
workflow = StateGraph(State)

workflow.add_node("agent", call_model)
workflow.add_node("tools", execute_tools)
workflow.add_node("reviewer", reviewer_node)  # Register new node

# Wire the logic
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "reviewer": "reviewer"})
workflow.add_edge("tools", "agent")
workflow.add_conditional_edges("reviewer", route_after_review, {END: END, "agent": "agent"})

# Compile the graph
app = workflow.compile()