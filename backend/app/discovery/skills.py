"""Skill taxonomy: canonical skill -> regex of its aliases.

Used both on job descriptions and on your facts, so "Spring Boot 3.2" in a fact
and "SpringBoot" in a JD land on the same canonical skill.
"""

import re

SKILLS: dict[str, str] = {
    # backend core
    "java": r"\bjava\b(?!\s*script)",
    "spring boot": r"\bspring\s*boot\b",
    "spring": r"\bspring (framework|mvc|cloud|data|security|batch)\b",
    "spring webflux": r"\bwebflux\b",
    "hibernate": r"\bhibernate\b|\bjpa\b",
    "microservices": r"\bmicro-?services?\b",
    "rest apis": r"\brestful\b|\brest\s*(apis?|services|endpoints)\b",
    "grpc": r"\bgrpc\b",
    "graphql": r"\bgraphql\b",
    "distributed systems": r"\bdistributed systems?\b",
    "system design": r"\bsystem design\b|\bdesign scalable\b",
    "kafka": r"\bkafka\b",
    "redis": r"\bredis\b",
    "sql": r"\bsql\b",
    "postgresql": r"\bpostgres(ql)?\b",
    "mysql": r"\bmysql\b",
    "mongodb": r"\bmongo(db)?\b",
    "elasticsearch": r"\belastic\s*search\b",
    "aws": r"\baws\b|\bamazon web services\b",
    "aws sqs": r"\bsqs\b",
    "aws s3": r"\bs3\b",
    "aws ecs": r"\becs\b",
    "gcp": r"\bgcp\b|\bgoogle cloud\b",
    "azure": r"\bazure\b",
    "docker": r"\bdocker\b|\bcontaineri[sz]ation\b",
    "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "terraform": r"\bterraform\b",
    "ci/cd": r"\bci\s*/\s*cd\b|\bjenkins\b|\bgithub actions\b",
    "oauth2": r"\boauth\s*2?\b|\bjwt\b",
    "python": r"\bpython\b",
    "fastapi": r"\bfastapi\b",
    "django": r"\bdjango\b",
    "go": r"\bgolang\b|\bgo\b(?=\s*(/|,|\)|developer|engineer|programming))",
    "kotlin": r"\bkotlin\b",
    "scala": r"\bscala\b",
    "node.js": r"\bnode(\.?js)?\b",
    "typescript": r"\btypescript\b",
    "react": r"\breact(\.js)?\b",
    "spark": r"\b(apache\s*)?spark\b",
    "dsa": r"\bdata structures\b|\balgorithms\b|\bleetcode\b|\bcompetitive programming\b",
    # AI / LLM
    "llms": r"\bllms?\b|\blarge language models?\b",
    "generative ai": r"\bgen\s*-?ai\b|\bgenerative ai\b",
    "rag": r"\brag\b|\bretrieval[- ]augmented\b",
    "embeddings": r"\bembeddings?\b",
    "vector databases": r"\bvector (databases?|stores?|search|db)\b|\bpinecone\b|\bweaviate\b|\bqdrant\b|\bchroma(db)?\b|\bpgvector\b|\bmilvus\b",
    "prompt engineering": r"\bprompt (engineering|design)\b|\bprompting\b",
    "ai agents": r"\bai agents?\b|\bagentic\b|\bmulti-?agent\b|\bautonomous agents?\b",
    "tool calling": r"\btool[- ]calling\b|\bfunction[- ]calling\b",
    "langchain": r"\blangchain\b",
    "langgraph": r"\blanggraph\b",
    "llamaindex": r"\bllama\s*index\b",
    # Not bare company names: an Anthropic or OpenAI job mentions its own name everywhere.
    "llm apis": r"\b(openai|anthropic|claude|gemini) apis?\b|\bgpt-?\d|\bllm apis?\b|\bmodel apis?\b",
    "llm evaluation": r"\bllm eval|\bevals?\b|\bevaluation (framework|pipeline)s?\b",
    "fine-tuning": r"\bfine[- ]?tun(e|ing)\b|\blora\b|\bpeft\b",
    "transformers": r"\btransformers?\b",
    "nlp": r"\bnlp\b|\bnatural language processing\b",
    "machine learning": r"\bmachine learning\b|\bml\b",
    "deep learning": r"\bdeep learning\b|\bneural networks?\b",
    "pytorch": r"\bpytorch\b",
    "tensorflow": r"\btensorflow\b",
    "mlops": r"\bmlops\b|\bmodel (serving|deployment)\b",
    "multimodal": r"\bmulti-?modal\b|\bvision[- ]language\b",
}
AI_SKILLS = {
    "llms", "generative ai", "rag", "embeddings", "vector databases", "prompt engineering", "ai agents",
    "tool calling", "langchain", "langgraph", "llamaindex", "llm apis", "llm evaluation", "fine-tuning",
    "transformers", "nlp", "machine learning", "deep learning", "pytorch", "tensorflow", "mlops", "multimodal",
}
# Backend skills that transfer directly into AI-backend work.
TRANSFERABLE = {
    "java", "spring boot", "microservices", "rest apis", "distributed systems", "aws", "aws sqs", "aws s3",
    "kafka", "postgresql", "sql", "docker", "system design", "python", "redis", "spring webflux",
}

_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in SKILLS.items()}


def extract_skills(text: str) -> list[str]:
    return sorted(name for name, rx in _COMPILED.items() if rx.search(text or ""))
