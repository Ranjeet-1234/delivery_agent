import os
import uuid
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# # ==========================================
# # 1. DATABASE CREDENTIALS (DUAL SETUP)
# # ==========================================
# DB_HOST = os.getenv("DB_HOST", "localhost")
# DB_PORT = os.getenv("DB_PORT", "5432")
# DB_NAME = os.getenv("DB_NAME", "delivey_database")

# # App Backend Credentials (Needs WRITE access for chat history)
# ADMIN_USER = os.getenv("ADMIN_USER", "ranjeet")
# ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "pass")

# # AI Agent Credentials (Strictly READ-ONLY for data analysis)
# AGENT_USER = os.getenv("AGENT_USER", "agent_readonly")
# AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "secure_agent_pass")

# # --- Connection for App Backend (Write Access) ---
# def get_admin_connection():
#     return psycopg2.connect(
#         host=DB_HOST, port=DB_PORT, database=DB_NAME,
#         user=ADMIN_USER, password=ADMIN_PASSWORD
#     )

# # --- Connection for AI Agent (Read-Only) ---
# def get_readonly_connection():
#     return psycopg2.connect(
#         host=DB_HOST, port=DB_PORT, database=DB_NAME,
#         user=AGENT_USER, password=AGENT_PASSWORD
#     )


# ==========================================
# 1. DATABASE CREDENTIALS (DUAL SETUP FOR NEON)
# ==========================================
# Fetch the full connection strings from .env
ADMIN_DB_URL = os.getenv("ADMIN_DB_URL")


# --- Connection for App Backend (Write Access) ---
def get_admin_connection():
    # Pass the full URL to psycopg2
    return psycopg2.connect(ADMIN_DB_URL)

# --- Connection for AI Agent (Read-Only) ---
def get_readonly_connection():
    # Pass the full URL to psycopg2
    return psycopg2.connect(ADMIN_DB_URL)