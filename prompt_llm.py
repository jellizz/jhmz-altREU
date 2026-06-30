'''
Takes pulled abstracts (JSON) and injects each into the prompt base. 
Feeds each prompt to the LLM and stores its responses as a JSON.
'''

# will probably format responses in a json like:
'''
{
    "id": abstract_id,
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
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from llama_api_client import LlamaAPIClient
from anthropic import Anthropic
from google import genai

'''
openai_client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)

llama_client = LlamaAPIClient(
    api_key=os.environ.get("LLAMA_API_KEY"),  # This is the default and can be omitted
)

anthropic_client = Anthropic(
    # This is the default and can be omitted
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
)

gemini_client = genai.Client()'''


prompt_base_tsk1 = "TASK 1: words..."
prompt_base_tsk2 = "TASK 2: more words..."
abstracts_file = "test_prompt_llm.json"


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

def build_prompt(abstract):
    return f"{prompt_base_tsk1} Abstract: {abstract} {prompt_base_tsk2}"


# 3. Make call to LLM API to prompt
    # determine which LLM is being prompted
    # based on LLM, make call
        # OpenAI
            # https://developers.openai.com/api/docs/quickstart
            # https://developers.openai.com/api/reference/python
        #response.choices[0].message.content

        # Llama
            # https://github.com/meta-llama/llama-api-python
        #response["completion_message"]["content"]["text"]

        # Anthropic
            # https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python
        #response.content[0].text

        # Gemini
            # https://ai.google.dev/gemini-api/docs/get-started 
        #response.output_text

def prompt_llm(prompt, llm):
    # !!! double check what all the response format jsons look like !!! gemini is checked
    # !!! determine correct models and change below
    # also, this currently only returns the llm's response. do we want other info, like tokens used?
    if llm == "openai":
        client = openai_client
        response = client.chat.completions.create(
            model="gpt-5.5", 
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    elif llm == "llama":
        client = llama_client
        response = client.chat.completions.create(
            messages=[
                {
                    "content": prompt,
                    "role": "user",
                }
            ],
            model="model",
        )
        return response["completion_message"]["content"]["text"]
    elif llm == "anthropic":
        client = anthropic_client
        response = client.messages.create(
            max_tokens=1024, # DETERMINE THIS???
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="claude-opus-4-8",
        )
        return response.content[0].text
    elif llm == "gemini":
        client = gemini_client
        response = client.interactions.create(
            model="gemini-3.5-flash",
            input=prompt
        )
        return response.output_text
    else:
        return "QUESTION:\nWhat is a pineapple?\nANSWER:\nA fruit.\nREFERENCES:\n[1] Doe, John. (2026). Pineapple. Pineapple Journal, 1(23), 45-67. DOI: pineapple.com.\n[2] Doe, Jane. (1234). Original Pineapple. Pineapple Origins, 1(23), 45-67. DOI: pineapple.og.com."
        

# 4. Store response, along with other info, into new JSON
# breaks the response into 'question', 'answer', 'references'
# !!! NEED TO TEST LLM RESPONSE to see if it actually formats how we want, bc this depends on the llm response format

def parse_response(response):
    '''
    say the LLM's response looks like this:
        "QUESTION:
        wordy words.
        ANSWER:
        words, words.
        REFERENCES:
        references."
    '''
    temp1 = response.split("QUESTION:\n") # ["", "wordy words. ANSWER: words, words. REFERENCES: references."]
    temp2 = temp1[1].split("\nANSWER:\n") # ["wordy words.", "words, words. REFERENCES: references."]
    temp3 = temp2[1].split("\nREFERENCES:\n") # ["words, words.", "references."]
    question = temp2[0]
    answer = temp3[0]
    references = temp3[1]
    return question, answer, references


def build_json(filename, abstract_id, llm, question, answer, references):
    output_file = load_file(filename)

    new_entry = {
        "id": abstract_id, 
        "model": llm,
        "response": {
            "question": question, 
            "answer": answer,
            "references": references
        }
    }

    output_file.append(new_entry)
    with open(filename, "w") as f:
        json.dump(output_file, f)


# 5. Repeat
# write main loop in here, later combine everything outside in main.py?

if __name__ == "__main__":
    llm = "testing" # update for different LLMs
    abstracts = load_file(abstracts_file)
    output_file = "test_responses.json" # update name for different LLMs
    completed_abstracts = completed_abstract_ids(output_file)

    for abstract in abstracts:
        abstract_id = abstract["id"]
        if abstract_id in completed_abstracts:
            continue

        prompt = build_prompt(abstract["abstract"])
        response = prompt_llm(prompt, llm)
        question, answer, references = parse_response(response)
        build_json(output_file, abstract_id, llm, question, answer, references)

# This currently spits out one big string... probably should fix format
# Also, it seems to work with hardcoded data. Dunno about LLM calls.