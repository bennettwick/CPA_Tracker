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
    """Keep only the highest-grade instance of each course name."""
    seen = {}
    for c in courses:
        name = c.get("name", "").strip().lower()
        if name not in seen:
            seen[name] = c
        else:
            existing_val = grade_value(seen[name].get("grade", ""))
            this_val = grade_value(c.get("grade", ""))
            if this_val > existing_val:
                seen[name] = c
    return list(seen.values())


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
    if "accounting" in state_req["exam_eligibility"] and "required_topics" in state_req["exam_eligibility"]["accounting"]:
        sections.append(state_req["exam_eligibility"]["accounting"]["required_topics"])
    if "business" in state_req["exam_eligibility"] and "required_topics" in state_req["exam_eligibility"].get("business", {}):
        sections.append(state_req["exam_eligibility"]["business"]["required_topics"])

    track = _detect_level_track(courses)

    for topics in sections:
        for topic_key, topic_def in topics.items():
            matching = [c for c in courses if c.get("cpa_category") == topic_key]
            earned = sum(float(c.get("credits", 0)) for c in matching)

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

        if section_name == "accounting":
            relevant_cats = ACCOUNTING_CATEGORIES
        else:
            relevant_cats = BUSINESS_CATEGORIES

        relevant = [c for c in courses if c.get("cpa_category") in relevant_cats]
        earned_ug = sum(float(c.get("credits", 0)) for c in relevant if c.get("level") != "grad")
        earned_grad = sum(float(c.get("credits", 0)) for c in relevant if c.get("level") == "grad")
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


def check_requirements(courses: list, state: str) -> dict:
    state_req = load_state_requirements(state)
    courses = _deduplicate_courses(courses)

    topic_results = check_topic_requirements(courses, state_req)
    hour_totals = check_hour_totals(courses, state_req)
    grade_flags = check_grade_thresholds(courses, state_req)
    unclear = collect_unclear_courses(courses)
    manual_checks = collect_manual_checks(state_req)

    has_unclear = len(unclear) > 0
    all_topics_met = all(t["met"] for t in topic_results)
    all_hours_met = all(v["met"] for v in hour_totals.values())
    no_grade_flags = len(grade_flags) == 0

    if all_topics_met and all_hours_met and no_grade_flags and not has_unclear:
        summary = "eligible"
    elif has_unclear or grade_flags:
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
        "level_detection_warning": has_null_level and state.lower() == "louisiana",
    }
