'''
Takes pulled abstracts (JSON) and injects each into the prompt base. 
Feeds each prompt to the LLM and stores its responses as a JSON.
'''

# will probably format responses in a json like:
'''
{
    "id": id,
    "model": llm,
    "response": {
        "question": xxx,
        "answer": xxx,
        "references": xxx
    }
}
'''

import os
import json


# 1a. Load current JSON, if it exists. Build off of this.
# (Safeguard for if it crashes in the middle, can pick up where it left off)
def load_file(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return []


# 1b. Parse the abstracts JSON for an abstract; cross-check ids of abstract
# JSON and current JSON being build to ensure that an abstract
# has not been prompted with yet
def completed_abstract_ids(filename):
    content = load_file(filename)
    completed_abstracts = []
    for abstract in content:
        completed_abstracts.append(abstract["id"])
    return completed_abstracts


# 2. Inject the abstract into the prompt base
def build_prompt(abstract, prompt_base):
    pass

# 3. Make call to LLM API to prompt
    # determine which LLM is being prompted
    # based on LLM, make call
        # OpenAI
        #response.choices[0].message.content

        # Llama
        #response["completion_message"]["content"]["text"]

        # Anthropic
        #response.content[0].text

        # Gemini
        #response["candidates"][0]["content"]["parts"][0]["text"]
def prompt_llm(prompt, llm):
    pass

# 4. Store response, along with other info, into new JSON
def parse_response(response):
    pass

def build_json(filename, id, llm, question, answer, references):
    pass

    '''
    {
        "id": id,
        "model": llm,
        "response": {
            "question": ,
            "answer": ,
            "references": 
        }
    }
    '''

# 5. Repeat
