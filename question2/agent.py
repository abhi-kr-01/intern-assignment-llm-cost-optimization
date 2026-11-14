
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from shared.billing import CostSession
from shared.kb import article_ids, load_article
from shared.llm import ChatMessage, LlmClient
from shared.tools import format_thread, get_order, get_ticket

from question1.agent import parse_resolution


@dataclass
class TicketResolution:
    action: str
    kb_article: str


STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "was", "were",
    "are", "you", "your", "have", "has", "had", "from", "but",
    "not", "what", "when", "where", "which", "would", "could",
    "should", "please", "hello", "hi", "thanks", "thank",
    "order", "customer", "item", "product", "ticket"
}

ALLOWED_ACTIONS = {
    "REFUND",
    "REPLACE",
    "SEND_ARTICLE",
    "ESCALATE_TIER2",
}


def terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [
        word for word in words
        if len(word) > 2 and word not in STOP_WORDS
    ]


def flatten_values(value) -> str:
    if isinstance(value, dict):
        return " ".join(flatten_values(v) for v in value.values())

    if isinstance(value, list):
        return " ".join(flatten_values(v) for v in value)

    return str(value) if isinstance(value, (str, int, float)) else ""


class SupportPipeline:
    """Cost-optimized four-stage ShopAssist pipeline."""

    def __init__(self, session: CostSession | None = None):
        self.session = session or CostSession()
        self.llm = LlmClient(self.session)

    def handle_ticket(self, ticket_id: str) -> TicketResolution:
        ticket = get_ticket(ticket_id)
        order = get_order(ticket["order_id"])

        thread = format_thread(ticket)
        snapshot = json.dumps(order, separators=(",", ":"))

        # Stage 1: Deterministic triage
        triage = self._triage(ticket_id, thread, snapshot)

        # Stage 2: Deterministic KB retrieval
        retrieved = self._retrieve(triage)

        # Stage 3: One concise LLM call
        draft = self._compose(
            ticket_id, thread, snapshot, triage, retrieved
        )

        # Stage 4: Deterministic audit
        final = self._audit(draft)

        parsed = parse_resolution(final)

        return TicketResolution(
            parsed.action,
            parsed.kb_article
        )

    def _triage(
        self,
        ticket_id: str,
        thread: str,
        snapshot: str
    ) -> str:
        order = json.loads(snapshot)

        combined = thread + " " + flatten_values(order)
        keywords = list(dict.fromkeys(terms(combined)))

        text = combined.lower()

        intents = []

        if any(x in text for x in ("refund", "return", "money back")):
            intents.append("refund")

        if any(x in text for x in ("replace", "replacement")):
            intents.append("replacement")

        if any(x in text for x in ("damage", "damaged", "broken", "cracked")):
            intents.append("damage")

        if any(x in text for x in ("digital", "license", "ebook", "download")):
            intents.append("digital")

        if any(x in text for x in ("custom", "customized", "personalized")):
            intents.append("custom")

        return json.dumps({
            "ticket_id": ticket_id,
            "intents": intents,
            "keywords": keywords[:30]
        })

    def _retrieve(self, triage: str) -> str:
        triage_data = json.loads(triage)
        query_words = set(triage_data["keywords"])
        query_words.update(triage_data["intents"])

        scored_articles = []

        for article_id in article_ids():
            content = load_article(article_id)

            id_words = set(terms(article_id.replace("-", " ")))
            content_words = set(terms(content))

            # Article ID matches receive a higher weight.
            score = (
                4 * len(query_words & id_words)
                + len(query_words & content_words)
            )

            scored_articles.append(
                (score, article_id, content)
            )

        # Deterministic ordering, including tie-breaking.
        scored_articles.sort(
            key=lambda item: (-item[0], item[1])
        )

        # Retrieve only the two most relevant articles.
        selected = scored_articles[:2]

        results = [
            {
                "article_id": article_id,
                "content": content[:1200]
            }
            for score, article_id, content in selected
        ]

        return json.dumps(
            {"articles": results},
            separators=(",", ":")
        )

    def _compose(
        self,
        ticket_id: str,
        thread: str,
        snapshot: str,
        triage: str,
        retrieved: str,
    ) -> str:
        messages = [
            ChatMessage(
                "system",
                "You are ShopAssist. Resolve the support ticket using "
                "the order facts and relevant policy articles. "
                "Return only JSON with action, kb_article, customer_reply."
            ),
            ChatMessage(
                "user",
                "\n".join([
                    f"TICKET: {ticket_id}",
                    f"THREAD:\n{thread}",
                    f"ORDER_SNAPSHOT:\n{snapshot}\nEND_SNAPSHOT",
                    f"TRIAGE:\n{triage}",
                    f"RETRIEVED_ARTICLES:\n{retrieved}",
                ])
            )
        ]

        return self.llm.chat("compose", messages)

    def _audit(self, draft: str) -> str:
        data = json.loads(draft)

        action = str(data["action"]).upper()
        kb_article = str(data["kb_article"])

        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Invalid action: {action}")

        if kb_article not in article_ids():
            raise ValueError(f"Unknown KB article: {kb_article}")

        # Return only the validated output fields.
        return json.dumps({
            "action": action,
            "kb_article": kb_article,
            "customer_reply": data.get("customer_reply", "")
        })
