import requests
from flask import request, make_response
import io
from pypdf import PdfReader
import re
from escape_helpers import sparql_escape_uri, sparql_escape_string
from helpers import generate_uuid, query, update, logger
from string import Template

BESLUIT_TYPE = 'https://id.erfgoed.net/vocab/ontology#Besluit'
FILE_RESOURCE_BASE = 'http://mu.semte.ch/services/file-service/files/'
GRAPH = 'http://mu.semte.ch/graphs/public'

# def get_decision_file(besluit_uri):
#     response = requests.get(besluit_uri, headers={
#         'Accept': 'application/json'
#     }).json()

#     files = [
#         f'{besluit_uri}/bestanden/{bestand["id"]}'
#         for bestand in response['bestanden']
#         if (
#             bestand['bestandssoort']['soort'] == 'Besluit'
#             and not bestand['naam'].endswith('metcert.pdf')
#         )
#     ]

#     return files[0]


def get_file_content(file_uri):
    response = requests.get(decision_file_uri)
    response.raise_for_status()  
    
    return io.BytesIO(response.content)


def pdf_to_str(content):
    reader = PdfReader(content)
    all_lines = []

    for page in reader.pages:
        text = page.extract_text()
        for line in text.split('\n'):
            if not re.match(r"^\s{0,}(Pagina\s\d+\svan\s\d+\s{0,})?$", line):
                all_lines.append(line.strip())
    
    one_string = '[[--PAGE BREAK--]]'.join(all_lines)

    return one_string


@app.route('/decisions/<decision_id>')
def get_decision(decision_id):
    decision_uri = f'https://besluiten.onroerenderfgoed.be/besluiten/{decision_id}'
    decision_file_uri = get_decision_file(decision_uri)
    return get_decision_content(decision_file_uri)


def get_resource_files(besluit):
    query_string = Template("""
        PREFIX ext: <http://mu.semte.ch/vocabularies/ext/>
        
        SELECT * WHERE {
            $besluit ext:file/nie:url ?url .
        } 
    """,
        besluit=sparql_escape_uri(besluit))

    response = query(query_string)

    app.logger.info(response)
    return response


def file_to_shared_uri(file_name):
    return f'share://{file_name}'


def insert_file_resource():
    upload_resource_uuid = generate_uuid()
    upload_resource_name = params['file'][:filename]
    upload_resource_uri = f"{FILE_RESOURCE_BASE}{upload_resource_uuid}"

    file_format = 'text/plain'
    file_extension = 'txt'

    file_resource_uuid = generate_uuid()
    file_resource_name = f"{file_resource_uuid}.{file_extension}"
    file_resource_uri = file_to_shared_uri(file_resource_name)

    # Lite version of files, shortcut because little time 
    # Only necessary props are added
    query_string = Template('''
        PREFIX nfo: <http://www.semanticdesktop.org/ontologies/2007/03/22/nfo>
        PREFIX mu: <http://mu.semte.ch/vocabularies/core/>
        PREFIX nie: <http://www.semanticdesktop.org/ontologies/2007/01/19/nie#>

        INSERT DATA {
            GRAPH $graph {
                $upload_resource_uri 
                    a nfo:FileDataObject ;
                    nfo:fileName $upload_resource_name ;
                    mu:uuid $upload_resource_uuid .
                
                $file_resource_uri 
                    a nfo:FileDataObject ;
                    nie:dataSource $upload_resource_uri ;
                    nfo:fileName $file_resource_name ;
                    mu:uuid $file_resource_uuid .
            }
        }
    ''',
        graph=sparql_escape_uri(GRAPH),
        upload_resource_uri=sparql_escape_uri(upload_resource_uri),
        upload_resource_name=sparql_escape_string(upload_resource_uri),
        upload_resource_uuid=sparql_escape_string(upload_resource_uuid),
        file_resource_uri=sparql_escape_uri(file_resource_uri),
        file_resource_name=sparql_escape_string(file_resource_name),
        file_resource_uuid=sparql_escape_string(file_resource_uuid)
    )

    update(query_string)

    return file_resource_uri, file_resource_name


def insert_decision(besluit_uri, text):
    file_uri, file_name = insert_file_resource()

    with open(f'/share/{file_name}', 'w') as f:
        f.write(text)
    
    add_file_to_decision(besluit_uri, file_uri)


def add_file_to_decision(besluit_uri, file_uri):
    query_string = Template('''
        PREFIX ext: <http://mu.semte.ch/vocabularies/ext/>

        INSERT DATA {
            GRAPH $graph {
                $decision ext:geextraheerdeTekstBestand $file .
            }
        }
    ''',
        graph=sparql_escape_uri(GRAPH),
        decision=sparql_escape_uri(besluit_uri),
        file=sparql_escape_uri(file_uri)
    )

    update(query_string)


@app.route('/delta')
def delta():
    data = request.get_json(force=True)
    inserts = data['inserts']
    for insert in inserts:
        if (
            insert['predicate'] == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' 
            and insert['object'] == BESLUIT_TYPE
        ):
            besluit_uri = insert['subject']
            urls = get_resource_files(besluit_uri)
            for url in urls:
                pdf_content = get_file_content(url)
                text = pdf_to_str(pdf_content)
                insert_decision(besluit_uri, text)

    return ''