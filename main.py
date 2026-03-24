"""
NARQ — Neurodegenerative Disease Triage Webhook
Dialogflow ES (v2) + CX dual-format webhook for render.com

Ontology source: NeuroTriageOntology.owl (NTO v1.0.0)
  Diseases : Alzheimer's Disease | ALS | Parkinson's Disease
  Relations: hasPrimarySymptom · hasSymptom · hasOverlappingSymptom
             hasRiskFactor · hasProtectiveFactor · hasContradictoryFactor
             moreTypicalOf · belongsToSymptomCategory · belongsToFactorCategory

Competency questions answered:
  CQ1  What are the symptoms of <disease>?
  CQ2  Given my symptoms, what diseases might I have?
  CQ3  How do I differentiate between Alzheimer's / ALS / Parkinson's?
  CQ4  What are the overlapping symptoms between two diseases?
  CQ5  What are the risk factors for <disease>?
  CQ6  What lifestyle factors affect <disease>?
"""

import os
import json
import logging
from flask import Flask, request, jsonify

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


# =============================================================================
# ONTOLOGY  — faithful translation of NeuroTriageOntology.owl
# Each symptom / factor entry carries:
#   "label"    : human-readable display string (from rdfs:label / rdfs:comment)
#   "category" : belongsToSymptomCategory / belongsToFactorCategory
#   "typical"  : moreTypicalOf (symptoms only, omitted when not asserted)
# =============================================================================

# ── Symptom catalogue ────────────────────────────────────────────────────────
SYMPTOMS: dict[str, dict] = {
    # Motor
    "resting_tremor":            {"label": "Resting Tremor",                        "category": "Motor",                  "typical": "parkinsons_disease"},
    "bradykinesia_symptom":      {"label": "Bradykinesia (slowness of movement)",   "category": "Motor",                  "typical": "parkinsons_disease"},
    "rigidity_symptom":          {"label": "Rigidity",                              "category": "Motor",                  "typical": "parkinsons_disease"},
    "postural_instability":      {"label": "Postural Instability",                  "category": "Motor",                  "typical": "parkinsons_disease"},
    "gait_disturbance":          {"label": "Gait Disturbance (shuffling/freezing)", "category": "Motor",                  "typical": "parkinsons_disease"},
    "akinesia_symptom":          {"label": "Akinesia (absence of movement)",        "category": "Motor",                  "typical": "parkinsons_disease"},
    "hypomimia_symptom":         {"label": "Hypomimia (masked face)",               "category": "Motor",                  "typical": "parkinsons_disease"},
    "limb_weakness":             {"label": "Limb Weakness",                         "category": "Motor",                  "typical": "als_disease"},
    "axial_weakness":            {"label": "Axial Weakness (trunk)",                "category": "Motor",                  "typical": "als_disease"},
    "muscle_weakness":           {"label": "Muscle Weakness",                       "category": "Motor",                  "typical": "als_disease"},
    # Speech & Swallowing
    "bulbar_dysfunction":        {"label": "Bulbar Dysfunction",                    "category": "Speech & Swallowing",    "typical": "als_disease"},
    "dysarthria_symptom":        {"label": "Dysarthria (slurred speech)",           "category": "Speech & Swallowing",    "typical": "als_disease"},
    "dysphagia_symptom":         {"label": "Dysphagia (difficulty swallowing)",     "category": "Speech & Swallowing"},
    "hypophonia_symptom":        {"label": "Hypophonia (soft/quiet voice)",         "category": "Speech & Swallowing",    "typical": "parkinsons_disease"},
    "pseudobulbar_affect":       {"label": "Pseudobulbar Affect",                   "category": "Speech & Swallowing",    "typical": "als_disease"},
    # Cognitive
    "episodic_memory_impairment":{"label": "Episodic Memory Impairment",            "category": "Cognitive",              "typical": "alzheimers_disease"},
    "memory_impairment":         {"label": "Memory Impairment",                     "category": "Cognitive",              "typical": "alzheimers_disease"},
    "language_impairment":       {"label": "Language Impairment (aphasia)",         "category": "Cognitive",              "typical": "alzheimers_disease"},
    "impaired_reasoning":        {"label": "Impaired Reasoning / Judgment",         "category": "Cognitive",              "typical": "alzheimers_disease"},
    "cognitive_psychiatric_als": {"label": "Cognitive & Psychiatric Symptoms (ALS subset)", "category": "Cognitive"},
    "confusion_symptom":         {"label": "Confusion / Disorientation",            "category": "Cognitive"},
    # Behavioural / Psychiatric
    "depression_symptom":        {"label": "Depression",                            "category": "Behavioural & Psychiatric"},
    "anxiety_symptom":           {"label": "Anxiety",                               "category": "Behavioural & Psychiatric"},
    "hallucination_symptom":     {"label": "Hallucinations",                        "category": "Behavioural & Psychiatric", "typical": "parkinsons_disease"},
    "neuropsychiatric_dysfunction": {"label": "Neuropsychiatric Dysfunction",       "category": "Behavioural & Psychiatric", "typical": "parkinsons_disease"},
    # Autonomic
    "constipation_symptom":      {"label": "Constipation",                          "category": "Autonomic",              "typical": "parkinsons_disease"},
    "autonomic_dysfunction_symptom": {"label": "Autonomic Dysfunction",             "category": "Autonomic",              "typical": "parkinsons_disease"},
    "autonomic_symptoms_als":    {"label": "Autonomic Symptoms (ALS)",              "category": "Autonomic"},
    "olfactory_dysfunction":     {"label": "Olfactory Dysfunction (loss of smell)", "category": "Autonomic",              "typical": "parkinsons_disease"},
    # Sleep
    "sleep_disturbance":         {"label": "Sleep Disturbance / REM disorder",      "category": "Sleep"},
    # Respiratory
    "respiratory_impairment":    {"label": "Respiratory Impairment",                "category": "Respiratory",            "typical": "als_disease"},
    # Sensory
    "sensory_symptom_als":       {"label": "Sensory Symptoms (ALS)",                "category": "Sensory"},
}

# ── Factor catalogue ─────────────────────────────────────────────────────────
FACTORS: dict[str, dict] = {
    # Genetic
    "apoe_e4":              {"label": "APOE e4 allele",                              "category": "Genetic"},
    "app_mutation":         {"label": "APP gene mutation",                           "category": "Genetic"},
    "psen1_mutation":       {"label": "PSEN1 gene mutation",                         "category": "Genetic"},
    "lrrk2_mutation":       {"label": "LRRK2 gene mutation",                         "category": "Genetic"},
    "snca_mutation":        {"label": "SNCA gene mutation",                          "category": "Genetic"},
    "c9orf72_repeat":       {"label": "C9orf72 hexanucleotide repeat expansion",     "category": "Genetic"},
    "sod1_mutation":        {"label": "SOD1 gene mutation",                          "category": "Genetic"},
    "family_history":       {"label": "Family history of neurodegenerative disease", "category": "Genetic"},
    # Lifestyle
    "aerobic_exercise":     {"label": "Aerobic Exercise (protective)",               "category": "Lifestyle"},
    "physical_inactivity":  {"label": "Physical Inactivity",                         "category": "Lifestyle"},
    "smoking":              {"label": "Smoking",                                     "category": "Lifestyle"},
    "alcohol_consumption":  {"label": "Alcohol Consumption",                         "category": "Lifestyle"},
    "coffee_drinking":      {"label": "Coffee / Caffeine Consumption",               "category": "Lifestyle"},
    "mediterranean_diet":   {"label": "Mediterranean Diet (protective)",             "category": "Lifestyle"},
    "obesity":              {"label": "Obesity",                                     "category": "Lifestyle"},
    "depression_factor":    {"label": "History of Depression",                       "category": "Lifestyle"},
    "low_education":        {"label": "Low Level of Education",                      "category": "Lifestyle"},
    "high_education":       {"label": "High Level of Education (protective)",        "category": "Lifestyle"},
    "stress":               {"label": "Chronic Stress",                              "category": "Lifestyle"},
    # Epidemiological
    "advanced_age":         {"label": "Advanced Age (65+)",                          "category": "Epidemiological"},
    "head_trauma":          {"label": "Head Trauma / TBI",                           "category": "Epidemiological"},
    "hypertension_factor":  {"label": "Hypertension",                                "category": "Epidemiological"},
    "diabetes_factor":      {"label": "Diabetes (Type 2)",                           "category": "Epidemiological"},
    "air_pollution":        {"label": "Air Pollution",                               "category": "Epidemiological"},
    "pesticide_exposure":   {"label": "Pesticide Exposure",                          "category": "Epidemiological"},
    "occupational_exposure":{"label": "Occupational Exposure (heavy metals/solvents)","category": "Epidemiological"},
    "military_service":     {"label": "Military Service",                            "category": "Epidemiological"},
    "cerebrovascular_disease_factor": {"label": "Cerebrovascular Disease",          "category": "Epidemiological"},
}

# ── Disease instances — direct translation of owl:NamedIndividual ─────────────
ONTOLOGY: dict[str, dict] = {
    "alzheimers_disease": {
        "label": "Alzheimer's Disease",
        "description": (
            "A progressive neurodegenerative disease primarily characterised by "
            "episodic memory impairment, language deterioration, and cognitive decline. "
            "Most common cause of dementia."
        ),
        "primary_symptoms": [
            "episodic_memory_impairment", "memory_impairment",
            "language_impairment", "impaired_reasoning",
        ],
        "secondary_symptoms": [
            "depression_symptom", "anxiety_symptom", "sleep_disturbance",
            "hallucination_symptom", "cognitive_psychiatric_als",
        ],
        "overlapping_symptoms": [
            "confusion_symptom", "dysphagia_symptom",
        ],
        "risk_factors": [
            "apoe_e4", "app_mutation", "psen1_mutation", "family_history",
            "advanced_age", "head_trauma", "hypertension_factor",
            "diabetes_factor", "air_pollution", "obesity", "depression_factor",
            "low_education", "stress", "physical_inactivity", "smoking",
            "cerebrovascular_disease_factor",
        ],
        "protective_factors": [
            "aerobic_exercise", "mediterranean_diet", "high_education",
        ],
        "contradictory_factors": [
            "coffee_drinking", "alcohol_consumption",
        ],
        "differentiators": [
            "Gradual episodic memory loss is the hallmark early sign",
            "Hippocampal atrophy visible on MRI; amyloid plaques and tau tangles are pathological markers",
            "Language difficulty (aphasia) more prominent than in Parkinson's or ALS",
            "Motor symptoms appear only in later stages — unlike Parkinson's or ALS",
            "APOE e4 allele is the strongest known genetic risk factor",
        ],
    },

    "als_disease": {
        "label": "ALS (Amyotrophic Lateral Sclerosis)",
        "description": (
            "A fatal motor neuron disease characterised by progressive upper and lower "
            "motor neuron degeneration leading to limb weakness, bulbar dysfunction, "
            "and respiratory failure."
        ),
        "primary_symptoms": [
            "limb_weakness", "muscle_weakness", "bulbar_dysfunction",
            "respiratory_impairment", "dysarthria_symptom",
            "dysphagia_symptom", "axial_weakness",
        ],
        "secondary_symptoms": [
            "pseudobulbar_affect", "autonomic_symptoms_als",
            "sensory_symptom_als", "sleep_disturbance", "cognitive_psychiatric_als",
        ],
        "overlapping_symptoms": [
            "confusion_symptom", "depression_symptom",
        ],
        "risk_factors": [
            "c9orf72_repeat", "sod1_mutation", "family_history",
            "advanced_age", "military_service", "occupational_exposure",
            "pesticide_exposure",
        ],
        "protective_factors": [],
        "contradictory_factors": [],
        "differentiators": [
            "Rapid progressive limb weakness and respiratory failure are the hallmarks",
            "Both upper (spasticity) and lower (fasciculations, wasting) motor neuron signs present",
            "Bulbar onset (speech/swallowing difficulty) is the presenting feature in ~25% of cases",
            "No primary memory loss — cognitive changes are frontotemporal and affect only a subset",
            "EMG is the key diagnostic test; C9orf72 / SOD1 genetic testing for familial cases",
        ],
    },

    "parkinsons_disease": {
        "label": "Parkinson's Disease",
        "description": (
            "A progressive neurodegenerative disease characterised by dopaminergic neuron "
            "loss in the substantia nigra, producing a triad of resting tremor, rigidity, "
            "and bradykinesia."
        ),
        "primary_symptoms": [
            "resting_tremor", "bradykinesia_symptom", "rigidity_symptom",
            "postural_instability", "gait_disturbance",
            "akinesia_symptom", "hypomimia_symptom",
        ],
        "secondary_symptoms": [
            "dysarthria_symptom", "dysphagia_symptom", "constipation_symptom",
            "sleep_disturbance", "hallucination_symptom", "depression_symptom",
            "anxiety_symptom", "autonomic_dysfunction_symptom",
            "olfactory_dysfunction", "neuropsychiatric_dysfunction",
            "hypophonia_symptom",
        ],
        "overlapping_symptoms": [
            "confusion_symptom",
        ],
        "risk_factors": [
            "lrrk2_mutation", "snca_mutation", "family_history",
            "advanced_age", "pesticide_exposure", "depression_factor",
            "air_pollution",
        ],
        "protective_factors": [
            "aerobic_exercise",
        ],
        "contradictory_factors": [],
        "differentiators": [
            "Resting (pill-rolling) tremor is the hallmark — not intention tremor",
            "Asymmetric onset distinguishes it from most other movement disorders",
            "Loss of smell (olfactory dysfunction) and REM sleep behaviour disorder are early non-motor clues",
            "Levodopa responsiveness is a key diagnostic criterion",
            "No prominent memory loss at onset — unlike Alzheimer's Disease",
        ],
    },
}

# ── Alias map — normalise free-text disease names from Dialogflow ─────────────
_ALIAS: dict[str, str] = {
    "alzheimer":                     "alzheimers_disease",
    "alzheimers":                    "alzheimers_disease",
    "alzheimer's":                   "alzheimers_disease",
    "alzheimers disease":            "alzheimers_disease",
    "alzheimer's disease":           "alzheimers_disease",
    "alzheimer disease":             "alzheimers_disease",
    "als":                           "als_disease",
    "amyotrophic lateral sclerosis": "als_disease",
    "motor neuron disease":          "als_disease",
    "mnd":                           "als_disease",
    "parkinson":                     "parkinsons_disease",
    "parkinsons":                    "parkinsons_disease",
    "parkinson's":                   "parkinsons_disease",
    "parkinsons disease":            "parkinsons_disease",
    "parkinson's disease":           "parkinsons_disease",
    "parkinson disease":             "parkinsons_disease",
}

# ── Symptom keyword map — for triage (CQ2) ───────────────────────────────────
_SYMPTOM_KEYWORDS: dict[str, str] = {
    "tremor":          "resting_tremor",
    "shaking":         "resting_tremor",
    "slow":            "bradykinesia_symptom",
    "slowness":        "bradykinesia_symptom",
    "bradykinesia":    "bradykinesia_symptom",
    "stiff":           "rigidity_symptom",
    "stiffness":       "rigidity_symptom",
    "rigidity":        "rigidity_symptom",
    "rigid":           "rigidity_symptom",
    "balance":         "postural_instability",
    "fall":            "postural_instability",
    "falling":         "postural_instability",
    "gait":            "gait_disturbance",
    "shuffle":         "gait_disturbance",
    "shuffling":       "gait_disturbance",
    "walking":         "gait_disturbance",
    "frozen":          "akinesia_symptom",
    "freezing":        "akinesia_symptom",
    "akinesia":        "akinesia_symptom",
    "masked":          "hypomimia_symptom",
    "expressionless":  "hypomimia_symptom",
    "weakness":        "muscle_weakness",
    "weak":            "limb_weakness",
    "limb":            "limb_weakness",
    "arm":             "limb_weakness",
    "leg":             "limb_weakness",
    "muscle":          "muscle_weakness",
    "atrophy":         "muscle_weakness",
    "trunk":           "axial_weakness",
    "slurred":         "dysarthria_symptom",
    "dysarthria":      "dysarthria_symptom",
    "speech":          "dysarthria_symptom",
    "swallow":         "dysphagia_symptom",
    "swallowing":      "dysphagia_symptom",
    "dysphagia":       "dysphagia_symptom",
    "bulbar":          "bulbar_dysfunction",
    "quiet":           "hypophonia_symptom",
    "hypophonia":      "hypophonia_symptom",
    "breathing":       "respiratory_impairment",
    "breath":          "respiratory_impairment",
    "respiratory":     "respiratory_impairment",
    "memory":          "memory_impairment",
    "forget":          "episodic_memory_impairment",
    "forgetful":       "episodic_memory_impairment",
    "recall":          "episodic_memory_impairment",
    "language":        "language_impairment",
    "word":            "language_impairment",
    "aphasia":         "language_impairment",
    "reason":          "impaired_reasoning",
    "judgment":        "impaired_reasoning",
    "confused":        "confusion_symptom",
    "confusion":       "confusion_symptom",
    "disoriented":     "confusion_symptom",
    "depressed":       "depression_symptom",
    "depression":      "depression_symptom",
    "anxious":         "anxiety_symptom",
    "anxiety":         "anxiety_symptom",
    "hallucin":        "hallucination_symptom",
    "constipat":       "constipation_symptom",
    "bowel":           "constipation_symptom",
    "autonomic":       "autonomic_dysfunction_symptom",
    "smell":           "olfactory_dysfunction",
    "anosmia":         "olfactory_dysfunction",
    "sleep":           "sleep_disturbance",
    "insomnia":        "sleep_disturbance",
    "rem":             "sleep_disturbance",
    "sensory":         "sensory_symptom_als",
    "numbness":        "sensory_symptom_als",
    "laughing":        "pseudobulbar_affect",
    "crying":          "pseudobulbar_affect",
}


# =============================================================================
# HELPERS
# =============================================================================

def _normalise_disease(raw: str) -> str | None:
    cleaned = raw.lower().strip()
    if cleaned in _ALIAS:
        return _ALIAS[cleaned]
    for suffix in (" disease", " disorder", " syndrome", "'s disease", "s disease"):
        if cleaned.endswith(suffix):
            trimmed = cleaned[: -len(suffix)].strip()
            if trimmed in _ALIAS:
                return _ALIAS[trimmed]
    return None


def _extract_diseases(params: dict) -> list[str]:
    candidates: list[str] = []
    for key in ("disease", "diseases", "disease_name",
                "disease_a", "disease_b", "disease1", "disease2"):
        val = params.get(key)
        if not val:
            continue
        if isinstance(val, list):
            candidates.extend(str(v) for v in val if v)
        else:
            candidates.append(str(val))
    seen, result = set(), []
    for c in candidates:
        k = _normalise_disease(c)
        if k and k not in seen:
            seen.add(k)
            result.append(k)
    return result


def _extract_symptom_keywords(params: dict) -> list[str]:
    raw = params.get("symptoms") or params.get("symptom", [])
    if isinstance(raw, str):
        return [raw.lower().strip()] if raw.strip() else []
    return [s.lower().strip() for s in raw if s]


def _sym_label(sym_id: str) -> str:
    return SYMPTOMS.get(sym_id, {}).get("label", sym_id.replace("_", " ").title())


def _fac_label(fac_id: str) -> str:
    return FACTORS.get(fac_id, {}).get("label", fac_id.replace("_", " ").title())


def _bullet(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items)


def _all_symptom_ids(dk: str) -> list[str]:
    d = ONTOLOGY[dk]
    return d["primary_symptoms"] + d["secondary_symptoms"] + d["overlapping_symptoms"]


# ── Response builders ─────────────────────────────────────────────────────────

def _es_response(messages: list[str]) -> dict:
    combined = "\n\n".join(m for m in messages if m)
    return {
        "fulfillmentText": combined,
        "fulfillmentMessages": [
            {"text": {"text": [msg]}} for msg in messages if msg
        ],
    }


def _cx_response(messages: list[str]) -> dict:
    return {
        "fulfillment_response": {
            "messages": [
                {"text": {"text": [msg]}} for msg in messages if msg
            ]
        }
    }


def _respond(messages: list[str], es: bool = False) -> dict:
    return _es_response(messages) if es else _cx_response(messages)


# =============================================================================
# PAYLOAD PARSERS
# =============================================================================

def _is_es(body: dict) -> bool:
    return "queryResult" in body


def _parse_es(body: dict) -> tuple[str, dict]:
    qr = body.get("queryResult", {})
    intent_name = qr.get("intent", {}).get("displayName", "").strip()
    raw = qr.get("parameters", {})
    flat: dict = {}
    for k, v in raw.items():
        if isinstance(v, list):
            flat[k] = v[0] if len(v) == 1 else (v if v else "")
        else:
            flat[k] = v
    return intent_name, flat


def _parse_cx(body: dict) -> tuple[str, dict]:
    tag = body.get("fulfillmentInfo", {}).get("tag", "").strip()
    display = body.get("intentInfo", {}).get("displayName", "").strip()
    intent_name = tag or display
    session = body.get("sessionInfo", {}).get("parameters", {})
    raw = body.get("intentInfo", {}).get("parameters", {})
    flat: dict = {}
    for k, v in raw.items():
        flat[k] = v.get("resolvedValue", v.get("originalValue", "")) if isinstance(v, dict) else v
    return intent_name, {**flat, **session}


# =============================================================================
# INTENT HANDLERS
# =============================================================================

# ── CQ1 — Symptoms of a disease ──────────────────────────────────────────────

def handle_get_primary_symptoms(params: dict, es: bool = False) -> dict:
    diseases = _extract_diseases(params)

    if not diseases:
        disease_list = _bullet([ONTOLOGY[dk]["label"] for dk in ONTOLOGY])
        return _respond([
            "I can report symptoms for the following diseases:",
            disease_list,
            "Which disease would you like to know about?",
        ], es)

    messages = []
    for dk in diseases:
        d = ONTOLOGY[dk]
        primary     = _bullet([_sym_label(s) for s in d["primary_symptoms"]])
        secondary   = _bullet([_sym_label(s) for s in d["secondary_symptoms"]])
        overlapping = _bullet([_sym_label(s) for s in d["overlapping_symptoms"]])
        messages.append(
            f"━━ {d['label']} ━━\n"
            f"Primary (hallmark) symptoms:\n{primary}\n\n"
            f"Secondary symptoms:\n{secondary}\n\n"
            f"Overlapping symptoms (shared with other diseases):\n{overlapping}"
        )
    return _respond(messages, es)


# ── CQ2 — Triage: what disease matches my symptoms? ──────────────────────────

def handle_get_triage_result(params: dict, es: bool = False) -> dict:
    user_keywords = _extract_symptom_keywords(params)

    if not user_keywords:
        return _respond([
            "Please describe your symptoms so I can help with triage.\n"
            "For example: 'I have tremor, stiffness, and trouble walking.'"
        ], es)

    matched_sym_ids: set[str] = set()
    for kw in user_keywords:
        for keyword, sym_id in _SYMPTOM_KEYWORDS.items():
            if keyword in kw or kw in keyword:
                matched_sym_ids.add(sym_id)

    if not matched_sym_ids:
        return _respond([
            f"I could not match '{', '.join(user_keywords)}' to any known symptoms.\n"
            "Try describing symptoms such as: tremor, memory loss, weakness, slurred speech.",
            "This tool provides informational support only — not a medical diagnosis. "
            "Please consult a qualified neurologist."
        ], es)

    # Score: primary=3, secondary=2, overlapping=1
    scores: dict[str, int] = {}
    matched_per_disease: dict[str, list[str]] = {}
    for dk, d in ONTOLOGY.items():
        score = 0
        matched: list[str] = []
        for tier, w in [("primary_symptoms", 3), ("secondary_symptoms", 2), ("overlapping_symptoms", 1)]:
            for sym_id in d[tier]:
                if sym_id in matched_sym_ids:
                    score += w
                    tier_label = tier.replace("_symptoms", "")
                    matched.append(f"{_sym_label(sym_id)} [{tier_label}]")
        scores[dk] = score
        matched_per_disease[dk] = matched

    ranked = sorted(
        [(dk, sc) for dk, sc in scores.items() if sc > 0],
        key=lambda x: x[1], reverse=True
    )

    if not ranked:
        return _respond([
            "The ontology could not find a symptom match for what you described.\n"
            "Please consult a medical professional for a proper evaluation.",
            "This tool provides informational support only — not a medical diagnosis."
        ], es)

    messages = [
        f"Based on the symptoms you described ({', '.join(user_keywords)}), "
        "here are possible conditions from the NTO ontology:"
    ]
    icons = ["[1st]", "[2nd]", "[3rd]"]
    for i, (dk, score) in enumerate(ranked[:3]):
        d = ONTOLOGY[dk]
        icon = icons[i] if i < len(icons) else "•"
        messages.append(
            f"{icon} {d['label']} — {score} ontology match point(s)\n"
            f"   Matched: {', '.join(matched_per_disease[dk])}"
        )
    messages.append(
        "This is informational triage support only and not a medical diagnosis. "
        "Please consult a qualified neurologist."
    )
    return _respond(messages, es)


# ── CQ3 — Differentiate between diseases ─────────────────────────────────────

def handle_differentiate_by_disease(params: dict, es: bool = False) -> dict:
    diseases = _extract_diseases(params)
    if len(diseases) < 2:
        diseases = list(ONTOLOGY.keys())

    messages = [
        "How to differentiate between "
        + ", ".join(ONTOLOGY[dk]["label"] for dk in diseases) + ":"
    ]
    for dk in diseases:
        d = ONTOLOGY[dk]
        messages.append(
            f"━━ {d['label']} ━━\n{_bullet(d['differentiators'])}"
        )
    messages.append(
        "Key principle: focus on onset pattern, primary symptom domain "
        "(motor vs cognitive vs both), and which symptoms appeared first."
    )
    return _respond(messages, es)


# ── CQ4 — Overlapping symptoms between two diseases ──────────────────────────

def handle_get_overlapping_symptoms(params: dict, es: bool = False) -> dict:
    diseases = _extract_diseases(params)

    if len(diseases) < 2:
        return _respond([
            "Please specify two diseases to compare.\n"
            "For example: 'What symptoms do Alzheimer's and Parkinson's share?'"
        ], es)

    dk1, dk2 = diseases[0], diseases[1]
    d1, d2 = ONTOLOGY[dk1], ONTOLOGY[dk2]

    set1 = set(_all_symptom_ids(dk1))
    set2 = set(_all_symptom_ids(dk2))
    shared_ids  = sorted(set1 & set2)
    only1_ids   = sorted(set1 - set2)
    only2_ids   = sorted(set2 - set1)

    explicit_overlap = sorted(
        set(d1["overlapping_symptoms"]) & set(d2["overlapping_symptoms"])
    )

    if not shared_ids:
        return _respond([
            f"The ontology contains no shared symptoms between "
            f"{d1['label']} and {d2['label']}."
        ], es)

    messages = [f"Symptom comparison: {d1['label']} vs {d2['label']}"]

    messages.append(
        f"Shared symptoms ({len(shared_ids)}):\n"
        + _bullet([_sym_label(s) for s in shared_ids])
    )
    if explicit_overlap:
        messages.append(
            "Explicitly marked as overlapping in the ontology "
            "(hasOverlappingSymptom):\n"
            + _bullet([_sym_label(s) for s in explicit_overlap])
        )
    if only1_ids:
        messages.append(
            f"Symptoms unique to {d1['label']}:\n"
            + _bullet([_sym_label(s) for s in only1_ids])
        )
    if only2_ids:
        messages.append(
            f"Symptoms unique to {d2['label']}:\n"
            + _bullet([_sym_label(s) for s in only2_ids])
        )
    return _respond(messages, es)


# ── CQ5 — Risk factors for a disease ─────────────────────────────────────────

def handle_get_risk_factors(params: dict, es: bool = False) -> dict:
    diseases = _extract_diseases(params)

    if not diseases:
        return _respond([
            "Which disease would you like risk factors for?\n"
            "Available: Alzheimer's Disease, ALS, Parkinson's Disease."
        ], es)

    messages = []
    for dk in diseases:
        d = ONTOLOGY[dk]
        risk_by_cat: dict[str, list[str]] = {}
        for fid in d["risk_factors"]:
            cat = FACTORS.get(fid, {}).get("category", "Other")
            risk_by_cat.setdefault(cat, []).append(_fac_label(fid))

        lines = [f"Risk factors for {d['label']}:"]
        for cat in ["Genetic", "Lifestyle", "Epidemiological", "Other"]:
            if cat in risk_by_cat:
                lines.append(f"\n[{cat}]\n{_bullet(risk_by_cat[cat])}")
        if d["protective_factors"]:
            lines.append(
                "\nProtective factors:\n"
                + _bullet([_fac_label(f) for f in d["protective_factors"]])
            )
        if d["contradictory_factors"]:
            lines.append(
                "\nContradictory evidence (mixed findings):\n"
                + _bullet([_fac_label(f) for f in d["contradictory_factors"]])
            )
        messages.append("\n".join(lines))

    return _respond(messages, es)


# ── CQ6 — Lifestyle factors affecting a disease ──────────────────────────────

def handle_get_lifestyle_risk_factors(params: dict, es: bool = False) -> dict:
    diseases = _extract_diseases(params)

    if not diseases:
        return _respond([
            "Which disease would you like lifestyle factor information for?\n"
            "For example: 'What lifestyle factors affect Parkinson's?'"
        ], es)

    messages = []
    for dk in diseases:
        d = ONTOLOGY[dk]
        lifestyle_risk = [
            _fac_label(fid) for fid in d["risk_factors"]
            if FACTORS.get(fid, {}).get("category") == "Lifestyle"
        ]
        lifestyle_protect = [
            _fac_label(fid) for fid in d["protective_factors"]
            if FACTORS.get(fid, {}).get("category") == "Lifestyle"
        ]
        lifestyle_contra = [
            _fac_label(fid) for fid in d["contradictory_factors"]
            if FACTORS.get(fid, {}).get("category") == "Lifestyle"
        ]

        lines = [f"Lifestyle factors for {d['label']}:"]
        if lifestyle_risk:
            lines.append(f"\nRisk factors (lifestyle):\n{_bullet(lifestyle_risk)}")
        if lifestyle_protect:
            lines.append(f"\nProtective lifestyle factors:\n{_bullet(lifestyle_protect)}")
        if lifestyle_contra:
            lines.append(f"\nContradictory evidence:\n{_bullet(lifestyle_contra)}")
        if not (lifestyle_risk or lifestyle_protect or lifestyle_contra):
            lines.append("\nNo lifestyle-specific factors recorded in the ontology.")
        messages.append("\n".join(lines))

    return _respond(messages, es)


# ── Fallback ──────────────────────────────────────────────────────────────────

def handle_unknown_intent(intent_name: str, es: bool = False) -> dict:
    return _respond([
        f"I don't know how to handle the intent '{intent_name}' yet.\n"
        "You can ask me about:\n"
        "• Symptoms of a disease (Alzheimer's, ALS, Parkinson's)\n"
        "• Which disease might match your symptoms\n"
        "• How to differentiate between the three diseases\n"
        "• Overlapping symptoms between two diseases\n"
        "• Risk factors for a disease\n"
        "• Lifestyle factors affecting a disease"
    ], es)


# =============================================================================
# INTENT ROUTER
# =============================================================================

INTENT_ROUTER: dict = {
    "ReportSymptoms":           handle_get_primary_symptoms,
    "GetPrimarySymptoms":       handle_get_primary_symptoms,
    "GetTriageResult":          handle_get_triage_result,
    "GetDiseaseFromSymptom":    handle_get_triage_result,
    "DifferentiateByDisease":   handle_differentiate_by_disease,
    "GetOverlappingSymptoms":   handle_get_overlapping_symptoms,
    "GetRiskFactors":           handle_get_risk_factors,
    "GetLifestyleRiskFactors":  handle_get_lifestyle_risk_factors,
}


# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "NARQ webhook is live", "ontology": "NTO v1.0.0"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        body: dict = request.get_json(force=True) or {}
        logger.info("Webhook received — keys: %s", list(body.keys()))

        es = _is_es(body)
        if es:
            intent_name, params = _parse_es(body)
        else:
            intent_name, params = _parse_cx(body)

        logger.info("Format: %s  |  Intent: '%s'  |  Params: %s",
                    "ES" if es else "CX", intent_name, params)

        handler = INTENT_ROUTER.get(intent_name)
        if handler:
            response = handler(params, es=es)
        else:
            logger.warning("No handler for intent: '%s'", intent_name)
            response = handle_unknown_intent(intent_name, es=es)

        return jsonify(response), 200

    except Exception as exc:
        logger.exception("Unhandled exception: %s", exc)
        return jsonify(_es_response([
            "I encountered an internal error. Please try again shortly."
        ])), 500


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting NARQ webhook on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
