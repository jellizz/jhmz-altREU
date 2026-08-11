"""
Analyzes the first author of each reference in a JSON of references. 
Analyzes by:
    Author gender
    Author citations
    Author productivity
"""

##### pseudocode for first author identifier
# If the citation was hallucinated, we want to verify if the author actually exists. 
# Check if the first author exists in the database (Google Scholar, Crossref, OpenAlex, etc.) by searching for their name and seeing if they have any publications.

# 1. Parse first authors from hallucinated references

# 2. Check if first author exists in database

# 3. Infer author gender 

# 4. If real, get author citations

# 5. If real, get author publications