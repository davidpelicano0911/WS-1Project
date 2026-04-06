## How to Run the Project

### 1. Setup Python Environment

In the root project folder:

```bash
# Create virtual environment
python3 -m venv venv

# Activate environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### 2. Data Conversion (CSV to RDF)

Run the conversion script to generate the RDF file:

```bash
python3 rdf/convert.py
```

### 3. Setup GraphDB

Before running the web application, load the data:

1. Open GraphDB and create a repository named `baseball`.
2. Import the file `rdf/baseball.nt` (Import → User Data).
3. Make sure GraphDB is running at:
   `http://localhost:7200`

---

### 4. Run Django Server

```bash
cd webapp
python manage.py runserver
```

Open in browser:
`http://127.0.0.1:8000`

---
