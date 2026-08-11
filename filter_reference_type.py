"""
Parses JSON of combined verified, partial hallucinated, and fully hallucinated references to get a list of only one type of reference.

Takes files creataed from verification.py.
"""

# set status to get a list of real or fake hallucinations from the main file

status = "" # Options: "verified", "partial", "hallucinated"
output_file = "xx_references.json" # Change name as you see fit
input_files = ["", ""] # Add files (created from verification.py) to get a list of a certain type of reference

