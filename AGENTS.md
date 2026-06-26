# Soccer Weather Pitch Project

Goal:
Build a Python pipeline that collects past Portugal and Colombia soccer matches, joins each match to historical weather at the venue, and outputs a CSV with inferred pitch conditions.

Definition of done:
- Pipeline runs from CLI.
- Pipeline runs automatically from GitHub Actions.
- No hardcoded API keys.
- Output is data/output/match_conditions.csv.
- Missing/problem matches go to data/output/skipped_matches.csv.
- Re-running the pipeline does not duplicate rows.
- Pitch condition must be labeled as inferred unless provider supplies official condition.
- Tests must pass with pytest.

Tech:
- Python 3.11+
- requests or httpx
- pandas
- pydantic
- python-dotenv
- pytest

Code style:
- Small files.
- Typed functions.
- Defensive API handling.
- Clear logging.
- Do not silently drop matches.