# Personal configuration for teams_captions.py.
# config.py is gitignored - edit it freely. config.example.py is the committed template.

# Words to highlight in the captions (case-insensitive), e.g. your name in different scripts
KEYWORDS = ["your name"]

PORT = 5000  # If you change this, also change the address in teams_captions.bat
LOG_FOLDER = "logs"  # Relative to the script folder
LOG_INTERVAL_SECONDS = 10  # Write the transcript to file at most every 10 seconds
