"""
EVALUX Backend API
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import json
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import re
import time

from auth import get_password_hash, verify_password, create_access_token, get_current_user
from database import get_db_connection
from ai import (
    analyze_cv, 
    generate_interview_question, 
    rate_interview,
    GROQ_AVAILABLE,
    GROQ_API_KEY,
    GROQ_MODEL
)

try:
    from groq import Groq
except ImportError:
    Groq = None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("evalux")

app = FastAPI(title="EVALUX API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# In-memory storage for OTP and sessions
otp_storage = {}
interview_sessions = {}

# Email Configuration
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# MODELS
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    interests: List[str] = []

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str

class InterviewStartRequest(BaseModel):
    topic: str = "Software Development"
    cv_skills: List[str] = []

class InterviewMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class CodeProblemRequest(BaseModel):
    difficulty: Optional[str] = "easy"

class CodeRunRequest(BaseModel):
    code: str
    language: str
    problem_id: int

# HELPER FUNCTIONS
def generate_otp() -> str:
    """Generate 6-digit OTP"""
    return str(random.randint(100000, 999999))


def send_otp_email(email: str, otp: str) -> bool:
    """Send OTP via email"""
    try:
        if not EMAIL_USER or not EMAIL_PASS:
            logger.warning("⚠️ Email not configured - OTP would be: " + otp)
            print(f"\n{'='*50}")
            print(f"🔑 OTP FOR {email}: {otp}")
            print(f"{'='*50}\n")
            return True
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = email
        msg['Subject'] = "EVALUX - Your OTP Code"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #36f3e2;">Welcome to EVALUX!</h2>
            <p>Your OTP code is:</p>
            <h1 style="color: #3a8fff; letter-spacing: 5px;">{otp}</h1>
            <p>This code will expire in 10 minutes.</p>
            <p>If you didn't request this code, please ignore this email.</p>
            <br>
            <p style="color: #999;">- EVALUX Team</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        
        logger.info(f"✅ OTP sent to {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Email send failed: {e}")
        print(f"\n{'='*50}")
        print(f"🔑 OTP FOR {email}: {otp}")
        print(f"⚠️ Email failed but OTP printed above")
        print(f"{'='*50}\n")
        return True
    
# AUTH ENDPOINTS (same as before)
@app.post("/register")
async def register(user: UserRegister):
    """Register new user - Send OTP for verification"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM users WHERE email = %s", (user.email,))
        existing = cursor.fetchone()
        
        if existing and existing.get("verified"):
            raise HTTPException(status_code=400, detail="Email already registered")
        
        otp = generate_otp()
        expires_at = datetime.now() + timedelta(minutes=10)
        
        otp_storage[user.email] = {
            "otp": otp,
            "expires": expires_at,
            "user_data": {
                "username": user.username,
                "email": user.email,
                "password_hash": get_password_hash(user.password),
                "interests": user.interests
            }
        }
        
        email_sent = send_otp_email(user.email, otp)
        
        if not email_sent:
            logger.warning("Email failed but continuing for development")
        
        logger.info(f"✅ OTP generated for: {user.email}")
        
        return {
            "message": "OTP sent to your email. Please verify to complete registration.",
            "email": user.email,
            "expires_in": "10 minutes"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.post("/verify-otp")
async def verify_otp(request: OTPVerify):
    """Verify OTP and create user account"""
    
    if request.email not in otp_storage:
        raise HTTPException(status_code=400, detail="No OTP found. Please register again.")
    
    stored_data = otp_storage[request.email]
    
    if datetime.now() > stored_data["expires"]:
        del otp_storage[request.email]
        raise HTTPException(status_code=400, detail="OTP expired. Please register again.")
    
    if request.otp != stored_data["otp"]:
        raise HTTPException(status_code=400, detail="Invalid OTP. Please try again.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        user_data = stored_data["user_data"]
        
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, interests, verified)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (
            user_data["username"],
            user_data["email"],
            user_data["password_hash"],
            json.dumps(user_data["interests"])
        ))
        conn.commit()
        
        del otp_storage[request.email]
        
        logger.info(f"✅ User verified and created: {request.email}")
        
        return {
            "message": "Email verified successfully! You can now login.",
            "email": request.email
        }
        
    except Exception as e:
        conn.rollback()
        logger.error(f"User creation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user account")
    finally:
        cursor.close()
        conn.close()


@app.post("/resend-otp")
async def resend_otp(email: EmailStr):
    """Resend OTP to email"""
    
    if email not in otp_storage:
        raise HTTPException(status_code=400, detail="No pending registration found")
    
    otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=10)
    
    otp_storage[email]["otp"] = otp
    otp_storage[email]["expires"] = expires_at
    
    send_otp_email(email, otp)
    
    logger.info(f"✅ OTP resent to: {email}")
    
    return {"message": "OTP resent successfully"}


@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login and get token"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(
            "SELECT * FROM users WHERE email=%s OR username=%s",
            (form_data.username, form_data.username)
        )
        user = cursor.fetchone()
        
        if not user or not verify_password(form_data.password, user.get("password_hash")):
            raise HTTPException(status_code=400, detail="Invalid credentials")
        
        if not user.get("verified"):
            raise HTTPException(status_code=400, detail="Please verify your email first")
        
        token = create_access_token(data={"sub": user["email"], "user_id": user["id"]})
        
        logger.info(f"✅ User logged in: {user['email']}")
        
        return {"access_token": token, "token_type": "bearer"}
        
    finally:
        cursor.close()
        conn.close()


@app.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(
            "SELECT id, username, email FROM users WHERE id = %s",
            (current_user["user_id"],)
        )
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user
        
    finally:
        cursor.close()
        conn.close()

# CV & INTERVIEW ENDPOINTS
@app.post("/cv/analyze")
async def analyze_cv_endpoint(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload CV → Extract text → Analyze → Store in DB"""
    logger.info(f"📄 CV upload from user {current_user['user_id']}: {file.filename}")
    
    try:
        content = await file.read()
        
        cv_text = ""
        if file.filename.lower().endswith('.pdf'):
            try:
                from pdfminer.high_level import extract_text_to_fp
                from pdfminer.layout import LAParams
                from io import BytesIO, StringIO
                
                output = StringIO()
                extract_text_to_fp(BytesIO(content), output, laparams=LAParams())
                cv_text = output.getvalue()
                
                logger.info(f"✅ PDF extracted: {len(cv_text)} chars")
            except Exception as e:
                logger.error(f"PDF extraction failed: {e}")
                raise HTTPException(status_code=400, detail="Failed to read PDF")
        else:
            cv_text = content.decode('utf-8', errors='ignore')
        
        if len(cv_text.strip()) < 50:
            raise HTTPException(status_code=400, detail="CV text too short")
        
        analysis = analyze_cv(cv_text)
        skills = analysis.get("skills", [])
        questions = analysis.get("interview_questions", [])
        
        logger.info(f"✅ Analysis complete: {len(skills)} skills, {len(questions)} questions")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO cv_analyses 
                (user_id, file_path, parsed_text, analysis_json, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                current_user["user_id"],
                file.filename,
                cv_text[:5000],
                json.dumps(analysis)
            ))
            conn.commit()
            cv_id = cursor.lastrowid
            
            logger.info(f"✅ CV saved to DB with ID: {cv_id}")
            
        finally:
            cursor.close()
            conn.close()
        
        return {
            "cv_id": cv_id,
            "skills": skills,
            "interview_questions": questions,
            "message": "CV analyzed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CV analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# CODE PRACTICE FUNCTIONS - NO INPUT VERSION
def validate_and_fix_problem(problem_data: Dict[str, Any]) -> Dict[str, Any]:
    title = problem_data.get("title", "")
    description = problem_data.get("description", "")
    expected = problem_data.get("expected_answer", "")
    
    import re
    
    # Check for average/mean calculations
    if "average" in description.lower() or "mean" in description.lower():
        # Extract list of numbers
        numbers_match = re.findall(r'\[([\d\s.,]+)\]', description)
        if numbers_match:
            try:
                # Parse the numbers
                numbers_str = numbers_match[0].replace(' ', '')
                numbers = [float(x.strip()) for x in numbers_str.split(',')]
                
                # Calculate correct average
                correct_avg = sum(numbers) / len(numbers)
                correct_answer = f"{correct_avg:.2f}"
                
                logger.info(f"📊 Validated average: {correct_answer} (AI said: {expected})")
                
                if abs(float(correct_answer) - float(expected)) > 0.01:
                    logger.warning(f"⚠️ Fixed incorrect expected answer: {expected} → {correct_answer}")
                    problem_data["expected_answer"] = correct_answer
                
            except Exception as e:
                logger.warning(f"Could not validate average calculation: {e}")
    
    # Check for sum calculations
    elif "sum" in description.lower() and "between" in description.lower():
        # Extract range like "1 and 20" or "1 to 20"
        range_match = re.search(r'(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)', description.lower())
        if range_match:
            try:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                
                # Check if it mentions "even" or "odd" or "prime"
                if "even" in description.lower():
                    correct_sum = sum(i for i in range(start, end + 1) if i % 2 == 0)
                elif "odd" in description.lower():
                    correct_sum = sum(i for i in range(start, end + 1) if i % 2 == 1)
                elif "prime" in description.lower():
                    def is_prime(n):
                        if n < 2: return False
                        for i in range(2, int(n**0.5) + 1):
                            if n % i == 0: return False
                        return True
                    correct_sum = sum(i for i in range(start, end + 1) if is_prime(i))
                else:
                    correct_sum = sum(range(start, end + 1))
                
                correct_answer = str(correct_sum)
                logger.info(f"📊 Validated sum: {correct_answer} (AI said: {expected})")
                
                if correct_answer != expected:
                    logger.warning(f"⚠️ Fixed incorrect expected answer: {expected} → {correct_answer}")
                    problem_data["expected_answer"] = correct_answer
                    
            except Exception as e:
                logger.warning(f"Could not validate sum calculation: {e}")
    
    # Check for list operations (max, min, second largest, etc.)
    elif any(word in description.lower() for word in ["largest", "smallest", "maximum", "minimum"]):
        numbers_match = re.findall(r'\[([\d\s.,\-]+)\]', description)
        if numbers_match:
            try:
                numbers_str = numbers_match[0].replace(' ', '')
                numbers = [int(x.strip()) for x in numbers_str.split(',')]
                
                if "second largest" in description.lower():
                    sorted_nums = sorted(set(numbers), reverse=True)
                    correct_answer = str(sorted_nums[1]) if len(sorted_nums) > 1 else str(sorted_nums[0])
                elif "largest" in description.lower() or "maximum" in description.lower():
                    correct_answer = str(max(numbers))
                elif "smallest" in description.lower() or "minimum" in description.lower():
                    correct_answer = str(min(numbers))
                else:
                    return problem_data
                
                logger.info(f"📊 Validated list operation: {correct_answer} (AI said: {expected})")
                
                if correct_answer != expected:
                    logger.warning(f"⚠️ Fixed incorrect expected answer: {expected} → {correct_answer}")
                    problem_data["expected_answer"] = correct_answer
                    
            except Exception as e:
                logger.warning(f"Could not validate list operation: {e}")
    
    return problem_data


# Now UPDATE generate_coding_problem_no_input function
# Find this part in the function:
#     problem = json.loads(result_text.strip())
#     problem["ai_generated"] = True
# 
# And ADD validation right after:
#     problem = json.loads(result_text.strip())
#     problem["ai_generated"] = True
#     
#     # VALIDATE AND FIX THE EXPECTED ANSWER
#     problem = validate_and_fix_problem(problem)
#     
#     logger.info(f"✅ AI-generated problem: {problem.get('title')} [Difficulty: {difficulty}]")
#     return problem


# Also improve the comparison logic in execute_code_no_input function
# Replace the comparison part with this:

def compare_answers(actual: str, expected: str) -> bool:
    """
    Smart answer comparison that handles different formats
    """
    try:
        # Strip ALL whitespace and convert to strings
        actual_clean = str(actual).strip().replace(" ", "").replace("\n", "").replace("\r", "")
        expected_clean = str(expected).strip().replace(" ", "").replace("\n", "").replace("\r", "")
        
        # Log for debugging
        logger.info(f"Comparing: actual='{actual_clean}' vs expected='{expected_clean}'")
        
        # Exact match (case-insensitive)
        if actual_clean.lower() == expected_clean.lower():
            logger.info("✅ Exact match!")
            return True
        
        # Try numeric comparison with tolerance
        try:
            actual_num = float(actual_clean)
            expected_num = float(expected_clean)
            # Allow 0.01 difference for floating point
            is_close = abs(actual_num - expected_num) < 0.01
            if is_close:
                logger.info(f"✅ Numeric match! {actual_num} ≈ {expected_num}")
            return is_close
        except (ValueError, TypeError):
            pass
        
        # Try boolean comparison
        true_vals = ['true', '1', 'yes']
        false_vals = ['false', '0', 'no']
        
        if actual_clean.lower() in true_vals and expected_clean.lower() in true_vals:
            logger.info("✅ Boolean True match!")
            return True
        if actual_clean.lower() in false_vals and expected_clean.lower() in false_vals:
            logger.info("✅ Boolean False match!")
            return True
        
        # Check if actual contains expected (for cases like "The answer is 12")
        if expected_clean in actual_clean:
            logger.info("✅ Contains match!")
            return True
        
        logger.warning(f"❌ No match: '{actual_clean}' != '{expected_clean}'")
        return False
        
    except Exception as e:
        logger.error(f"Comparison error: {e}")
        return False

def generate_coding_problem_no_input(cv_skills: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate a MORE CHALLENGING and DIVERSE NO-INPUT coding problem"""
    
    if GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            
            # Add randomness and difficulty levels
            difficulty_prompts = [
                "easy beginner level",
                "medium difficulty requiring loops",
                "moderate difficulty with data structures",
                "challenging problem with algorithms"
            ]
            
            problem_types = [
                "mathematical calculation",
                "string manipulation", 
                "list/array operations",
                "pattern recognition",
                "sorting or searching",
                "logical puzzle"
            ]
            
            import random
            difficulty = random.choice(difficulty_prompts)
            problem_type = random.choice(problem_types)
            
            # Add timestamp to make problems unique
            import time
            timestamp = int(time.time())
            
            prompt = f"""Generate a UNIQUE {difficulty} coding problem about {problem_type}.

TIMESTAMP: {timestamp} (use this to ensure variety)

CRITICAL RULES:
- NO parameters in the function - function takes NO INPUT
- Data must be HARDCODED in the problem description
- Make it DIFFERENT from simple counting problems
- Include some logic or calculation
- NOT just "count letters" or basic math

PROBLEM VARIETY IDEAS:
✅ "Find the sum of all prime numbers between 1 and 20"
✅ "Reverse the string 'hello world' and return it"
✅ "Find the second largest number in [15, 8, 23, 42, 4, 16]"
✅ "Count how many palindromes are in ['racecar', 'hello', 'level', 'world']"
✅ "Calculate the factorial of 5"
✅ "Find the missing number in the sequence [1, 2, 4, 5, 6]"
✅ "Check if 'A man a plan a canal Panama' is a palindrome (ignore spaces/caps)"
✅ "Find the Fibonacci number at position 8"
✅ "Count vowels and consonants in 'programming' - return difference"
✅ "Sort the list [5, 2, 8, 1, 9] in descending order, return the middle element"

AVOID:
❌ Simple counting like "count letters in hello"
❌ Basic addition like "5 + 3"
❌ Overly simple problems

Return ONLY valid JSON:
{{
  "title": "Descriptive Title (5-8 words)",
  "description": "Clear problem statement with specific data. Be precise about what to return.",
  "expected_answer": "the correct answer as string",
  "hint": "Helpful hint about the approach (optional)",
  "difficulty": "{difficulty}",
  "starter_code_python": "def solution():\\n    # Write your code here\\n    pass",
  "starter_code_javascript": "function solution() {{\\n    // Write your code here\\n}}",
  "starter_code_java": "public class Solution {{\\n    public static String solution() {{\\n        // Write your code here\\n        return \\"\\";\\n    }}\\n}}"
}}

Make it interesting and educational!"""

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,  # Higher temperature for more variety
                max_tokens=1000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            problem = json.loads(result_text.strip())
            problem["ai_generated"] = True

            # VALIDATE AND FIX THE EXPECTED ANSWER
            problem = validate_and_fix_problem(problem)

            logger.info(f"✅ AI-generated problem: {problem.get('title')}")
            return problem
            
        except Exception as e:
            logger.error(f"⚠️ AI problem generation failed: {e}")
            logger.info("Falling back to diverse predefined problems...")
    
    # Enhanced fallback with more challenging problems
    fallback_problems = [
        # EASY PROBLEMS
        {
            "title": "Sum Even Numbers in Range",
            "description": "Find the sum of all even numbers from 1 to 20. Return the sum.",
            "expected_answer": "110",
            "hint": "Even numbers are 2, 4, 6, 8... Use a loop or formula",
            "difficulty": "easy",
            "starter_code_python": "def solution():\n    # Sum even numbers 1-20\n    pass",
            "starter_code_javascript": "function solution() {\n    // Sum even numbers 1-20\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Reverse a String",
            "description": "Reverse the string 'Python' and return it. Result should be 'nohtyP'.",
            "expected_answer": "nohtyP",
            "hint": "You can use slicing [::-1] or a loop",
            "difficulty": "easy",
            "starter_code_python": "def solution():\n    # Reverse 'Python'\n    pass",
            "starter_code_javascript": "function solution() {\n    // Reverse 'Python'\n}",
            "starter_code_java": "public class Solution {\n    public static String solution() {\n        return \"\";\n    }\n}"
        },
        
        # MEDIUM PROBLEMS
        {
            "title": "Find Second Largest Number",
            "description": "Find the second largest number in the list [15, 8, 23, 42, 4, 16]. Return that number.",
            "expected_answer": "23",
            "hint": "Sort the list or track the two largest values",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Find second largest in [15, 8, 23, 42, 4, 16]\n    pass",
            "starter_code_javascript": "function solution() {\n    // Find second largest\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Count Palindromes in List",
            "description": "Count how many palindromes are in ['racecar', 'hello', 'level', 'world', 'radar']. Return the count.",
            "expected_answer": "3",
            "hint": "A palindrome reads the same forwards and backwards",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Count palindromes\n    pass",
            "starter_code_javascript": "function solution() {\n    // Count palindromes\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Calculate Factorial",
            "description": "Calculate the factorial of 6. Factorial means 6 × 5 × 4 × 3 × 2 × 1. Return the result.",
            "expected_answer": "720",
            "hint": "Use a loop to multiply numbers from 1 to 6",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Calculate 6!\n    pass",
            "starter_code_javascript": "function solution() {\n    // Calculate 6!\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        
        # HARDER PROBLEMS
        {
            "title": "Find Missing Number in Sequence",
            "description": "Find the missing number in the sequence [1, 2, 3, 5, 6, 7, 8]. One number between 1-8 is missing. Return it.",
            "expected_answer": "4",
            "hint": "The sum of 1-8 should be 36. Find the difference.",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Find missing number\n    pass",
            "starter_code_javascript": "function solution() {\n    // Find missing number\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Fibonacci Number at Position",
            "description": "Find the Fibonacci number at position 7. Fibonacci sequence: 0, 1, 1, 2, 3, 5, 8, 13... Return the 7th number.",
            "expected_answer": "8",
            "hint": "Each number is the sum of the previous two",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Find 7th Fibonacci number\n    pass",
            "starter_code_javascript": "function solution() {\n    // Find 7th Fibonacci number\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Sum of Prime Numbers",
            "description": "Find the sum of all prime numbers between 1 and 15. Prime numbers are 2, 3, 5, 7, 11, 13. Return the sum.",
            "expected_answer": "41",
            "hint": "Check each number if it's only divisible by 1 and itself",
            "difficulty": "hard",
            "starter_code_python": "def solution():\n    # Sum primes 1-15\n    pass",
            "starter_code_javascript": "function solution() {\n    // Sum primes 1-15\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Check Palindrome Phrase",
            "description": "Check if 'Was it a car or a cat I saw' is a palindrome when you ignore spaces and make it lowercase. Return True or False.",
            "expected_answer": "True",
            "hint": "Remove spaces, convert to lowercase, then compare with reverse",
            "difficulty": "hard",
            "starter_code_python": "def solution():\n    # Check if palindrome\n    pass",
            "starter_code_javascript": "function solution() {\n    // Check if palindrome\n}",
            "starter_code_java": "public class Solution {\n    public static boolean solution() {\n        return false;\n    }\n}"
        },
        {
            "title": "Find Duplicate in List",
            "description": "Find the number that appears twice in [1, 2, 3, 4, 5, 3, 6, 7]. Return the duplicate number.",
            "expected_answer": "3",
            "hint": "Use a set to track which numbers you've seen",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Find duplicate\n    pass",
            "starter_code_javascript": "function solution() {\n    // Find duplicate\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Vowel to Consonant Ratio",
            "description": "In the word 'education', count vowels and consonants. Return the difference (vowels - consonants).",
            "expected_answer": "0",
            "hint": "Vowels: a,e,i,o,u. Count both and subtract.",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Count difference\n    pass",
            "starter_code_javascript": "function solution() {\n    // Count difference\n}",
            "starter_code_java": "public class Solution {\n    public static int solution() {\n        return 0;\n    }\n}"
        },
        {
            "title": "Find Most Frequent Character",
            "description": "Find the most frequent character in 'mississippi'. Return the character.",
            "expected_answer": "i",
            "hint": "Count occurrences of each letter",
            "difficulty": "medium",
            "starter_code_python": "def solution():\n    # Find most frequent char\n    pass",
            "starter_code_javascript": "function solution() {\n    // Find most frequent char\n}",
            "starter_code_java": "public class Solution {\n    public static String solution() {\n        return \"\";\n    }\n}"
        }
    ]
    
    problem = random.choice(fallback_problems).copy()
    problem["ai_generated"] = False
    
    logger.info(f"📚 Fallback problem: {problem.get('title')} [{problem.get('difficulty')}]")
    return problem


def execute_code_no_input(code: str, expected_answer: str, language: str = "python") -> Dict[str, Any]:
    """Execute NO-INPUT code - just call function and check return value"""
    try:
        if language == "python":
            import io
            import sys
            from contextlib import redirect_stdout, redirect_stderr
            
            # Extract function name
            func_match = re.search(r'def\s+(\w+)\s*\(\s*\)', code)
            if not func_match:
                return {
                    "success": False,
                    "output": "",
                    "error": "Function must have NO parameters: def solution():",
                    "passed": False,
                    "expected": expected_answer,
                    "actual": ""
                }
            
            func_name = func_match.group(1)
            
            # Create execution environment
            safe_globals = {
                "__builtins__": {
                    'print': print,
                    'len': len,
                    'str': str,
                    'int': int,
                    'float': float,
                    'bool': bool,
                    'list': list,
                    'dict': dict,
                    'tuple': tuple,
                    'set': set,
                    'range': range,
                    'sum': sum,
                    'max': max,
                    'min': min,
                    'abs': abs,
                    'round': round,
                    'sorted': sorted,
                    'reversed': reversed,
                    'enumerate': enumerate,
                    'zip': zip,
                    'map': map,
                    'filter': filter,
                    'True': True,
                    'False': False,
                    'None': None,
                }
            }
            
            # Execute the user's code to define the function
            try:
                exec(code, safe_globals)
            except Exception as e:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Code compilation error: {str(e)}",
                    "passed": False,
                    "expected": expected_answer,
                    "actual": ""
                }
            
            # Check if function was defined
            if func_name not in safe_globals:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Function '{func_name}' not found in code",
                    "passed": False,
                    "expected": expected_answer,
                    "actual": ""
                }
            
            # Call the function and capture result
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            
            result = None
            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    result = safe_globals[func_name]()
                
                # Get any printed output (though we primarily care about return value)
                printed_output = stdout_capture.getvalue().strip()
                error_output = stderr_capture.getvalue().strip()
                
                if error_output:
                    return {
                        "success": False,
                        "output": printed_output,
                        "error": error_output,
                        "passed": False,
                        "expected": expected_answer,
                        "actual": printed_output or str(result)
                    }
                
                # The actual output is the RETURN VALUE, not printed text
                actual_output = str(result) if result is not None else printed_output
                
                logger.info(f"🔍 Function returned: {result} (type: {type(result)})")
                logger.info(f"🔍 Printed output: {printed_output}")
                logger.info(f"🔍 Using actual_output: {actual_output}")
                
                # Compare the result with expected answer
                passed = compare_answers(actual_output, expected_answer)
                
                return {
                    "success": True,
                    "output": actual_output,
                    "expected": expected_answer,
                    "actual": actual_output,
                    "error": None,
                    "passed": passed
                }
                
            except Exception as e:
                error_msg = str(e)
                return {
                    "success": False,
                    "output": stdout_capture.getvalue().strip(),
                    "error": f"Runtime error: {error_msg}",
                    "passed": False,
                    "expected": expected_answer,
                    "actual": stdout_capture.getvalue().strip()
                }
            
        elif language == "javascript":
            return {
                "success": False,
                "output": "",
                "error": "JavaScript execution not implemented yet",
                "passed": False,
                "expected": expected_answer,
                "actual": ""
            }
        
        elif language == "java":
            return {
                "success": False,
                "output": "",
                "error": "Java execution not implemented yet",
                "passed": False,
                "expected": expected_answer,
                "actual": ""
            }
        
        else:
            return {
                "success": False,
                "output": "",
                "error": f"Unsupported language: {language}",
                "passed": False,
                "expected": expected_answer,
                "actual": ""
            }
            
    except Exception as e:
        logger.error(f"❌ Execution error: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "passed": False,
            "expected": expected_answer,
            "actual": ""
        }


# ============================================
# CODE PRACTICE ENDPOINTS - NO INPUT VERSION
# ============================================

@app.post("/api/code/generate-problem")
async def generate_problem(
    request: CodeProblemRequest = None,
    current_user: dict = Depends(get_current_user)
):
    """Generate a NO-INPUT coding problem"""
    try:
        problem_data = generate_coding_problem_no_input()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO code_problems 
                (title, description, difficulty, examples, test_cases, 
                 starter_code_python, starter_code_javascript, starter_code_java, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                problem_data["title"],
                problem_data["description"],
                "Easy",
                json.dumps([]),  # No examples needed for no-input
                json.dumps([{"expected": problem_data["expected_answer"]}]),
                problem_data.get("starter_code_python", ""),
                problem_data.get("starter_code_javascript", ""),
                problem_data.get("starter_code_java", "")
            ))
            conn.commit()
            problem_id = cursor.lastrowid
            
            logger.info(f"✅ NO-INPUT Problem stored: ID={problem_id} | AI={problem_data.get('ai_generated', False)}")
            
        finally:
            cursor.close()
            conn.close()
        
        return {
            "id": problem_id,
            "title": problem_data["title"],
            "description": problem_data["description"],
            "difficulty": "Easy",
            "expected_answer": problem_data["expected_answer"],
            "hint": problem_data.get("hint", ""),
            "starter_code_python": problem_data.get("starter_code_python", ""),
            "starter_code_javascript": problem_data.get("starter_code_javascript", ""),
            "starter_code_java": problem_data.get("starter_code_java", ""),
            "ai_generated": problem_data.get("ai_generated", False)
        }
        
    except Exception as e:
        logger.error(f"Problem generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/code/run")
async def run_code(
    request: CodeRunRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute NO-INPUT code and check answer"""
    try:
        # Get problem from database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT test_cases FROM code_problems 
                WHERE id = %s
            """, (request.problem_id,))
            
            problem = cursor.fetchone()
            
            if not problem:
                raise HTTPException(status_code=404, detail="Problem not found")
            
            test_cases = json.loads(problem["test_cases"])
            expected_answer = test_cases[0]["expected"]
            
        finally:
            cursor.close()
            conn.close()
        
        # Execute code
        result = execute_code_no_input(request.code, expected_answer, request.language)
        
        # Calculate score
        score = 10 if result["passed"] else 0
        
        output_text = f"Expected: {result.get('expected', '')}\n"
        output_text += f"Your Output: {result.get('output', '')}\n\n"
        
        if result["passed"]:
            output_text += "✅ CORRECT! Well done!\n"
        else:
            output_text += "❌ INCORRECT. Try again!\n"
        
        if result.get("error"):
            output_text += f"\nError: {result['error']}\n"
        
        logger.info(f"✅ Code executed: Passed={result['passed']} | Score={score}/10")
        
        return {
            "success": result["success"],
            "output": output_text,
            "passed": result["passed"],
            "score": score,
            "expected": result.get("expected", ""),
            "actual": result.get("output", ""),
            "error": result.get("error")
        }
        
    except Exception as e:
        logger.error(f"Code execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/code/submit-session")
async def submit_coding_session(
    current_user: dict = Depends(get_current_user)
):
    """Submit final coding session score"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT result_summary FROM code_submissions
            WHERE user_id = %s
            AND JSON_EXTRACT(result_summary, '$.is_submission') = true
            AND DATE(created_at) = CURDATE()
            ORDER BY created_at DESC
            LIMIT 10
        """, (current_user["user_id"],))
        
        submissions = cursor.fetchall()
        
        if not submissions:
            return {"message": "No submissions found today", "score": 0}
        
        scores = []
        for sub in submissions:
            try:
                summary = json.loads(sub["result_summary"])
                scores.append(summary.get("score", 0))
            except:
                continue
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        cursor.execute("""
            INSERT INTO code_submissions 
            (user_id, problem, code, result_summary, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (
            current_user["user_id"],
            "SESSION_SUMMARY",
            "",
            json.dumps({
                "is_session_summary": True,
                "session_score": round(avg_score, 1),
                "problems_solved": len(scores),
                "timestamp": datetime.now().isoformat()
            })
        ))
        conn.commit()
        
        logger.info(f"✅ Session saved for user {current_user['user_id']}: {avg_score}/10")
        
        return {
            "message": "Session saved successfully",
            "score": round(avg_score, 1),
            "problems_solved": len(scores)
        }
        
    except Exception as e:
        logger.error(f"Session submission error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/api/code/session-history")
async def get_coding_session_history(current_user: dict = Depends(get_current_user)):
    """Get coding session history for progress graph"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT result_summary, created_at
            FROM code_submissions
            WHERE user_id = %s
            AND problem = 'SESSION_SUMMARY'
            ORDER BY created_at ASC
            LIMIT 30
        """, (current_user["user_id"],))
        
        sessions = cursor.fetchall()
        
        history = []
        for session in sessions:
            try:
                summary = json.loads(session["result_summary"])
                if summary.get("is_session_summary"):
                    history.append({
                        "date": session["created_at"].isoformat() if session["created_at"] else None,
                        "score": summary.get("session_score", 0),
                        "problems_solved": summary.get("problems_solved", 0)
                    })
            except:
                continue
        
        return {
            "sessions": history,
            "total_sessions": len(history)
        }
        
    finally:
        cursor.close()
        conn.close()


# ============================================
# INTERVIEW ENDPOINTS (keeping existing)
# ============================================

@app.post("/api/interview/start")
async def start_interview(
    request: InterviewStartRequest,
    current_user: dict = Depends(get_current_user)
):
    """Start interview"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT analysis_json FROM cv_analyses
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (current_user["user_id"],))
        
        cv_data = cursor.fetchone()
        cv_skills = request.cv_skills
        
        if not cv_skills and cv_data:
            try:
                analysis = json.loads(cv_data["analysis_json"])
                cv_skills = analysis.get("skills", [])
                logger.info(f"✅ Found CV with skills: {cv_skills}")
            except:
                pass
        
        session_id = f"session_{current_user['user_id']}_{int(datetime.now().timestamp())}"
        
        if cv_skills and len(cv_skills) > 0:
            greeting = (
                f"Hello! I've reviewed your CV and I'm impressed by your experience with "
                f"{', '.join(cv_skills[:3])}. Let's start - tell me about yourself and what "
                f"excites you most about your work."
            )
        else:
            greeting = (
                "Hello! I'm your AI interviewer. Let's begin - tell me about yourself "
                "and what interests you in your career."
            )
        
        interview_sessions[session_id] = {
            "user_id": current_user["user_id"],
            "topic": request.topic,
            "stage": "intro",
            "cv_skills": cv_skills,
            "history": [
                {"role": "assistant", "content": greeting, "timestamp": datetime.now().isoformat()}
            ],
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"✅ Interview started: {session_id}")
        
        return {
            "session_id": session_id,
            "message": greeting,
            "cv_skills": cv_skills
        }
        
    finally:
        cursor.close()
        conn.close()


@app.post("/api/interview/message")
async def send_interview_message(
    request: InterviewMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send message and get AI response"""
    if request.session_id not in interview_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = interview_sessions[request.session_id]
    
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    session["history"].append({
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now().isoformat()
    })
    
    ai_question, metadata = generate_interview_question(
        user_answer=request.message,
        conversation_history=session["history"],
        cv_skills=session.get("cv_skills", [])
    )
    
    session["history"].append({
        "role": "assistant",
        "content": ai_question,
        "timestamp": datetime.now().isoformat()
    })
    
    logger.info(f"✅ AI replied (Q#{metadata.get('question_number')}): {ai_question[:50]}...")
    
    return {
        "reply": ai_question,
        "stage": session.get("stage"),
        "question_number": metadata.get("question_number"),
        "provider": metadata.get("provider")
    }


@app.post("/api/interview/end/{session_id}")
async def end_interview(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """End interview and get rating"""
    if session_id not in interview_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = interview_sessions[session_id]
    
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    rating = rate_interview(session["history"])
    
    if "tips" not in rating:
        rating["tips"] = [
            "Practice STAR method (Situation, Task, Action, Result)",
            "Take time to think before answering",
            "Prepare specific examples from your experience"
        ]
    
    if "strengths" not in rating:
        rating["strengths"] = ["Completed the interview", "Engaged with questions"]
    
    if "improvements" not in rating:
        rating["improvements"] = ["Keep practicing to improve"]
    
    if "weaknesses" not in rating:
        rating["weaknesses"] = rating.get("improvements", ["Keep practicing"])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO interview_sessions
            (id, user_id, topic, started_at, ended_at, metadata, score, feedback)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s)
        """, (
            session_id,
            session["user_id"],
            session.get("topic"),
            session.get("created_at"),
            json.dumps(session["history"]),
            rating.get("score"),
            json.dumps(rating)
        ))
        conn.commit()
        
        logger.info(f"✅ Interview saved: {session_id}")
        
    finally:
        cursor.close()
        conn.close()
    
    del interview_sessions[session_id]
    
    return {
        "message": "Interview ended",
        "rating": rating
    }


@app.get("/api/progress/summary")
async def get_progress_summary(current_user: dict = Depends(get_current_user)):
    """Get user's interview progress"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT topic, score, started_at
            FROM interview_sessions
            WHERE user_id = %s AND score IS NOT NULL
            ORDER BY started_at ASC
        """, (current_user["user_id"],))
        
        interviews = cursor.fetchall()
        
        total = len(interviews)
        avg = sum(float(i['score']) for i in interviews) / total if total > 0 else 0
        
        return {
            "total_interviews": total,
            "average_score": round(avg, 1),
            "sessions_history": [
                {
                    "date": i['started_at'].isoformat() if i['started_at'] else None,
                    "score": float(i['score']) if i['score'] else 0,
                    "topic": i.get('topic', 'General')
                }
                for i in interviews
            ]
        }
        
    finally:
        cursor.close()
        conn.close()


@app.get("/api/cv/count")
async def get_cv_count(current_user: dict = Depends(get_current_user)):
    """Get total CV uploads"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM cv_analyses 
            WHERE user_id = %s
        """, (current_user["user_id"],))
        
        result = cursor.fetchone()
        return {"cv_count": result["count"] if result else 0}
        
    finally:
        cursor.close()
        conn.close()


# ============================================
# HEALTH & ROOT ENDPOINTS
# ============================================

@app.get("/")
async def root():
    return {"status": "online", "version": "2.0-NO-INPUT", "service": "EVALUX API"}


@app.get("/health")
async def health():
    """Health check"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat(),
            "mode": "NO-INPUT"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "degraded",
            "database": "disconnected",
            "error": str(e)
        }
    
# ============================================
# ADMIN ENDPOINTS
# ============================================

def get_current_admin(current_user: dict = Depends(get_current_user)):
    """Check if current user is admin"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(
            "SELECT is_admin FROM users WHERE id = %s",
            (current_user["user_id"],)
        )
        user = cursor.fetchone()
        
        if not user or not user.get("is_admin"):
            raise HTTPException(
                status_code=403, 
                detail="Admin access required"
            )
        
        return current_user
        
    finally:
        cursor.close()
        conn.close()


@app.get("/api/admin/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_admin)):
    """Get admin dashboard statistics"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Total users
        cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_admin = FALSE")
        total_users = cursor.fetchone()["total"]
        
        # Users registered today
        cursor.execute("""
            SELECT COUNT(*) as today 
            FROM users 
            WHERE DATE(created_at) = CURDATE() AND is_admin = FALSE
        """)
        users_today = cursor.fetchone()["today"]
        
        # Users registered this week
        cursor.execute("""
            SELECT COUNT(*) as week 
            FROM users 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND is_admin = FALSE
        """)
        users_week = cursor.fetchone()["week"]
        
        # Get all users with interests
        cursor.execute("""
            SELECT id, username, email, interests, created_at
            FROM users
            WHERE is_admin = FALSE
            ORDER BY created_at DESC
        """)
        users = cursor.fetchall()
        
        # Parse interests
        users_data = []
        interest_count = {}
        
        for user in users:
            try:
                interests = json.loads(user.get("interests") or "[]")
                
                # Count interests
                for interest in interests:
                    interest_count[interest] = interest_count.get(interest, 0) + 1
                
                users_data.append({
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "interests": interests,
                    "joined": user["created_at"].isoformat() if user["created_at"] else None
                })
            except:
                users_data.append({
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "interests": [],
                    "joined": user["created_at"].isoformat() if user["created_at"] else None
                })
        
        # Sort interests by popularity
        top_interests = sorted(interest_count.items(), key=lambda x: x[1], reverse=True)
        
        logger.info(f"✅ Admin stats retrieved: {total_users} users")
        
        return {
            "total_users": total_users,
            "users_today": users_today,
            "users_this_week": users_week,
            "users": users_data,
            "interests_breakdown": [
                {"interest": k, "count": v} 
                for k, v in top_interests
            ]
        }
        
    finally:
        cursor.close()
        conn.close()


@app.get("/api/admin/check")
async def check_admin(current_user: dict = Depends(get_current_user)):
    """Check if current user is admin"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(
            "SELECT is_admin, username FROM users WHERE id = %s",
            (current_user["user_id"],)
        )
        user = cursor.fetchone()
        
        return {
            "is_admin": bool(user.get("is_admin")) if user else False,
            "username": user.get("username") if user else None
        }
        
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting EVALUX Backend (NO-INPUT VERSION)...")   
    uvicorn.run(app, host="0.0.0.0", port=8000)