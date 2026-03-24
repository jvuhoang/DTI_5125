import os
from flask import Flask, request, jsonify
import rdflib

app = Flask(__name__)

# 1. Load the Ontology
# This happens once when the server starts for high performance
g = rdflib.Graph()
try:
    g.parse("NeuroTriageOntology.owl", format="xml")
    print("Ontology loaded successfully.")
except Exception as e:
    print(f"Error loading ontology: {e}")

# Define Namespace
NTO = rdflib.Namespace("http://www.semanticweb.org/NeuroTriageOntology#")
RDFS = rdflib.RDFS

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True)
    if not req:
        return jsonify({"fulfillmentText": "Invalid request."})

    query_result = req.get('queryResult', {})
    intent_name = query_result.get('intent', {}).get('displayName')
    parameters = query_result.get('parameters', {})

    # Route to the correct logic based on Intent Name
    if intent_name == "GetPrimarySymptoms":
        return get_primary_symptoms(parameters.get('disease'))
    
    elif intent_name == "GetDiseaseFromSymptom":
        return get_disease_from_symptom(parameters.get('symptom'))
    
    elif intent_name == "GetOverlappingSymptoms":
        # Supports parameters 'disease' and 'disease1' from your Dialogflow setup
        d1 = parameters.get('disease')
        d2 = parameters.get('disease1')
        return get_overlapping_symptoms(d1, d2)
    
    elif intent_name == "GetRiskFactors" or intent_name == "GetLifestyleRiskFactors":
        return get_risk_factors(parameters.get('disease'))
    
    elif intent_name == "DifferentiateByDisease":
        d1 = parameters.get('disease')
        d2 = parameters.get('disease1')
        return differentiate_diseases(d1, d2)

    return jsonify({"fulfillmentText": "I'm connected to the ontology, but I don't have logic for this intent yet."})

# --- Helper Functions (The Logic) ---

def get_primary_symptoms(disease_label):
    if not disease_label: return jsonify({"fulfillmentText": "Which disease are you asking about?"})
    
    query = f"""
    SELECT ?sLabel WHERE {{
        ?d rdfs:label ?dLabel .
        FILTER(LCASE(STR(?dLabel)) = LCASE("{disease_label}"))
        ?d <http://www.semanticweb.org/NeuroTriageOntology#hasPrimarySymptom> ?s .
        ?s rdfs:label ?sLabel .
    }}
    """
    results = [str(row.sLabel) for row in g.query(query)]
    if results:
        return jsonify({"fulfillmentText": f"The primary symptoms for {disease_label} include: {', '.join(results)}."})
    return jsonify({"fulfillmentText": f"I couldn't find specific primary symptoms for {disease_label} in my records."})

def get_disease_from_symptom(symptom_label):
    if not symptom_label: return jsonify({"fulfillmentText": "Which symptom are you concerned about?"})
    
    query = f"""
    SELECT ?dLabel WHERE {{
        ?s rdfs:label ?sLabel .
        FILTER(CONTAINS(LCASE(STR(?sLabel)), LCASE("{symptom_label}")))
        ?d <http://www.semanticweb.org/NeuroTriageOntology#hasSymptom> ?s .
        ?d rdfs:label ?dLabel .
    }}
    """
    results = list(set([str(row.dLabel) for row in g.query(query)])) # Unique list
    if results:
        return jsonify({"fulfillmentText": f"{symptom_label} can be associated with: {', '.join(results)}."})
    return jsonify({"fulfillmentText": f"I don't have information on which diseases are linked to {symptom_label}."})

def get_overlapping_symptoms(d1, d2):
# If d2 is empty, check if d1 was sent as a list by Dialogflow 
    # (Sometimes Dialogflow sends ['ALS', 'Parkinsons'] as one parameter)
    if isinstance(d1, list) and len(d1) >= 2:
        d2 = d1[1]
        d1 = d1[0]

    if not d1 or not d2: 
        return jsonify({"fulfillmentText": "I recognized one disease, but I need two to find overlaps. (e.g., 'What are the shared symptoms between ALS and Parkinson's?')" })  
    query = f"""
    SELECT ?sLabel WHERE {{
        ?dis1 rdfs:label ?dl1 . FILTER(LCASE(STR(?dl1)) = LCASE("{d1}"))
        ?dis2 rdfs:label ?dl2 . FILTER(LCASE(STR(?dl2)) = LCASE("{d2}"))
        ?dis1 <http://www.semanticweb.org/NeuroTriageOntology#hasSymptom> ?s .
        ?dis2 <http://www.semanticweb.org/NeuroTriageOntology#hasSymptom> ?s .
        ?s rdfs:label ?sLabel .
    }}
    """
    results = list(set([str(row.sLabel) for row in g.query(query)]))
    if results:
        return jsonify({"fulfillmentText": f"The shared symptoms between {d1} and {d2} are: {', '.join(results)}."})
    return jsonify({"fulfillmentText": f"I couldn't find any overlapping symptoms between {d1} and {d2} in the ontology."})

def get_risk_factors(disease_label):
    # If the user says "ALS", we want it to match "Amyotrophic Lateral Sclerosis"
    # We use CONTAINS and LCASE to make the search flexible
    query = f"""
    SELECT ?fLabel WHERE {{
        ?d rdfs:label ?dLabel . 
        FILTER(CONTAINS(LCASE(STR(?dLabel)), LCASE("{disease_label}")) || 
               CONTAINS(LCASE("{disease_label}"), LCASE(STR(?dLabel))))
        ?d <http://www.semanticweb.org/NeuroTriageOntology#hasRiskFactor> ?f .
        ?f rdfs:label ?fLabel .
    }}
    """
    results = [str(row.fLabel) for row in g.query(query)]
    if results:
        return jsonify({"fulfillmentText": f"Identified risk factors for {disease_label}: {', '.join(results)}."})
    return jsonify({"fulfillmentText": f"I couldn't find risk factors for {disease_label} in the ontology."})

def differentiate_diseases(d1, d2):
    # This combines logic to show what makes them different
    if not d1 or not d2: return jsonify({"fulfillmentText": "Tell me which two diseases you'd like to differentiate."})
    
    # Logic: Find symptoms that are PRIMARY to d1 but NOT d2
    query = f"""
    SELECT ?sLabel WHERE {{
        ?dis1 rdfs:label ?dl1 . FILTER(LCASE(STR(?dl1)) = LCASE("{d1}"))
        ?dis1 <http://www.semanticweb.org/NeuroTriageOntology#hasPrimarySymptom> ?s .
        ?s rdfs:label ?sLabel .
        MINUS {{
            ?dis2 rdfs:label ?dl2 . FILTER(LCASE(STR(?dl2)) = LCASE("{d2}"))
            ?dis2 <http://www.semanticweb.org/NeuroTriageOntology#hasPrimarySymptom> ?s .
        }}
    }}
    """
    unique_to_d1 = [str(row.sLabel) for row in g.query(query)]
    
    response = f"While {d1} and {d2} may share some features, {d1} is more typically characterized by {', '.join(unique_to_d1[:3])}."
    return jsonify({"fulfillmentText": response})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)