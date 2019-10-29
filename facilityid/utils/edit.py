# TODO: Create a function to extract unused ids and the max used id
# TODO: Create an edit function for assigning the next available id
# TODO: Create edit functions for each case (e.g. one for No id, one for no prefix, etc) (7 total)
def extract_incorrect(rows: list, prefix: str) -> dict:
    for row in rows:
        # All possible edits fall into these seven categories
        row_edits = {
            "NO_PREFIX": None,
            "NO_CAP": None,
            "WRONG_PREFIX": None,
            "NO_ID": None,
            "LEAD_ZEROS": None,
            "EMPTY": None,
            "DUPLICATE": None
        }
        # If a FACILITYID exists for the row, break out the 
        # component parts and analyze the need for edits based 
        # on the criteria above
        if row["FACILITYID"]:
            pfix = row["FACILITYID"]["prefix"]
            id_str = row["FACILITYID"]["str_id"]
            id_int = int(id_str)

            # EDITS TO THE PREFIX
            # Check if the prefix of the row does not exist
            row_edits["NO_PREFIX"] = not pfix
            # Check if the prefix of the row is not capitalized
            row_edits["NO_CAP"] = not pfix.isupper()
            # Check if the prefix of the row is completely wrong
            row_edits["WRONG_PREFIX"] = pfix.upper() != prefix

            # EDITS TO THE ID
            # Check if the row does not have an ID
            row_edits["NO_ID"] = not id_str
            # Check if the ID has leading zeros
            row_edits["LEAD_ZEROS"] = len(id_str) != len(str(id_int))
            # Check if the ID is duplicated in the table
            row_edits["DUPLICATE"] = None
        else:
            # Check if the FACILITYID is completely empty
            row_edits["EMPTY"] = True
