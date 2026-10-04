"""From an endpoint to the adapter that speaks its API."""

from __future__ import annotations

import httpx2

from app.domain.llm import Model
from app.providers.anthropic import AnthropicModel
from app.providers.endpoint import Endpoint
from app.providers.openai_compatible import ChatCompletionsModel
from app.providers.openai_responses import ResponsesModel


def model_for(endpoint: Endpoint, http: httpx2.AsyncClient) -> Model:
    if endpoint.adapter == "anthropic":
        return AnthropicModel(endpoint, http)

    if endpoint.adapter == "openai_responses":
        return ResponsesModel(endpoint, http)

    return ChatCompletionsModel(endpoint, http)
