import uuid
import psycopg2
from connection import get_admin_connection 

# (Keep your existing DB connection and tool setup from before)

def get_all_sessions():
    """Retrieve all saved chat sessions for the sidebar."""
    conn = get_admin_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT session_id, title FROM chat_sessions ORDER BY created_at DESC;")
            return cursor.fetchall()
    finally:
        conn.close()

def create_new_session(title="New Delivery Chat"):
    """Create a new chat session ID."""
    session_id = str(uuid.uuid4())
    conn = get_admin_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_sessions (session_id, title) VALUES (%s, %s);",
                (session_id, title)
            )
            conn.commit()
            return session_id
    finally:
        conn.close()

def save_message_to_db(session_id, role, content):
    """Save an individual message to Postgres."""
    conn = get_admin_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s);",
                (session_id, role, content)
            )
            conn.commit()
    finally:
        conn.close()

def load_session_messages(session_id):
    """Load all messages for a specific session."""
    conn = get_admin_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY timestamp ASC;",
                (session_id,)
            )
            return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    finally:
        conn.close()

def delete_session(session_id: str):
    """Deletes a chat session and all its messages from PostgreSQL."""
    conn = get_admin_connection()  # Must use the admin connection for DELETE
    try:
        with conn.cursor() as cursor:
            # ON DELETE CASCADE handles deleting the associated messages automatically
            cursor.execute(
                "DELETE FROM chat_sessions WHERE session_id = %s;", 
                (session_id,)
            )
            conn.commit()
    finally:
        conn.close()