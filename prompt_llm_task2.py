"""
Takes questions generated from abstracts and prompts the various LLMS for answers. Saves the responses to a new JSON file.
"""

# will format responses in a json like:
'''
{
    "id": abstract_id,
    "model": llm,
    "question": question,
    "response": {
        "answer": xxx,
        "references": {
            xxx,
            xxx,
            ...,
        }
    }
}
'''

import os
import json
import re
from dotenv import load_dotenv

from prompt_llm_task1 import completed_abstract_ids
load_dotenv()

from openai import OpenAI
from anthropic import Anthropic
from google import genai

openai_client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)

anthropic_client = Anthropic(
    # This is the default and can be omitted
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
)

gemini_client = genai.Client()


# ----------------------------------------------------------------------
# PROMPT BASES CAN BE WRITTEN HERE! Open to modification as we run test cases.
# ----------------------------------------------------------------------

# Prompt base(s) that will be injected with the question. 
prompt_base_v1 = (
    """Answer the provided scientific question and justify your answer using at least 5 scientific references, but use as many as needed to get your point across. References must have: Author name(s), article title, journal, year of publication, and a DOI.
References should follow the format: Last, Firstname Middlename. (Year). Title of article. Title of Journal, Volume(Issue), Page-Range. DOI: doi.org/xxxxx. 

You must format your response EXACTLY as follows, with no other text before or after:
ANSWER:
<your answer here>
REFERENCES:
<your references here, one per line>

""" 
)

# does not require that the answer be fully written out.
prompt_base_v2 = """Given a provided scientific question, provide a concise answer (less than 100 words) supported by at least 5 academic references. Do not include any reasoning, commentary, or explanation for why you selected the references. 

References must include: Author name(s), article title, journal, year of publication, and a DOI.
References should follow the format: Last, Firstname Middlename. (Year). Title of article. Title of Journal, Volume(Issue), Page-Range. DOI: doi.org/xxxxx. 

You must format your response EXACTLY as follows, with no other text before or after:
ANSWER:
<your concise answer here, must be less than 100 words>
REFERENCES:
<your references here, strictly one reference per line with no commentary>
""" 


# 1a. Load current JSON, if it exists. Build off of this.
# (Safeguard for if it crashes in the middle, can pick up where it left off)

def load_file(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    return []


# 1b. Parse the QUESTIONS JSON for a question.

def completed_questions(filename):
    content = load_file(filename)
    completed_questions = []
    for question in content:
        completed_questions.append(question["id"])
    return completed_questions


# 2. Inject the question into the prompt base

def build_prompt(question, prompt_base=prompt_base_v1):
    return f"{prompt_base}. Answer this specific question: {question}"


# 3. Make call to LLM API to prompt
    # determine which LLM is being prompted
    # based on LLM, make call
        # OpenAI
            # https://developers.openai.com/api/docs/quickstart
            # https://developers.openai.com/api/reference/python
        #response.choices[0].message.content


        # Anthropic
            # https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python
        #response.content[0].text

        # Gemini
            # https://ai.google.dev/gemini-api/docs/get-started 
        #response.output_text

def prompt_llm(prompt, llm):

    if llm == "openai":
        client = openai_client
        response = client.chat.completions.create(
            model="gpt-5.5", 
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    elif llm == "anthropic":
        client = anthropic_client
        response = client.messages.create(
            max_tokens=2000, # DETERMINE THIS??? (this is cutting off our responses WITH ANSWERS)
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
    else: # for testing purposes, if you want to see what the rest of the code does without actually calling an LLM
        return "QUESTION:\nWhat is a pineapple?\nANSWER:\nA fruit.\nREFERENCES:\n[1] Doe, John. (2026). Pineapple. Pineapple Journal, 1(23), 45-67. DOI: pineapple.com.\n[2] Doe, Jane. (1234). Original Pineapple. Pineapple Origins, 1(23), 45-67. DOI: pineapple.og.com."
        

# 4. Store response, along with other info, into new JSON
# breaks the response into 'question', 'answer', 'references'
# !!! NEED TO TEST LLM RESPONSE to see if it actually formats how we want, bc this depends on the llm response format

# parse first, then build the JSON and save it to the output file.
ANSWER_RE = re.compile(
    r"(?:\*\*|###\s*)?ANSWER:\s*(?:\*\*)?\s*(.*?)\s*(?:\*\*|###\s*)?REFERENCES:\s*(?:\*\*)?\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)

def parse_response(raw_response):
    """
    Parses the raw response from the LLM into an answer and as a list of references."""
    
    match = ANSWER_RE.search(raw_response)
    if not match:
        # Model didn't follow the format
        # stash the whole thing as the answer and flag it for review.
        return raw_response.strip(), ["check response b/c it didn't follow the expected format"]
    answer = match.group(1).strip()
    references_raw = match.group(2).strip()
    
    # Split references by newline, remove bullets, numbers, and whitespace, and ignore empty lines
    references = []
    for line in references_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^(\d+\.|\[\d+\]|\-|\*)\s*", "", line)
        references.append(line)

    return answer, references # a string, a list of strings.
    




def build_json(filename, abstract_id, llm, question, answer, references):
    output_file = load_file(filename)

    new_entry = {
        "id": abstract_id, 
        "model": llm,
        "question": question, 
        "response": {
            "answer": answer, 
            "references": references # LIST.
        },
    }

    output_file.append(new_entry)
    with open(filename, "w") as f:
        json.dump(output_file, f, indent = 4)

def generate_responses(questions_file, output_file, llm="testing", prompt_base=prompt_base_v2):
    """
    Reads lit-review questions from questions_file, prompts the given llm for a
    literature-review-style answer on each one, and adds results
    to output_file. Safe to re-run as well, as it skips any question id already
    present in output_file (won't re-run questions).

    Has an optional prompt_base parameter (for testing or for different prompt styles, defaults to
    one without full response to limit tokens used).
    """
    questions = load_file(questions_file)
    done_ids = set(completed_questions(output_file))

    for q in questions:
        qid = q["id"]
        if qid in done_ids:
            continue

        prompt = build_prompt(q["question"], prompt_base=prompt_base) 
        try:
            raw_response = prompt_llm(prompt, llm)
        except Exception as e:
            print(f"  [{qid}] ERROR calling {llm}: {e}")
            continue

        answer, references = parse_response(raw_response)
        build_json(output_file, qid, llm, q["question"], answer, references)
        print(f"  [{qid}] done")

    print(f"Done. Responses saved to {output_file}")

# 5. Repeat
# write main loop in here, later combine everything outside in main.py?

if __name__ == "__main__":
    # calling on anthropic and test_questions.json
    generate_responses(
        questions_file="data/questions/questions_S1980519.json",
        output_file="data/responses/anthropic/responses_anthropic_physics_astrophys.json",
        llm="anthropic",
        prompt_base=prompt_base_v2
    )

    # # calling on anthropic and abstracts_S24807848.json (Physical Review Letters)
    # generate_responses(
    #     questions_file="data/abstracts_S24807848.json",
    #     output_file="data/responses_physics_prl_anthropic.json",
    #     llm="anthropic",
    #     prompt_base=prompt_base_v2
    # )
