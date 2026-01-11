"""
AI Module for EVALUX
Handles CV analysis and adaptive interview questions
"""
from dotenv import load_dotenv
load_dotenv()

import os
import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Groq Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq SDK not installed")


def analyze_cv(cv_text: str) -> Dict:
    """
    Analyze CV text and extract skills + generate questions
    
    Args:
        cv_text: Raw text from CV
        
    Returns:
        Dict with skills and interview_questions
    """
    logger.info(f"Analyzing CV... Text length: {len(cv_text)}")
    
    # Validate input
    if not cv_text or len(cv_text.strip()) < 50:
        logger.warning("CV text too short, using fallback")
        return {
            "skills": ["Python", "Communication"],
            "interview_questions": [
                "Tell me about your professional background.",
                "What are your key technical skills?",
                "Describe a challenging project you've worked on.",
                "How do you approach problem-solving?",
                "What are you currently learning?"
            ]
        }
    
    # Try AI-powered analysis
    if GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            
            prompt = f"""Analyze this CV and extract information in JSON format:

CV Text:
{cv_text[:3000]}

Return ONLY this JSON structure:
{{
  "skills": ["skill1", "skill2", "skill3", "skill4", "skill5"],
  "interview_questions": [
    "Question 1 about their experience?",
    "Question 2 about their skills?",
    "Question 3 about projects?",
    "Question 4 about challenges?",
    "Question 5 about goals?"
  ]
}}

Rules:
- Extract 5-8 technical skills
- Generate 5 specific questions based on their CV content
- Questions should be natural and conversational"""

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=800
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Clean markdown if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            result = json.loads(result_text.strip())
            
            logger.info(f"✅ AI Analysis: {len(result.get('skills', []))} skills, {len(result.get('interview_questions', []))} questions")
            
            return {
                "skills": result.get("skills", [])[:8],
                "interview_questions": result.get("interview_questions", [])[:5]
            }
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
    
    # Keyword-based fallback
    logger.info("Using keyword extraction fallback")
    
    lower_text = cv_text.lower()
    skills = []
    
    # Common tech skills
    skill_map = {
        "python": "Python", "java": "Java", "javascript": "JavaScript",
        "react": "React", "node": "Node.js", "sql": "SQL",
        "aws": "AWS", "docker": "Docker", "git": "Git",
        "html": "HTML", "css": "CSS"
    }
    
    for keyword, skill_name in skill_map.items():
        if keyword in lower_text:
            skills.append(skill_name)
    
    if not skills:
        skills = ["Software Development", "Problem Solving"]
    
    # Generate basic questions
    questions = [
        f"Tell me about your experience with {skills[0]}." if skills else "Tell me about your background.",
        "What's the most challenging project you've worked on?",
        "How do you approach debugging issues?",
        "Describe your teamwork style.",
        "What are you learning right now?"
    ]
    
    logger.info(f"✅ Keyword Analysis: {len(skills)} skills extracted")
    
    return {
        "skills": skills[:8],
        "interview_questions": questions
    }


def generate_interview_question(
    user_answer: str,
    conversation_history: List[Dict],
    cv_skills: Optional[List[str]] = None
) -> Tuple[str, Dict]:
    """
    Generate next interview question based on conversation and CV
    
    Args:
        user_answer: Latest answer from candidate
        conversation_history: Previous Q&A
        cv_skills: Skills from CV analysis
        
    Returns:
        Tuple of (question_text, metadata)
    """
    question_count = len([m for m in conversation_history if m.get("role") == "assistant"])
    
    # Build context
    context = "You are a professional interviewer.\n\n"
    
    if cv_skills:
        context += f"CANDIDATE'S CV SKILLS: {', '.join(cv_skills[:5])}\n"
        context += "Ask questions related to these skills.\n\n"
    
    context += f"QUESTION #{question_count + 1}\n"
    context += f"CANDIDATE'S LAST ANSWER: {user_answer}\n\n"
    
    # Add recent conversation
    if conversation_history:
        context += "RECENT CONVERSATION:\n"
        for msg in conversation_history[-4:]:
            role = msg.get("role", "").upper()
            content = msg.get("content", "")
            context += f"{role}: {content}\n"
    
    context += "\nGenerate ONE follow-up question (max 20 words). Be conversational and natural."
    
    # Try AI generation
    if GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": context}],
                temperature=0.7,
                max_tokens=60
            )
            
            question = response.choices[0].message.content.strip()
            
            # Clean up formatting
            question = question.replace('"', '').replace("Question:", "").strip()
            
            logger.info(f"✅ AI Question: {question[:50]}...")
            
            return question, {"provider": "groq", "question_number": question_count + 1}
            
        except Exception as e:
            logger.error(f"Question generation failed: {e}")
    
    # Fallback questions based on count
    fallback_questions = [
        "Tell me more about your background.",
        "What's your experience with the skills on your CV?",
        "Describe a challenging project you worked on.",
        "How do you handle difficult technical problems?",
        "What are your career goals?",
        "Can you elaborate on that?"
    ]
    
    question = fallback_questions[min(question_count, len(fallback_questions) - 1)]
    
    return question, {"provider": "fallback", "question_number": question_count + 1}


def rate_interview(conversation_history: List[Dict]) -> Dict:
    """
    Rate interview performance
    
    Args:
        conversation_history: Full conversation
        
    Returns:
        Rating dict with score, feedback, etc.
    """
    user_responses = [m for m in conversation_history if m.get("role") == "user"]
    
    # Check if interview is complete enough
    if len(user_responses) < 3:
        return {
            "score": None,
            "summary": "Interview too short. Answer at least 3 questions.",
            "incomplete": True
        }
    
    # Try AI rating
    if GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            
            # Build transcript
            transcript = "\n".join([
                f"{m['role'].upper()}: {m.get('content', '')}"
                for m in conversation_history
            ])
            
            prompt = f"""Rate this interview on a scale of 0-10. Return JSON:

{{
  "score": 7.5,
  "summary": "2-3 sentence assessment",
  "strengths": ["strength1", "strength2"],
  "improvements": ["improvement1", "improvement2"]
}}

TRANSCRIPT:
{transcript[:2000]}"""

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400
            )
            
            rating_text = response.choices[0].message.content.strip()
            
            # Clean markdown
            if "```json" in rating_text:
                rating_text = rating_text.split("```json")[1].split("```")[0]
            elif "```" in rating_text:
                rating_text = rating_text.split("```")[1].split("```")[0]
            
            rating = json.loads(rating_text.strip())
            rating["incomplete"] = False
            
            logger.info(f"✅ Interview rated: {rating.get('score')}/10")
            
            return rating
            
        except Exception as e:
            logger.error(f"Rating failed: {e}")
    
    # Fallback rating
    return {
        "score": 6.5,
        "summary": "Interview completed. Keep practicing!",
        "strengths": ["Engaged with questions"],
        "improvements": ["Provide more specific examples"],
        "incomplete": False
    }