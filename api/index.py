from flask import Flask, request, jsonify
import requests, pandas as pd, numpy as np, io, base64, datetime
from collections import Counter

app = Flask(__name__)

@app.route('/api/investigate')
def investigate():
    orcid = request.args.get('orcid').strip().split('/')[-1]
    email = "audit-app@vercel.com"
    base_url = "https://api.openalex.org"

    # 1. Verification
    auth_url = f"{base_url}/authors?filter=orcid:https://orcid.org/{orcid}&mailto={email}"
    auth_data = requests.get(auth_url).json()
    if auth_data['meta']['count'] == 0: return "Author not found", 404
    
    author = auth_data['results'][0]
    alex_id = author['id']
    author_name = author['display_name']

    # 2. Career Harvest (Limit to 100 for speed on Vercel)
    works_url = f"{base_url}/works?filter=author.id:{alex_id}&per_page=100&mailto={email}"
    works = requests.get(works_url).json()['results']
    
    cited_by_target = set()
    coauthor_freq = Counter()
    career_venues = []
    for w in works:
        for ref in w.get('referenced_works', []): cited_by_target.add(ref.split('/')[-1])
        for auth in w.get('authorships', []):
            name = auth.get('author', {}).get('display_name')
            if name and name != author_name: coauthor_freq[name] += 1
        v = (w.get('primary_location') or {}).get('source') or {}
        if v.get('display_name'): career_venues.append(v.get('display_name'))

    inner_circle = {n for n, c in coauthor_freq.most_common(max(1, len(coauthor_freq)//2))}

    # 3. High Impact Probe (Top 10 papers for speed)
    sorted_works = sorted(works, key=lambda x: x.get('cited_by_count', 0), reverse=True)
    citing_authors, citing_journals, reciprocity_tally = [], [], Counter()

    for work in sorted_works[:10]:
        c_url = f"{base_url}/works?filter=cites:{work['id'].split('/')[-1]}&per_page=50&mailto={email}"
        c_results = requests.get(c_url).json().get('results', [])
        for cw in c_results:
            j = ((cw.get('primary_location') or {}).get('source') or {}).get('display_name', 'Other')
            citing_journals.append(j)
            for auth in cw.get('authorships', []):
                bn = auth.get('author', {}).get('display_name')
                if bn and bn != author_name:
                    citing_authors.append(bn)
                    if cw['id'].split('/')[-1] in cited_by_target: reciprocity_tally[bn] += 1

    # 4. Analytics
    c_counts = Counter(citing_authors)
    j_counts = Counter(citing_journals)
    total_c = sum(c_counts.values())
    nci = (sum(count for n, count in c_counts.items() if n in inner_circle) / max(1, total_c)) * 100
    jci = (j_counts.most_common(1)[0][1] / max(1, total_c)) * 100 if citing_journals else 0
    
    top_nodes = []
    for n, c in c_counts.most_common(8):
        top_nodes.append({'name': n, 'cites': c, 'status': 'Core' if n in inner_circle else 'Ext', 'recip': reciprocity_tally[n], 'intens': round(c/10, 2)})

    # Determine Risk
    risk = "CRITICAL" if nci > 45 else "HIGH" if nci > 30 else "MODERATE" if nci > 15 else "LOW"
    
    # 5. Simplified Report HTML (Return as string)
    # [Note: You would paste your optimized Cell 5 HTML template here]
    report_html = f"<html><body style='font-family:sans-serif; padding:40px;'><h1>Audit: {author_name}</h1><h3>Risk: {risk}</h3><p>Network Concentration: {nci:.1f}%</p><p>Journal Concentration: {jci:.1f}%</p></body></html>"
    
    return report_html

if __name__ == "__main__":
    app.run()
