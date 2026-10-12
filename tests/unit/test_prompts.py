from geoagent.agent.prompts import SYSTEM_PROMPT, system_prompt


def test_default_prompt_is_the_full_prompt():
    assert system_prompt() is SYSTEM_PROMPT
    assert "isochrones" in system_prompt(True)


def test_mining_only_prompt_does_not_promise_routing():
    prompt = system_prompt(routing_enabled=False)
    assert "tenement" in prompt.lower() and "MINEDEX" in prompt
    assert "shortest_route" not in prompt
    # It keeps the guidance about the two unlinked datasets and about tool errors.
    assert "aren't linked" in prompt
    assert "If a tool returns an error" in prompt
    # And it must not carry the routing-specific paragraphs.
    assert "Bare street names" not in prompt
    assert "Map saved" not in prompt and "interactive map was saved" not in prompt
