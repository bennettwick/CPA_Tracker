import json
import os

ACCOUNTING_CATEGORIES = {
    "financial_accounting", "management_accounting", "governmental_nonprofit",
    "taxation", "auditing", "accounting_information_systems",
    "accounting_elective", "upper_division_accounting",
}
BUSINESS_CATEGORIES = {
    "general_business", "business_law", "ethics",
}

GRADE_ORDER = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F": 0.0,
}


def load_state_requirements(state: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "state_requirements.json")
    with open(path, "r") as f:
        data = json.load(f)
    key = state.lower()
    if key not in data:
        raise ValueError(f"State '{state}' not found in requirements file.")
    return data[key]


def grade_value(grade: str) -> float:
    if not grade:
        return -1.0
    return GRADE_ORDER.get(grade.strip().upper(), -1.0)


def _deduplicate_courses(courses: list) -> list:
    seen = {}   # name -> index in result
    result = []
    for c in courses:
        name = (c.get("name") or "").strip().lower()
        this_val = grade_value(c.get("grade", ""))
        if name not in seen:
            seen[name] = len(result)
            result.append(c)
        else:
            existing_idx = seen[name]
            existing_val = grade_value(result[existing_idx].get("grade", ""))
            # Only collapse as a retake when the prior attempt was a failing grade (D+ or below)
            if this_val > existing_val and 0.0 <= existing_val <= 1.3:
                result[existing_idx] = c
            else:
                # Separate enrollment in a repeatable course — preserve both
                seen[name] = len(result)
                result.append(c)
    return result


def _detect_level_track(courses: list) -> str:
    """Return 'grad' if majority of accounting/business courses are grad, else 'undergrad'."""
    grad = sum(1 for c in courses if c.get("level") == "grad")
    total = len(courses)
    if total == 0:
        return "undergrad"
    return "grad" if grad / total > 0.5 else "undergrad"


def check_topic_requirements(courses: list, state_req: dict) -> list:
    results = []

    sections = []
    elig = state_req["exam_eligibility"]
    if "accounting" in elig and "required_topics" in elig["accounting"]:
        sections.append((elig["accounting"], elig["accounting"]["required_topics"]))
    if "business" in elig and "required_topics" in elig.get("business", {}):
        sections.append((elig["business"], elig["business"]["required_topics"]))

    track = _detect_level_track(courses)

    for section_def, topics in sections:
        upper_only = section_def.get("upper_level_only", False)
        for topic_key, topic_def in topics.items():
            matching = [c for c in courses if c.get("cpa_category") == topic_key]
            if upper_only:
                matching = [c for c in matching if c.get("is_upper_level") is not False]
            earned = sum(float(c.get("credits") or 0) for c in matching)

            # Louisiana financial_accounting has different credits by level
            grad_credits_req = topic_def.get("graduate_credits_required")
            if grad_credits_req is not None and track == "grad":
                required = float(grad_credits_req)
            else:
                required = float(topic_def.get("credits_required", 0))

            results.append({
                "topic": topic_key,
                "required_credits": required,
                "earned_credits": round(earned, 1),
                "met": earned >= required,
                "courses": [c.get("name") for c in matching],
            })

    return results


def check_hour_totals(courses: list, state_req: dict) -> dict:
    result = {}
    elig = state_req["exam_eligibility"]

    for section_name in ("accounting", "business"):
        section = elig.get(section_name)
        if not section:
            continue

        req_ug = float(section.get("undergraduate_hours_required", 0))
        req_grad = float(section.get("graduate_hours_required", req_ug))
        combo_allowed = section.get("combination_allowed", True)
        upper_only = section.get("upper_level_only", False)

        if section_name == "accounting":
            relevant_cats = ACCOUNTING_CATEGORIES
        else:
            relevant_cats = BUSINESS_CATEGORIES

        relevant = [c for c in courses if c.get("cpa_category") in relevant_cats]
        if upper_only:
            relevant = [c for c in relevant if c.get("is_upper_level") is not False]

        # Cap each required topic's contribution at its minimum credits_required.
        # This prevents extra courses in one topic from inflating the total beyond
        # what that topic can legitimately contribute toward the hours requirement.
        track = _detect_level_track(relevant)
        topic_caps: dict[str, float] = {}
        for topic_key, topic_def in section.get("required_topics", {}).items():
            grad_cap = topic_def.get("graduate_credits_required")
            if grad_cap is not None and track == "grad":
                topic_caps[topic_key] = float(grad_cap)
            else:
                topic_caps[topic_key] = float(topic_def.get("credits_required", 0))

        topic_tally: dict[str, float] = {}
        earned_ug = 0.0
        earned_grad = 0.0
        for c in relevant:
            cat = c.get("cpa_category")
            credits = float(c.get("credits") or 0)
            if cat in topic_caps:
                tally = topic_tally.get(cat, 0.0)
                countable = min(credits, max(0.0, topic_caps[cat] - tally))
                topic_tally[cat] = tally + credits
            else:
                countable = credits
            if c.get("level") == "grad":
                earned_grad += countable
            else:
                earned_ug += countable

        earned_total = earned_ug + earned_grad

        if combo_allowed:
            met = earned_total >= req_ug or earned_grad >= req_grad
            shortfall = None
            if not met:
                if req_grad and earned_grad > 0:
                    shortfall = f"Need {req_grad - earned_grad:.0f} more grad OR {req_ug - earned_total:.0f} more total {section_name} hours"
                else:
                    shortfall = f"Need {req_ug - earned_total:.0f} more {section_name} hours"
        else:
            ug_met = earned_ug >= req_ug
            grad_met = req_grad > 0 and earned_grad >= req_grad
            met = ug_met or grad_met
            shortfall = None
            if not met:
                ug_short = req_ug - earned_ug
                grad_short = req_grad - earned_grad if req_grad else None
                if grad_short is not None:
                    shortfall = (
                        f"Undergrad track: need {ug_short:.0f} more hours. "
                        f"Grad track: need {grad_short:.0f} more hours. "
                        f"Cannot mix undergrad and grad credits."
                    )
                else:
                    shortfall = f"Need {ug_short:.0f} more undergrad {section_name} hours."

        result[section_name] = {
            "required_undergrad": req_ug,
            "required_grad": req_grad,
            "combination_allowed": combo_allowed,
            "earned_undergrad": round(earned_ug, 1),
            "earned_grad": round(earned_grad, 1),
            "earned_total": round(earned_total, 1),
            "met": met,
            "shortfall_message": shortfall,
        }

    return result


def check_degree_conferred(
    courses: list, state_req: dict, graduation_status: str,
    topic_results: list, hour_totals: dict,
) -> dict:
    if not state_req["exam_eligibility"].get("degree_required"):
        return None

    if graduation_status == "conferred":
        return {
            "assumed_conferred": True,
            "confidence": "detected",
            "note": "Your transcript indicates a degree has been awarded.",
        }
    if graduation_status == "in_progress":
        return {
            "assumed_conferred": False,
            "confidence": "detected",
            "note": "Your transcript shows the degree is still in progress.",
        }

    # Infer from credit count and requirement completion
    total_earned = sum(float(c.get("credits") or 0) for c in courses)
    if total_earned < 120:
        return {
            "assumed_conferred": False,
            "confidence": "inferred",
            "note": (
                f"Graduation status unclear on transcript. "
                f"Only {round(total_earned):.0f} total credits found — assumed not yet conferred."
            ),
        }

    all_topics_met = all(t["met"] for t in topic_results)
    all_hours_met = all(v["met"] for v in hour_totals.values())
    if all_topics_met and all_hours_met:
        return {
            "assumed_conferred": True,
            "confidence": "inferred",
            "note": (
                "Graduation status unclear on transcript. "
                "Assumed conferred — 120+ credits and all required coursework appear met."
            ),
        }

    return {
        "assumed_conferred": False,
        "confidence": "inferred",
        "note": (
            "Graduation status unclear on transcript. "
            "Assumed not yet conferred — required coursework not fully met."
        ),
    }


def check_grade_thresholds(courses: list, state_req: dict) -> list:
    elig = state_req["exam_eligibility"]
    min_grade_str = elig.get("accounting", {}).get("min_grade")
    if not min_grade_str:
        return []

    min_val = grade_value(min_grade_str)
    accounting_topics = set(elig.get("accounting", {}).get("required_topics", {}).keys())
    business_topics = set(elig.get("business", {}).get("required_topics", {}).keys())
    required_topics = accounting_topics | business_topics

    flags = []
    for c in courses:
        if c.get("cpa_category") not in required_topics:
            continue
        g = c.get("grade")
        val = grade_value(g)
        if val == -1.0:
            continue
        if val < min_val:
            flags.append({
                "name": c.get("name"),
                "grade": g,
                "min_required": min_grade_str,
                "topic": c.get("cpa_category"),
            })
    return flags


def collect_manual_checks(state_req: dict) -> list:
    checks = []
    elig = state_req["exam_eligibility"]
    if elig.get("min_age"):
        checks.append(f"You must be at least {elig['min_age']} years old.")
    if elig.get("residency_days_required"):
        checks.append(
            f"You must have been a Louisiana resident for at least "
            f"{elig['residency_days_required']} days before applying."
        )
    return checks


def collect_unclear_courses(courses: list) -> list:
    return [c for c in courses if c.get("cpa_category") == "unclear"]


def check_requirements(courses: list, state: str, graduation_status: str = "unknown") -> dict:
    state_req = load_state_requirements(state)
    courses = _deduplicate_courses(courses)

    topic_results = check_topic_requirements(courses, state_req)
    hour_totals = check_hour_totals(courses, state_req)
    grade_flags = check_grade_thresholds(courses, state_req)
    unclear = collect_unclear_courses(courses)
    manual_checks = collect_manual_checks(state_req)
    degree_info = check_degree_conferred(courses, state_req, graduation_status, topic_results, hour_totals)

    has_unclear = len(unclear) > 0
    all_topics_met = all(t["met"] for t in topic_results)
    all_hours_met = all(v["met"] for v in hour_totals.values())
    no_grade_flags = len(grade_flags) == 0
    degree_ok = degree_info is None or degree_info["assumed_conferred"]

    if degree_ok and all_topics_met and all_hours_met and no_grade_flags and not has_unclear:
        summary = "eligible"
    elif has_unclear or grade_flags or (degree_info and not degree_info["assumed_conferred"] and degree_info["confidence"] == "inferred"):
        summary = "needs_review"
    else:
        summary = "not_eligible"

    has_null_level = any(c.get("level") is None for c in courses)

    return {
        "state": state_req["state"],
        "summary": summary,
        "topic_results": topic_results,
        "hour_totals": hour_totals,
        "grade_flags": grade_flags,
        "unclear_courses": unclear,
        "manual_checks": manual_checks,
        "degree_info": degree_info,
        "level_detection_warning": has_null_level and state.lower() == "louisiana",
    }
