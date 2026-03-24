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

    # Helper to clean/flatten parameters
    def clean(val):
        if isinstance(val, list) and len(val) > 0:
            val = val[0]
        # Escape single quotes and handle empty values
        return str(val).replace("'", "''").strip() if val else ""

    if intent_name == "GetPrimarySymptoms":
        return get_primary_symptoms(clean(parameters.get('disease')))
    
    elif intent_name == "GetOverlappingSymptoms":
        return get_overlapping(clean(parameters.get('disease')), clean(parameters.get('disease1')))
    
    elif intent_name == "GetRiskFactors":
        return get_risk_factors(clean(parameters.get('disease')))

    return jsonify({"fulfillmentText": "Webhook is active, but the intent was not recognized."})

def get_primary_symptoms(disease):
    if not disease:
        return jsonify({"fulfillmentText": "Please specify a disease name."})
    
    # Query with FILTER at the end to avoid parser errors
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
        return jsonify({"fulfillmentText": "I need two diseases to compare. For example, 'What symptoms are shared between ALS and Parkinson's?'"})
    
    query = f"""
    PREFIX nto: <http://www.semanticweb.org/NeuroTriageOntology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?sLabel
    WHERE {{
        ?dis1 rdfs:label ?dl1 .
        ?dis2 rdfs:label ?dl2 .
        ?dis1 nto:hasSymptom ?s .
        ?dis2 nto:hasSymptom ?s .
        ?s rdfs:label ?sLabel .
        FILTER(CONTAINS(LCASE(STR(?dl1)), LCASE("{d1}")))
        FILTER(CONTAINS(LCASE(STR(?dl2)), LCASE("{d2}")))
    }}
    """
    return execute_query(query, f"The shared symptoms between {d1} and {d2} include: ")

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
        # Handle different variable names dynamically
        results = []
        for row in query_results:
            for val in row:
                results.append(str(val))
        
        if results:
            # Remove duplicates and clean formatting
            unique_results = list(set(results))
            formatted_list = ", ".join(unique_results).replace("_", " ")
            return jsonify({"fulfillmentText": f"{response_prefix}{formatted_list}."})
        
        return jsonify({"fulfillmentText": f"I couldn't find any specific information for that request in the ontology."})
    except Exception as e:
        print(f"SPARQL Execution Error: {e}")
        return jsonify({"fulfillmentText": "I'm having trouble accessing the clinical data right now."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)