import os
from flask import Flask, request, jsonify
import rdflib

app = Flask(__name__)

# Load Ontology
g = rdflib.Graph()
try:
    g.parse("NeuroTriageOntology.owl", format="xml")
    print("Ontology loaded successfully.")
except Exception as e:
    print(f"Error loading ontology: {e}")

# Define the standard Prefix for your project
PREFIXES = """
PREFIX nto: <http://www.semanticweb.org/NeuroTriageOntology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True)
    if not req: return jsonify({"fulfillmentText": "Invalid request."})

    query_result = req.get('queryResult', {})
    intent_name = query_result.get('intent', {}).get('displayName')
    parameters = query_result.get('parameters', {})
    
    # Helper to clean/flatten parameters (fixes the ['Parkinson's'] list error)
    def clean(val):
        if isinstance(val, list) and len(val) > 0: val = val[0]
        return str(val).replace("'", "\\'").strip() if val else ""

    if intent_name == "GetPrimarySymptoms":
        return get_primary_symptoms(clean(parameters.get('disease')))
    
    elif intent_name == "GetOverlappingSymptoms":
        return get_overlapping(clean(parameters.get('disease')), clean(parameters.get('disease1')))
    
    elif intent_name == "GetRiskFactors":
        return get_risk_factors(clean(parameters.get('disease')))

    return jsonify({"fulfillmentText": "Webhook active. Intent not recognized."})

def get_primary_symptoms(disease):
    if not disease: return jsonify({"fulfillmentText": "Please specify a disease."})
    
    # FIX: Explicit SELECT structure with WHERE and PREFIX
    query = PREFIXES + f"""
    SELECT DISTINCT ?sLabel
    WHERE {{
        ?d rdfs:label ?dLabel .
        FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease}")))
        ?d nto:hasPrimarySymptom ?s .
        ?s rdfs:label ?sLabel .
    }}
    """
    return execute_and_return(query, f"Primary symptoms for {disease}: ")

def get_overlapping(d1, d2):
    if not d1 or not d2: return jsonify({"fulfillmentText": "I need two diseases to compare shared symptoms."})
    
    query = PREFIXES + f"""
    SELECT DISTINCT ?sLabel
    WHERE {{
        ?dis1 rdfs:label ?dl1 . FILTER(CONTAINS(LCASE(STR(?dl1)), LCASE("{d1}")))
        ?dis2 rdfs:label ?dl2 . FILTER(CONTAINS(LCASE(STR(?dl2)), LCASE("{d2}")))
        ?dis1 nto:hasSymptom ?s .
        ?dis2 nto:hasSymptom ?s .
        ?s rdfs:label ?sLabel .
    }}
    """
    return execute_and_return(query, f"Shared symptoms between {d1} and {d2}: ")

def get_risk_factors(disease):
    if not disease: return jsonify({"fulfillmentText": "Please specify a disease for risk factors."})
    
    query = PREFIXES + f"""
    SELECT DISTINCT ?fLabel
    WHERE {{
        ?d rdfs:label ?dLabel .
        FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease}")))
        ?d nto:hasRiskFactor ?f .
        ?f rdfs:label ?fLabel .
    }}
    """
    return execute_and_return(query, f"Risk factors for {disease}: ")

def execute_and_return(query, prefix_text):
    try:
        results = [str(row.sLabel if hasattr(row, 'sLabel') else row.fLabel) for row in g.query(query)]
        if results:
            clean_list = ", ".join(list(set(results))).replace("_", " ")
            return jsonify({"fulfillmentText": f"{prefix_text}{clean_list}."})
        return jsonify({"fulfillmentText": f"I found no records matching that request in the NeuroTriage ontology."})
    except Exception as e:
        print(f"SPARQL Error: {e}")
        return jsonify({"fulfillmentText": "I encountered a technical error querying the ontology."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))