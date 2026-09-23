#!/usr/bin/env bash
# fix-sigma-list-controls.sh - repoint a workbook's LIST controls at a self-referential
# value source so their dropdowns actually populate.
#
#   ./fix-sigma-list-controls.sh <workbookId> <slug> [--dry-run]
#
# WHY THIS EXISTS
#   A Sigma list control with `source: {kind: manual, valueType: text}` and `values: []`
#   is a hand-maintained list that starts empty and NEVER populates itself. The
#   CallRail Analytics template shipped all 8 of its list controls that way, so every
#   workbook cloned from it has permanently blank Source and Medium dropdowns.
#   The fix is to point the value source at the control's own filter target:
#
#     source:
#       kind: source
#       source: {kind: table, elementId: <same element the filter targets>}
#       columnId: <same column the filter targets>
#
#   The old handoff claimed the API rejects `kind: source` on write. It does not -
#   verified with a 200 + clean readback on Blackstone 2026-08-26.
#
# SAFETY
#   - GETs and saves a full rollback spec BEFORE any write.
#   - Only touches controls with controlType == list that already have a resolvable
#     filters[0] target. Date-range and segmented controls are never modified.
#   - Refuses to PUT if document.schemaVersion is absent.
#   - Skips the PUT entirely when there is nothing to change (idempotent).
#   - Strips server-managed fields the API rejects on PUT.
#   - Re-GETs afterwards and verifies every list control landed.
#
# NETWORK NOTE (this workstation)
#   powershell.exe and curl.exe launched from it CANNOT reach the Sigma API here.
#   Git Bash curl can. So all HTTP goes through curl and python is used only for
#   local YAML/JSON work. Do not "simplify" this into python urllib.
#
# Requires: ~/.sigma-env (see setup-sigma-creds.ps1 or setup.py), python w/ pyyaml.

set -euo pipefail

WB="${1:-}"
SLUG="${2:-}"
DRY="${3:-}"
if [ -z "$WB" ] || [ -z "$SLUG" ]; then
    echo "usage: $0 <workbookId> <slug> [--dry-run]" >&2
    exit 2
fi

# shellcheck disable=SC1090
source ~/.sigma-env
: "${SIGMA_BASE_URL:?}" "${SIGMA_CLIENT_ID:?}" "${SIGMA_CLIENT_SECRET:?}"

BKDIR=/c/Users/venka/projects/swyft-sigma/clients/_callrail-control-fix
mkdir -p "$BKDIR"
STAMP=$(date +%Y%m%d)

# NEVER clobber an existing rollback. The name used to be date-stamped only, so a second
# run on the same day - INCLUDING a --dry-run, which still GETs and saves - overwrote the
# pre-change spec with the post-change one and destroyed the only way back. Observed on
# Blackstone 2026-08-26. Find the first free suffix instead; the lowest-numbered file is
# always the original.
BKNAME="${SLUG}-backup-${STAMP}"
if [ -e "$BKDIR/${BKNAME}.yaml" ]; then
    n=2
    while [ -e "$BKDIR/${BKNAME}-${n}.yaml" ]; do n=$((n + 1)); done
    BKNAME="${BKNAME}-${n}"
    echo "  note: a backup for today already exists; the ORIGINAL is kept, this run writes ${BKNAME}.yaml"
fi

BK="$BKDIR/${BKNAME}.yaml"
BODY="$BKDIR/${SLUG}-putbody.json"
RB="$BKDIR/${SLUG}-readback.yaml"

# Windows-form paths: this python is Windows python and cannot resolve MSYS /c/ paths.
WBASE="C:/Users/venka/projects/swyft-sigma/clients/_callrail-control-fix"
WBK="$WBASE/${BKNAME}.yaml"
WBODY="$WBASE/${SLUG}-putbody.json"
WRB="$WBASE/${SLUG}-readback.yaml"

TOKEN=$(curl -s --max-time 30 -X POST "$SIGMA_BASE_URL/v2/auth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "grant_type=client_credentials" \
    --data-urlencode "client_id=$SIGMA_CLIENT_ID" \
    --data-urlencode "client_secret=$SIGMA_CLIENT_SECRET" \
    | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
[ -z "$TOKEN" ] && { echo "token mint failed" >&2; exit 1; }

echo "=== $SLUG ($WB) ==="

# --- identity, so we can never write to the wrong copy ---
curl -s --max-time 30 -H "Authorization: Bearer $TOKEN" \
    "$SIGMA_BASE_URL/v2/workbooks/$WB" \
 | python -c "
import json,sys
d=json.load(sys.stdin)
print('  name : %s' % d.get('name'))
print('  path : %s' % d.get('path'))
print('  ver  : %s' % d.get('latestVersion'))
"

# --- step 1: rollback ---
curl -s --max-time 60 -H "Authorization: Bearer $TOKEN" \
    "$SIGMA_BASE_URL/v2/workbooks/$WB/spec" -o "$BK"
echo "  backup: $(wc -c < "$BK") bytes -> $BK"

# --- step 2: transform locally ---
python - "$WBK" "$WBODY" <<'PY'
import json, sys, yaml
src, out = sys.argv[1], sys.argv[2]
d = yaml.safe_load(open(src, encoding='utf-8'))
doc = d.get('document') or {}
if 'schemaVersion' not in doc:
    sys.exit('  ABORT: document.schemaVersion missing, refusing to build a PUT')

READ_ONLY = {"workbookId","dataModelId","url","ownerId","createdBy",
             "updatedBy","createdAt","updatedAt","latestDocumentVersion"}

changed, already, skipped, selections = [], [], [], []
def walk(o):
    if isinstance(o, dict):
        if o.get('kind') == 'control' and o.get('controlType') == 'list':
            cid = o.get('controlId')
            cur = o.get('source') or {}

            # A saved default SELECTION lives at control level `values`. We never touch
            # that key, but record it so a changed filter default cannot pass unnoticed.
            if o.get('values'):
                selections.append((cid, o['values']))

            # HAND-CURATED OPTION LIST GUARD.
            # A manual source stores its options at source.values (+ optional
            # source.labels). Replacing the source wholesale would silently delete a
            # list somebody typed in by hand. Only an EMPTY manual source is safe to
            # convert - that is the broken-by-default template state. Anything with
            # content is left alone and reported for a human decision.
            if cur.get('values') or cur.get('labels'):
                skipped.append((cid, len(cur.get('values') or []),
                                     len(cur.get('labels') or [])))
                for v in o.values(): walk(v)
                return

            f = (o.get('filters') or [None])[0]
            if f:
                el  = (f.get('source') or {}).get('elementId')
                col = f.get('columnId')
                if el and col:
                    want = {'kind': 'source',
                            'source': {'kind': 'table', 'elementId': el},
                            'columnId': col}
                    if cur == want:
                        already.append(cid)
                    else:
                        o['source'] = want
                        changed.append((cid, el, col))
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(doc)

for cid, el, col in changed:
    print('    fix   %-22s %-14s %s' % (cid, el, col))
for cid in already:
    print('    ok    %-22s (already self-referential)' % cid)
for cid, nv, nl in skipped:
    print('    SKIP  %-22s hand-curated: %d values, %d labels - NOT touched' % (cid, nv, nl))
for cid, vals in selections:
    print('    note  %-22s has a saved default selection, preserved: %s' % (cid, vals))

json.dump({k: v for k, v in d.items() if k not in READ_ONLY},
          open(out, 'w', encoding='utf-8'))
print('  to_change=%d already_ok=%d' % (len(changed), len(already)))
PY

TO_CHANGE=$(python -c "
import sys,yaml
d=yaml.safe_load(open(r'$WBK',encoding='utf-8'))
n=0
def walk(o):
    global n
    if isinstance(o,dict):
        if o.get('kind')=='control' and o.get('controlType')=='list':
            cur=o.get('source') or {}
            if cur.get('values') or cur.get('labels'):
                pass  # hand-curated, skipped by the transform above
            else:
                f=(o.get('filters') or [None])[0]
                if f and (f.get('source') or {}).get('elementId') and f.get('columnId'):
                    el=(f.get('source') or {}).get('elementId'); col=f.get('columnId')
                    want={'kind':'source','source':{'kind':'table','elementId':el},'columnId':col}
                    if cur!=want: n+=1
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        for v in o: walk(v)
walk(d.get('document') or {})
print(n)")

if [ "$TO_CHANGE" = "0" ]; then
    echo "  nothing to change - skipping PUT"
    exit 0
fi

if [ "$DRY" = "--dry-run" ]; then
    echo "  DRY RUN - no PUT issued"
    exit 0
fi

# --- step 3: write ---
resp=$(curl -s -w '\n%{http_code}' --max-time 90 -X PUT \
    "$SIGMA_BASE_URL/v2/workbooks/$WB/spec" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    --data-binary @"$BODY")
code=$(printf '%s' "$resp" | tail -1)
if [ "$code" -ge 300 ] 2>/dev/null; then
    echo "  PUT FAILED HTTP $code"
    printf '%s' "$resp" | sed '$d' | head -c 600
    echo
    echo "  rollback available at $BK"
    exit 1
fi
echo "  PUT HTTP $code"

# --- step 4: readback verify ---
curl -s --max-time 60 -H "Authorization: Bearer $TOKEN" \
    "$SIGMA_BASE_URL/v2/workbooks/$WB/spec" -o "$RB"
python - "$WRB" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
ok = bad = preserved = 0
def walk(o):
    global ok, bad, preserved
    if isinstance(o, dict):
        if o.get('kind') == 'control' and o.get('controlType') == 'list':
            f = (o.get('filters') or [{}])[0]
            el = (f.get('source') or {}).get('elementId'); col = f.get('columnId')
            s = o.get('source') or {}
            inner = s.get('source') or {}
            # A hand-curated list was deliberately skipped by the transform. It is NOT
            # a failure, so do not report it as broken - report it as left alone.
            if s.get('values') or s.get('labels'):
                preserved += 1
                print('    preserved (hand-curated): %s' % o.get('controlId'))
            elif (s.get('kind') == 'source' and inner.get('kind') == 'table'
                  and inner.get('elementId') == el and s.get('columnId') == col):
                ok += 1
            else:
                bad += 1
                print('    STILL BROKEN: %s' % o.get('controlId'))
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(d.get('document') or {})
print('  readback: documentVersion=%s list_ok=%d preserved=%d list_broken=%d'
      % (d.get('documentVersion'), ok, preserved, bad))
sys.exit(1 if bad else 0)
PY
echo "  DONE"
