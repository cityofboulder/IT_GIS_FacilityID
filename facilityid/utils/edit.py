from datetime import datetime


def _merge(x):
    """Concatenate an ID back together."""

    p = x['FACILITYID']['prefix']
    i = x['FACILITYID']['str_id']
    return p + i


def _get_values(rows: list, field: str) -> list:
    """An internal function for returning all values of a particular
    column of the table."""

    values = [r[field] for r in rows]
    return values


def edit(rows: list, duplicates: list, prefix: str, geom_type: str) -> list:
    """Iterates through a list of rows, editing incorrect or duplicated
    entries along the way.

    This function edits duplicated FACILITYIDs first, followed by
    incorrect or missing FACILITYIDs. The function knows to edit
    incorrect IDs based on the following criteria:

        Prefix is not capitalized
        Prefix of the row does not exist
        Prefix does not equal the layer's designated prefix
        The ID does not exist
        The ID has leading zeros
        The ID has already been used

    Parameters
    ----------
    rows : list
        Rows represented as dictionaries, packaged in a list
    duplicates : list
        A list of GLOBALIDs that have duplicated FACILITYIDs
    prefix : str
        The correct prefix for the layer
    geom_type : str
        The type of geometry being evaluated

    Returns
    -------
    list
        Edited rows represented as dictionaries, packaged in a list
    """

    def get_ids() -> tuple:
        """Extracts lists of all used and unused ids (between the
        minimum and maximum ids).

        Returns
        -------
        used : list
            Used IDs, sorted in reverse order.
        unused : list
            Unused IDs, sorted in reverse order. The unused list is
            empty if all IDs between min and max have been assigned.
        """

        used = sorted([x["FACILITYID"]["int_id"]
                      for x in rows if x["FACILITYID"]["int_id"] is not None],
                      reverse=True)
        min_id = used[-1]

        # initiate a try block in case the max id is too large to compute a set
        # and overflows computer memory
        for m in used:
            try:
                set_of_all = set(range(min_id, m))
                set_of_used = set(used)
                unused = sorted(list(set_of_all - set_of_used), reverse=True)
                break
            except (OverflowError, MemoryError):
                continue

        return (used, unused)

    def apply_id(used: list, unused: list) -> int:
        """Finds the next best ID to apply to a row with missing or
        duplicated IDs.

        This function modifies both inputs by either popping the last
        item off the end of the unused list or incrementing the used
        list by 1

        Parameters
        ----------
        used : list
            A list of used IDs in the table, sorted in reverse order.
        unused : list
            A list of unused IDs between the minimum and maximum IDs in
            the feature class, sorted in reverse order.

        Returns
        -------
        int
            An integer number representing the next logical ID to assign
        """

        if unused:
            new_id = unused.pop()
        else:
            max_id = used[0] + 1
            used.insert(0, max_id)
            new_id = max_id

        return new_id

    def sorter(x):
        """A function meant to be used in the builtin sort function for
        lists.

        Dynamically sorts the lists of duplicates based on the shape
        type of the feature class in question.

        Parameters
        ----------
        x : dict
            Represents a single row from the list of rows

        Returns
        -------
        tuple
            The tuple that dictates how to multi-sort
        """

        # Define date to replace Null values in the sort
        # Null values first, followed byt oldest to newest
        _null_date = datetime(1400, 1, 1)

        def geom_sorter(g):
            """Determines the proper field to sort on based
            on the spatial data type."""

            if g == 'Polygon':
                return - x['SHAPE@'].area
            elif g == 'Polyline':
                return - x['SHAPE@'].length
            else:
                return (x['CREATED_DATE'] or _null_date)

        sort_1 = _merge(x)
        sort_2 = geom_sorter(geom_type)
        sort_3 = (x['LAST_EDITED_DATE'] or _null_date)

        return (sort_1, sort_2, sort_3)

    # Summarize IDs in the table
    used_ids, unused_ids = get_ids()
    # Initialize a list of rows that will need edits
    edited = list()

    # ------------------
    # EDITING DUPLICATES
    # ------------------
    # In order to be analyzed for duplication, the ID must have the
    # correct prefix
    if duplicates:
        # Identify rows that contain duplicate FACILITYIDs
        dup_rows = [row for row in rows if row['GLOBALID']
                    in duplicates and row['FACILITYID']['prefix'] == prefix]
        # Perform the sort
        dup_rows.sort(key=sorter)
        # Iterate through each unique ID in the duplicated rows
        distinct = set([_merge(r) for r in dup_rows])
        for i in distinct:
            chunk = [x for x in dup_rows if _merge(x) == i]
            # The last ID of the list (e.g. 'chunk[-1]'), does not need to be
            # edited, since all of its dupes have been replaced
            for c in chunk[:-1]:
                # Modify 'rows' input at function call so that they are not
                # inspected later on
                edit_row = rows.pop(rows.index(c))
                new_id = apply_id(used_ids, unused_ids)
                edit_row["FACILITYID"]["int_id"] = new_id
                edit_row["FACILITYID"]["str_id"] = str(new_id)
                edited.append(edit_row)

    # ------------------------
    # EDITING INCORRECT FACIDS
    # ------------------------
    # Prefix of the row does not exist
    # Prefix is not capitalized
    # Prefix does not equal the layer's designated prefix
    # The ID does not exist
    # The ID has leading zeros
    # The ID has already been used
    while rows:
        row = rows.pop(0)
        # Boolean describing whether edits needed to be made for the row
        edits = False
        pfix = row["FACILITYID"]["prefix"]
        str_id = row["FACILITYID"]["str_id"]
        int_id = row["FACILITYID"]["int_id"]

        # PREFIX EDITS
        if not pfix or not pfix.isupper() or pfix != prefix:
            row["FACILITYID"]["prefix"] = prefix
            edits = True

        # ID EDITS
        if not str_id or len(str_id) != len(str(int_id)) or int_id in used_ids:
            new_id = apply_id(used_ids, unused_ids)
            row["FACILITYID"]["int_id"] = new_id
            row["FACILITYID"]["str_id"] = str(new_id)
            edits = True

        if edits:
            edited.append(row)

        return edited
