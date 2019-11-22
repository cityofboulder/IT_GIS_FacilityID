from ..config import post_edits

if post_edits:
    insert = ("Versioned edits to Facility IDs have been posted on your "
              "behalf by the GISSCR user.<br><br>"
              "If you have not authorized edits, registered your data as "
              "versioned, or granted GISSCR edit access to your data, a layer "
              "file with a table of joined edits has been attached to this "
              "email for your inspection.")
else:
    insert = (" Versioned edits to Facility IDs have been performed on your "
              "behalf by the GISSCR user.<br><br>"
              "Please navigate to your department's attached layer file to "
              "inspect the versioned edits and post all changes.<br><br>"
              "If you have not authorized edits, registered your data as "
              "versioned, or granted GISSCR edit access to your data, your "
              "department's layer file contains read-only layers joined to a "
              "table of edits. You can manually change sources for each "
              "layer and perform the edits yourself.")

body = f"""\
            <html>
                <head></head>
                <body>
                    <p>
                    Dear Human,<br><br>
                    {insert}
                    </p>
                    <p>
                    Beep Boop Beep,<br><br>
                    End Transmission
                    </p>
                </body>
            </html>
            """
