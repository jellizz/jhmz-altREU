"""
Verfies that citations exist, given a list of citations in APA formatting.
Based on tools such as Hallucite Checker & CheckIfExist, working by checking if the citation exists in Google Scholar, Crossref, OpenAlex, 
or other databases.
"""

##### pseudocode for hallucination checker

# 1. Load citation string from JSON file
# 2. Parse references as list from citation string
# 3. For each reference, check if it exists in Google Scholar, Crossref, OpenAlex, or other databases
#   3a. checking if title exists (if not, then it is a hallucinated reference).
#   3b. checking if author names exist for that title (if not, then it is a hallucinated reference).
#   3c. checking if DOI exists for that title (if not, then it is a hallucinated reference).
# 4. Return a list of references that do not exist!!

##### pseudocode for first author identifier
# 1. If the citation was hallucinated, we want to verify if the author actually exists. Check if the first author exists in the database (Google Scholar, Crossref, OpenAlex, etc.) by searching for their name and seeing if they have any publications.
