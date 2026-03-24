"""
NARQ - Neurological Abstracts Retrieval & Q&A
Dialogflow CX Webhook — render.com deployment
Course: DTI5125 Data Science Applications
Authors: Adjmal, Younoussa | Pathan, Ferdous | Hoang, Julian Vu

Handles intents:
  - ReportSymptoms / GetPrimarySymptoms
  - GetTriageResult / GetDiseaseFromSymptom
  - DifferentiateByDisease
  - GetOverlappingSymptoms
  - GetRiskFactors / GetLifestyleRiskFactors
"""

import os
import json
import logging
from flask import Flask, request, jsonify

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# ONTOLOGY  (inline — replace with DB / FAISS calls in production)
# ═════════════════════════════════════════════════════════════════════════════

# Maps each disease to its canonical symptom list, risk factors, and
# lifestyle risk factors. Keep everything lower-case for easy matching.

ONTOLOGY: dict = {
    "alzheimers": {
        "label": "Alzheimer's Disease",
        "primary_symptoms": [
            "memory loss",
            "confusion",
            "disorientation",
            "difficulty with language",
            "mood changes",
            "difficulty with daily tasks",
            "poor judgment",
            "withdrawal from social activities",
        ],
        "risk_factors": [
            "age (65+)",
            "family history / genetics (APOE-e4 allele)",
            "down syndrome",
            "traumatic brain injury",
            "cardiovascular disease",
            "diabetes",
            "hypertension",
            "obesity",
        ],
        "lifestyle_risk_factors": [
            "physical inactivity",
            "smoking",
            "excessive alcohol consumption",
            "poor diet (high saturated fat, low Mediterranean diet)",
            "social isolation",
            "poor sleep",
            "chronic stress",
            "low cognitive engagement / education level",
        ],
        "differentiators": [
            "gradual memory decline is the hallmark onset",
            "hippocampal atrophy visible on MRI",
            "amyloid plaques and tau tangles are pathological markers",
            "language difficulty (aphasia) more prominent than in Parkinson's",
            "motor symptoms appear only in later stages unlike Parkinson's",
        ],
    },

    "als": {
        "label": "ALS / Huntington's Disease",
        "primary_symptoms": [
            "progressive muscle weakness",
            "muscle atrophy",
            "fasciculations (muscle twitching)",
            "spasticity",
            "dysarthria (slurred speech)",
            "dysphagia (difficulty swallowing)",
            "breathing difficulties",
            "involuntary movements (Huntington's chorea)",
            "cognitive decline (Huntington's)",
            "psychiatric symptoms (Huntington's)",
        ],
        "risk_factors": [
            "genetic mutations (SOD1, C9orf72 for ALS; HTT CAG repeat for Huntington's)",
            "age (40-70 for ALS)",
            "military service (ALS)",
            "family history",
            "male sex (slightly higher ALS risk)",
        ],
        "lifestyle_risk_factors": [
            "smoking (ALS association)",
            "heavy physical exertion / contact sports (ALS hypothesis)",
            "exposure to pesticides or heavy metals",
            "high-intensity athletic activity (ALS hypothesis)",
        ],
        "differentiators": [
            "ALS: both upper and lower motor neuron signs",
            "Huntington's: autosomal dominant — genetic test (CAG repeat) is definitive",
            "ALS: no genetic pre-test needed for diagnosis; EMG is key",
            "Huntington's: involuntary choreiform movements are distinctive",
            "motor decline is central — cognitive changes lag unlike Alzheimer's",
        ],
    },

    "dementia": {
        "label": "Dementia / Mild Cognitive Impairment (MCI)",
        "primary_symptoms": [
            "memory loss (short-term)",
            "confusion",
            "disorientation",
            "personality changes",
            "difficulty with complex tasks",
            "impaired reasoning",
            "language problems",
            "getting lost in familiar places",
        ],
        "risk_factors": [
            "age (65+)",
            "family history",
            "cardiovascular disease",
            "diabetes",
            "hypertension",
            "high cholesterol",
            "depression",
            "prior stroke",
        ],
        "lifestyle_risk_factors": [
            "physical inactivity",
            "poor diet",
            "smoking",
            "excessive alcohol",
            "social isolation",
            "poor sleep quality",
            "low educational attainment",
        ],
        "differentiators": [
            "MCI: subjective cognitive complaint but daily function preserved",
            "dementia: functional impairment distinguishes it from MCI",
            "vascular dementia: stepwise decline linked to stroke events",
            "Lewy body dementia: visual hallucinations and REM sleep disorder",
            "overlaps heavily with Alzheimer's — biomarker tests help distinguish",
        ],
    },

    "parkinsons": {
        "label": "Parkinson's Disease",
        "primary_symptoms": [
            "resting tremor",
            "bradykinesia (slowness of movement)",
            "muscle rigidity",
            "postural instability",
            "shuffling gait",
            "loss of smell (anosmia)",
            "sleep disturbances (REM behaviour disorder)",
            "constipation",
            "micrographia (small handwriting)",
        ],
        "risk_factors": [
            "age (60+)",
            "male sex",
            "family history (LRRK2, SNCA, PINK1 mutations)",
            "exposure to pesticides / herbicides",
            "traumatic brain injury",
            "rural living (well-water / herbicide exposure)",
        ],
        "lifestyle_risk_factors": [
            "pesticide / herbicide exposure (farming)",
            "physical inactivity",
            "smoking (paradoxically associated with lower risk in epidemiology)",
            "high dairy consumption (possible association)",
            "head trauma history",
        ],
        "differentiators": [
            "resting tremor ('pill-rolling') is the hallmark — not intention tremor",
            "asymmetric onset distinguishes it from most other movement disorders",
            "levodopa responsiveness is a diagnostic criterion",
            "anosmia and REM sleep disorder are early non-motor clues",
            "no prominent memory loss at onset unlike Alzheimer's",
        ],
    },

    "stroke": {
        "label": "Stroke",
        "primary_symptoms": [
            "sudden facial drooping",
            "sudden arm weakness (unilateral)",
            "sudden speech difficulty",
            "sudden vision loss",
            "sudden severe headache ('thunderclap')",
            "sudden loss of balance or coordination",
            "confusion",
            "numbness on one side of the body",
        ],
        "risk_factors": [
            "hypertension (leading modifiable risk factor)",
            "atrial fibrillation",
            "diabetes",
            "high cholesterol",
            "age (55+)",
            "family history",
            "prior stroke or TIA",
            "carotid artery disease",
            "sickle cell disease",
        ],
        "lifestyle_risk_factors": [
            "smoking",
            "excessive alcohol consumption",
            "physical inactivity",
            "poor diet (high sodium, low fruit/vegetable)",
            "obesity",
            "stress",
            "illicit drug use",
        ],
        "differentiators": [
            "sudden onset is the key — neurological symptoms appear within seconds/minutes",
            "FAST acronym (Face, Arms, Speech, Time) is the clinical screen",
            "CT/MRI differentiates ischemic vs. haemorrhagic sub-types",
            "unlike Parkinson's or Alzheimer's, onset is abrupt not insidious",
            "post-stroke cognitive impairment can mimic dementia but history clarifies",
        ],
    },
}

# Convenient alias map: normalise free-text disease mentions
_ALIAS: dict[str, str] = {
    "alzheimer": "alzheimers",
    "alzheimers": "alzheimers",
    "alzheimer's": "alzheimers",
    "als": "als",
    "huntington": "als",
    "huntington's": "als",
    "amyotrophic lateral sclerosis": "als",
    "dementia": "dementia",
    "mci": "dementia",
    "mild cognitive impairment": "dementia",
    "parkinson": "parkinsons",
    "parkinsons": "parkinsons",
    "parkinson's": "parkinsons",
    "stroke": "stroke",
    "cerebrovascular": "stroke",
}

ALL_DISEASES = list(ONTOLOGY.keys())


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _normalise_disease(raw: str) -> str | None:
    """Return canonical disease key from free-text, or None if not found."""
    return _ALIAS.get(raw.lower().strip())


def _extract_diseases_from_params(params: dict) -> list[str]:
    """
    Pull disease names out of Dialogflow CX parameters.
    Dialogflow may send a single string or a list under various keys.
    """
    candidates: list[str] = []
    for key in ("disease", "diseases", "disease_name", "disease_a", "disease_b",
                "disease1", "disease2"):
        val = params.get(key)
        if not val:
            continue
        if isinstance(val, list):
            candidates.extend(val)
        else:
            candidates.append(str(val))
    return [k for c in candidates if (k := _normalise_disease(c))]


def _extract_symptoms_from_params(params: dict) -> list[str]:
    """Pull symptom strings out of Dialogflow CX parameters."""
    val = params.get("symptoms") or params.get("symptom", [])
    if isinstance(val, str):
        return [val.lower().strip()]
    return [s.lower().strip() for s in val] if val else []


def _bullet(items: list[str]) -> str:
    return "\n".join(f"• {item.capitalize()}" for item in items)


def _cx_response(messages: list[str]) -> dict:
    """
    Build a minimal Dialogflow CX webhook response.
    Wraps each string in a text response message.
    """
    return {
        "fulfillment_response": {
            "messages": [
                {"text": {"text": [msg]}} for msg in messages
            ]
        }
    }


# ═════════════════════════════════════════════════════════════════════════════
# INTENT HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

# ── 1. ReportSymptoms / GetPrimarySymptoms ────────────────────────────────

def handle_get_primary_symptoms(params: dict) -> dict:
    """
    Intents: ReportSymptoms.json, GetPrimarySymptoms.json
    Returns the primary symptom list for one or more diseases.
    If no disease is specified, lists all diseases.
    """
    diseases = _extract_diseases_from_params(params)

    if not diseases:
        # No disease specified — list all available diseases
        disease_list = "\n".join(
            f"• {info['label']}" for info in ONTOLOGY.values()
        )
        return _cx_response([
            "I can report symptoms for the following neurological diseases:",
            disease_list,
            "Which disease would you like to know about? "
            "For example: 'What are the symptoms of Parkinson's Disease?'",
        ])

    messages = []
    for dk in diseases:
        info = ONTOLOGY[dk]
        messages.append(
            f"Primary symptoms of {info['label']}:\n{_bullet(info['primary_symptoms'])}"
        )
    return _cx_response(messages)


# ── 2. GetTriageResult / GetDiseaseFromSymptom ────────────────────────────

def handle_get_triage_result(params: dict) -> dict:
    """
    Intents: GetTriageResult.json, GetDiseaseFromSymptom.json
    Given a list of user-reported symptoms, scores each disease and returns
    the most likely candidates.
    """
    user_symptoms = _extract_symptoms_from_params(params)

    if not user_symptoms:
        return _cx_response([
            "Please tell me your symptoms so I can help triage. "
            "For example: 'I have tremor, stiffness, and slow movement.'"
        ])

    # Score each disease: count matching keywords
    scores: dict[str, int] = {}
    matched_per_disease: dict[str, list[str]] = {}

    for dk, info in ONTOLOGY.items():
        count = 0
        matched: list[str] = []
        for user_s in user_symptoms:
            for disease_s in info["primary_symptoms"]:
                if user_s in disease_s or disease_s in user_s:
                    count += 1
                    matched.append(disease_s)
                    break  # avoid double-counting per user symptom
        scores[dk] = count
        matched_per_disease[dk] = matched

    # Rank diseases by score, keep those with at least 1 match
    ranked = sorted(
        [(dk, sc) for dk, sc in scores.items() if sc > 0],
        key=lambda x: x[1],
        reverse=True,
    )

    if not ranked:
        return _cx_response([
            "I could not match your symptoms to any disease in my knowledge base. "
            "Please consult a medical professional for a proper diagnosis.",
            "Try describing symptoms such as: tremor, memory loss, weakness, "
            "sudden speech difficulty, etc.",
        ])

    messages = [
        f"Based on the symptoms you reported ({', '.join(user_symptoms)}), "
        f"here are the possible conditions:"
    ]

    for dk, score in ranked[:3]:  # top 3
        info = ONTOLOGY[dk]
        matched = matched_per_disease[dk]
        messages.append(
            f"{'🔴' if score == ranked[0][1] else '🟡'} {info['label']} "
            f"({score} symptom(s) matched)\n"
            f"  Matching: {', '.join(matched)}"
        )

    messages.append(
        "⚠️ This is informational only and not a medical diagnosis. "
        "Please consult a qualified neurologist."
    )
    return _cx_response(messages)


# ── 3. DifferentiateByDisease ─────────────────────────────────────────────

def handle_differentiate_by_disease(params: dict) -> dict:
    """
    Intent: DifferentiateByDisease.json
    Explains how to differentiate between two or more specified diseases.
    Default: Parkinson's vs ALS vs Alzheimer's.
    """
    diseases = _extract_diseases_from_params(params)

    # Default comparison if none or only one is specified
    if len(diseases) < 2:
        diseases = ["alzheimers", "als", "parkinsons"]

    messages = [
        f"Here is how to differentiate between "
        f"{', '.join(ONTOLOGY[d]['label'] for d in diseases)}:"
    ]

    for dk in diseases:
        info = ONTOLOGY[dk]
        messages.append(
            f"━━ {info['label']} ━━\n"
            + _bullet(info["differentiators"])
        )

    # Add a cross-disease comparison note for the common pair Alzheimer's / dementia
    if set(diseases) >= {"alzheimers", "dementia"}:
        messages.append(
            "📌 Note: Alzheimer's Disease is the most common cause of Dementia (~60-70%). "
            "Key differentiators include biomarker results (amyloid PET, CSF tau/Aβ42) "
            "and rate of progression."
        )

    return _cx_response(messages)


# ── 4. GetOverlappingSymptoms ─────────────────────────────────────────────

def handle_get_overlapping_symptoms(params: dict) -> dict:
    """
    Intent: GetOverlappingSymptoms.json
    Returns the symptom intersection between exactly two diseases.
    """
    diseases = _extract_diseases_from_params(params)

    if len(diseases) < 2:
        return _cx_response([
            "Please specify two diseases to compare. "
            "For example: 'What symptoms overlap between Alzheimer's and Dementia?'"
        ])

    d1_key, d2_key = diseases[0], diseases[1]
    d1_info, d2_info = ONTOLOGY[d1_key], ONTOLOGY[d2_key]

    set1 = set(d1_info["primary_symptoms"])
    set2 = set(d2_info["primary_symptoms"])
    overlap = sorted(set1 & set2)

    only_d1 = sorted(set1 - set2)
    only_d2 = sorted(set2 - set1)

    if not overlap:
        msg = (
            f"There are no exact symptom overlaps between "
            f"{d1_info['label']} and {d2_info['label']} "
            f"in the current ontology. Their symptom profiles are largely distinct."
        )
        return _cx_response([msg])

    messages = [
        f"Overlapping symptoms between {d1_info['label']} "
        f"and {d2_info['label']}:\n{_bullet(overlap)}",
        f"Symptoms unique to {d1_info['label']}:\n{_bullet(only_d1)}" if only_d1 else "",
        f"Symptoms unique to {d2_info['label']}:\n{_bullet(only_d2)}" if only_d2 else "",
    ]
    return _cx_response([m for m in messages if m])


# ── 5. GetRiskFactors ─────────────────────────────────────────────────────

def handle_get_risk_factors(params: dict) -> dict:
    """
    Intent: GetRiskFactors.json
    Returns general (non-lifestyle) risk factors for specified diseases.
    """
    diseases = _extract_diseases_from_params(params)

    if not diseases:
        return _cx_response([
            "Which disease are you asking about? "
            "I can provide risk factors for: Alzheimer's, ALS/Huntington's, "
            "Dementia/MCI, Parkinson's, and Stroke."
        ])

    messages = []
    for dk in diseases:
        info = ONTOLOGY[dk]
        messages.append(
            f"Risk factors for {info['label']}:\n{_bullet(info['risk_factors'])}"
        )
    return _cx_response(messages)


# ── 6. GetLifestyleRiskFactors ────────────────────────────────────────────

def handle_get_lifestyle_risk_factors(params: dict) -> dict:
    """
    Intent: GetLifestyleRiskFactors.json
    Returns lifestyle-specific risk factors.
    """
    diseases = _extract_diseases_from_params(params)

    if not diseases:
        return _cx_response([
            "Which disease are you asking about for lifestyle risk factors? "
            "For example: 'What lifestyle factors affect Alzheimer's?'"
        ])

    messages = []
    for dk in diseases:
        info = ONTOLOGY[dk]
        messages.append(
            f"Lifestyle risk factors for {info['label']}:\n"
            f"{_bullet(info['lifestyle_risk_factors'])}"
        )
    return _cx_response(messages)


# ── Fallback ──────────────────────────────────────────────────────────────

def handle_unknown_intent(intent_display_name: str) -> dict:
    return _cx_response([
        f"I'm sorry, I don't know how to handle the intent '{intent_display_name}' yet. "
        "You can ask me about:\n"
        "• Symptoms of a neurological disease\n"
        "• Which disease might match your symptoms\n"
        "• How to differentiate between two diseases\n"
        "• Overlapping symptoms between diseases\n"
        "• Risk factors or lifestyle risk factors for a disease"
    ])


# ═════════════════════════════════════════════════════════════════════════════
# INTENT ROUTER
# ═════════════════════════════════════════════════════════════════════════════

# Maps every Dialogflow intent display name (or tag) to its handler.
# Keys must match exactly what you set in Dialogflow CX intent display names.

INTENT_ROUTER: dict = {
    # ── Symptoms ──────────────────────────────────────────────
    "ReportSymptoms":           handle_get_primary_symptoms,
    "GetPrimarySymptoms":       handle_get_primary_symptoms,

    # ── Triage ────────────────────────────────────────────────
    "GetTriageResult":          handle_get_triage_result,
    "GetDiseaseFromSymptom":    handle_get_triage_result,

    # ── Differentiation ───────────────────────────────────────
    "DifferentiateByDisease":   handle_differentiate_by_disease,

    # ── Overlapping ───────────────────────────────────────────
    "GetOverlappingSymptoms":   handle_get_overlapping_symptoms,

    # ── Risk factors ──────────────────────────────────────────
    "GetRiskFactors":           handle_get_risk_factors,
    "GetLifestyleRiskFactors":  handle_get_lifestyle_risk_factors,
}


# ═════════════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
def health_check():
    """render.com health-check endpoint."""
    return jsonify({"status": "NARQ webhook is live 🧠"}), 200


def _is_dialogflow_es(body: dict) -> bool:
    """Return True if the payload is Dialogflow ES (v2) format."""
    return "queryResult" in body


def _parse_es_payload(body: dict) -> tuple[str, dict]:
    """
    Parse a Dialogflow ES (v2) WebhookRequest.

    ES payload structure:
    {
      "queryResult": {
        "intent": { "displayName": "GetOverlappingSymptoms" },
        "parameters": {
          "disease":  "Alzheimer's Disease",   # string or list
          "disease1": ["Parkinson's Disease"],  # string or list
          "symptom":  ["symptoms"]
        }
      }
    }
    Returns (intent_name, flat_params).
    """
    query_result = body.get("queryResult", {})
    intent_name: str = query_result.get("intent", {}).get("displayName", "").strip()

    raw_params: dict = query_result.get("parameters", {})
    flat: dict = {}
    for k, v in raw_params.items():
        if isinstance(v, list):
            # Keep lists as-is; _extract_diseases_from_params handles them
            flat[k] = v if v else ""
        else:
            flat[k] = v
    return intent_name, flat


def _parse_cx_payload(body: dict) -> tuple[str, dict]:
    """
    Parse a Dialogflow CX WebhookRequest.

    CX payload structure:
    {
      "fulfillmentInfo": { "tag": "GetPrimarySymptoms" },
      "intentInfo": {
        "displayName": "GetPrimarySymptoms",
        "parameters": { "disease": { "resolvedValue": "Parkinson's" } }
      },
      "sessionInfo": { "parameters": { "disease": "Parkinson's" } }
    }
    Returns (intent_name, flat_params).
    """
    fulfillment_tag: str = body.get("fulfillmentInfo", {}).get("tag", "").strip()
    intent_display_name: str = body.get("intentInfo", {}).get("displayName", "").strip()
    intent_name = fulfillment_tag or intent_display_name

    session_params: dict = body.get("sessionInfo", {}).get("parameters", {})
    intent_params_raw: dict = body.get("intentInfo", {}).get("parameters", {})

    intent_params_flat: dict = {}
    for k, v in intent_params_raw.items():
        if isinstance(v, dict):
            intent_params_flat[k] = v.get("resolvedValue", v.get("originalValue", ""))
        else:
            intent_params_flat[k] = v

    params: dict = {**intent_params_flat, **session_params}
    return intent_name, params


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Main webhook endpoint — supports both Dialogflow ES (v2) and CX formats.

    Dialogflow ES POST body (WebhookRequest v2) looks like:
    {
      "queryResult": {
        "queryText": "...",
        "intent": { "displayName": "GetOverlappingSymptoms" },
        "parameters": { "disease": "Alzheimer's Disease", "disease1": ["Parkinson's Disease"] }
      }
    }

    Dialogflow CX POST body (WebhookRequest) looks like:
    {
      "fulfillmentInfo": { "tag": "GetPrimarySymptoms" },
      "intentInfo": { "displayName": "GetPrimarySymptoms", "parameters": { ... } },
      "sessionInfo": { "parameters": { "disease": "Parkinson's" } }
    }
    """
    try:
        body: dict = request.get_json(force=True) or {}
        logger.info("Webhook received — intent payload keys: %s", list(body.keys()))

        # ── Auto-detect payload format and parse ─────────────────────────────
        if _is_dialogflow_es(body):
            intent_name, params = _parse_es_payload(body)
            logger.info("Format: Dialogflow ES  |  Intent: '%s'", intent_name)
        else:
            intent_name, params = _parse_cx_payload(body)
            logger.info("Format: Dialogflow CX  |  Intent: '%s'", intent_name)

        logger.info("Params: %s", params)

        # ── Dispatch ─────────────────────────────────────────────────────────
        handler = INTENT_ROUTER.get(intent_name)
        if handler:
            response = handler(params)
        else:
            logger.warning("No handler for intent: '%s'", intent_name)
            response = handle_unknown_intent(intent_name)

        return jsonify(response), 200

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Unhandled exception in webhook: %s", exc)
        error_response = _cx_response([
            "I encountered an internal error. Please try again shortly."
        ])
        return jsonify(error_response), 500


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # render.com sets PORT automatically; default to 8080 locally.
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting NARQ webhook on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
