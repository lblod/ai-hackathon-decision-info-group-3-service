import requests
from flask import request, make_response

BESLUIT_TYPE = 'https://schema.org/Project'

def get_decision_urls(besluit_uri):
    response = requests.get(besluit_uri)
    print(response)

@app.route('/decision')
def get_decision():
    decision_uri = request.args.get('uri')
    print(decision_uri)
    get_decision_urls(decision_uri)

    return make_response('', 200)


@app.route('/delta')
def delta():
    data = request.get_json(force=True)
    inserts = data['inserts']
    for insert in inserts:
        if insert['predicate'] == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' and insert['object'] == BESLUIT_TYPE:
            decision_urls = get_decision_urls(insert['subject'])
            for url in decision_urls:
                pdf_content = get_decision_content(url)
                text = extract_text(pdf_content)
                insert_decision(url)
                attach_decision_text(url, text)

    return ''