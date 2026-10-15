"""Vector-only baseline for demo beat 1: neo4j-graphrag GraphRAG over the policy chunks.

Stands in for the Orchestrate knowledge-base agent until Phase 5. It sees only the
policy text, not the customer's accounts or transactions.
"""

import argparse

import neo4j
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.retrievers import VectorRetriever
from neo4j_graphrag.types import RetrieverResultItem

from graphrag_banking.config import get_driver, load_settings
from graphrag_banking.eval_local import load_scenarios
from graphrag_banking.models import SharedEmbedder
from graphrag_banking.tools import VECTOR_INDEX_NAME

TOP_K = 5


def chunk_text(record: neo4j.Record) -> RetrieverResultItem:
    return RetrieverResultItem(
        content=record["node"]["text"], metadata={"score": record["score"]}
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question", nargs="?", help="question to ask; runs the hero prompts if omitted"
    )
    args = parser.parse_args()

    if args.question:
        questions = [("Question", args.question)]
    else:
        questions = [
            (f"Scenario {s['id']}", s["prompt"])
            for s in load_scenarios()
            if not s.get("adversarial")
        ]

    settings = load_settings()
    with get_driver(settings) as driver:
        retriever = VectorRetriever(
            driver,
            index_name=VECTOR_INDEX_NAME,
            embedder=SharedEmbedder(settings.embedding_config),
            return_properties=["text"],
            result_formatter=chunk_text,
            neo4j_database=settings.neo4j_database,
        )
        llm = OpenAILLM(
            model_name=settings.chat_model,
            api_key=settings.openai_api_key,
        )
        rag = GraphRAG(retriever=retriever, llm=llm)
        for label, question in questions:
            result = rag.search(
                query_text=question,
                retriever_config={"top_k": TOP_K},
                return_context=True,
            )
            print(f"{label}: {question}\n")
            print(f"{result.answer}\n")
            print("Retrieved chunks:")
            for item in result.retriever_result.items:
                first_line = item.content.splitlines()[0]
                print(f"  {item.metadata['score']:.4f}  {first_line[:100]}")
            print()


if __name__ == "__main__":
    main()
