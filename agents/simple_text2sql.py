import os

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, List, TypedDict

from agents.prompts import QA_SYSTEM_PROMPT, SQL_SYSTEM_PROMPT
from agents.utils import (
    SQLDatabase,
    get_detailed_table_info,
    get_engine_for_chinook_db,
)

# Not override=True: real environment variables must win over a local .env.
# Otherwise a stale .env silently overrides credentials that CI or a deployment
# set deliberately, which is confusing to debug.
load_dotenv()

#: Default model per route. Gateway IDs are provider-qualified; direct ones are not.
DEFAULT_MODELS = {
    "gateway": "anthropic/claude-haiku-4-5-20251001",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}


def resolve_llm_route() -> str:
    """Decide how to reach a model, honouring an explicit ``LLM_PROVIDER``.

    Otherwise pick the first route that is actually configured, preferring the
    gateway because it needs no provider key at all.
    """
    explicit = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if explicit:
        if explicit not in DEFAULT_MODELS:
            raise ValueError(
                f"LLM_PROVIDER={explicit!r} is not supported; expected one of "
                f"{', '.join(sorted(DEFAULT_MODELS))}."
            )
        return explicit
    if os.environ.get("LLM_GATEWAY_BASE_URL"):
        return "gateway"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"


def build_llm():
    """Build the chat model, supporting three ways to reach a provider.

    ``gateway``
        Route through the `LangSmith LLM Gateway
        <https://docs.langchain.com/langsmith/llm-gateway-api-formats>`_, which is
        OpenAI-compatible and authenticates with a LangSmith API key. No provider
        key is needed, which is the only workable setup where developers are not
        issued them. Model IDs are provider-qualified, e.g.
        ``anthropic/claude-sonnet-4-6``. LangSmith Cloud injects
        ``LANGSMITH_API_KEY`` into deployments automatically.

    ``anthropic``
        Call Anthropic directly with ``ANTHROPIC_API_KEY``.

    ``openai``
        Call OpenAI directly with ``OPENAI_API_KEY`` -- the original behaviour.

    Set ``LLM_PROVIDER`` to force a route, or ``LLM_MODEL`` to override the model.
    """
    route = resolve_llm_route()
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS[route]

    if route == "gateway":
        api_key = os.environ.get("LANGSMITH_API_KEY")
        if not api_key:
            raise ValueError(
                "The LLM gateway authenticates with LANGSMITH_API_KEY, but that "
                "variable is empty. LangSmith Cloud sets it for you; elsewhere, "
                "set it yourself."
            )
        return ChatOpenAI(
            model=model,
            base_url=os.environ.get(
                "LLM_GATEWAY_BASE_URL", "https://gateway.smith.langchain.com/v1"
            ),
            api_key=api_key,
            temperature=0,
        )

    if route == "anthropic":
        # Imported lazily so the OpenAI-only path needs no Anthropic install.
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)

    return ChatOpenAI(model=model, temperature=0)


class OverallState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    schema: str
    sql: str
    records: List[dict]


class InputState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


class OutputState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def generate_sql(llm):
    def _generate(state: OverallState) -> dict:
        last_message = state["messages"][-1]
        prompt = f"""Generate a SQL query for the following question:
        Question: {last_message.content}
        Schema: {get_detailed_table_info()}
        SQL:
        """
        sql_query = llm.invoke(
            [SystemMessage(SQL_SYSTEM_PROMPT)]
            + state["messages"]
            + [HumanMessage(prompt)]
        )
        sql_query = sql_query.content.replace("```sql", "").replace("```", "")
        return {"sql": sql_query}

    return _generate


def execute_sql(db):
    def _execute(state: OverallState) -> dict:
        records = db.run(state["sql"])
        return {"records": records}

    return _execute


def generate_answer(llm):
    def _answer(state: OverallState) -> dict:
        last_message = state["messages"][-1]
        prompt = f"Given the question: {last_message.content} and the database results: {state['records']}, provide a concise answer."
        answer = llm.invoke(
            [SystemMessage(QA_SYSTEM_PROMPT)]
            + state["messages"]
            + [HumanMessage(prompt)]
        )
        return {"messages": [answer]}

    return _answer


def create_agent(llm, db):
    builder = StateGraph(
        OverallState, input_schema=InputState, output_schema=OutputState
    )
    builder.add_node("generate_sql", generate_sql(llm))
    builder.add_node("execute_sql", execute_sql(db))
    builder.add_node("generate_answer", generate_answer(llm))
    builder.add_edge(START, "generate_sql")
    builder.add_edge("generate_sql", "execute_sql")
    builder.add_edge("execute_sql", "generate_answer")
    builder.add_edge("generate_answer", END)
    return builder.compile()


llm = build_llm()
# Pass the factory, not an engine: the Agent Server imports this module
# during startup, and a network call there would block the deployment.
db = SQLDatabase(get_engine_for_chinook_db)
agent = create_agent(llm, db)
