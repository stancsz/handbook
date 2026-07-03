#!/usr/bin/env python3
"""Push handbook changes to GitHub."""
import urllib.request
import urllib.error
import base64
import json
import os
import sys

TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = 'badlandslabs/handbook'
BRANCH = 'main'

headers = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
}

def get_sha(path):
    url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}'
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        return data['sha']
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def push_file(path, content, sha=None, message=None):
    data = {
        'message': message or f'Update {path}',
        'content': base64.b64encode(content).encode(),
        'branch': BRANCH,
    }
    if sha:
        data['sha'] = sha
    body = json.dumps(data).encode()

    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    req = urllib.request.Request(url, headers=headers, data=body)
    req.get_method = lambda: 'PUT'
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        print(f'✓ {path} → {result["commit"]["sha"][:8]}')
        return True
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f'✗ {path} → HTTP {e.code}: {body_text[:200]}')
        return False

# Files to push
files = [
    ('stacks/s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md',
     'S-385: Agent Trajectory Evaluation — Process vs. Outcome Scoring'),
    ('knowledge-pulse.md',
     'Update knowledge-pulse.md: add I-014 trajectory-eval'),
]

os.chdir('/opt/data/handbook')
results = []
for rel_path, commit_msg in files:
    abs_path = rel_path
    if not os.path.exists(abs_path):
        print(f'SKIP {rel_path} — file not found')
        continue
    with open(abs_path, 'rb') as f:
        content = f.read()
    sha = get_sha(rel_path)
    if sha:
        print(f'  {rel_path}: updating SHA {sha[:8]}...')
    else:
        print(f'  {rel_path}: new file')
    ok = push_file(rel_path, content, sha=sha, message=commit_msg)
    results.append((rel_path, ok))

print()
failed = [p for p, ok in results if not ok]
if failed:
    print(f'FAILED: {failed}')
    sys.exit(1)
else:
    print(f'All {len(results)} files pushed successfully.')
