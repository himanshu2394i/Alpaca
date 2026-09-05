"""The LLM decision layer.

decide() takes the screener's candidate and the contracts that already passed
every deterministic gate, and returns enter-or-skip with a reason. It cannot
invent a symbol: the tool schema constrains `symbol` to an enum built from the
exact contracts it was handed, plus the literal "none" for skip. That is a
structural gate, not a prompt instruction - the API rejects a value outside the
enum before this code ever sees it.

Sizing stays out of this module entirely. gates.size_contracts is the only
place a quantity is computed; the model is never asked for one.

This is the swappable seam: a multi-agent debate ensemble can replace decide()
later without touching the screener, gates, or execute - same signature, same
Decision return type.
"""
from dataclasses import dataclass

from agent.gates import Contract

MODEL = "claude-sonnet-5"

SYSTEM = (
    "You are the decision layer of an autonomous options trading agent running "
    "in an Alpaca paper account during a 5-day trading competition. A "
    "deterministic screener has already flagged a momentum candidate, and a "
    "deterministic risk system has already filtered the option chain down to "
    "contracts that meet liquidity, spread, delta and DTE requirements - your "
    "job is not to re-check those, it is to judge whether THIS setup is worth "
    "taking now. You may enter only one of the contracts you are given, by its "
    "exact symbol, or skip. You cannot trade a symbol that is not listed. "
    "Be selective: skipping is free, a bad entry is not. Weigh the strength of "
    "the momentum signal, how far price has already moved, and the quality of "
    "the specific contract (spread, delta, liquidity) before entering."
)


@dataclass(frozen=True)
class Decision:
    action: str                  # "enter" | "skip"
    contract: Contract | None
    confidence: float
    thesis: str


def build_decision_tool(symbols: list[str]) -> dict:
    """Strict tool schema whose `symbol` enum is exactly the given contracts.

    "none" is a real enum member rather than an optional/nullable field: strict
    tool use wants every property in `required`, and an explicit sentinel is
    simpler to reason about than a nullable string.
    """
    return {
        "name": "submit_decision",
        "description": "Decide whether to enter the nominated options candidate.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["enter", "skip"]},
                "symbol": {"type": "string", "enum": [*symbols, "none"]},
                "confidence": {"type": "number",
                              "description": "0.0 to 1.0"},
                "thesis": {"type": "string", "description": "One or two sentences."},
            },
            "required": ["action", "symbol", "confidence", "thesis"],
            "additionalProperties": False,
        },
    }


def parse_decision(tool_input: dict, contracts_by_symbol: dict[str, Contract]) -> Decision:
    """Map the model's tool call onto a Decision.

    A symbol the enum should have prevented is treated as skip, not an error:
    the failure mode of a decision layer must be "do nothing", never "trade
    something unverified".
    """
    confidence = float(tool_input.get("confidence", 0.0))
    thesis = str(tool_input.get("thesis", ""))

    if tool_input.get("action") != "enter":
        return Decision("skip", None, confidence, thesis)

    contract = contracts_by_symbol.get(tool_input.get("symbol"))
    if contract is None:
        return Decision("skip", None, confidence,
                        f"model referenced an unrecognised symbol; skipping ({thesis})")

    return Decision("enter", contract, confidence, thesis)


def _describe(c: Contract, today: str) -> str:
    return (f"- {c.symbol}: strike {c.strike:.1f}, {c.dte(today)} DTE, "
           f"bid/ask {c.bid:.2f}/{c.ask:.2f} (spread {c.spread_pct:.1%}), "
           f"delta {c.delta:.2f}, IV {c.iv:.2f}, prior-day volume {c.prev_volume}")


def _prompt(candidate, contracts: list[Contract], portfolio: dict, today: str) -> str:
    listed = "\n".join(_describe(c, today) for c in contracts)
    return (
        f"Screener candidate: {candidate.symbol} {candidate.direction}\n"
        f"  underlying price {candidate.price:.2f}, moved {candidate.move_adr:+.2f} "
        f"average daily ranges from today's open, RVOL {candidate.rvol:.2f}\n\n"
        f"Contracts that already passed liquidity, DTE, spread and delta gates "
        f"(enter exactly one of these, or skip):\n{listed}\n\n"
        f"Portfolio: equity ${portfolio['equity']:,.0f}, "
        f"{portfolio['open_positions']} open position(s), "
        f"${portfolio['deployed']:,.0f} deployed in options.\n\n"
        f"Decide."
    )


def decide(client, candidate, contracts: list[Contract], portfolio: dict,
          today: str, model: str = MODEL) -> Decision:
    """One decision. `client` is an anthropic client, injected for testability."""
    if not contracts:
        return Decision("skip", None, 0.0, "no viable contracts to choose from")

    by_symbol = {c.symbol: c for c in contracts}
    tool = build_decision_tool(list(by_symbol))

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_decision"},
        messages=[{"role": "user", "content": _prompt(candidate, contracts, portfolio, today)}],
    )

    if response.stop_reason == "refusal":
        return Decision("skip", None, 0.0, "model declined to respond")

    block = next((b for b in response.content if b.type == "tool_use"), None)
    if block is None:
        return Decision("skip", None, 0.0, "model did not return a decision")

    return parse_decision(block.input, by_symbol)


def make_client():
    """Real Anthropic client, reading ANTHROPIC_API_KEY from the environment."""
    import anthropic

    return anthropic.Anthropic()
