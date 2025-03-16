import psycopg2
import os

# ✅ Load database credentials from environment variables
DB_CONFIG = {
    "dbname": "my_database",
    "user": "postgres",
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

def fetch_similar_loans(income, expenses, cibil_score):
    """Fetches similar loan records from PostgreSQL based on user input."""
    try:
        conn = psycopg2.connect(
            dbname=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"]
        )
        cursor = conn.cursor()

        query = """
        SELECT income_annum, expenses, cibil_score, loan_status
        FROM my_table
        WHERE ABS(income_annum - %s) < 1000000 
        AND ABS(expenses - %s) < 500000 
        AND ABS(cibil_score - %s) < 50
        LIMIT 5;
        """
        
        cursor.execute(query, (income, expenses, cibil_score))
        results = cursor.fetchall()

        conn.close()
        
        return results

    except Exception as e:
        print(f"Database Error: {e}")
        return []