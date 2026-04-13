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

### 2. Data Conversion (CSV to RDF / N3)

Run the conversion script to generate the RDF file:

```bash
python3 rdf/convert.py
```

By default the converter uses a lean profile that exports only the RDF currently used by the web application.
If you want the full archive export instead, run:

```bash
python3 rdf/convert.py --profile full
```

---

### 3. Setup GraphDB

#### Recommended — automated script

The script starts GraphDB Desktop (if not already running), creates the `baseball` repository and imports the RDF data automatically:

```bash
bash scripts/start_graphdb.sh
```

By default it expects GraphDB Desktop at `/opt/graphdb-desktop/bin/graphdb-desktop`. If yours is installed elsewhere, set the environment variable before running:

```bash
GRAPHDB_DESKTOP_BIN=/path/to/graphdb-desktop bash scripts/start_graphdb.sh
```

The script will wait up to 120 seconds for GraphDB to become reachable. If it is already running it skips the launch step; if the repository already exists it skips the import.

#### Manual alternative

1. Open GraphDB and create a repository named `baseball`.
2. Import the file `rdf/baseball.n3` (Import → User Data).
3. Make sure GraphDB is running at `http://localhost:7200`.

#### Deleting the repository

To delete the `baseball` repository and start fresh:

```bash
bash scripts/delete_graphdb_repo.sh
```

Add `--yes` to skip the confirmation prompt.

---

### 4. Run Django Server

```bash
cd webapp
python manage.py runserver
```

Open in browser:
`http://127.0.0.1:8000`

---
