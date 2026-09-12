"""Create a synthetic JD fixture for exercising the agreed OR-group contract."""
from pathlib import Path
import fitz

text = """Junior Full Stack Developer Intern - SYNTHETIC DEMO JD
Must have strong programming knowledge in Python or JavaScript.
Required: Hands-on experience developing web applications with React or Node.js.
Must know database management with MongoDB or PostgreSQL.
Preferred: REST API and Git.
Docker is a bonus.

Test fixture based on the project plan; not an official organizer document.
"""
target = Path(__file__).resolve().parents[1] / "data" / "jd" / "Synthetic_Demo_JD.pdf"
target.parent.mkdir(parents=True, exist_ok=True)
with fitz.open() as doc:
    page = doc.new_page()
    page.insert_text((40, 50), text, fontsize=10)
    doc.save(str(target))
print(target)
