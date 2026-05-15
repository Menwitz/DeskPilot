import os

import pytest

from desktop_agent.site_playbooks import load_site_playbooks, resolve_site_flow

SMOKE_FLOWS = {
    "linkedin": "open-search",
    "x-twitter": "open-search",
    "instagram": "open-search",
    "facebook": "open-search",
    "medium": "open-editor",
    "youtube": "open-search",
    "tiktok": "open-search",
}


@pytest.mark.live_site_smoke
@pytest.mark.skipif(
    os.environ.get("DESKPILOT_LIVE_SITE_SMOKE") != "1",
    reason="set DESKPILOT_LIVE_SITE_SMOKE=1 for authorized live-site smoke checks",
)
def test_live_site_smoke_tests_require_explicit_environment_flag() -> None:
    assert os.environ["DESKPILOT_LIVE_SITE_SMOKE"] == "1"


def test_live_site_smoke_flows_never_run_final_actions_by_default() -> None:
    for site_id, flow_id in SMOKE_FLOWS.items():
        _assert_read_only_smoke_flow(site_id, flow_id)


def test_each_seed_site_has_one_read_only_smoke_flow() -> None:
    playbooks = {playbook.site_id: playbook for playbook in load_site_playbooks()}

    assert set(playbooks) == set(SMOKE_FLOWS)
    for site_id, flow_id in SMOKE_FLOWS.items():
        flow = resolve_site_flow(playbooks[site_id], flow_id)
        assert flow.steps


@pytest.mark.parametrize(
    ("site_id", "flow_id"),
    tuple(SMOKE_FLOWS.items()),
    ids=tuple(SMOKE_FLOWS),
)
def test_seed_site_read_only_smoke_flow(site_id: str, flow_id: str) -> None:
    _assert_read_only_smoke_flow(site_id, flow_id)


def _assert_read_only_smoke_flow(site_id: str, flow_id: str) -> None:
    playbooks = {playbook.site_id: playbook for playbook in load_site_playbooks()}
    flow = resolve_site_flow(playbooks[site_id], flow_id)

    # Live smoke flows may navigate public sites, but they must never mutate state.
    assert flow.steps
    for step in flow.steps:
        assert step.requires_confirmation is False
        assert step.sensitive_category is None
