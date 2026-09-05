"""The decision agent. Fully mocked - no network call belongs in a test suite
that runs on every commit and costs real tokens.
"""
from types import SimpleNamespace

import pytest

from agent import decide, gates


def contract(symbol, delta=0.45, bid=1.60, ask=1.63):
    return gates.parse_chain({"snapshots": {symbol: {
        "greeks": {"delta": delta}, "impliedVolatility": 0.10,
        "latestQuote": {"bp": bid, "ap": ask},
        "dailyBar": {"v": 1200}, "prevDailyBar": {"v": 5180},
    }}})[0]


CANDIDATE = SimpleNamespace(symbol="SPY", direction="call", price=765.55,
                            move_adr=0.69, rvol=2.21, ema=763.0)
PORTFOLIO = {"equity": 100_000, "open_positions": 1, "deployed": 3_200}
TODAY = "2026-08-24"


def tool_use_response(input_dict, stop_reason="tool_use"):
    block = SimpleNamespace(type="tool_use", input=input_dict)
    return SimpleNamespace(stop_reason=stop_reason, content=[block])


class FakeClient:
    def __init__(self, response):
        self.response, self.calls = response, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


# --- tool schema -------------------------------------------------------------

def test_tool_constrains_symbol_to_the_provided_contracts():
    tool = decide.build_decision_tool(["SPY260904C00765000", "SPY260904C00770000"])
    assert tool["strict"] is True
    props = tool["input_schema"]["properties"]
    assert set(props["symbol"]["enum"]) == {
        "SPY260904C00765000", "SPY260904C00770000", "none"}
    assert tool["input_schema"]["additionalProperties"] is False


# --- parsing -----------------------------------------------------------------

def test_parse_decision_enter_resolves_the_matching_contract():
    c = contract("SPY260904C00765000")
    d = decide.parse_decision(
        {"action": "enter", "symbol": c.symbol, "confidence": 0.7, "thesis": "x"},
        {c.symbol: c})
    assert d.action == "enter" and d.contract is c and d.confidence == 0.7


def test_parse_decision_skip_ignores_whatever_symbol_is_present():
    d = decide.parse_decision(
        {"action": "skip", "symbol": "none", "confidence": 0.2, "thesis": "no edge"},
        {})
    assert d.action == "skip" and d.contract is None


def test_parse_decision_fails_closed_on_an_unrecognised_symbol():
    # Should be unreachable under a strict enum, but a decision that resolves
    # to nothing tradeable must skip, never crash or trade blind.
    d = decide.parse_decision(
        {"action": "enter", "symbol": "MADE_UP", "confidence": 0.9, "thesis": "x"},
        {})
    assert d.action == "skip" and d.contract is None


# --- decide() ------------------------------------------------------------

def test_decide_skips_without_calling_the_model_when_no_contracts_are_viable():
    client = FakeClient(tool_use_response({}))
    d = decide.decide(client, CANDIDATE, [], PORTFOLIO, TODAY)
    assert d.action == "skip" and client.calls == []


def test_decide_forces_the_decision_tool_and_names_it():
    c = contract("SPY260904C00765000")
    client = FakeClient(tool_use_response(
        {"action": "skip", "symbol": "none", "confidence": 0.1, "thesis": "x"}))
    decide.decide(client, CANDIDATE, [c], PORTFOLIO, TODAY)

    kwargs = client.calls[0]
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_decision"}
    assert kwargs["tools"][0]["name"] == "submit_decision"


def test_decide_returns_an_enter_decision():
    c = contract("SPY260904C00765000")
    client = FakeClient(tool_use_response(
        {"action": "enter", "symbol": c.symbol, "confidence": 0.8, "thesis": "strong"}))
    d = decide.decide(client, CANDIDATE, [c], PORTFOLIO, TODAY)
    assert d.action == "enter" and d.contract.symbol == c.symbol


def test_decide_treats_a_refusal_as_skip():
    client = FakeClient(tool_use_response({}, stop_reason="refusal"))
    d = decide.decide(client, CANDIDATE, [contract("SPY260904C00765000")],
                      PORTFOLIO, TODAY)
    assert d.action == "skip"


def test_decide_treats_a_missing_tool_call_as_skip():
    response = SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text="hm")])
    client = FakeClient(response)
    d = decide.decide(client, CANDIDATE, [contract("SPY260904C00765000")],
                      PORTFOLIO, TODAY)
    assert d.action == "skip"


def test_decide_prompt_lists_every_contract_by_symbol():
    contracts = [contract("SPY260904C00765000"), contract("SPY260904C00770000")]
    client = FakeClient(tool_use_response(
        {"action": "skip", "symbol": "none", "confidence": 0.1, "thesis": "x"}))
    decide.decide(client, CANDIDATE, contracts, PORTFOLIO, TODAY)

    prompt = client.calls[0]["messages"][0]["content"]
    assert "SPY260904C00765000" in prompt and "SPY260904C00770000" in prompt


def test_decide_uses_sonnet_5_by_default():
    client = FakeClient(tool_use_response(
        {"action": "skip", "symbol": "none", "confidence": 0.1, "thesis": "x"}))
    decide.decide(client, CANDIDATE, [contract("SPY260904C00765000")],
                  PORTFOLIO, TODAY)
    assert client.calls[0]["model"] == "claude-sonnet-5"


def test_tool_schema_avoids_number_bounds_the_strict_api_rejects():
    # Live: 'tools.0.custom: For "number" type, properties maximum, minimum
    # are not supported'. Pin the fix so it cannot regress.
    tool = decide.build_decision_tool(["SPY260904C00765000"])
    conf = tool["input_schema"]["properties"]["confidence"]
    assert "minimum" not in conf and "maximum" not in conf
