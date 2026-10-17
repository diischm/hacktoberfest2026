"""
Route comparison API: E8 scenarios, E9 compare. The scoring lives in routes/scoring.py.

Errors are raised as exceptions and turned into the contract shape by config/exceptions.py.
"""

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from reports.views import PublicReadView
from routes.scoring import compare, get_scenario, list_scenarios


class ScenarioListView(PublicReadView):
    """E8: demo origin/destination pairs."""

    def get(self, request):
        return Response(list_scenarios())


class CompareView(PublicReadView):
    """E9: the scenario's route alternatives, scored against the current reports."""

    def get(self, request):
        scenario_id = request.query_params.get("scenario", "").strip()
        if not scenario_id:
            raise ValidationError({"scenario": ["This field is required."]})
        scenario = get_scenario(scenario_id)
        if scenario is None:
            raise NotFound()
        return Response(compare(scenario))
