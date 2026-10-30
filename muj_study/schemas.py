from typing import Literal
from pydantic import BaseModel, Field


class Topic(BaseModel):
    name: str
    concepts: list[str]
    definitions: list[str]
    difficulty: Literal['foundational', 'intermediate', 'tricky']
    prerequisites: list[str]
    source_pages: list[int]
    queries: list[str] = Field(min_length=3, max_length=4)
    scope: Literal['concept', 'chapter'] = 'concept'
    fast_changing: bool = False


class Analysis(BaseModel):
    summary: str
    topics: list[Topic]
    readability_warning: str = ''


class LeanTopic(BaseModel):
    name: str
    concepts: list[str]
    definitions: list[str]
    difficulty: Literal['foundational', 'intermediate', 'tricky']
    prerequisites: list[str]
    source_pages: list[int]
    scope: Literal['concept', 'chapter'] = 'concept'
    fast_changing: bool = False


class LeanAnalysis(BaseModel):
    summary: str
    topics: list[LeanTopic]
    readability_warning: str = ''


class Score(BaseModel):
    video_id: str
    relevance: float = Field(ge=0, le=10)
    clarity: float = Field(ge=0, le=10)
    level_match: float = Field(ge=0, le=10)
    depth: float = Field(ge=0, le=10)
    examples: float = Field(ge=0, le=10)
    role: Literal['quick intro', 'deep dive', 'exam revision', 'solved problems']
    reason: str
    confidence: Literal['low', 'medium', 'high']
    language: str


class Scores(BaseModel):
    scores: list[Score]


class VideoSearchPlan(BaseModel):
    queries: list[str] = Field(min_length=2, max_length=3)


class Question(BaseModel):
    kind: Literal['mcq', 'short-answer']
    question: str
    options: list[str]
    answer: str
    explanation: str
    source_pages: list[int]


class Card(BaseModel):
    front: str
    back: str


class Aids(BaseModel):
    quiz: list[Question]
    flashcards: list[Card]
    cheat_sheet: str


class Answer(BaseModel):
    answer: str
    source_pages: list[int]
    insufficient_evidence: bool


class Coverage(BaseModel):
    covered_concepts: list[str]
    missing_concepts: list[str]
    terminology_warnings: list[str]
    start_seconds: int = Field(ge=0)
    evidence_quote: str


class GapReport(BaseModel):
    matched_units: list[str]
    missing_topics: list[str]
    explanation: str


class PlaylistRange(BaseModel):
    relevant: bool
    first_lesson: int = Field(ge=1)
    last_lesson: int = Field(ge=1)
    reason: str
    confidence: Literal['low', 'medium', 'high']
