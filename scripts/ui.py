import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from agent import app as agent_app
from agent import generate_chat_title, update_session_title
from server import get_all_sessions,create_new_session,save_message_to_db,load_session_messages ,delete_session

st.set_page_config(page_title="Delivery Logistics AI Agent", page_icon="🚚", layout="wide")

# ==========================================
# SIDEBAR: CHAT HISTORY & NEW CHAT BUTTON
# ==========================================
st.sidebar.title("💬 Chat History")

if st.sidebar.button("➕ New Chat", use_container_width=True):
    new_id = create_new_session("New Delivery Query")
    st.session_state.current_session_id = new_id
    st.session_state.messages = []
    st.rerun()

# (Make sure you imported delete_session at the top of app.py)
# from agent import delete_session 

st.sidebar.divider()

# Fetch previous sessions
sessions = get_all_sessions()

# Handle default session loading if none is selected
if "current_session_id" not in st.session_state or st.session_state.current_session_id is None:
    if sessions:
        st.session_state.current_session_id = sessions[0][0]  # Load most recent
        st.session_state.messages = load_session_messages(st.session_state.current_session_id)
    else:
        st.session_state.current_session_id = create_new_session("First Chat")
        st.session_state.messages = []
        # Re-fetch sessions so the newly created chat appears immediately in the loop below
        sessions = get_all_sessions()

# EXACTLY ONE LOOP to display previous sessions with a Delete button
for i, (sess_id, sess_title) in enumerate(sessions):
    # Create two columns in the sidebar: 80% for the title, 20% for the delete button
    col1, col2 = st.sidebar.columns([4, 1])
    
    is_active = sess_id == st.session_state.current_session_id
    button_type = "primary" if is_active else "secondary"
    
    # Column 1: The Chat Selector Button (Uses {i} in the key for guaranteed uniqueness)
    with col1:
        if st.button(sess_title[:25], key=f"sel_{i}_{sess_id}", type=button_type, use_container_width=True):
            st.session_state.current_session_id = sess_id
            st.session_state.messages = load_session_messages(sess_id)
            st.rerun()
            
    # Column 2: The Delete Button (Uses {i} in the key here as well)
    with col2:
        if st.button("🗑️", key=f"del_{i}_{sess_id}", help="Delete this chat"):
            delete_session(sess_id)
            
            # If the user deletes the chat they are currently viewing, clear the view
            if st.session_state.current_session_id == sess_id:
                st.session_state.current_session_id = None
                st.session_state.messages = []
            
            # Refresh the UI to remove it from the sidebar
            st.rerun()
# ==========================================
# MAIN CHAT WINDOW
# ==========================================
st.title("🚚 Delivery Logistics Data Assistant")
st.markdown("Analyze your food delivery dataset, traffic conditions, and logistics performance with persistent chat history.")

# Display message history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# Handle user text input
if prompt := st.chat_input("Ask a question about your delivery data..."):
    # Check if this is the very first query in this session
    is_first_message = len(st.session_state.messages) == 0

    # 1. Save and display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message_to_db(st.session_state.current_session_id, "user", prompt)
    
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. If it's the first message, dynamically generate and update the chat title
    if is_first_message:
        with st.spinner():
            new_title = generate_chat_title(prompt)
            update_session_title(st.session_state.current_session_id, new_title)

    # 3. Run your LangGraph Agent as usual
    with st.chat_message("assistant"):
        with st.spinner("Analyzing delivery database..."):
            langgraph_history = [
                HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
                for m in st.session_state.messages
            ]

            response_content = ""
            try:
                for event in agent_app.stream({"messages": langgraph_history}, stream_mode="values"):
                    latest_msg = event["messages"][-1]
                    if isinstance(latest_msg, AIMessage) and latest_msg.content:
                        response_content = latest_msg.content
                
                if not response_content:
                    response_content = "I processed your request, but received no final text output."
            except Exception as e:
                response_content = f"Error executing query: {str(e)}"

            st.markdown(response_content)

    # 4. Save assistant response to DB
    st.session_state.messages.append({"role": "assistant", "content": response_content})
    save_message_to_db(st.session_state.current_session_id, "assistant", response_content)

    # 5. Rerun to reflect the new chat title in the sidebar immediately on the first turn
    if is_first_message:
        st.rerun()
   