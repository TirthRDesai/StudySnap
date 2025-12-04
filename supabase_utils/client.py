import os

from dotenv import load_dotenv
from supabase import Client, create_client

# Load environment variables from a .env file if present so local runs pick up credentials.
load_dotenv()


def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using environment variables.

    Required env vars:
      - SUPABASE_URL
      - SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_ANON_KEY (limited)
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
        "SUPABASE_ANON_KEY")

    if not url or not key:
        raise RuntimeError(
            "Supabase credentials are missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY."
        )

    return create_client(url, key)
