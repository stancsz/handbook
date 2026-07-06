#!/usr/bin/env python3
import urllib.request
import urllib.parse
import base64
import json
import os
import sys

TOKEN='github...58b3'
REPO = 'badlandslabs/handbook'
BRANCH = 'main'
FILE_PATH = 'stacks/s218-agent-stack-stratification.md'

headers = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
}

# Read the file content
with open(FILE_PATH, 'rb') as f:
    content = f.read()
encoded = base64.b64encode(content).decode()

# Get current SHA
url = f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={BRANCH}'
req = urllib.request.Request(url, headers=headers)
try:
    resp = urllib.request.urlopen(req)
    current = json.loads(resp.read())
    sha = current['sha']
    print(f'Existing file SHA: {sha[:8]}...')
except urllib.error.HTTPError as e:
    if e.code == 404:
        sha = None
        print('File does not exist yet, creating new')
    else:
        print(f'Error getting SHA: {e.read()}')
        sys.exit(1)

# Push
data = {
    'message': 'Add S-218 · Agent Stack Stratification',
    'content': encoded,
    'branch': BRANCH,
}
if sha:
    data['sha'] = sha

body = json.dumps(data).encode()
req = urllib.request.Request(
    f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}',
    data=body,
    headers=headers,
    method='PUT'
)
try:
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f'SUCCESS: {result.get("content", {}).get("html_url", "no url")}')
except urllib.error.HTTPError as e:
    err = e.read()
    print(f'ERROR {e.code}: {err.decode()}')
    sys.exit(1)
