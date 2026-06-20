
from typing import List, Optional, Dict, Any
from ..schemas import ProposalMetadataSchema, ScoredProposals
from pydantic import BaseModel
    
def get_n_matching_proposals(user_input: Dict[str, Any], proposals: List[ProposalMetadataSchema], N: int = 2) -> List[ScoredProposals]:
    weights = {
        "solution": 5,
        "business_offering": 4,
        "commercial_use_case": 4,
        "project_type": 3,
        "existing_infra": 2,
        "business_model": 1,
        "region": 1,
    }

    def calc_partial_score(user_vals: List[str], prop_vals: Optional[List[str]], weight: int) -> float:
        if not user_vals or not prop_vals:
            return 0.0
        matches = [val for val in user_vals if val in prop_vals]
        return (len(matches) / len(user_vals)) * weight

    scored_proposals:List[ScoredProposals] = []

    for proposal in proposals:
        score = 0
        props = proposal.properties
        if not props:
            continue

        score += calc_partial_score(user_input.get("solution", []), props.solution, weights["solution"])
        score += calc_partial_score(user_input.get("business_offering", []), props.business_offering, weights["business_offering"])
        score += calc_partial_score(user_input.get("commercial_use_case", []), props.commercial_use_case, weights["commercial_use_case"])
        score += calc_partial_score(user_input.get("project_type", []), props.project_type, weights["project_type"])
        score += calc_partial_score(user_input.get("business_model", []), props.business_model, weights["business_model"])

        # Exact match for radio-type inputs
        if user_input.get("existing_infra") and user_input["existing_infra"][0] in (props.existing_infra or []):
            score += weights["existing_infra"]

        if user_input.get("region") and user_input["region"][0] in (props.region or []):
            score += weights["region"]

        scored_proposals.append(ScoredProposals(
            proposal=proposal,
            score=score
        ))

    # Sort proposals by score descending
    scored_proposals.sort(key=lambda x: x.score, reverse=True)

    # Return top N (with ties)
    top_n: List[ScoredProposals] = []
    last_score = None
    for item in scored_proposals:
        if len(top_n) < N or item.score == last_score:
            top_n.append(item)
            last_score = item.score
        else:
            break

    return top_n
