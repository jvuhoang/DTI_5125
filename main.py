import os
from flask import Flask, request, jsonify
import rdflib

app = Flask(__name__)

# Load the Ontology
g = rdflib.Graph()
try:
    g.parse("NeuroTriageOntology.owl", format="xml")
    print("Ontology loaded successfully.")
except Exception as e:
    print(f"Error loading ontology: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True)
    if not req:
        return jsonify({"fulfillmentText": "Invalid request."})

    query_result = req.get('queryResult', {})
    intent_name = query_result.get('intent', {}).get('displayName')
    parameters = query_result.get('parameters', {})

    def clean(val):
        if isinstance(val, list) and len(val) > 0:
            val = val[0]
        if not val:
            return ""
        return str(val).replace("'", "''").strip()

    if intent_name == "GetPrimarySymptoms":
        return get_primary_symptoms(clean(parameters.get('disease')))
    elif intent_name == "GetOverlappingSymptoms":
        return get_overlapping(clean(parameters.get('disease')), clean(parameters.get('disease1')))
    elif intent_name == "GetRiskFactors":
        return get_risk_factors(clean(parameters.get('disease')))

    return jsonify({"fulfillmentText": "Webhook is active, but the intent was not recognized."})


def get_symptoms_for_disease(disease_filter):
    """Return a set of symptom labels for a single disease. Tries hasPrimarySymptom first."""
    query = f"""
    PREFIX nto: <http://www.semanticweb.org/NeuroTriageOntology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?sLabel
    WHERE {{
        ?d rdfs:label ?dLabel .
        ?d nto:hasPrimarySymptom ?s .
        ?s rdfs:label ?sLabel .
        FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease_filter}")))
    }}
    """
    results = set()
    for row in g.query(query):
        results.add(str(row[0]))

    # Fallback to hasSymptom if nothing found
    if not results:
        query2 = f"""
        PREFIX nto: <http://www.semanticweb.org/NeuroTriageOntology#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?sLabel
        WHERE {{
            ?d rdfs:label ?dLabel .
            ?d nto:hasSymptom ?s .
            ?s rdfs:label ?sLabel .
            FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease_filter}")))
        }}
        """
        for row in g.query(query2):
            results.add(str(row[0]))

    return results


def get_primary_symptoms(disease):
    if not disease:
        return jsonify({"fulfillmentText": "Please specify a disease name."})
    query = f"""
    PREFIX nto: <http://www.semanticweb.org/NeuroTriageOntology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?sLabel
    WHERE {{
        ?d rdfs:label ?dLabel .
        ?d nto:hasPrimarySymptom ?s .
        ?s rdfs:label ?sLabel .
        FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease}")))
    }}
    """
    return execute_query(query, f"The primary symptoms for {disease} are: ")


def get_overlapping(d1, d2):
    if not d1 or not d2:
        return jsonify({"fulfillmentText": "I need two diseases to compare. Please name both diseases."})
    try:
        # Run two fast single-disease queries, intersect in Python — avoids UNION timeout
        symptoms_d1 = get_symptoms_for_disease(d1)
        symptoms_d2 = get_symptoms_for_disease(d2)
        shared = symptoms_d1 & symptoms_d2  # set intersection

        if shared:
            formatted = ", ".join(sorted(shared)).replace("_", " ")
            return jsonify({"fulfillmentText": f"The shared symptoms between {d1} and {d2} include: {formatted}."})
        else:
            return jsonify({"fulfillmentText": f"No overlapping symptoms were found between {d1} and {d2} in the ontology."})
    except Exception as e:
        print(f"Overlapping query error: {e}")
        return jsonify({"fulfillmentText": "I'm having trouble accessing the clinical data right now."})


def get_risk_factors(disease):
    if not disease:
        return jsonify({"fulfillmentText": "Which disease are you asking about?"})
    query = f"""
    PREFIX nto: <http://www.semanticweb.org/NeuroTriageOntology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?fLabel
    WHERE {{
        ?d rdfs:label ?dLabel .
        ?d nto:hasRiskFactor ?f .
        ?f rdfs:label ?fLabel .
        FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease}")))
    }}
    """
    return execute_query(query, f"The identified risk factors for {disease} are: ")


def execute_query(query, response_prefix):
    try:
        query_results = g.query(query)
        results = []
        for row in query_results:
            for val in row:
                results.append(str(val))
        if results:
            unique_results = list(set(results))
            formatted_list = ", ".join(unique_results).replace("_", " ")
            return jsonify({"fulfillmentText": f"{response_prefix}{formatted_list}."})
        return jsonify({"fulfillmentText": "I couldn't find any specific information for that request in the ontology."})
    except Exception as e:
        print(f"SPARQL Execution Error: {e}")
        return jsonify({"fulfillmentText": "I'm having trouble accessing the clinical data right now."})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
