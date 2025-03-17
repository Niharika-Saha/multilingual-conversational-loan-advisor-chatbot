import google.generativeai as genai
import os
from db_connector import fetch_similar_loans  # Import PostgreSQL function

#  Configure Gemini AI
genai.configure(api_key=API_KEY)

def check_loan_eligibility(income, expenses, cibil_score):
    """Fetches past loan records and uses Gemini AI for eligibility prediction."""

    # Step 1: Fetch similar loans from PostgreSQL
    similar_loans = fetch_similar_loans(income, expenses, cibil_score)

    #  Step 2: Format the data for Gemini
    loan_data = "\n".join([
        f"Income: ₹{loan[0]}, Expenses: ₹{loan[1]}, CIBIL: {loan[2]}, Approved: {loan[3]}"
        for loan in similar_loans
    ])

     # Validate input data
    if income < expenses:
        # Return a custom message instead of relying on Gemini
        return "The expenses exceed income. This indicates a negative cash flow, which would likely result in loan rejection. Consider reducing expenses or increasing income before applying for a loan."

    #  Step 3: Create a dynamic prompt for Gemini
    prompt = f"""
    Based on past loan approvals:
    {loan_data}

    Predict whether a new user with:
    - Income: Rs{income}
    - Expenses: Rs{expenses}
    - CIBIL Score: {cibil_score}

    would be eligible for a loan. **Provide an answer (≤100 words)** summarizing eligibility, risks, and ways to improve approval chances.
    """

    #  Step 4: Send to Gemini AI
    response = genai.GenerativeModel("gemini-1.5-pro-latest").generate_content(prompt)
    # Replace Rupee symbol with "Rs." in your text
    response_text = response.text.replace("\u20b9", "Rs.")
    return response_text

def calculate_emi(principal, annual_rate, tenure_years):
    """Calculates EMI using the standard formula."""
    r = (annual_rate / 12) / 100  # Convert annual interest rate to monthly
    n = tenure_years * 12  # Convert years to months
    if r == 0:
        return principal / n  # Simple division if 0% interest
    emi = (principal * r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return round(emi, 2)

def calculate_dti(income, expenses, emi):
    """Calculates Debt-to-Income (DTI) ratio."""
    total_debt_payments = expenses + emi  # Include EMI in total obligations
    dti = (total_debt_payments / income) * 100
    return round(dti, 2)

def gemini_loan_insights(income, expenses, cibil_score, loan_amount, interest_rate, tenure):
    """Uses Gemini AI to analyze EMI, affordability, and eligibility."""
    
    # Step 1: Compute EMI and DTI
    emi = calculate_emi(loan_amount, interest_rate, tenure)
    dti = calculate_dti(income, expenses, emi)

    # Step 2: Generate Prompt for Gemini
    prompt = f"""
    Analyze the following financial data and provide **brief insights (≤100 words)** on  loan affordability, eligibility, and risk factors.

    **User Profile:**
    - Income: Rs{income}
    - Expenses: Rs{expenses}
    - CIBIL Score: {cibil_score}

    **Loan Details:**
    - Requested Loan Amount: Rs{loan_amount}
    - Interest Rate: {interest_rate}% per annum
    - Loan Tenure: {tenure} years
    - Calculated EMI: Rs{emi} per month
    - Debt-to-Income (DTI) Ratio: {dti}%

    **Questions for Analysis:**
    - Based on EMI and DTI, is the loan affordable?
    - Are there any risks in approving this loan?
    - How can the user improve their eligibility?
    - What other financial recommendations can you provide?
    """

    # Step 3: Send Prompt to Gemini
    response = genai.GenerativeModel("gemini-1.5-pro-latest").generate_content(prompt)
    
    return response.text.replace("\u20b9", "Rs.")
