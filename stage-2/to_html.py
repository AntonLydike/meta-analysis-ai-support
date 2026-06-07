import html
from typing import Any, Dict, List

# ==========================================
# STATIC ASSETS (CLEAN LABELED STRINGS)
# ==========================================

CSS_STYLES = """
:root {
    --bg-color: #fcfcfd;
    --card-bg: #ffffff;
    --text-color: #2b303a;
    --border-color: #e9ecef;
    --primary-color: #4a6fa5;
    
    --include-bg: #e8f5e9; --include-text: #1b5e20; --include-border: #c8e6c9;
    --exclude-bg: #ffebee; --exclude-text: #c62828; --exclude-border: #ffcdd2;
    --na-bg: #f5f5f5;      --na-text: #616161;    --na-border: #e0e0e0;
    
    /* Document Type Color Registry */
    --dt-empirical-bg: #e0f2fe; --dt-empirical-txt: #0369a1; --dt-empirical-brd: #bae6fd;
    --dt-abstract-bg:  #f3e8ff; --dt-abstract-txt:  #6b21a8; --dt-abstract-brd:  #e9d5ff;
    --dt-diss-bg:      #fef3c7; --dt-diss-txt:      #92400e; --dt-diss-brd:      #fde68a;
    --dt-letter-bg:    #e0fcfc; --dt-letter-txt:    #037a7a; --dt-letter-brd:    #baf7f7;
    --dt-missing-bg:   #f1f5f9; --dt-missing-txt:   #475569; --dt-missing-brd:   #cbd5e1;
    --dt-other-bg:     #ffedd5; --dt-other-txt:     #9a3412; --dt-other-brd:     #fed7aa;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, sans-serif;
    background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; line-height: 1.4;
}
.header { margin-bottom: 20px; }
h1 { margin: 0 0 4px 0; font-size: 1.6rem; color: #1e293b; }
.meta-total { color: #64748b; font-size: 0.95rem; }

.dashboard-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 16px;
}
.card {
    background: var(--card-bg); border-radius: 6px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid var(--border-color);
}
.card h3 { margin-top: 0; margin-bottom: 10px; font-size: 0.95rem; color: #475569; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px; }
.metric-list { max-height: 160px; overflow-y: auto; border-radius: 4px; }
.metric-item {
    display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; font-size: 0.85rem; border-bottom: 1px solid #f8fafc; cursor: pointer; transition: background 0.1s ease;
}
.metric-item:hover { background-color: rgba(74, 111, 165, 0.15) !important; }
.metric-count { font-weight: 600; color: #334155; pointer-events: none; }
.metric-count small { color: #64748b; font-weight: 400; margin-left: 4px; }

.info-details {
    background: #f8fafc; border: 1px solid var(--border-color); border-radius: 6px; margin-bottom: 16px; padding: 10px 14px; font-size: 0.85rem; color: #475569;
}
.info-summary { font-weight: 600; cursor: pointer; user-select: none; outline: none; color: var(--primary-color); }
.info-content { margin-top: 8px; line-height: 1.5; }
.info-content ul { margin: 4px 0; padding-left: 20px; }
.info-content code { background: #e2e8f0; padding: 1px 4px; border-radius: 3px; font-family: monospace; font-size: 0.8rem; color: #0f172a; }

.controls-panel {
    background: var(--card-bg); padding: 12px; border-radius: 6px; margin-bottom: 16px; border: 1px solid var(--border-color); display: flex; align-items: center; gap: 12px;
}
.search-input {
    flex: 1; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 0.9rem;
}
.search-input:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px rgba(74, 111, 165, 0.15); }
.counter-badge { background: #f1f5f9; padding: 6px 12px; border-radius: 4px; font-size: 0.85rem; font-weight: 500; color: #475569; white-space: nowrap; }

.table-container {
    background: var(--card-bg); border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid var(--border-color); overflow: hidden;
}
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.88rem; table-layout: fixed; }

th:nth-child(1), td:nth-child(1) { width: 50px; text-align: center; }
th:nth-child(2), td:nth-child(2) { width: 190px; }
th:nth-child(3), td:nth-child(3) { width: 30%; }
th:nth-child(4), td:nth-child(4) { width: 140px; }
th:nth-child(5), td:nth-child(5) { width: 70px; text-align: center; }

th {
    background-color: #f8fafc; padding: 10px 12px; font-weight: 600; color: #475569; cursor: pointer; user-select: none; border-bottom: 2px solid var(--border-color);
}
th:hover { background-color: #f1f5f9; }
th::after { content: ' ↕'; opacity: 0.25; font-size: 0.75rem; }
th.sort-asc::after { content: ' ▴'; opacity: 1; color: var(--primary-color); }
th.sort-desc::after { content: ' ▾'; opacity: 1; color: var(--primary-color); }

td { padding: 10px 12px; border-bottom: 1px solid var(--border-color); vertical-align: top; word-wrap: break-word; overflow: hidden; }
tr:hover td { background-color: #f8fafc; }

.badge {
    display: inline-block; padding: 3px 7px; border-radius: 4px; font-size: 0.78rem; font-weight: 500; line-height: 1.2; border: 1px solid transparent; text-transform: capitalize;
}
.badge-include { background-color: var(--include-bg); color: var(--include-text); border-color: var(--include-border); }
.badge-exclude { background-color: var(--exclude-bg); color: var(--exclude-text); border-color: var(--exclude-border); }
.badge-na      { background-color: var(--na-bg);      color: var(--na-text);      border-color: var(--na-border); font-style: italic; }
.badge-lang    { background-color: #fff3cd;        color: #856404;        border-color: #ffeeba; text-transform: uppercase; font-family: monospace; font-weight: bold; }

/* Document Type Badge Variations */
.badge-empirical { background-color: var(--dt-empirical-bg); color: var(--dt-empirical-txt); border-color: var(--dt-empirical-brd); }
.badge-abstract  { background-color: var(--dt-abstract-bg);  color: var(--dt-abstract-txt);  border-color: var(--dt-abstract-brd); }
.badge-diss      { background-color: var(--dt-diss-bg);      color: var(--dt-diss-txt);      border-color: var(--dt-diss-brd); }
.badge-letter    { background-color: var(--dt-letter-bg);    color: var(--dt-letter-txt);    border-color: var(--dt-letter-brd); }
.badge-missing   { background-color: var(--dt-missing-bg);   color: var(--dt-missing-txt);   border-color: var(--dt-missing-brd); }
.badge-other     { background-color: var(--dt-other-bg);     color: var(--dt-other-txt);     border-color: var(--dt-other-brd); }

.doc-title { font-weight: 600; color: #0f172a; margin-bottom: 2px; line-height: 1.3; }
.doc-authors { font-size: 0.8rem; color: #64748b; margin-bottom: 6px; }
.doc-links { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }

.file-link {
    display: inline-flex; align-items: center; background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; padding: 2px 6px; border-radius: 4px; text-decoration: none; font-size: 0.75rem; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.file-link:hover { background: #dbeafe; color: #1e3a8a; }
.reasoning-cell { font-size: 0.82rem; color: #334155; white-space: pre-wrap; line-height: 1.4; }
"""

JAVASCRIPT_LOGIC = """
document.addEventListener('DOMContentLoaded', () => {
    const searchBar = document.getElementById('searchBar');
    const tableBody = document.getElementById('tableBody');
    const rows = Array.from(tableBody.getElementsByTagName('tr'));
    const visibleCount = document.getElementById('visibleCount');
    const headers = document.querySelectorAll('#resultsTable th');
    const metricItems = document.querySelectorAll('.metric-item');

    const classMapping = {
        'incl': 'include',
        'excl-wf': 'exclude: wrong format',
        'excl-wl': 'exclude: wrong language',
        'excl-wv': 'exclude: wrong variables',
        'excl-dsm': 'exclude: design / sample mismatch'
    };

    function runFilter() {
        const queryText = searchBar.value.toLowerCase().trim();
        
        if (queryText === "") {
            for (let i = 0; i < rows.length; i++) rows[i].style.display = "";
            visibleCount.innerText = rows.length;
            return;
        }

        const tokens = queryText.split(/\s+/);
        const structuredFilters = [];
        const globalSearchTokens = [];

        tokens.forEach(token => {
            if (token.includes(':')) {
                let [key, value] = token.split(':', 2);
                if (key && value) {
                    if (key === 'class' && classMapping[value]) {
                        value = classMapping[value];
                    }
                    structuredFilters.push({ key, value });
                }
            } else {
                if (token) globalSearchTokens.push(token);
            }
        });

        let visible = 0;

        for (let i = 0; i < rows.length; i++) {
            const row = rows[i];
            
            const rId = row.getAttribute('data-id');
            const rClass = row.getAttribute('data-class');
            const rType = row.getAttribute('data-type');
            const rLang = row.getAttribute('data-lang');
            const rSearch = row.getAttribute('data-search');

            let match = true;

            for (let j = 0; j < structuredFilters.length; j++) {
                const { key, value } = structuredFilters[j];
                if (key === 'id' && rId !== value) { match = false; break; }
                if (key === 'lang' && rLang !== value) { match = false; break; }
                if (key === 'type' && !rType.includes(value)) { match = false; break; }
                if (key === 'class' && !rClass.includes(value)) { match = false; break; }
            }

            if (match && globalSearchTokens.length > 0) {
                for (let k = 0; k < globalSearchTokens.length; k++) {
                    if (!rSearch.includes(globalSearchTokens[k])) {
                        match = false;
                        break;
                    }
                }
            }

            if (match) {
                row.style.display = "";
                visible++;
            } else {
                row.style.display = "none";
            }
        }
        visibleCount.innerText = visible;
    }

    let searchTimeout;
    searchBar.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(runFilter, 60);
    });

    // Upgraded Category-Isolation Clicking Logic
    metricItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetType = item.getAttribute('data-metric-type');
            let value = item.getAttribute('data-metric-value').toLowerCase();

            let filterToken = `${targetType}:${value}`;
            if (targetType === 'class') {
                const foundShortcut = Object.keys(classMapping).find(k => classMapping[k] === value);
                filterToken = foundShortcut ? `class:${foundShortcut}` : `class:${value}`;
            }

            // Extract existing search elements
            const currentTokens = searchBar.value.trim().split(/\s+/).filter(t => t.length > 0);
            
            // Filter out any existing conditions that match the targeted type namespace
            const sanitizedTokens = currentTokens.filter(token => {
                return !token.toLowerCase().startsWith(`${targetType}:`);
            });

            // Append the new specific category limit back to token array
            sanitizedTokens.push(filterToken);
            
            searchBar.value = sanitizedTokens.join(' ');
            runFilter();
        });
    });

    headers.forEach(header => {
        header.addEventListener('click', () => {
            const colIndex = parseInt(header.getAttribute('data-col'));
            if (isNaN(colIndex)) return;
            
            const isAscending = header.classList.contains('sort-asc');
            headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
            const direction = isAscending ? -1 : 1;
            header.classList.add(isAscending ? 'sort-desc' : 'sort-asc');

            rows.sort((rowA, rowB) => {
                const cellA = rowA.cells[colIndex].getAttribute('data-val');
                const cellB = rowB.cells[colIndex].getAttribute('data-val');
                if (colIndex === 0) return (parseInt(cellA) - parseInt(cellB)) * direction;
                return cellA.localeCompare(cellB, undefined, {numeric: true, sensitivity: 'base'}) * direction;
            });

            const fragment = document.createDocumentFragment();
            rows.forEach(row => fragment.appendChild(row));
            tableBody.appendChild(fragment);
        });
    });
});
"""

# ==========================================
# MAIN DASHBOARD INTERFACE COMPILER
# ==========================================

def generate_html_result(docs: List[Any], batch_results: List[Dict[int, Any]]) -> str:
    """
    Generates a single-file interactive HTML dashboard with decoupled style blocks.
    Features specific color mappings for document type states and categorical search isolation.
    """
    # Helper to map document types cleanly to CSS sub-classes
    def get_doc_type_badge_class(dt_val: str) -> str:
        dt_clean = dt_val.lower()
        if "empirical" in dt_clean: return "badge-empirical"
        if "abstract" in dt_clean:  return "badge-abstract"
        if "dissertation" in dt_clean: return "badge-diss"
        if "letter" in dt_clean:    return "badge-letter"
        if "missing" in dt_clean:   return "badge-missing"
        if "other" in dt_clean:     return "badge-other"
        return "badge-neutral"

    # 1. Flatten results map
    results_map = {}
    for batch in batch_results:
        if not batch: continue
        for doc_id, res in batch.items():
            if res is None: results_map[int(doc_id)] = {}
            elif hasattr(res, "model_dump"): results_map[int(doc_id)] = res.model_dump()
            elif hasattr(res, "dict"): results_map[int(doc_id)] = res.dict()
            else: results_map[int(doc_id)] = dict(res)

    # 2. Metric Accumulation Frame
    total_docs = len(docs) if docs else 1
    counts_class, counts_type, counts_lang = {}, {}, {}

    for doc in docs:
        res = results_map.get(doc.id) or {}
        c_res = str(res.get("classification_result") or "N/A")
        d_type = str(res.get("document_type") or "N/A")
        lang = str(res.get("source_language") or "N/A")

        counts_class[c_res] = counts_class.get(c_res, 0) + 1
        counts_type[d_type] = counts_type.get(d_type, 0) + 1
        counts_lang[lang] = counts_lang.get(lang, 0) + 1

    def make_summary_cards(title: str, m_type: str, data_dict: dict) -> str:
        sorted_data = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)
        items_html = ""
        for k, v in sorted_data:
            pct = round((v / total_docs) * 100, 1)
            items_html += f"""
            <div class="metric-item" data-metric-type="{m_type}" data-metric-value="{html.escape(k)}" style="background: linear-gradient(90deg, rgba(74,111,165,0.08) {pct}%, transparent {pct}%);">
                <span>{html.escape(k)}</span>
                <span class="metric-count">{v} <small>({pct}%)</small></span>
            </div>"""
        return f'<div class="card"><h3>{title}</h3><div class="metric-list">{items_html}</div></div>'

    summary_html = (
        make_summary_cards("Classification Outcomes", "class", counts_class) +
        make_summary_cards("Document Types", "type", counts_type) +
        make_summary_cards("Languages", "lang", counts_lang)
    )

    # 3. Micro-Structured Row Loop Generation
    table_rows = []
    for doc in docs:
        res = results_map.get(doc.id) or {}
        
        c_result = str(res.get("classification_result") or "N/A")
        d_type = str(res.get("document_type") or "N/A")
        lang = str(res.get("source_language") or "N/A")
        reasoning = str(res.get("reasoning") or "N/A")
        authors_str = ", ".join(doc.authors) if doc.authors else "Unknown Author"

        attachments_html = "".join([
            f'<a class="file-link" href="{html.escape(path)}" target="_blank">📄 {html.escape(path.split("/")[-1])}</a>'
            for path in doc.attachments if path
        ])
        links_div = f'<div class="doc-links">{attachments_html}</div>' if attachments_html else ""

        if c_result == "N/A": cls_type = "badge-na"
        elif "Include" in c_result: cls_type = "badge-include"
        else: cls_type = "badge-exclude"

        doc_type_class = get_doc_type_badge_class(d_type)
        search_blob = f"{doc.id} {doc.title} {authors_str} {c_result} {d_type} {lang}".lower()

        row = f"""
        <tr data-id="{doc.id}" data-class="{c_result.lower()}" data-type="{d_type.lower()}" data-lang="{lang.lower()}" data-search="{html.escape(search_blob)}">
            <td data-val="{doc.id}"><code>{doc.id}</code></td>
            <td data-val="{html.escape(c_result)}"><span class="badge {cls_type}">{html.escape(c_result)}</span></td>
            <td data-val="{html.escape(doc.title or '')}">
                <div class="doc-title">{html.escape(doc.title or "Untitled")}</div>
                <div class="doc-authors">{html.escape(authors_str)}</div>
                {links_div}
            </td>
            <td data-val="{html.escape(d_type)}"><span class="badge {doc_type_class}">{html.escape(d_type)}</span></td>
            <td data-val="{html.escape(lang)}"><span class="badge badge-lang">{html.escape(lang)}</span></td>
            <td class="reasoning-cell" data-val="{html.escape(reasoning)}">{html.escape(reasoning)}</td>
        </tr>
        """
        table_rows.append(row)

    all_rows_html = "\n".join(table_rows)

    # 4. Final HTML Dashboard Compilation Assembly
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Document Classification Dashboard</title>
    <style>{CSS_STYLES}</style>
</head>
<body>

    <div class="header">
        <h1>Document Classification Dashboard</h1>
        <div class="meta-total">Total Processed Documents: <strong>{len(docs)}</strong></div>
    </div>

    <div class="dashboard-grid">{summary_html}</div>

    <details class="info-details">
        <summary class="info-summary">💡 View Advanced Search Syntax Instructions</summary>
        <div class="info-content">
            You can combine keywords with space separation for basic matches, or apply exact system filters to target properties explicitly:
            <ul>
                <li><code>id:1005</code> &mdash; Finds records containing exactly that tracking identifier.</li>
                <li><code>lang:en</code> or <code>lang:fr</code> &mdash; Targets records flagged under specific ISO codes.</li>
                <li><code>type:empirical</code> &mdash; Filters text contents against localized sub-schema options.</li>
                <li><code>class:incl</code> &mdash; Displays everything matching the <b>Include</b> criteria badge.</li>
                <li><code>class:excl-wf</code>, <code>class:excl-wl</code>, <code>class:excl-wv</code>, <code>class:excl-dsm</code> &mdash; Matches specific inclusion exclusion parameters directly.</li>
            </ul>
            <i>Note: Clicking on any metric summary component at the top replaces any previous filters on that specific category, while retaining terms from other fields.</i>
        </div>
    </details>

    <div class="controls-panel">
        <input type="text" id="searchBar" class="search-input" placeholder="Search parameters (e.g., 'lang:en class:incl keyword')...">
        <div class="counter-badge">Showing: <span id="visibleCount">{len(docs)}</span> / {len(docs)}</div>
    </div>

    <div class="table-container">
        <table id="resultsTable">
            <thead>
                <tr>
                    <th data-col="0">ID</th>
                    <th data-col="1">Classification</th>
                    <th data-col="2">Title & Authors</th>
                    <th data-col="3">Doc Type</th>
                    <th data-col="4">Lang</th>
                    <th data-col="5">Reasoning Summary</th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {all_rows_html}
            </tbody>
        </table>
    </div>

    <script>{JAVASCRIPT_LOGIC}</script>
</body>
</html>
"""
