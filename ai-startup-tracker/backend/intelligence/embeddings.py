"""
Embedding generation using local sentence-transformers
No API key required - runs locally on your machine
"""
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from loguru import logger
from sqlalchemy import text

from ..database.models import Startup
from ..database.connection import get_db_session
from ..config import get_settings


class EmbeddingGenerator:
    """Generate embeddings using local sentence-transformers model"""

    def __init__(self):
        self.settings = get_settings()
        self.model_name = self.settings.EMBEDDING_MODEL
        self.dimension = self.settings.EMBEDDING_DIMENSION

        logger.info(f"Loading embedding model: {self.model_name}")
        # This downloads the model on first use (~80MB for all-MiniLM-L6-v2)
        # Cached locally afterward
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"Model loaded. Embedding dimension: {self.dimension}")

        # Reference embedding for "AI startup"
        self._reference_embedding = None

    @property
    def reference_embedding(self) -> np.ndarray:
        """Get cached reference embedding for AI startup"""
        if self._reference_embedding is None:
            reference_text = """
            Artificial Intelligence startup company developing machine learning
            AI technology deep learning neural networks LLM GPT computer vision
            natural language processing automation robotics software
            """
            self._reference_embedding = self.generate_embedding(reference_text)
            logger.info("Generated reference embedding for AI startup")
        return self._reference_embedding

    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            Numpy array of embedding vector
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return np.zeros(self.dimension)

        try:
            # Truncate text if too long (model max is usually 512 tokens)
            text = text[:2000]  # ~500 tokens
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return np.zeros(self.dimension)

    def generate_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts (faster)

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        try:
            # Truncate all texts
            texts = [text[:2000] if text else "" for text in texts]

            # Batch encode for efficiency
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                show_progress_bar=True,
                convert_to_numpy=True
            )
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return [np.zeros(self.dimension) for _ in texts]

    def calculate_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score between 0 and 1
        """
        try:
            # Cosine similarity
            similarity = np.dot(embedding1, embedding2) / (
                np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
            )
            return float(similarity)

        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0

    def is_ai_related(self, text: str, threshold: float = None) -> tuple[bool, float]:
        """
        Check if text is AI-related based on embedding similarity

        Args:
            text: Text to check
            threshold: Similarity threshold (uses config default if None)

        Returns:
            Tuple of (is_ai_related, similarity_score)
        """
        if threshold is None:
            threshold = self.settings.SIMILARITY_THRESHOLD

        embedding = self.generate_embedding(text)
        similarity = self.calculate_similarity(embedding, self.reference_embedding)

        is_related = similarity >= threshold
        return is_related, similarity

    async def process_unembedded_startups(self, batch_size: int = 100) -> dict:
        """
        Process all startups that don't have embeddings yet

        Args:
            batch_size: Number of startups to process at once

        Returns:
            Dictionary with processing statistics
        """
        logger.info("Processing startups without embeddings...")

        processed = 0
        filtered = 0
        errors = 0

        try:
            with get_db_session() as session:
                # Get startups without embeddings
                startups = session.query(Startup).filter(
                    Startup.content_embedding.is_(None),
                    Startup.landing_page_text.isnot(None)
                ).limit(batch_size).all()

                if not startups:
                    logger.info("No startups to process")
                    return {'processed': 0, 'filtered': 0, 'errors': 0}

                logger.info(f"Found {len(startups)} startups to process")

                # Extract texts
                texts = [s.landing_page_text or "" for s in startups]

                # Generate embeddings in batch
                embeddings = self.generate_embeddings_batch(texts)

                # Update database
                for startup, embedding in zip(startups, embeddings):
                    try:
                        # Calculate relevance score
                        relevance = self.calculate_similarity(
                            embedding,
                            self.reference_embedding
                        )

                        # Update startup
                        startup.content_embedding = embedding.tolist()
                        startup.relevance_score = round(relevance, 2)

                        # Filter out non-AI startups
                        if relevance < self.settings.SIMILARITY_THRESHOLD:
                            startup.review_status = "rejected"
                            filtered += 1
                            logger.debug(
                                f"Filtered out {startup.name} (score: {relevance:.2f})"
                            )
                        else:
                            startup.review_status = "pending"
                            logger.debug(
                                f"Kept {startup.name} (score: {relevance:.2f})"
                            )

                        processed += 1

                    except Exception as e:
                        logger.error(f"Error processing startup {startup.id}: {e}")
                        errors += 1

                session.commit()

        except Exception as e:
            logger.error(f"Failed to process startups: {e}")
            errors += 1

        logger.info(
            f"Processed {processed} startups, "
            f"filtered {filtered}, "
            f"errors {errors}"
        )

        return {
            'processed': processed,
            'filtered': filtered,
            'errors': errors,
            'kept': processed - filtered
        }

    async def find_similar_startups(
        self,
        startup_id: int,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[tuple[int, str, float]]:
        """
        Find startups similar to a given startup

        Args:
            startup_id: ID of the startup to compare against
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold

        Returns:
            List of tuples (id, name, similarity_score)
        """
        try:
            with get_db_session() as session:
                # Get the target startup's embedding
                startup = session.query(Startup).filter(
                    Startup.id == startup_id
                ).first()

                if not startup or not startup.content_embedding:
                    logger.error(f"Startup {startup_id} not found or has no embedding")
                    return []

                target_embedding = np.array(startup.content_embedding)

                # Find similar startups using pgvector
                # Using the cosine distance operator: <=>
                query = text("""
                    SELECT id, name,
                           1 - (content_embedding <=> :embedding) as similarity
                    FROM startups
                    WHERE id != :startup_id
                      AND content_embedding IS NOT NULL
                      AND 1 - (content_embedding <=> :embedding) >= :min_similarity
                    ORDER BY content_embedding <=> :embedding
                    LIMIT :limit
                """)

                result = session.execute(query, {
                    'embedding': target_embedding.tolist(),
                    'startup_id': startup_id,
                    'min_similarity': min_similarity,
                    'limit': limit
                })

                similar = [(row[0], row[1], row[2]) for row in result]
                return similar

        except Exception as e:
            logger.error(f"Failed to find similar startups: {e}")
            return []


# Singleton instance
_embedding_generator = None


def get_embedding_generator() -> EmbeddingGenerator:
    """Get singleton embedding generator instance"""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator
