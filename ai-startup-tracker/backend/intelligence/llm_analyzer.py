"""
LLM-powered startup analysis using Groq API
Groq provides fast inference for Llama, Mixtral, and other open-source models
"""
from typing import Dict, Optional, List
import json
from groq import Groq
from loguru import logger

from ..database.models import Startup
from ..database.connection import get_db_session
from ..config import get_settings


class LLMAnalyzer:
    """Analyze startups using Groq LLM"""

    def __init__(self):
        self.settings = get_settings()
        self.client = Groq(api_key=self.settings.GROQ_API_KEY)
        self.model = self.settings.LLM_MODEL

        logger.info(f"Initialized Groq LLM analyzer with model: {self.model}")

    def _call_llm(
        self,
        prompt: str,
        system_prompt: str = "You are an AI expert analyzing startup companies.",
        max_tokens: int = 1000,
        temperature: float = 0.3
    ) -> str:
        """
        Call Groq LLM with a prompt

        Args:
            prompt: User prompt
            system_prompt: System instruction
            max_tokens: Maximum response tokens
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            LLM response text
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            return ""

    def categorize_vertical(self, startup_data: Dict) -> tuple[str, float]:
        """
        Categorize startup into specific AI vertical

        Args:
            startup_data: Dictionary with name, description, landing_page_text

        Returns:
            Tuple of (vertical, confidence_score)
        """
        prompt = f"""
Analyze this AI startup and assign it to ONE specific vertical category.

Company: {startup_data.get('name', 'Unknown')}
Description: {startup_data.get('description', 'N/A')}
Website Content: {startup_data.get('landing_page_text', '')[:1000]}

Available categories:
- AI Health (healthcare, medical, diagnostics, drug discovery)
- AI Finance (fintech, trading, banking, insurance)
- AI Manufacturing (industrial, supply chain, quality control)
- AI Education (edtech, tutoring, learning platforms)
- AI Sales & Marketing (CRM, analytics, advertising)
- AI Developer Tools (APIs, SDKs, MLOps, infrastructure)
- AI Creative (content generation, design, media)
- AI Security (cybersecurity, fraud detection)
- AI HR & Recruiting (talent, hiring, workforce)
- AI Customer Service (chatbots, support automation)
- AI Legal (contract analysis, compliance)
- AI Research (foundational AI, AGI)
- AI Consumer (apps, entertainment, lifestyle)
- Other AI

Respond in JSON format:
{{
  "vertical": "category name",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}
"""

        response = self._call_llm(prompt, temperature=0.2)

        try:
            # Parse JSON response
            data = json.loads(response)
            vertical = data.get('vertical', 'Other AI')
            confidence = float(data.get('confidence', 0.5))

            logger.debug(f"Categorized as {vertical} (confidence: {confidence})")
            return vertical, confidence

        except json.JSONDecodeError:
            # Fallback: extract from text
            logger.warning("Failed to parse JSON, using text extraction")
            if "AI Health" in response:
                return "AI Health", 0.6
            elif "AI Finance" in response:
                return "AI Finance", 0.6
            else:
                return "Other AI", 0.4

    def detect_stealth_status(self, startup_data: Dict) -> tuple[bool, float, str]:
        """
        Detect if startup is in stealth mode

        Args:
            startup_data: Dictionary with startup information

        Returns:
            Tuple of (is_stealth, confidence, reasoning)
        """
        prompt = f"""
Determine if this AI startup is in "stealth mode".

Company: {startup_data.get('name', 'Unknown')}
Website: {startup_data.get('url', 'N/A')}
Landing Page: {startup_data.get('landing_page_text', '')[:500]}

Stealth indicators:
- Website shows only "Coming Soon" or minimal content
- No product details or features described
- Placeholder or under-construction pages
- "We're building something amazing" type messaging
- Heavy focus on hiring without explaining the product
- Generic AI/tech buzzwords without specifics

Respond in JSON format:
{{
  "is_stealth": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "signals": ["signal1", "signal2"]
}}
"""

        response = self._call_llm(prompt, temperature=0.2)

        try:
            data = json.loads(response)
            is_stealth = data.get('is_stealth', False)
            confidence = float(data.get('confidence', 0.5))
            reasoning = data.get('reasoning', '')

            return is_stealth, confidence, reasoning

        except json.JSONDecodeError:
            # Fallback heuristic
            text = startup_data.get('landing_page_text', '').lower()
            if any(phrase in text for phrase in ['coming soon', 'under construction', 'launching soon']):
                return True, 0.7, "Coming soon page detected"
            return False, 0.5, "Unable to determine"

    def extract_founder_info(self, startup_data: Dict) -> Dict:
        """
        Extract founder information and backgrounds

        Args:
            startup_data: Dictionary with startup information

        Returns:
            Dictionary with founder details
        """
        prompt = f"""
Extract information about the founders of this startup.

Company: {startup_data.get('name', 'Unknown')}
Content: {startup_data.get('landing_page_text', '')[:1000]}
Existing founder data: {startup_data.get('founder_names', [])}

Look for:
- Founder names
- Previous companies (especially notable ones like Google, Meta, OpenAI, etc.)
- Universities or research institutions
- Notable achievements or credentials
- LinkedIn profiles or backgrounds

Respond in JSON format:
{{
  "founders": [
    {{
      "name": "founder name",
      "background": "brief background",
      "notable": true/false
    }}
  ],
  "has_notable_founders": true/false,
  "summary": "brief summary of team"
}}
"""

        response = self._call_llm(prompt, max_tokens=800)

        try:
            data = json.loads(response)
            return {
                'founders': data.get('founders', []),
                'has_notable_founders': data.get('has_notable_founders', False),
                'founder_backgrounds': data.get('summary', '')
            }

        except json.JSONDecodeError:
            return {
                'founders': [],
                'has_notable_founders': False,
                'founder_backgrounds': ''
            }

    async def analyze_startup(self, startup_id: int) -> Dict:
        """
        Comprehensive analysis of a startup

        Args:
            startup_id: Startup ID to analyze

        Returns:
            Dictionary with analysis results
        """
        try:
            with get_db_session() as session:
                startup = session.query(Startup).filter(
                    Startup.id == startup_id
                ).first()

                if not startup:
                    logger.error(f"Startup {startup_id} not found")
                    return {}

                logger.info(f"Analyzing startup: {startup.name}")

                # Prepare data for analysis
                startup_data = {
                    'name': startup.name,
                    'url': startup.url,
                    'description': startup.description,
                    'landing_page_text': startup.landing_page_text,
                    'founder_names': startup.founder_names
                }

                # Run analyses
                vertical, vertical_confidence = self.categorize_vertical(startup_data)
                is_stealth, stealth_confidence, stealth_reason = self.detect_stealth_status(startup_data)
                founder_info = self.extract_founder_info(startup_data)

                # Calculate overall confidence
                overall_confidence = (vertical_confidence + stealth_confidence) / 2

                # Update startup
                startup.industry_vertical = vertical
                startup.is_stealth = is_stealth
                startup.confidence_score = round(overall_confidence, 2)
                startup.has_notable_founders = founder_info['has_notable_founders']
                startup.founder_backgrounds = founder_info['founder_backgrounds']

                # If confidence is low, flag for human review
                if overall_confidence < self.settings.LLM_CONFIDENCE_THRESHOLD:
                    startup.review_status = "needs_review"
                else:
                    startup.review_status = "approved"

                session.commit()

                logger.info(
                    f"Analysis complete: {startup.name} - {vertical} "
                    f"(stealth: {is_stealth}, confidence: {overall_confidence:.2f})"
                )

                return {
                    'startup_id': startup_id,
                    'vertical': vertical,
                    'is_stealth': is_stealth,
                    'confidence': overall_confidence,
                    'has_notable_founders': founder_info['has_notable_founders']
                }

        except Exception as e:
            logger.error(f"Failed to analyze startup {startup_id}: {e}")
            return {}

    async def batch_analyze_startups(self, limit: int = 50) -> Dict:
        """
        Analyze multiple startups that haven't been analyzed yet

        Args:
            limit: Maximum number to analyze

        Returns:
            Statistics dictionary
        """
        logger.info(f"Starting batch analysis (limit: {limit})...")

        analyzed = 0
        errors = 0

        try:
            with get_db_session() as session:
                # Get startups that need analysis
                # (have embeddings and passed relevance filter, but not yet analyzed)
                startups = session.query(Startup).filter(
                    Startup.content_embedding.isnot(None),
                    Startup.relevance_score >= self.settings.SIMILARITY_THRESHOLD,
                    Startup.industry_vertical.is_(None)
                ).limit(limit).all()

                if not startups:
                    logger.info("No startups to analyze")
                    return {'analyzed': 0, 'errors': 0}

                logger.info(f"Found {len(startups)} startups to analyze")

                for startup in startups:
                    try:
                        await self.analyze_startup(startup.id)
                        analyzed += 1

                    except Exception as e:
                        logger.error(f"Error analyzing startup {startup.id}: {e}")
                        errors += 1

        except Exception as e:
            logger.error(f"Batch analysis failed: {e}")
            errors += 1

        logger.info(f"Batch analysis complete: {analyzed} analyzed, {errors} errors")

        return {
            'analyzed': analyzed,
            'errors': errors
        }


# Singleton instance
_llm_analyzer = None


def get_llm_analyzer() -> LLMAnalyzer:
    """Get singleton LLM analyzer instance"""
    global _llm_analyzer
    if _llm_analyzer is None:
        _llm_analyzer = LLMAnalyzer()
    return _llm_analyzer
